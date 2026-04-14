"""Упрощённый тестер Xray конфигов для ArcParse.

Использует подход из rjsxrd: запуск Xray процесса на порт, тест через SOCKS.
Multi-config batching: один Xray процесс с множеством inbound портов.
"""

import os
import json
import base64
import subprocess
import tempfile
import time
import socket
import threading
import atexit
import itertools
from typing import List, Tuple, Optional, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qs, unquote, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from constants import XRAY_BASE_PORT, XRAY_PORT_RANGE, MAX_SAFE_CONCURRENCY
except ImportError:
    # Fallback если constants.py недоступен
    XRAY_BASE_PORT = 20000
    XRAY_PORT_RANGE = 10000
    MAX_SAFE_CONCURRENCY = 500


# Константы батчинга (из полной версии xray_tester.py)
BATCH_SIZE = 100       # Оптимально: 100 конфигов на Xray процесс
MAX_BATCH_SIZE = 150   # Абсолютный максимум
MIN_BATCH_SIZE = 50    # Минимум для эффективности


# Глобальный список процессов для очистки
_running_processes: List[subprocess.Popen] = []
_process_lock = threading.Lock()
# Монотонный счётчик портов (диапазон 20000-20000+XRAY_PORT_RANGE)
_port_counter = itertools.count(XRAY_BASE_PORT)
_port_counter_lock = threading.Lock()
# Семафор для ограничения реального количества одновременных Xray-процессов
_xray_semaphore = threading.Semaphore(30)  # не более 30 Xray одновременно


def _cleanup_all():
    """Очистка всех процессов при выходе."""
    with _process_lock:
        for proc in _running_processes[:]:
            try:
                if proc.poll() is None:
                    try:
                        proc.terminate()
                        proc.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        try:
                            proc.kill()
                            proc.wait(timeout=1)
                        except Exception:
                            pass
            except Exception:
                pass
        _running_processes.clear()


atexit.register(_cleanup_all)


def _get_next_port() -> int:
    """
    Выдаёт следующий свободный порт из диапазона.
    После вычисления обёрнутого порта делаем bind-проверку,
    чтобы убедиться, что порт не занят другим Xray-процессом.
    """
    max_attempts = 10
    for _ in range(max_attempts):
        with _port_counter_lock:
            raw = next(_port_counter)
        # Оборачиваем в диапазон XRAY_BASE_PORT .. XRAY_BASE_PORT + XRAY_PORT_RANGE
        port = XRAY_BASE_PORT + (raw % XRAY_PORT_RANGE)

        # Проверяем, что порт реально свободен
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('127.0.0.1', port))
            sock.close()
            return port
        except OSError:
            continue  # Порт занят — берём следующий

    raise RuntimeError(f"Не удалось найти свободный порт после {max_attempts} попыток")


def _wait_for_port(port: int, timeout: float = 1.0) -> bool:
    """Ждет пока SOCKS порт станет доступен. Оптимизировано для скорости."""
    start = time.time()
    check_interval = 0.01  # Проверяем каждые 10ms
    while time.time() - start < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.05)  # Быстрый timeout на сокет
                if sock.connect_ex(('127.0.0.1', port)) == 0:
                    return True
        except Exception:
            pass
        time.sleep(check_interval)
    return False


def _parse_vless_url(url: str, tag: str = "proxy") -> Optional[Dict]:
    """Parse VLESS URL to Xray outbound (улучшенная версия из полной)."""
    try:
        url_part = url.replace('vless://', '', 1)
        if '#' in url_part:
            url_part, _ = url_part.split('#', 1)
        if '?' in url_part:
            base_part, query_part = url_part.split('?', 1)
        else:
            base_part = url_part
            query_part = ''

        if '@' not in base_part:
            return None

        uuid, host_port = base_part.rsplit('@', 1)
        if ':' not in host_port:
            return None

        hostname, port_str = host_port.rsplit(':', 1)
        port = int(port_str.strip().rstrip('/'))

        params = parse_qs(query_part)
        security = params.get('security', ['none'])[0]

        outbound = {
            "tag": tag,
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": hostname,
                    "port": port,
                    "users": [{
                        "id": uuid,
                        "encryption": params.get('encryption', ['none'])[0],
                        "flow": params.get('flow', [''])[0]
                    }]
                }]
            },
            "streamSettings": {
                "network": params.get('type', ['tcp'])[0],
                "security": security
            }
        }

        if security == 'tls':
            outbound["streamSettings"]["tlsSettings"] = {
                "serverName": params.get('sni', [hostname])[0],
                "fingerprint": params.get('fp', ['chrome'])[0]
            }
        elif security == 'reality':
            outbound["streamSettings"]["realitySettings"] = {
                "serverName": params.get('sni', [''])[0],
                "fingerprint": params.get('fp', ['chrome'])[0],
                "publicKey": params.get('pbk', [''])[0],
                "shortId": params.get('sid', [''])[0]
            }

        transport = params.get('type', ['tcp'])[0]
        if transport == 'ws':
            outbound["streamSettings"]["wsSettings"] = {
                "path": unquote(params.get('path', ['/'])[0]),
                "headers": {"Host": unquote(params.get('host', [hostname])[0])}
            }
        elif transport == 'grpc':
            outbound["streamSettings"]["grpcSettings"] = {
                "serviceName": unquote(params.get('serviceName', [''])[0])
            }

        return outbound
    except Exception:
        return None


def _parse_hysteria2_to_outbound(url: str, tag: str = "proxy") -> Optional[Dict]:
    """Parse Hysteria2/Hy2 URL to Xray outbound (из полной версии xray_tester.py)."""
    try:
        parsed = urlparse('//' + url.replace('hysteria2://', '').replace('hy2://', ''))
        params = parse_qs(parsed.query)

        if not parsed.hostname or not parsed.port:
            return None

        return {
            "tag": tag,
            "protocol": "hysteria2",
            "settings": {
                "servers": [{
                    "address": parsed.hostname,
                    "port": parsed.port,
                    "password": unquote(parsed.username) if parsed.username else ""
                }]
            },
            "streamSettings": {
                "network": "udp",
                "security": "tls",
                "tlsSettings": {
                    "serverName": params.get('sni', [parsed.hostname])[0]
                }
            }
        }
    except Exception:
        return None


def _url_to_outbound(url: str, tag: str = "proxy") -> Optional[Dict]:
    """Convert URL to outbound based on protocol (из полной версии)."""
    # Удаляем все пробельные символы (пробелы, переносы \n\r, табы), ломающие Base64 в парсерах
    url = "".join(url.split())
    
    protocol_parsers = {
        'vless://': _parse_vless_url,
        'hysteria2://': _parse_hysteria2_to_outbound,
        'hy2://': _parse_hysteria2_to_outbound,
    }

    for prefix, parser in protocol_parsers.items():
        if url.startswith(prefix):
            return parser(url, tag)

    # Остальные протоколы обрабатываем через _create_xray_config логику
    protocol = url.split('://')[0].lower() if '://' in url else ''
    if protocol == 'vmess':
        return _parse_vmess_url(url, tag)
    elif protocol == 'trojan':
        return _parse_trojan_url(url, tag)
    elif protocol == 'ss':
        return _parse_shadowsocks_url(url, tag)

    return None


def _parse_vmess_url(url: str, tag: str = "proxy") -> Optional[Dict]:
    """Parse VMess URL to Xray outbound (улучшенная версия из полной)."""
    try:
        encoded = url.replace('vmess://', '').strip()
        if '#' in encoded:
            encoded = encoded.split('#')[0]
        encoded = encoded.replace('\n', '').replace('\r', '').replace(' ', '')

        padding = 4 - len(encoded) % 4
        if padding != 4:
            encoded += '=' * padding

        decoded = base64.b64decode(encoded).decode('utf-8', errors='ignore')
        data = json.loads(decoded)

        if not data.get('add') or not data.get('port') or not data.get('id'):
            return None

        outbound = {
            "tag": tag,
            "protocol": "vmess",
            "settings": {
                "vnext": [{
                    "address": str(data.get('add', '')),
                    "port": int(data.get('port', 443)),
                    "users": [{
                        "id": str(data.get('id', '')),
                        "alterId": int(data.get('aid', 0)),
                        "security": data.get('scy', 'auto')
                    }]
                }]
            },
            "streamSettings": {
                "network": data.get('net', 'tcp'),
                "security": 'tls' if data.get('tls') == 'tls' else 'none'
            }
        }
        if data.get('tls') == 'tls':
            outbound["streamSettings"]["tlsSettings"] = {
                "serverName": data.get('sni', data.get('add', ''))
            }
        return outbound
    except Exception:
        return None


def _parse_trojan_url(url: str, tag: str = "proxy") -> Optional[Dict]:
    """Parse Trojan URL to Xray outbound (улучшенная версия из полной)."""
    try:
        url_part = url.replace('trojan://', '', 1).split('#')[0]
        if '?' in url_part:
            url_part, query_part = url_part.split('?', 1)
            params = parse_qs(query_part)
        else:
            params = {}

        password, host_port = url_part.rsplit('@', 1)
        hostname, port_str = host_port.rsplit(':', 1)
        port = int(port_str.strip().rstrip('/'))

        if not hostname or not port or not password:
            return None

        security = params.get('security', ['tls'])[0]
        transport = params.get('type', ['tcp'])[0]
        sni = params.get('sni', [hostname])[0]

        stream_settings = {
            "network": transport,
            "security": security
        }

        if security == 'tls':
            stream_settings["tlsSettings"] = {
                "serverName": sni,
                "fingerprint": params.get('fp', ['chrome'])[0]
            }
        elif security == 'reality':
            stream_settings["realitySettings"] = {
                "serverName": sni,
                "fingerprint": params.get('fp', ['chrome'])[0],
                "publicKey": params.get('pbk', [''])[0],
                "shortId": params.get('sid', [''])[0]
            }

        if transport == 'ws':
            stream_settings["wsSettings"] = {
                "path": unquote(params.get('path', ['/'])[0]),
                "headers": {"Host": unquote(params.get('host', [hostname])[0])}
            }
        elif transport == 'grpc':
            stream_settings["grpcSettings"] = {
                "serviceName": unquote(params.get('serviceName', [''])[0])
            }

        return {
            "tag": tag,
            "protocol": "trojan",
            "settings": {
                "servers": [{
                    "address": hostname,
                    "port": port,
                    "password": password
                }]
            },
            "streamSettings": stream_settings
        }
    except Exception:
        return None


def _parse_shadowsocks_url(url: str, tag: str = "proxy") -> Optional[Dict]:
    """Parse Shadowsocks URL to Xray outbound (улучшенная версия из полной)."""
    try:
        url_part = url.replace('ss://', '', 1).split('#')[0]
        if '?' in url_part:
            url_part, query_part = url_part.split('?', 1)
        else:
            query_part = ''

        method = 'chacha20-poly1305'
        password = ''
        hostname = None
        port = None

        # SIP002: ss://method:pass@host:port или ss://BASE64@host:port
        if '@' in url_part:
            userinfo, server_part = url_part.rsplit('@', 1)
            hostname, port_str = server_part.rsplit(':', 1)
            port = int(port_str.rstrip('/'))

            if ':' not in userinfo:
                # base64-encoded userinfo
                decoded_ui = base64.urlsafe_b64decode(userinfo + '==').decode('utf-8', errors='ignore')
                method, password = decoded_ui.split(':', 1) if ':' in decoded_ui else (decoded_ui, '')
            else:
                method, password = userinfo.split(':', 1)
        else:
            # Legacy: всё в base64
            padding = 4 - len(url_part) % 4
            if padding != 4:
                url_part += '=' * padding
            decoded = base64.urlsafe_b64decode(url_part).decode('utf-8', errors='ignore')
            if '@' not in decoded:
                return None
            userinfo, server = decoded.rsplit('@', 1)
            method, password = userinfo.split(':', 1) if ':' in userinfo else (userinfo, '')
            hostname, port_str = server.rsplit(':', 1)
            port = int(port_str)

        if not hostname:
            return None

        return {
            "tag": tag,
            "protocol": "shadowsocks",
            "settings": {
                "servers": [{
                    "address": hostname,
                    "port": port,
                    "password": password,
                    "method": method
                }]
            }
        }
    except Exception:
        return None


def _create_xray_config(url: str, socks_port: int) -> Optional[Dict]:
    """Создаёт конфиг Xray для одного URL (legacy fallback)."""
    outbound = _url_to_outbound(url, "proxy")
    if not outbound:
        return None

    return {
        "log": {"loglevel": "error", "access": "", "error": ""},
        "inbounds": [{
            "tag": "socks",
            "listen": "127.0.0.1",
            "port": socks_port,
            "protocol": "mixed",
            "settings": {"auth": "noauth", "udp": True},
            "sniffing": {"enabled": True, "routeOnly": True, "destOverride": ["http", "tls", "quic"]}
        }],
        "outbounds": [
            outbound,
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"}
        ],
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [{"type": "field", "inboundTag": ["socks"], "outboundTag": "proxy"}]
        }
    }


# ─── Error tracking ──────────────────────────────────────────────────────

_error_stats: Dict[str, int] = {}
_error_samples: Dict[str, List[str]] = {}
_error_lock = threading.Lock()


def _track_error(error_msg: str, url: str = ""):
    """Track error for statistics (из полной версии)."""
    with _error_lock:
        _error_stats[error_msg] = _error_stats.get(error_msg, 0) + 1
        if error_msg not in _error_samples:
            _error_samples[error_msg] = []
        if url and len(_error_samples[error_msg]) < 3:
            _error_samples[error_msg].append(url[:80])


def _print_error_summary(log_func=None):
    """Print error summary (из полной версии)."""
    with _error_lock:
        if not _error_stats:
            return
        _log_func = log_func or (lambda m, t="": print(m))
        _log_func("── Error Summary ──", "info")
        sorted_errors = sorted(_error_stats.items(), key=lambda x: x[1], reverse=True)
        for error, count in sorted_errors[:10]:
            sample = _error_samples.get(error, [])
            sample_str = f" (e.g. {sample[0]}...)" if sample else ""
            _log_func(f"  {error}: {count}{sample_str}", "warning")
        _error_stats.clear()
        _error_samples.clear()


def _reset_error_stats():
    """Reset error stats (для нового батча)."""
    global _error_stats, _error_samples
    with _error_lock:
        _error_stats = {}
        _error_samples = {}


# ─── Pre-validation ─────────────────────────────────────────────────────

def _pre_validate_url(url: str) -> Tuple[bool, str]:
    """Pre-validate URL before parsing (из полной версии).

    Returns: (is_valid, error_message)
    """
    if not url or not url.strip():
        return False, "Empty config"

    # Удаляем пробелы и переносы для корректной пре-валидации
    url = "".join(url.split())

    if '://' not in url:
        return False, "Missing protocol prefix"

    protocol = url.split('://')[0].lower()

    # Quick checks for common issues
    if protocol == 'vless':
        try:
            url_part = url.replace('vless://', '', 1).split('#')[0].split('?')[0]
            if '@' in url_part:
                uuid_part = url_part.rsplit('@', 1)[0]
                if not uuid_part or uuid_part.strip() == '':
                    return False, "VLESS with empty UUID"
        except Exception:
            pass
    elif protocol in ('trojan',):
        try:
            url_part = url.replace('trojan://', '', 1).split('#')[0].split('?')[0]
            if '@' in url_part:
                password_part = url_part.rsplit('@', 1)[0]
                if not password_part or password_part.strip() == '':
                    return False, "Trojan with empty password"
        except Exception:
            pass
    elif protocol in ('ss', 'shadowsocks'):
        try:
            url_part = url.replace('ss://', '', 1).split('#')[0].split('?')[0]
            if '@' in url_part:
                userinfo = url_part.rsplit('@', 1)[0]
                # Check if base64 userinfo decodes properly
                if ':' not in userinfo:
                    try:
                        padding = 4 - len(userinfo) % 4
                        if padding != 4:
                            userinfo_check = userinfo + '=' * padding
                        else:
                            userinfo_check = userinfo
                        decoded = base64.urlsafe_b64decode(userinfo_check).decode('utf-8', errors='ignore')
                        if ':' not in decoded:
                            return False, "Shadowsocks parse error"
                    except Exception:
                        pass
        except Exception:
            pass

    return True, ""


# ─── Multi-config batching ──────────────────────────────────────────────

def _create_multi_config(urls: List[str]) -> Tuple[Optional[Dict], Dict[int, str], List[Tuple[str, str]]]:
    """Create SINGLE Xray config with multiple inbounds/outbounds.

    OPTIMAL BATCH SIZE: 100 configs per Xray instance.
    This creates ONE Xray process with 100 inbounds instead of 100 processes.

    Returns: (config_dict, port_to_url_mapping, skipped_list) or (None, {}, skipped_list)
    """
    if len(urls) > MAX_BATCH_SIZE:
        pass  # Will process anyway

    config = {
        "log": {"loglevel": "error", "access": "", "error": ""},
        "inbounds": [],
        "outbounds": [
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"}
        ],
        "routing": {"domainStrategy": "AsIs", "rules": []}
    }
    port_map = {}
    used_ports = set()
    skipped_urls = []

    for idx, url in enumerate(urls):
        port = _get_next_port()
        while port in used_ports:
            port = _get_next_port()

        # PRE-VALIDATE: Skip obviously broken configs BEFORE parsing
        valid, error_msg = _pre_validate_url(url)
        if not valid:
            skipped_urls.append((url, error_msg))
            _track_error(error_msg, url)
            continue

        outbound = _url_to_outbound(url, f"proxy{port}")
        if not outbound:
            skipped_urls.append((url, "Failed to parse outbound"))
            _track_error(f"Failed to parse outbound", url)
            continue

        # VALIDATE: Check for common config errors BEFORE adding to batch
        try:
            protocol = outbound.get("protocol", "")
            settings = outbound.get("settings", {})

            if protocol == "vless":
                vnext = settings.get("vnext", [])
                if vnext and len(vnext) > 0:
                    users = vnext[0].get("users", [])
                    if users and len(users) > 0:
                        user = users[0]
                        if not user.get("id"):
                            skipped_urls.append((url, "VLESS/REALITY with empty UUID"))
                            _track_error("VLESS/REALITY with empty UUID", url)
                            continue

            if protocol == "shadowsocks":
                servers = settings.get("servers", [])
                if servers and len(servers) > 0:
                    password = servers[0].get("password", "")
                    if not password:
                        skipped_urls.append((url, "Shadowsocks with empty password"))
                        _track_error("Shadowsocks with empty password", url)
                        continue

            if protocol == "trojan":
                servers = settings.get("servers", [])
                if servers and len(servers) > 0:
                    password = servers[0].get("password", "")
                    if not password:
                        skipped_urls.append((url, "Trojan with empty password"))
                        _track_error("Trojan with empty password", url)
                        continue

        except Exception as e:
            skipped_urls.append((url, f"Validation error: {str(e)[:60]}"))
            _track_error(f"Validation error", url)
            continue

        inbound = {
            "tag": f"mixed{port}",
            "listen": "127.0.0.1",
            "port": port,
            "protocol": "mixed",
            "settings": {"auth": "noauth", "udp": True}
        }
        config["inbounds"].append(inbound)
        config["outbounds"].append(outbound)

        rule = {
            "type": "field",
            "inboundTag": [f"mixed{port}"],
            "outboundTag": f"proxy{port}"
        }
        config["routing"]["rules"].append(rule)

        port_map[port] = url
        used_ports.add(port)

    if skipped_urls:
        sample = skipped_urls[:5]
        reasons = {}
        for _, reason in sample:
            reasons[reason] = reasons.get(reason, 0) + 1

    if not port_map:
        return None, {}, skipped_urls

    return config, port_map, skipped_urls


# ─── Single config test (legacy fallback) ───────────────────────────────


def _test_single_config_legacy(url: str, xray_path: str, timeout: float,
                                target_url: str = "https://www.google.com/generate_204") -> Tuple[str, bool, float]:
    """Legacy: тестирует один конфиг через Xray (обратная совместимость)."""
    with _xray_semaphore:
        if not os.path.exists(xray_path):
            return (url, False, 0.0)

        port = _get_next_port()
        config = _create_xray_config(url, port)
        if not config:
            return (url, False, 0.0)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            config_path = f.name

        proc = None
        try:
            proc = subprocess.Popen([xray_path, '-c', config_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with _process_lock:
                _running_processes.append(proc)

            if not _wait_for_port(port, timeout=1.0):
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()
                with _process_lock:
                    if proc in _running_processes:
                        _running_processes.remove(proc)
                try:
                    os.unlink(config_path)
                except Exception:
                    pass
                return (url, False, 0.0)

            try:
                os.unlink(config_path)
            except Exception:
                pass

            session = requests.Session()
            session.proxies = {'http': f'socks5h://127.0.0.1:{port}', 'https': f'socks5h://127.0.0.1:{port}'}
            retry = Retry(total=0, status_forcelist=())
            adapter = HTTPAdapter(max_retries=retry, pool_connections=1, pool_maxsize=1)
            session.mount('http://', adapter)
            session.mount('https://', adapter)

            try:
                start = time.perf_counter()
                response = session.get(target_url, timeout=timeout, allow_redirects=False)
                latency = (time.perf_counter() - start) * 1000
                if response.status_code < 500:
                    return (url, True, latency)
                else:
                    return (url, False, 0.0)
            except Exception:
                return (url, False, 0.0)
        except Exception:
            return (url, False, 0.0)
        finally:
            if proc:
                try:
                    proc.terminate()
                    try:
                        proc.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=1)
                except Exception:
                    pass
                with _process_lock:
                    if proc in _running_processes:
                        _running_processes.remove(proc)


# ─── Multi-config batch testing ─────────────────────────────────────────

def _test_multi_config_batch(
    urls: List[str],
    xray_path: str,
    timeout: float,
    target_url: str,
    max_ping_ms: float,
    log_func,
    progress_func,
    stop_flag,
    internal_stop,
    suitable_counter: List[int] = None,
    required_count: int = None,
) -> List[Tuple[str, bool, float]]:
    """Test a batch of configs using MULTI-CONFIG approach (ONE Xray process, many ports).

    Creates a single Xray config with multiple inbounds (one per URL),
    then tests each port concurrently.
    """
    results: List[Tuple[str, bool, float]] = []
    results_lock = threading.Lock()

    # Create multi-config
    config, port_map, skipped = _create_multi_config(urls)
    if not config:
        for url, reason in skipped:
            _track_error(reason, url)
        return []

    if len(port_map) == 0:
        return []

    # Write config to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f)
        config_path = f.name

    proc = None
    try:
        # Start Xray
        proc = subprocess.Popen([xray_path, '-c', config_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with _process_lock:
            _running_processes.append(proc)

        # Wait for all ports to be ready
        all_ports = list(port_map.keys())
        ready = True
        for p in all_ports:
            if not _wait_for_port(p, timeout=2.0):
                ready = False
                break

        if not ready:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()
            with _process_lock:
                if proc in _running_processes:
                    _running_processes.remove(proc)
            try:
                os.unlink(config_path)
            except Exception:
                pass
            return []

        try:
            os.unlink(config_path)
        except Exception:
            pass

        # Test all ports concurrently using thread pool
        def _test_port(port: int) -> Tuple[str, bool, float]:
            url = port_map[port]
            with requests.Session() as session:
                session.proxies = {'http': f'socks5h://127.0.0.1:{port}', 'https': f'socks5h://127.0.0.1:{port}'}
                retry = Retry(total=0, status_forcelist=())
                adapter = HTTPAdapter(max_retries=retry, pool_connections=1, pool_maxsize=1)
                session.mount('http://', adapter)
                session.mount('https://', adapter)

                try:
                    start = time.perf_counter()
                    response = session.get(target_url, timeout=timeout, allow_redirects=False)
                    latency = (time.perf_counter() - start) * 1000
                    if response.status_code < 500:
                        return (url, True, latency)
                    return (url, False, 0.0)
                except Exception:
                    return (url, False, 0.0)

        # Use thread pool to test all ports concurrently
        worker_count = min(len(all_ports), MAX_SAFE_CONCURRENCY)
        with ThreadPoolExecutor(max_workers=worker_count) as worker_executor:
            futures = {worker_executor.submit(_test_port, p): p for p in all_ports}
            for future in as_completed(futures):
                if internal_stop.is_set() or (stop_flag and stop_flag.is_set()):
                    for f in futures:
                        f.cancel()
                    break
                try:
                    result = future.result(timeout=timeout + 5)
                    url, success, ping = result
                    with results_lock:
                        results.append(result)
                    
                    if success:
                        is_suitable = not (max_ping_ms and ping > max_ping_ms)
                        if is_suitable and log_func:
                            log_func(f"✓ Xray {ping:.0f} мс", "success")
                        
                        if is_suitable and suitable_counter is not None:
                            with results_lock:
                                suitable_counter[0] += 1
                                if required_count and suitable_counter[0] >= required_count:
                                    internal_stop.set()

                except Exception:
                    port = futures[future]
                    with results_lock:
                        results.append((port_map[port], False, 0.0))

    except Exception:
        pass
    finally:
        if proc:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=1)
            except Exception:
                pass
            with _process_lock:
                if proc in _running_processes:
                    _running_processes.remove(proc)

    return results


def test_batch(
    urls: List[str],
    xray_path: str,
    concurrency: int = 90,
    timeout: float = 6.0,
    required_count: int = None,
    max_ping_ms: float = None,
    target_url: str = "https://www.google.com/generate_204",
    log_func: callable = None,
    progress_func: callable = None,
    stop_flag: threading.Event = None,
    skip_flag: threading.Event = None,
) -> List[Tuple[str, bool, float]]:
    """Тестирует батч конфигов используя MULTI-CONFIG подход.

    Один Xray процесс с множеством inbound портов вместо одного процесса на конфиг.

    Args:
        urls: Список URL для тестирования
        xray_path: Путь к Xray бинарнику
        concurrency: Количество одновременных потоков
        timeout: Таймаут для каждого теста в секундах
        required_count: Сколько рабочих конфигов нужно найти (None = все)
        max_ping_ms: Максимальный пинг (None = не фильтровать)
        target_url: URL для тестирования
        log_func: Функция логирования
        progress_func: Функция прогресса
        stop_flag: threading.Event для остановки
        skip_flag: threading.Event для пропуска
    """
    def _log(msg, tag="info"):
        if log_func:
            log_func(msg, tag)
        else:
            print(msg)

    def _progress(current, total, suitable=0, required=0):
        if progress_func:
            progress_func(current, total, suitable, required)

    if not urls:
        return []

    _reset_error_stats()

    _log(f"Тестирование {len(urls)} конфигов (multi-config batch, timeout={timeout}s)...", "info")

    results = []
    results_lock = threading.Lock()
    completed = [0]
    suitable_counter = [0]
    internal_stop = threading.Event()

    # Split into multi-config batches
    batch_size = min(BATCH_SIZE, MAX_BATCH_SIZE)

    for batch_start in range(0, len(urls), batch_size):
        if internal_stop.is_set() or (stop_flag and stop_flag.is_set()):
            break

        if skip_flag and skip_flag.is_set():
            _log("Пропуск текущего батча...", "warning")
            skip_flag.clear()
            break

        batch = urls[batch_start:batch_start + batch_size]

        # Test batch with multi-config
        batch_results = _test_multi_config_batch(
            urls=batch,
            xray_path=xray_path,
            timeout=timeout,
            target_url=target_url,
            max_ping_ms=max_ping_ms,
            log_func=log_func,
            progress_func=progress_func,
            stop_flag=stop_flag,
            internal_stop=internal_stop,
            suitable_counter=suitable_counter,
            required_count=required_count,
        )

        with results_lock:
            results.extend(batch_results)
            completed[0] += len(batch_results)
            count = completed[0]

        # Progress update
        all_working_count = sum(1 for r in results if r[1])
        if max_ping_ms is not None:
            suitable_count = sum(1 for r in results if r[1] and r[2] <= max_ping_ms)
        else:
            suitable_count = all_working_count

        _progress(count, len(urls), suitable_count, required_count or 0)

        # Log progress
        log_every = 5 if log_func else 20
        if count % log_every == 0 or count >= len(urls):
            batch_pings = [r[2] for r in results if r[1]]
            min_ping = min(batch_pings) if batch_pings else 0
            if max_ping_ms is not None:
                _log(f"Прогресс: {count}/{len(urls)} — Рабочих: {all_working_count} — Подходящих: {suitable_count} — Мин. пинг: {min_ping:.0f}мс", "info")
            else:
                _log(f"Прогресс: {count}/{len(urls)} — Рабочих: {all_working_count} — Мин. пинг: {min_ping:.0f}мс", "info")

        # Check if enough found
        if required_count and suitable_count >= required_count:
            _log(f"Найдено достаточно конфигов ({required_count}), остановка", "success")
            internal_stop.set()
            break

    # Sort by latency (fastest first)
    working = [(url, success, latency) for url, success, latency in results if success]
    working.sort(key=lambda x: x[2])

    all_working = len(working)
    suitable = sum(1 for url, success, latency in working if latency <= max_ping_ms) if max_ping_ms else all_working

    if max_ping_ms is not None:
        _log(f"Готово: {suitable}/{all_working} подходящих из рабочих", "success")
    else:
        _log(f"Готово: {all_working}/{len(urls)} рабочих", "success")

    _print_error_summary(log_func)

    return working

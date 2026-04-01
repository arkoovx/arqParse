"""Упрощённый тестер Xray конфигов для ArcParse.

Использует подход из rjsxrd: запуск Xray процесса на порт, тест через SOCKS.
"""

import os
import sys
import json
import subprocess
import tempfile
import time
import socket
import threading
import atexit
from typing import List, Tuple, Optional, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Глобальный список процессов для очистки
_running_processes: List[subprocess.Popen] = []
_process_lock = threading.Lock()
_port_counter = [20000]
_port_lock = threading.Lock()


def _cleanup_all():
    """Очистка всех процессов при выходе."""
    with _process_lock:
        for proc in _running_processes[:]:
            try:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=2)
            except Exception:
                pass
        _running_processes.clear()


atexit.register(_cleanup_all)


def _get_next_port() -> int:
    """Получает следующий свободный порт."""
    for _ in range(10):
        with _port_lock:
            port = _port_counter[0]
            _port_counter[0] = (port - 20000 + 1) % 2000 + 20000
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('127.0.0.1', port))
            sock.close()
            return port
        except OSError:
            continue
    
    raise RuntimeError("Не удалось найти свободный порт")


def _wait_for_port(port: int, timeout: float = 1.5) -> bool:
    """Ждет пока SOCKS порт станет доступен."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.1)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            if result == 0:
                return True
        except Exception:
            pass
        time.sleep(0.05)
    return False


def _parse_vless_url(url: str) -> Optional[Dict]:
    """Парсит VLESS URL в outbound конфиг."""
    from urllib.parse import parse_qs, unquote
    import base64
    
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
            "tag": "proxy",
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


def _create_xray_config(url: str, socks_port: int) -> Optional[Dict]:
    """Создаёт конфиг Xray для одного URL."""
    protocol = url.split('://')[0].lower() if '://' in url else ''
    
    if protocol == 'vless':
        outbound = _parse_vless_url(url)
    elif protocol == 'vmess':
        # Упрощённый парсинг VMess
        try:
            import base64
            encoded = url.replace('vmess://', '').strip()
            padding = 4 - len(encoded) % 4
            if padding != 4:
                encoded += '=' * padding
            decoded = base64.b64decode(encoded).decode('utf-8', errors='ignore')
            data = json.loads(decoded)
            
            outbound = {
                "tag": "proxy",
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
        except Exception:
            return None
    elif protocol == 'trojan':
        try:
            url_part = url.replace('trojan://', '', 1).split('#')[0]
            if '?' in url_part:
                url_part = url_part.split('?')[0]
            password, host_port = url_part.rsplit('@', 1)
            hostname, port_str = host_port.rsplit(':', 1)
            
            outbound = {
                "tag": "proxy",
                "protocol": "trojan",
                "settings": {
                    "servers": [{
                        "address": hostname,
                        "port": int(port_str),
                        "password": password
                    }]
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "tls",
                    "tlsSettings": {"serverName": hostname}
                }
            }
        except Exception:
            return None
    elif protocol == 'ss':
        try:
            url_part = url.replace('ss://', '', 1).split('#')[0]
            # Пробуем base64 decode
            try:
                padding = 4 - len(url_part) % 4
                if padding != 4:
                    url_part += '=' * padding
                decoded = base64.urlsafe_b64decode(url_part).decode('utf-8', errors='ignore')
                if '@' in decoded:
                    userinfo, server = decoded.rsplit('@', 1)
                    method, password = userinfo.split(':', 1) if ':' in userinfo else (userinfo, '')
                    hostname, port_str = server.rsplit(':', 1)
                    port = int(port_str)
                else:
                    return None
            except Exception:
                return None
            
            outbound = {
                "tag": "proxy",
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
    else:
        return None
    
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


def _test_single_config(url: str, xray_path: str, timeout: float) -> Tuple[str, bool, float]:
    """Тестирует один конфиг через Xray."""
    if not os.path.exists(xray_path):
        return (url, False, 0.0)
    
    port = _get_next_port()
    config = _create_xray_config(url, port)
    
    if not config:
        return (url, False, 0.0)
    
    # Создаём временный файл конфига
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f)
        config_path = f.name
    
    proc = None
    try:
        # Запускаем Xray
        proc = subprocess.Popen([xray_path, '-c', config_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with _process_lock:
            _running_processes.append(proc)
        
        # Ждём порт
        if not _wait_for_port(port, timeout=2.0):
            proc.terminate()
            proc.wait(timeout=2)
            with _process_lock:
                if proc in _running_processes:
                    _running_processes.remove(proc)
            os.unlink(config_path)
            return (url, False, 0.0)
        
        os.unlink(config_path)
        
        # Тест через SOCKS
        session = requests.Session()
        session.proxies = {'http': f'socks5h://127.0.0.1:{port}', 'https': f'socks5h://127.0.0.1:{port}'}
        retry = Retry(total=1, backoff_factor=0.1)
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        # Тест URL (как в rjsxrd)
        test_urls = ["https://www.google.com/generate_204", "https://google.com"]
        latencies = []
        
        for test_url in test_urls:
            try:
                start = time.perf_counter()
                response = session.get(test_url, timeout=timeout, allow_redirects=True)
                latency = (time.perf_counter() - start) * 1000
                latencies.append(latency)
                if response.status_code < 400:
                    break
            except Exception:
                continue
        
        if latencies:
            return (url, True, min(latencies))
        else:
            return (url, False, 0.0)
            
    except Exception:
        return (url, False, 0.0)
    finally:
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                pass
            with _process_lock:
                if proc in _running_processes:
                    _running_processes.remove(proc)


def test_batch(
    urls: List[str],
    xray_path: str,
    concurrency: int = 100,
    timeout: float = 10.0
) -> List[Tuple[str, bool, float]]:
    """Тестирует батч конфигов конкурентно."""
    if not urls:
        return []
    
    results = []
    results_lock = threading.Lock()
    completed = [0]
    stop_flag = threading.Event()
    
    print(f"Тестирование {len(urls)} конфигов (concurrency={concurrency}, timeout={timeout}s)...")
    
    def test_with_progress(url: str) -> Tuple[str, bool, float]:
        if stop_flag.is_set():
            return (url, False, 0.0)
        result = _test_single_config(url, xray_path, timeout)
        with results_lock:
            completed[0] += 1
            count = completed[0]
            # Лог каждые 20 конфигов
            if count % 20 == 0 or count == len(urls):
                working = sum(1 for r in results if r[1])
                print(f"Progress: {count}/{len(urls)} - Working: {working}")
        return result
    
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(test_with_progress, url): url for url in urls}
        try:
            for future in as_completed(futures):
                if stop_flag.is_set():
                    break
                try:
                    result = future.result(timeout=timeout + 5)
                    with results_lock:
                        results.append(result)
                except Exception:
                    with results_lock:
                        results.append((futures[future], False, 0.0))
        except KeyboardInterrupt:
            stop_flag.set()
        finally:
            stop_flag.set()
            executor.shutdown(wait=False, cancel_futures=True)
            # Принудительная очистка процессов
            time.sleep(0.5)
            _cleanup_all()
    
    # Сортируем по latency (fastest first)
    working = [(url, success, latency) for url, success, latency in results if success]
    working.sort(key=lambda x: x[2])
    
    print(f"Готово: {len(working)}/{len(urls)} рабочих")
    
    return working

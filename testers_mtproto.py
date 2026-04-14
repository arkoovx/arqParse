"""
FAST+ проверка MTProto прокси.

Алгоритм:
  1. TCP connect + валидный MTProto obfuscated2 handshake
  2. Приём ответа и ВАЛИДАЦИЯ (энтропия, HTTP-префиксы, уникальные байты)
  3. Классификация: STRONG / WEAK / FAIL
  4. WEAK НЕ считаются для required_count — поиск продолжается пока STRONG < required
  5. После всех тестов — WEAK перепроверяются
  6. Финал: STRONG[:required] + WEAK[:remaining] (если STRONG не хватило)
"""

import os
import socket
import time
import hashlib
import threading
import struct
from typing import List, Tuple, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from formatting import format_config_name

from parser import parse_mtproto_url


# ──────────────────────────────────────────────────────────────────────────────
# Статусы
# ──────────────────────────────────────────────────────────────────────────────

STRONG = 2  # Реальный MTProto ответ
WEAK = 1    # Timeout, порт жив
FAIL = 0    # Мёртвый/мусор


# ──────────────────────────────────────────────────────────────────────────────
# AES-CTR
# ──────────────────────────────────────────────────────────────────────────────

def _make_aes_ctr(key: bytes, iv: bytes):
    try:
        from Crypto.Cipher import AES
        return AES.new(key, AES.MODE_CTR, nonce=b'', initial_value=iv)
    except ImportError:
        pass
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        enc = Cipher(algorithms.AES(key), modes.CTR(iv), backend=default_backend()).encryptor()
        class _C:
            @staticmethod
            def encrypt(data): return enc.update(data) + enc.finalize()
        return _C()
    except ImportError:
        pass
    raise ImportError("Установите: pip install pycryptodome  или  pip install cryptography")


# ──────────────────────────────────────────────────────────────────────────────
# Secret parsing
# ──────────────────────────────────────────────────────────────────────────────

_FORBIDDEN_FIRST_BYTES = frozenset([0xef, 0x44, 0x47, 0x50, 0x48, 0x16, 0x03])
_FORBIDDEN_FIRST_DWORDS = frozenset([b'\x00\x00\x00\x00', b'\xef\xef\xef\xef'])


def _parse_secret(secret_str: str) -> Optional[bytes]:
    s = secret_str.strip().lower()
    try:
        raw = bytes.fromhex(s)
    except ValueError:
        import base64
        try:
            raw = base64.urlsafe_b64decode(s + '==')
        except Exception:
            return None
    if len(raw) == 16:
        return raw
    elif len(raw) >= 17 and raw[0] in (0xdd, 0xee):
        return raw[1:17]
    return raw[:16] if len(raw) >= 16 else None


# ──────────────────────────────────────────────────────────────────────────────
# Obfuscated2 handshake
# ──────────────────────────────────────────────────────────────────────────────

def _build_obfuscated2_packet(secret_raw: bytes) -> bytes:
    while True:
        nonce = bytearray(os.urandom(64))
        if nonce[0] in _FORBIDDEN_FIRST_BYTES:
            continue
        if bytes(nonce[0:4]) in _FORBIDDEN_FIRST_DWORDS:
            continue
        break
    # Модифицируем ДО превращения в bytes
    nonce[56] = 0xef
    nonce[57] = 0xef
    nonce[58] = 0xef
    nonce[59] = 0xef
    nonce = bytes(nonce)
    key_out = hashlib.sha256(nonce[8:40] + secret_raw).digest()
    iv_out = hashlib.sha256(nonce[40:56] + secret_raw).digest()[:16]
    cipher = _make_aes_ctr(key_out, iv_out)
    encrypted = cipher.encrypt(nonce)
    return nonce[:56] + encrypted[56:]


# ──────────────────────────────────────────────────────────────────────────────
# Валидация ответа
# ──────────────────────────────────────────────────────────────────────────────

_HTTP_PREFIXES = (b"HTTP/", b"GET ", b"POST ", b"HEAD ", b"PUT ", b"DELETE ", b"OPTIONS ")


def _is_valid_mtproto_response(data: bytes) -> Tuple[bool, str]:
    if not data or len(data) == 0:
        return False, "empty"
    if len(data) < 16:
        return False, f"too_short({len(data)})"
    for prefix in _HTTP_PREFIXES:
        if data.upper().startswith(prefix):
            return False, "http_like"
    if data == b"\x00" * len(data):
        return False, "all_zeros"
    sample = data[:64]
    unique = len(set(sample))
    if unique < 8:
        return False, f"low_entropy({unique})"
    return True, "ok"


# ──────────────────────────────────────────────────────────────────────────────
# Тест одного прокси
# ──────────────────────────────────────────────────────────────────────────────

def _test_single_mtproto_fast(url: str, recv_timeout: float, debug_log=None) -> Tuple[int, float]:
    parsed = parse_mtproto_url(url)
    if not parsed:
        return FAIL, float('inf')

    server, port = parsed['server'], parsed['port']
    secret_raw = _parse_secret(parsed['secret'])
    if secret_raw is None or len(secret_raw) < 16:
        return FAIL, float('inf')

    try:
        packet = _build_obfuscated2_packet(secret_raw)
    except Exception:
        return FAIL, float('inf')

    def _try_once() -> Tuple[int, float]:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Отключение TIME_WAIT для предотвращения переполнения NAT таблицы роутера
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.settimeout(max(recv_timeout / 2, 1.0))
            start = time.perf_counter()
            try:
                sock.connect((server, port))
            except (socket.timeout, ConnectionRefusedError, OSError):
                return FAIL, float('inf')
            try:
                sock.sendall(packet)
            except OSError:
                return FAIL, float('inf')
            sock.settimeout(recv_timeout)
            try:
                response = sock.recv(128)
                elapsed = (time.perf_counter() - start) * 1000
                if len(response) == 0:
                    return FAIL, elapsed
                ok, reason = _is_valid_mtproto_response(response)
                return (STRONG if ok else FAIL), elapsed
            except socket.timeout:
                return WEAK, (time.perf_counter() - start) * 1000
            except (ConnectionResetError, ConnectionAbortedError, OSError):
                return FAIL, float('inf')
        except Exception:
            return FAIL, float('inf')
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    status, ping_ms = _try_once()
    if status == WEAK:
        s2, p2 = _try_once()
        if s2 == STRONG:
            return STRONG, p2
    return status, ping_ms


# ──────────────────────────────────────────────────────────────────────────────
# Массовое тестирование
# ──────────────────────────────────────────────────────────────────────────────

def _collect_mtproto_results(
    strong: List[Tuple[float, str]],
    still_weak: List[Tuple[float, str]],
    required_count: int,
) -> List[Tuple[str, int, float]]:
    """Собрать финальный список рабочих прокси из STRONG и WEAK."""
    strong.sort(key=lambda x: x[0])
    still_weak.sort(key=lambda x: x[0])

    strong_urls_set = {u for _, u in strong}
    final: List[Tuple[str, float]] = [(u, p) for p, u in strong[:required_count]]
    remaining = required_count - len(final)
    if remaining > 0 and still_weak:
        for p, u in still_weak[:remaining]:
            final.append((u, p))

    return [(url, STRONG if url in strong_urls_set else WEAK, ping) for url, ping in final]


def test_mtproto_configs_console(
    configs: List[str],
    max_ping_ms: float,
    required_count: int,
    max_workers: int = 100,
    log_func: Callable = None,
    progress_func: Callable = None,
    profile_title: str = None,
    config_type: str = None,
    stop_flag=None,
    skip_flag=None,
) -> List[Tuple[str, int, float]]:
    """
    FAST+ MTProto тест для консольного режима.
    Возвращает список кортежей: [(url, status, ping_ms), ...]
    """
    # Делегируем основную логику внутренней функции
    result = _run_mtproto_tests(
        configs=configs,
        max_ping_ms=max_ping_ms,
        required_count=required_count,
        max_workers=max_workers,
        log_func=log_func,
        progress_func=progress_func,
        stop_flag=stop_flag,
        skip_flag=skip_flag,
    )
    return _collect_mtproto_results(
        result['strong'], result['still_weak'], required_count
    )


def test_mtproto_configs(
    configs: List[str],
    max_ping_ms: float,
    required_count: int,
    max_workers: int = 100,
    log_func: Callable = None,
    progress_func: Callable = None,
    out_file: str = None,
    profile_title: str = None,
    config_type: str = None,
    stop_flag=None,
    skip_flag=None,
) -> Tuple[int, int, int]:
    """
    FAST+ MTProto тест для GUI-режима.
    Возвращает кортеж: (working, passed, failed)
    """
    result = _run_mtproto_tests(
        configs=configs,
        max_ping_ms=max_ping_ms,
        required_count=required_count,
        max_workers=max_workers,
        log_func=log_func,
        progress_func=progress_func,
        stop_flag=stop_flag,
        skip_flag=skip_flag,
    )

    strong = result['strong']
    still_weak = result['still_weak']
    processed = result['processed']
    over_limit = result['over_limit']

    final = _collect_mtproto_results(strong, still_weak, required_count)
    strong_urls = {su for _, su in strong}
    working = len(strong) + len(still_weak)
    passed = len(final)
    failed = processed - working - over_limit

    # ── Сохранение в файл ────────────────────────────────────────────────
    if final:
        try:
            dir_name = os.path.dirname(out_file)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with open(out_file, 'w', encoding='utf-8') as f:
                f.write(f"#profile-title: {profile_title or 'arqVPN MTProto'}\n")
                f.write("#profile-update-interval: 48\n")
                f.write("#support-url: https://t.me/arqhub\n\n")
                for idx, (url, status, ping_ms) in enumerate(final, 1):
                    formatted_url = format_config_name(url, idx, config_type, ping_ms)
                    f.write(f"{formatted_url}\n")
            strong_in_final = sum(1 for u, _, _ in final if u in strong_urls)
            weak_added = sum(1 for u, _, _ in final if u not in strong_urls)
            if log_func:
                log_func(f"✓ Сохранено {passed} конфигов (STRONG: {strong_in_final}, WEAK: {weak_added}) в {out_file}", "success")
        except Exception as e:
            if log_func:
                log_func(f"Ошибка сохранения: {e}", "error")
    else:
        if log_func:
            log_func("Рабочих прокси не найдено", "warning")

    return working, passed, failed


# ─── Внутренняя функция с общей логикой тестирования ───────────────────────

def _run_mtproto_tests(
    configs: List[str],
    max_ping_ms: float,
    required_count: int,
    max_workers: int,
    log_func: Callable,
    progress_func: Callable,
    stop_flag,
    skip_flag,
) -> dict:
    """
    Общая логика MTProto тестирования. Возвращает dict с результатами.
    """
    def _log(msg: str, tag: str = "info"):
        print(f"[{tag.upper()}] MTPROTO: {msg}")  # Terminal debug
        if log_func:
            # Не спамим фейлы в GUI чтобы не положить очередь событий Kivy
            if tag == "error" and "FAIL" in msg:
                return
            log_func(msg, tag)

    def _progress(current: int, total: int):
        if progress_func:
            # Обновляем GUI не чаще чем раз в 50-100 ходов, чтобы не забить event loop
            if current % 50 == 0 or current == total:
                progress_func(current, total)

    try:
        _make_aes_ctr(b'\x00' * 32, b'\x00' * 16)
    except ImportError as e:
        _log(str(e), "error")
        return {'strong': [], 'still_weak': [], 'processed': len(configs), 'over_limit': 0}

    strong: List[Tuple[float, str]] = []   # (ping, url)
    weak: List[Tuple[float, str]] = []      # (ping, url)
    over_limit = [0]                         # валидный ответ, но пинг > max_ping_ms
    total = len(configs)
    processed = [0]
    lock = threading.Lock()
    local_stop = threading.Event()

    # ─── ЭТАП 1: Основной прогон ────────────────────────────────────────
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(_test_single_mtproto_fast, cfg, 2.0, None): cfg for cfg in configs}

        for future in as_completed(future_map):
            if local_stop.is_set() or (stop_flag and stop_flag.is_set()) or (skip_flag and skip_flag.is_set()):
                for f in future_map:
                    f.cancel()
                if skip_flag and skip_flag.is_set():
                    local_stop.set()  # Чтобы сразу пропустить и Этап 2
                break
            try:
                status, ping_ms = future.result()
            except Exception as e:
                with lock:
                    processed[0] += 1
                _progress(processed[0], total)
                print(f"[DEBUG] MTPROTO Exception: {e}")
                continue

            url = future_map[future]
            with lock:
                processed[0] += 1
                _progress(processed[0], total)

                if status == STRONG and ping_ms <= max_ping_ms:
                    strong.append((ping_ms, url))
                    _log(f"✓ STRONG {ping_ms:.0f} мс  (найдено: {len(strong)}/{required_count})", "success")
                    if len(strong) >= required_count:
                        local_stop.set()
                elif status == WEAK and ping_ms <= max_ping_ms:
                    weak.append((ping_ms, url))
                    _log(f"~ WEAK   {ping_ms:.0f} мс  (в запасе: {len(weak)})", "warning")
                elif status in (STRONG, WEAK) and ping_ms > max_ping_ms:
                    over_limit[0] += 1
                    # Не спамим таймлимиты в GUI
                else:
                    _log(f"✗ FAIL {url[:60]}", "error")

    # ─── ЭТАП 2: Перепроверка WEAK (только если STRONG < required) ──────
    upgraded: List[Tuple[float, str]] = []
    still_weak: List[Tuple[float, str]] = []

    if weak and len(strong) < required_count:
        _log(f"Перепроверка {len(weak)} WEAK прокси (STRONG={len(strong)} < {required_count})...", "info")
        weak_total = len(weak)
        weak_processed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_weak = {executor.submit(_test_single_mtproto_fast, u, 2.0, None): (p, u) for p, u in weak}
            for future in as_completed(future_weak):
                if stop_flag and (stop_flag.is_set() or (skip_flag and skip_flag.is_set())):
                    for f in future_weak:
                        f.cancel()
                    break
                
                weak_processed += 1
                with lock:
                    processed[0] += 1
                _progress(processed[0], total)

                try:
                    new_status, new_ping = future.result()
                except Exception as e:
                    print(f"[DEBUG] MTPROTO Phase 2 Exception: {e}")
                    still_weak.append(future_weak[future])
                    continue
                if new_status == STRONG and new_ping <= max_ping_ms:
                    upgraded.append((new_ping, future_weak[future][1]))
                    _log(f"  ↑ апгрейд → STRONG {new_ping:.0f} мс", "success")
                else:
                    still_weak.append(future_weak[future])

        strong.extend(upgraded)
        if upgraded:
            _log(f"Апгрейднуто WEAK → STRONG: {len(upgraded)}", "success")
        else:
            _log("WEAK не удалось апгрейднуть", "info")
    elif weak:
        _log(f"STRONG достаточно ({len(strong)}), WEAK перепроверка пропущена", "info")
        still_weak = weak

    return {
        'strong': strong,
        'still_weak': still_weak,
        'processed': processed[0],
        'over_limit': over_limit[0],
    }


test_mtproto_configs_and_save = test_mtproto_configs

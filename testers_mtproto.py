import os
import socket
import time
import hashlib
import struct
import threading
from typing import List, Tuple, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from parser import parse_mtproto_url


# ──────────────────────────────────────────────────────────────────────────────
# AES-CTR — пробуем загрузить pycryptodome или cryptography
# ──────────────────────────────────────────────────────────────────────────────

def _make_aes_ctr(key: bytes, iv: bytes):
    """
    Возвращает объект с методом .encrypt(data: bytes) -> bytes.
    Использует pycryptodome или cryptography (что установлено).
    Если ничего нет — бросает ImportError с понятным сообщением.
    """
    try:
        from Crypto.Cipher import AES
        # pycryptodome: nonce=b'' означает, что весь 16-байтный блок — счётчик
        return AES.new(key, AES.MODE_CTR, nonce=b'', initial_value=iv)
    except ImportError:
        pass

    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend

        class _CryptographyCTR:
            def __init__(self, key, iv):
                self._enc = Cipher(
                    algorithms.AES(key),
                    modes.CTR(iv),
                    backend=default_backend()
                ).encryptor()

            def encrypt(self, data: bytes) -> bytes:
                return self._enc.update(data) + self._enc.finalize()

        return _CryptographyCTR(key, iv)
    except ImportError:
        pass

    raise ImportError(
        "Для тестирования MTProto нужна библиотека AES.\n"
        "Установите: pip install pycryptodome\n"
        "  или:      pip install cryptography"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Парсинг secret
# ──────────────────────────────────────────────────────────────────────────────

# Байты, с которых не должен начинаться nonce (чтобы прокси не спутал нас
# с другим протоколом). Источник: исходники MTProxy от Telegram.
_FORBIDDEN_FIRST_BYTES = frozenset([
    0xef,  # MTProto abridged (однобайтный заголовок длины)
    0x44,  # 'D' — начало "HEAD" (HTTP)
    0x47,  # 'G' — начало "GET"  (HTTP)
    0x50,  # 'P' — начало "POST" (HTTP)
    0x48,  # 'H' — начало "HTTP"
    0x16,  # начало TLS ClientHello
    0x03,  # продолжение TLS handshake
])

# Первые 4 байта не должны быть такими (Telegram зарезервировал для других вещей)
_FORBIDDEN_FIRST_DWORDS = frozenset([
    b'\x00\x00\x00\x00',
    b'\xef\xef\xef\xef',
])


def _parse_secret(secret_str: str) -> Optional[bytes]:
    """
    Разбирает строку secret в 16 байт ключа для MTProto Obfuscated2.

    Форматы:
      - 32 hex-символа                  →  простой secret (16 байт)
      - "dd" + 32 hex-символа (34 chars) →  современный DD-secret
      - "ee" + hex + domain             →  FakeTLS; берём первые 16 байт после ee

    Возвращает bytes(16) или None при ошибке.
    """
    s = secret_str.strip().lower()

    # Попытка декодировать как hex
    try:
        raw = bytes.fromhex(s)
    except ValueError:
        # Иногда секрет приходит в base64 (urlsafe)
        import base64
        try:
            raw = base64.urlsafe_b64decode(s + '==')
        except Exception:
            return None

    if len(raw) == 16:
        # Простой secret
        return raw
    elif len(raw) >= 17 and raw[0] in (0xdd, 0xee):
        # DD или EE-secret: первый байт — маркер, следующие 16 — ключ
        return raw[1:17]
    else:
        # Нестандартная длина — берём первые 16 байт или None
        return raw[:16] if len(raw) >= 16 else None


# ──────────────────────────────────────────────────────────────────────────────
# Построение MTProto Obfuscated2 init-пакета
# ──────────────────────────────────────────────────────────────────────────────

def _build_obfuscated2_packet(secret_raw: bytes) -> bytes:
    """
    Строит 64-байтный init-пакет MTProto Obfuscated2.

    Протокол (источник: https://core.telegram.org/mtproto/mtproto-transports
    и исходники github.com/TelegramMessenger/MTProxy):

      nonce[0:64]   — случайные байты с ограничениями
      nonce[56:60]  — маркер протокола: 0xefefefef (MTProto abridged inside)

      key_out = SHA256(nonce[8:40]  + secret)   — 32 байта, ключ шифрования
      iv_out  = SHA256(nonce[40:56] + secret)[:16]  — 16 байт, IV

      aes_ctr = AES-256-CTR(key_out, iv_out)
      encrypted_nonce = aes_ctr.encrypt(nonce)

      Отправляем: nonce[0:56] + encrypted_nonce[56:64]
      (первые 56 байт открытые, последние 8 — зашифрованные;
       именно так прокси-сервер находит ключ расшифровки)

    Возвращает bytes(64) — готовый пакет для отправки.
    """
    # Генерируем nonce, соблюдая ограничения
    while True:
        nonce = bytearray(os.urandom(64))

        # Первый байт не должен быть запрещённым
        if nonce[0] in _FORBIDDEN_FIRST_BYTES:
            continue

        # Первые 4 байта не должны быть запрещёнными DWORD-ами
        if bytes(nonce[0:4]) in _FORBIDDEN_FIRST_DWORDS:
            continue

        break

    # Маркер протокола: используем MTProto abridged (0xef x4)
    # Прокси прочитает это поле из расшифрованного пакета и поймёт формат
    nonce[56] = 0xef
    nonce[57] = 0xef
    nonce[58] = 0xef
    nonce[59] = 0xef

    nonce = bytes(nonce)

    # Ключевой материал: берём срезы nonce и смешиваем с secret через SHA256
    key_out = hashlib.sha256(nonce[8:40] + secret_raw).digest()    # 32 байта
    iv_out  = hashlib.sha256(nonce[40:56] + secret_raw).digest()[:16]  # 16 байт

    # Шифруем весь nonce
    cipher = _make_aes_ctr(key_out, iv_out)
    encrypted = cipher.encrypt(nonce)

    # Итоговый пакет: открытая часть + зашифрованный хвост
    return nonce[:56] + encrypted[56:]


# ──────────────────────────────────────────────────────────────────────────────
# Основная функция тестирования одного прокси
# ──────────────────────────────────────────────────────────────────────────────

def _test_single_mtproto(url: str, timeout: float) -> Tuple[bool, float, str]:
    """
    Тестирует один MTProto прокси через настоящий Obfuscated2 handshake.

    Алгоритм:
      1. Парсим URL → получаем server, port, secret
      2. TCP connect (таймаут timeout/2, чтобы не тратить всё время на мёртвые хосты)
      3. Отправляем Obfuscated2 init-пакет (64 байта)
      4. Ждём ответ (таймаут timeout/2):
           • Получили ≥1 байт        → РАБОЧИЙ (прокси ответил)
           • socket.timeout          → РАБОЧИЙ (прокси держит соединение открытым,
                                                 форвардит на Telegram DC)
           • ConnectionResetError    → МЁРТВЫЙ  (прокси сбросил соединение — неверный
                                                 handshake или сервис не MTProto)
           • Любое другое исключение → МЁРТВЫЙ

    Возвращает:
      (success: bool, ping_ms: float, url: str)
      ping_ms — время до первого ответа (или до таймаута recv), float('inf') если провал
    """
    parsed = parse_mtproto_url(url)
    if not parsed:
        return False, float('inf'), url

    server    = parsed['server']
    port      = parsed['port']
    secret_str = parsed['secret']

    # Разбираем secret → 16 байт
    secret_raw = _parse_secret(secret_str)
    if secret_raw is None or len(secret_raw) < 16:
        return False, float('inf'), url

    # Строим пакет заранее, чтобы не тратить время после connect()
    try:
        packet = _build_obfuscated2_packet(secret_raw)
    except ImportError as e:
        # AES библиотека не установлена — ошибка конфигурации, пробрасываем
        raise
    except Exception:
        return False, float('inf'), url

    half_timeout = max(timeout / 2, 1.0)

    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # отключаем Nagle
        sock.settimeout(half_timeout)

        start = time.perf_counter()

        # ── Шаг 1: TCP connect ──────────────────────────────────────────────
        try:
            sock.connect((server, port))
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False, float('inf'), url

        # ── Шаг 2: Отправляем MTProto Obfuscated2 handshake ─────────────────
        try:
            sock.sendall(packet)
        except OSError:
            return False, float('inf'), url

        # ── Шаг 3: Ждём ответ ───────────────────────────────────────────────
        sock.settimeout(half_timeout)
        try:
            response = sock.recv(128)
            elapsed_ms = (time.perf_counter() - start) * 1000

            if len(response) == 0:
                # Сервер закрыл соединение сразу → не MTProto прокси
                return False, float('inf'), url

            # Получили данные → прокси живой
            return True, elapsed_ms, url

        except socket.timeout:
            # Соединение держится, данных пока нет.
            # Это НОРМАЛЬНОЕ поведение рабочего прокси: он ждёт следующего
            # пакета от клиента (Telegram DC пока не ответил).
            elapsed_ms = (time.perf_counter() - start) * 1000
            return True, elapsed_ms, url

        except (ConnectionResetError, ConnectionAbortedError, OSError):
            # Соединение сброшено — прокси не принял наш handshake
            return False, float('inf'), url

    except Exception:
        return False, float('inf'), url

    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


# ──────────────────────────────────────────────────────────────────────────────
# Массовое тестирование (интерфейс не изменился)
# ──────────────────────────────────────────────────────────────────────────────

def test_mtproto_configs(
    configs: List[str],
    max_ping_ms: float,
    required_count: int,
    max_workers: int = 100,
    log_func: Callable = None,
    progress_func: Callable = None,
    out_file: str = None,
    profile_title: str = None,
    stop_flag=None,
    skip_flag=None,
) -> Tuple[int, int, int]:
    """
    Асинхронно тестирует список MTProto конфигов с настоящим Obfuscated2 handshake.

    Останавливается, когда найдено required_count рабочих конфигов.

    Args:
        configs        : Список MTProto URL (https://t.me/proxy?...)
        max_ping_ms    : Максимально допустимый пинг в мс
        required_count : Сколько рабочих конфигов нужно найти
        max_workers    : Кол-во параллельных потоков (100 — разумный максимум)
        log_func       : Функция логирования (msg: str, tag: str) → None
        progress_func  : Функция прогресса (current: int, total: int) → None
        out_file       : Путь для сохранения результатов (GUI-режим)
        profile_title  : Заголовок профиля в файле результатов
        stop_flag      : threading.Event для остановки извне
        skip_flag      : threading.Event для пропуска (не используется, для совместимости)

    Returns:
        GUI-режим  (out_file задан):  (working: int, passed: int, failed: int)
        Консольный (out_file = None): List[Tuple[url: str, ping_ms: float]]
    """

    def _log(msg: str, tag: str = "info"):
        if log_func:
            log_func(msg, tag)

    def _progress(current: int, total: int):
        if progress_func:
            progress_func(current, total)

    # Проверяем, что AES-библиотека установлена, до начала работы
    try:
        _make_aes_ctr(b'\x00' * 32, b'\x00' * 16)
    except ImportError as e:
        _log(str(e), "error")
        return (0, 0, len(configs)) if out_file is not None else []

    results: List[Tuple[str, float]] = []
    total = len(configs)
    processed = [0]
    lock = threading.Lock()
    local_stop = threading.Event()

    # Объединяем внешний и внутренний stop_flag
    def _check_stop():
        if stop_flag is not None and stop_flag.is_set():
            return True
        return local_stop.is_set()

    _log(
        f"Тестирование {total} MTProto прокси "
        f"({max_workers} потоков, Obfuscated2 handshake)...",
        "info"
    )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(_test_single_mtproto, cfg, 5.0): cfg
            for cfg in configs
        }

        for future in as_completed(future_to_url):
            if _check_stop():
                break

            try:
                success, ping_ms, url = future.result()
            except Exception as e:
                with lock:
                    processed[0] += 1
                _progress(processed[0], total)
                _log(f"Ошибка: {e}", "error")
                continue

            with lock:
                processed[0] += 1
                _progress(processed[0], total)

                if success and ping_ms <= max_ping_ms:
                    results.append((url, ping_ms))
                    _log(
                        f"✓ {ping_ms:.0f} мс  (найдено: {len(results)}/{required_count})",
                        "success"
                    )
                    if len(results) >= required_count:
                        local_stop.set()
                else:
                    if ping_ms == float('inf'):
                        _log("✗ недоступен", "warning")
                    elif ping_ms > max_ping_ms:
                        _log(f"✗ {ping_ms:.0f} мс — превышен лимит", "warning")
                    else:
                        _log("✗ не ответил на handshake", "warning")

        # Если найдено нужное количество — отменяем оставшиеся задачи
        if _check_stop():
            executor.shutdown(wait=False, cancel_futures=True)

    # Сортируем по пингу: лучшие первые
    results.sort(key=lambda x: x[1])
    top_results = results[:required_count]

    # ── GUI-режим: сохраняем файл и возвращаем статистику ──────────────────
    if out_file is not None:
        working = len(results)
        passed  = len(top_results)
        failed  = processed[0] - working

        if top_results:
            try:
                os.makedirs(os.path.dirname(out_file), exist_ok=True)
                with open(out_file, 'w', encoding='utf-8') as f:
                    f.write(f"#profile-title: {profile_title or 'arqVPN MTProto'}\n")
                    f.write("#profile-update-interval: 48\n")
                    f.write("#support-url: https://t.me/arqhub\n")
                    f.write("\n")
                    for url, ping_ms in top_results:
                        f.write(f"{url}\n")
                _log(f"✓ Сохранено {passed} конфигов в {out_file}", "success")
            except Exception as e:
                _log(f"Ошибка сохранения: {e}", "error")
        else:
            _log("Рабочих прокси не найдено", "warning")

        return working, passed, failed

    # ── Консольный режим ────────────────────────────────────────────────────
    return top_results


# Алиас для обратной совместимости (используется в gui.py)
test_mtproto_configs_and_save = test_mtproto_configs
"""Тестирование Xray конфигов через Xray-core."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Dict, List, Optional, Tuple

from config import BIN_DIR, XRAY_TIMEOUT
from parsers.xray_parser import create_xray_config, is_valid_xray_config, parse_config
from utils.logger import log

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class XrayTester:
    """Тестировщик Xray конфигов."""

    def __init__(self, xray_path: str = None):
        self.xray_path = xray_path or self._find_xray()
        self._running_processes = []
        self._config_files = {}
        self._process_lock = threading.Lock()
        self._base_port = 20000
        self._port_counter = 0
        self._port_lock = threading.Lock()

    def _find_xray(self) -> str:
        """Ищет бинарник Xray."""
        candidates = [
            os.path.join(BIN_DIR, "xray"),
            os.path.join(BIN_DIR, "xray.exe"),
            "/usr/bin/xray",
            "/usr/local/bin/xray",
        ]

        for path in candidates:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path

        return ""

    def _get_next_port(self) -> int:
        """Получает следующий свободный порт."""
        with self._port_lock:
            port = self._base_port + self._port_counter
            self._port_counter = (self._port_counter + 1) % 1000
            return port

    def _wait_for_port(self, port: int, timeout: float = 3.0) -> bool:
        """Ждёт пока порт откроется."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.1)
                result = sock.connect_ex(("127.0.0.1", port))
                sock.close()
                if result == 0:
                    return True
            except Exception:
                pass
            time.sleep(0.05)
        return False

    def start_xray(self, config: Dict, socks_port: int) -> Tuple[bool, Optional[subprocess.Popen], str]:
        """Запускает Xray с конфигом."""
        if not self.xray_path:
            return False, None, "Xray binary not found"

        # Создаём временный файл конфига
        fd, config_file = tempfile.mkstemp(suffix=".json", prefix="xray_")
        try:
            os.chmod(config_file, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(config, f, separators=(",", ":"))
        except Exception as e:
            return False, None, f"Failed to write config: {e}"

        try:
            cmd = [self.xray_path, "run", "-config", config_file]

            # Запускаем процесс
            kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "bufsize": 1024 * 1024}

            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            process = subprocess.Popen(cmd, **kwargs)

            # Ждём инициализации
            time.sleep(0.5)

            # Проверяем не упал ли сразу
            if process.poll() is not None:
                _, stderr = process.communicate(timeout=2)
                error = stderr.decode("utf-8", errors="ignore")[:500]
                os.unlink(config_file)
                return False, None, error or "Xray exited immediately"

            # Ждём порт
            if not self._wait_for_port(socks_port, timeout=3.0):
                process.terminate()
                try:
                    process.wait(timeout=2)
                except Exception:
                    process.kill()
                os.unlink(config_file)
                return False, None, "Port not listening"

            # Сохраняем для очистки
            with self._process_lock:
                self._running_processes.append(process)
                self._config_files[process.pid] = config_file

            return True, process, ""

        except Exception as e:
            try:
                os.unlink(config_file)
            except Exception:
                pass
            return False, None, str(e)

    def stop_xray(self, process: subprocess.Popen):
        """Останавливает Xray процесс."""
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        except Exception:
            pass

        # Удаляем конфиг
        try:
            config_file = self._config_files.pop(process.pid, None)
            if config_file and os.path.exists(config_file):
                os.unlink(config_file)
        except Exception:
            pass

        with self._process_lock:
            if process in self._running_processes:
                self._running_processes.remove(process)

    def test_through_proxy(self, socks_port: int, timeout: float, target_url: str) -> Tuple[bool, float]:
        """Тестирует соединение через SOCKS прокси."""
        if not REQUESTS_AVAILABLE:
            return False, 0.0

        proxy_url = f"socks5h://127.0.0.1:{socks_port}"

        session = requests.Session()
        session.proxies = {"http": proxy_url, "https": proxy_url}

        retry = Retry(total=0)
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Делаем 2 запроса как v2rayN, берём минимальный
        latencies = []

        for _ in range(2):
            try:
                start = time.perf_counter()
                session.get(target_url, timeout=timeout, allow_redirects=True)
                latency = (time.perf_counter() - start) * 1000
                latencies.append(latency)
                break
            except Exception:
                continue

        session.close()

        if latencies:
            return True, min(latencies)
        return False, 0.0

    def test_single(self, url: str, target_url: str, timeout: float = None) -> Tuple[str, bool, float]:
        """
        Тестирует один конфиг.

        Returns:
            (url, is_working, latency_ms)
        """
        timeout = timeout or XRAY_TIMEOUT

        # Валидация
        if not is_valid_xray_config(url):
            return (url, False, 0.0)

        # Парсинг
        parsed = parse_config(url)
        if not parsed:
            return (url, False, 0.0)

        # Создаём конфиг для Xray
        socks_port = self._get_next_port()
        xray_config = create_xray_config(parsed, socks_port)

        # Запускаем Xray
        success, process, _ = self.start_xray(xray_config, socks_port)
        if not success:
            return (url, False, 0.0)

        try:
            # Тестируем через прокси
            tested, latency = self.test_through_proxy(socks_port, timeout, target_url)
            return (url, tested, latency)
        finally:
            self.stop_xray(process)

    def test_batch(
        self,
        urls: List[str],
        target_url: str,
        required_count: int,
        max_ping_ms: float,
        timeout: float = None,
        concurrency: int = 50,
    ) -> List[Tuple[str, float]]:
        """
        Тестирует пакет конфигов, останавливается когда набрано required_count.

        Returns:
            Список кортежей (url, ping_ms) отсортированный по пингу
        """
        import concurrent.futures

        timeout = timeout or XRAY_TIMEOUT
        working = []
        stop_flag = threading.Event()
        progress_lock = threading.Lock()
        tested_count = 0
        total_count = len(urls)

        log(
            f"⏳ Запускаю тестирование Xray: всего {total_count} конфигов, "
            f"параллельность {concurrency}, таймаут {timeout:.1f}с"
        )

        def test_with_progress(url: str) -> Optional[Tuple[str, float]]:
            nonlocal tested_count
            if stop_flag.is_set():
                return None

            result = self.test_single(url, target_url, timeout)

            with progress_lock:
                tested_count += 1
                # Периодический прогресс, чтобы в логах было видно что процесс жив.
                if tested_count == 1 or tested_count % 100 == 0 or tested_count == total_count:
                    log(
                        f"📈 Прогресс Xray: {tested_count}/{total_count}, "
                        f"найдено рабочих: {len(working)}/{required_count}"
                    )

            with self._process_lock:
                if result[1] and result[2] <= max_ping_ms:
                    working.append((result[0], result[2]))

                    # Проверяем не набрали ли достаточно
                    if len(working) >= required_count:
                        stop_flag.set()
                        return (result[0], result[2])

            return None

        # Тестируем параллельно
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {executor.submit(test_with_progress, url): url for url in urls}

            for future in concurrent.futures.as_completed(futures):
                if stop_flag.is_set():
                    # Отменяем оставшиеся
                    for pending in futures:
                        pending.cancel()
                    break

                try:
                    future.result(timeout=timeout + 5)
                except Exception:
                    pass

        self.cleanup()

        # Сортируем по пингу (лучшие первыми)
        working.sort(key=lambda x: x[1])

        log(f"🏁 Тестирование Xray завершено: найдено {len(working)} рабочих конфигов")

        return working[:required_count]

    def cleanup(self):
        """Останавливает все процессы."""
        with self._process_lock:
            for process in self._running_processes[:]:
                try:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except Exception:
                            process.kill()
                            process.wait(timeout=2)
                except Exception:
                    pass
            self._running_processes.clear()

            for config_file in self._config_files.values():
                try:
                    if os.path.exists(config_file):
                        os.unlink(config_file)
                except Exception:
                    pass
            self._config_files.clear()

"""Конфигурация задач для ArcParse."""

import os

# Базовые пути
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(BASE_DIR, "rawconfigs")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
BIN_DIR = os.path.join(BASE_DIR, "bin")

# Гарантируем существование папок
os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(BIN_DIR, exist_ok=True)

# Список задач - легко добавлять новые источники
TASKS = [
    {
        "name": "Base VPN",
        "url": "https://raw.githubusercontent.com/whoahaow/rjsxrd/refs/heads/main/githubmirror/default/22.txt",
        "raw_file": os.path.join(RAW_DIR, "22.txt"),
        "out_file": os.path.join(RESULTS_DIR, "top_vpn.txt"),
        "type": "xray",
        "target_url": "https://google.com",
        "max_ping_ms": 900,
        "required_count": 10,
    },
    {
        "name": "Bypass VPN",
        "url": "https://raw.githubusercontent.com/whoahaow/rjsxrd/refs/heads/main/githubmirror/bypass/bypass-all.txt",
        "raw_file": os.path.join(RAW_DIR, "bypass-all.txt"),
        "out_file": os.path.join(RESULTS_DIR, "top_bypass.txt"),
        "type": "xray",
        "target_url": "https://youtube.com",
        "max_ping_ms": 900,
        "required_count": 10,
    },
    {
        "name": "Telegram MTProto",
        "url": "https://raw.githubusercontent.com/whoahaow/rjsxrd/refs/heads/main/githubmirror/tg-proxy/MTProto.txt",
        "raw_file": os.path.join(RAW_DIR, "MTProto.txt"),
        "out_file": os.path.join(RESULTS_DIR, "top_MTProto.txt"),
        "type": "mtproto",
        "target_url": "https://core.telegram.org",
        "max_ping_ms": 500,
        "required_count": 10,
    },
]

# Настройки тестирования
XRAY_TIMEOUT = 5.0  # Таймаут HTTP теста (сек)
XRAY_CONCURRENCY = 200  # Параллельных тестов
MTPROTO_TIMEOUT = 3.0  # Таймаут TCP теста (сек)
MTPROTO_CONCURRENCY = 200  # Параллельных тестов

# Тестовые URL для разных типов
TEST_URLS_XRAY = [
    "https://www.google.com/generate_204",
    "https://www.youtube.com/generate_204",
    "https://www.gstatic.com/generate_204",
]

TEST_URLS_MTPROTO = [
    ("149.154.175.50", 443),
    ("149.154.167.50", 443),
    ("149.154.175.100", 443),
]

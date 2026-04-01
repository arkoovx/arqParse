"""Конфигурация и настройки задач для ArcParse."""

import os

# Пути к директориям
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_CONFIGS_DIR = os.path.join(BASE_DIR, "rawconfigs")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
BIN_DIR = os.path.join(BASE_DIR, "bin")

# Создаем директории при импорте
os.makedirs(RAW_CONFIGS_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(BIN_DIR, exist_ok=True)

# Путь к Xray
XRAY_BIN = os.path.join(BIN_DIR, "xray.exe" if os.name == "nt" else "xray")

# Задачи для скачивания и тестирования
# Каждая задача может иметь несколько URL источников (проверяются по порядку)
TASKS = [
    {
        "name": "Base VPN",
        "urls": [
            "https://raw.githubusercontent.com/whoahaow/rjsxrd/refs/heads/main/githubmirror/default/22.txt",
            "https://raw.githubusercontent.com/whoahaow/rjsxrd/refs/heads/main/githubmirror/default/23.txt",
            "https://raw.githubusercontent.com/whoahaow/rjsxrd/refs/heads/main/githubmirror/default/24.txt",
            "https://raw.githubusercontent.com/whoahaow/rjsxrd/refs/heads/main/githubmirror/default/25.txt",
        ],
        "raw_files": [
            os.path.join(RAW_CONFIGS_DIR, "22.txt"),
            os.path.join(RAW_CONFIGS_DIR, "23.txt"),
            os.path.join(RAW_CONFIGS_DIR, "24.txt"),
            os.path.join(RAW_CONFIGS_DIR, "25.txt"),
        ],
        "out_file": os.path.join(RESULTS_DIR, "top_vpn.txt"),
        "type": "xray",
        "target_url": "https://google.com",
        "max_ping_ms": 15000,
        "required_count": 10
    },
    {
        "name": "Bypass VPN",
        "urls": [
            "https://raw.githubusercontent.com/whoahaow/rjsxrd/refs/heads/main/githubmirror/bypass/bypass-all.txt",
        ],
        "raw_files": [
            os.path.join(RAW_CONFIGS_DIR, "bypass-all.txt"),
        ],
        "out_file": os.path.join(RESULTS_DIR, "top_bypass.txt"),
        "type": "xray",
        "target_url": "https://youtube.com",
        "max_ping_ms": 15000,
        "required_count": 10
    },
    {
        "name": "Telegram MTProto",
        "urls": [
            "https://raw.githubusercontent.com/whoahaow/rjsxrd/refs/heads/main/githubmirror/tg-proxy/MTProto.txt",
        ],
        "raw_files": [
            os.path.join(RAW_CONFIGS_DIR, "MTProto.txt"),
        ],
        "out_file": os.path.join(RESULTS_DIR, "top_MTProto.txt"),
        "type": "mtproto",
        "target_url": "https://core.telegram.org",
        "max_ping_ms": 500,
        "required_count": 10
    }
]

# User-Agent для запросов
CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/138.0.0.0 Safari/537.36"
)

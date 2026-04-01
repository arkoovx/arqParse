"""Настройки для xray_tester.py (совместимость с rjsxrd)."""

import os

# Таймауты
VALIDATION_HTTP_TIMEOUT = 10.0
VALIDATION_TCP_TIMEOUT = 3.0

# Конкурентность
ASYNC_CONCURRENCY_WIN32 = 50
ASYNC_CONCURRENCY_LINUX = 300

# Логгер (заглушка)
def log(msg):
    print(msg)

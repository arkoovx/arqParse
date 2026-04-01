#!/usr/bin/env python3
"""
ArcParse - Легковесный парсер и тестировщик VPN конфигов.

Архитектура:
1. downloader.py - скачивает raw-файлы
2. parsers/ - парсят конфиги по типам
3. testers/ - тестируют через Xray или TCP
4. utils/ - утилиты
"""

import os
import signal
import sys

from config import MTPROTO_CONCURRENCY, TASKS, XRAY_CONCURRENCY
from downloader import download_all
from testers.mtproto_tester import MTProtoTester
from testers.xray_tester import XrayTester
from utils.file_utils import read_lines, write_results
from utils.logger import log


def signal_handler(signum, frame):
    """Обработка Ctrl+C."""
    _ = (signum, frame)
    log("\n⚠ Прервано пользователем, очистка...")
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def process_task(task: dict) -> list:
    """
    Обрабатывает одну задачу.

    Returns:
        Список кортежей (config, ping) для этой задачи
    """
    log(f"\n{'=' * 60}")
    log(f"📋 Задача: {task['name']}")
    log(f"   Тип: {task['type']}")
    log(f"   Цель: {task['target_url']}")
    log(f"   Макс пинг: {task['max_ping_ms']}ms")
    log(f"   Нужно найти: {task['required_count']}")
    log(f"{'=' * 60}")

    # Читаем raw файл
    if not os.path.exists(task["raw_file"]):
        log(f"✗ Файл не найден: {task['raw_file']}")
        return []

    lines = read_lines(task["raw_file"])
    log(f"✓ Загружено {len(lines)} конфигов из {task['raw_file']}")

    if not lines:
        log("✗ Пустой файл")
        return []

    if task["type"] == "xray":
        # Тестирование через Xray
        tester = XrayTester()

        if not tester.xray_path:
            log("⚠ Xray binary не найден! Скачайте в bin/")
            log("   https://github.com/XTLS/Xray-core/releases")
            return []

        log(f"✓ Xray найден: {tester.xray_path}")

        results = tester.test_batch(
            urls=lines,
            target_url=task["target_url"],
            required_count=task["required_count"],
            max_ping_ms=task["max_ping_ms"],
            concurrency=XRAY_CONCURRENCY,
        )

    elif task["type"] == "mtproto":
        # Тестирование MTProto
        tester = MTProtoTester()

        results = tester.test_batch(
            urls=lines,
            required_count=task["required_count"],
            max_ping_ms=task["max_ping_ms"],
            concurrency=MTPROTO_CONCURRENCY,
        )

    else:
        log(f"✗ Неизвестный тип: {task['type']}")
        return []

    # Сохраняем результаты
    if results:
        write_results(task["out_file"], results)
        log(f"✓ Сохранено {len(results)} конфигов в {task['out_file']}")
    else:
        log("✗ Не найдено рабочих конфигов")

    return results


def print_summary(all_results: dict):
    """Выводит итоговую таблицу результатов."""
    print("\n" + "=" * 70)
    print(" " * 20 + "📊 ИТОГОВЫЕ РЕЗУЛЬТАТЫ")
    print("=" * 70)

    for task_name, results in all_results.items():
        print(f"\n📁 {task_name}:")

        if not results:
            print("   ⚠ Нет рабочих конфигов")
            continue

        print(f"   {'Конфиг':<60} {'Пинг':>8}")
        print("   " + "-" * 70)

        for config, ping in results:
            # Обрезаем длинные конфиги
            display_config = config[:57] + "..." if len(config) > 60 else config
            print(f"   {display_config:<60} {ping:>6.0f}ms")

    print("\n" + "=" * 70)


def main():
    """Основная функция."""
    log("🚀 ArcParse запущен")
    log(f"📂 Рабочая директория: {os.path.dirname(os.path.abspath(__file__))}")

    # Этап 1: Скачивание
    log("\n📥 Этап 1: Скачивание raw-файлов...")
    download_results = download_all(force=False)

    failed = [name for name, success in download_results.items() if not success]
    if failed:
        log(f"⚠ Не удалось скачать: {', '.join(failed)}")

    # Этап 2: Тестирование
    log("\n🧪 Этап 2: Тестирование конфигов...")

    all_results = {}

    for task in TASKS:
        results = process_task(task)
        all_results[task["name"]] = results

    # Этап 3: Итоги
    print_summary(all_results)

    log("\n✅ ArcParse завершил работу!")


if __name__ == "__main__":
    main()

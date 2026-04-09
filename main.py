#!/usr/bin/env python3
"""
ArcParse - утилита для скачивания и тестирования VPN конфигов.
Стильный консольный интерфейс.
"""

import os
import sys
import signal
import argparse
import time
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import TASKS, XRAY_BIN, RESULTS_DIR
from downloader import download_all_tasks
from parser import read_configs_from_file, read_mtproto_from_file
from testers import test_xray_configs
from testers_mtproto import test_mtproto_configs
from formatting import format_config_name, _url_key
from setup_xray import ensure_xray
from ui import (
    print_banner, print_logo, print_header, print_subheader,
    print_success, print_error, print_warning, print_info,
    print_results_table, print_summary, Colors
)

RESULTS_MERGED_FILENAME = "all_top_vpn.txt"


def _task_out_file(task_name: str):
    """Возвращает путь к файлу результатов для задачи по имени."""
    for task in TASKS:
        if task.get("name") == task_name:
            return task.get("out_file")
    return None


def _test_xray_task(task: dict, skip_xray: bool) -> list:
    """Тестирует Xray-задачу (VLESS, VMess, Trojan, SS). Возвращает список (url, ping_ms)."""
    if skip_xray:
        print_warning("Пропущено (--skip-xray)")
        return []

    # Проверка Xray
    if not os.path.exists(XRAY_BIN):
        print_error(f"Xray не найден: {XRAY_BIN}")
        print_info("Скачайте Xray-core: https://github.com/XTLS/Xray-core/releases")
        return []

    print_success(f"Xray готов: {XRAY_BIN}")

    # Поддержка нескольких источников
    raw_files = task.get('raw_files', [task.get('raw_file')])
    all_working_configs = []

    for idx, raw_file in enumerate(raw_files):
        if not raw_file or not os.path.exists(raw_file):
            print_warning(f"Файл {os.path.basename(raw_file) if raw_file else '(не задан)'} не найден")
            continue

        print(f"\n  {Colors.CYAN}Источник:{Colors.RESET} {os.path.basename(raw_file)}")

        # Читаем конфиги из файла
        configs = read_configs_from_file(raw_file)

        if not configs:
            print_warning("Нет конфигов в файле")
            continue

        # Фильтруем локальные адреса
        filtered = [c for c in configs if '127.0.0.1' not in c and 'localhost' not in c]
        print(f"  {Colors.DIM}Конфигов после фильтрации:{Colors.RESET} {len(filtered)}")

        # Тестируем
        remaining = task['required_count'] - len(all_working_configs)
        if remaining <= 0:
            break

        print(f"\n  {Colors.YELLOW}Тестирование...{Colors.RESET}\n")
        print(f"  {Colors.DIM}(Нажмите Ctrl+C для пропуска файла){Colors.RESET}\n")

        try:
            results = test_xray_configs(
                configs=filtered,
                target_url=task['target_url'],
                max_ping_ms=task['max_ping_ms'],
                required_count=remaining,
                xray_path=XRAY_BIN
            )

            # Дедупликация по базовой части URL (без #fragment)
            seen_keys = set()
            unique_results = []
            for url, ping_ms in results:
                key = _url_key(url)
                if key not in seen_keys:
                    seen_keys.add(key)
                    unique_results.append((url, ping_ms))

            all_working_configs.extend(unique_results)
            dedup_count = len(results) - len(unique_results)
            if dedup_count > 0:
                print(f"  {Colors.DIM}Удалено дубликатов: {dedup_count}{Colors.RESET}")
            found_in_file = len(unique_results)
            print(f"\n  {Colors.GREEN}Найдено в этом файле:{Colors.RESET} {found_in_file} (всего: {len(all_working_configs)}/{task['required_count']})")

            # Если нашли достаточно - переходим к следующей задаче
            if len(all_working_configs) >= task['required_count']:
                print_success("Достаточное количество конфигов найдено!")
                break

        except KeyboardInterrupt:
            print(f"\n  {Colors.YELLOW}⚠ Тестирование этого файла прервано{Colors.RESET}")
            print(f"  {Colors.DIM}Продолжаем со следующего файла...{Colors.RESET}")

    return all_working_configs[:task['required_count']]


def _test_mtproto_task(task: dict) -> list:
    """Тестирует MTProto-задачу. Возвращает список (url, ping_ms)."""
    # Читаем MTProto прокси из файла
    raw_file = task.get('raw_files', [task.get('raw_file')])[0]
    configs = read_mtproto_from_file(raw_file)

    if not configs:
        print_warning("Нет MTProto прокси в файле")
        return []

    print(f"  {Colors.DIM}Найдено прокси:{Colors.RESET} {len(configs)}")
    print(f"\n  {Colors.YELLOW}Тестирование...{Colors.RESET}\n")
    print(f"  {Colors.DIM}(Нажмите Ctrl+C для пропуска){Colors.RESET}\n")

    try:
        results = test_mtproto_configs(
            configs=configs,
            max_ping_ms=task['max_ping_ms'],
            required_count=task['required_count']
        )
        return results
    except KeyboardInterrupt:
        print(f"\n  {Colors.YELLOW}⚠ Тестирование прервано{Colors.RESET}")
        return []


def stage_test_task(task: dict, skip_xray: bool) -> list:
    """Этап 3: тестирование одной задачи. Возвращает список (url, ping_ms)."""
    if task['type'] == 'xray':
        return _test_xray_task(task, skip_xray)
    elif task['type'] == 'mtproto':
        return _test_mtproto_task(task)
    else:
        print_warning(f"Неизвестный тип: {task['type']}")
        return []


def main(force_download: bool = False, skip_xray: bool = False, proxy_url: str = None, no_ui: bool = False):
    """Основная функция."""

    if not no_ui:
        print_banner()
    else:
        print_logo()

    # Этап 1: Скачивание конфигов
    print_header("📥 ЭТАП 1: СКАЧИВАНИЕ КОНФИГОВ")

    if force_download:
        print_info("Принудительное обновление всех файлов...")
    else:
        print_info("Проверка актуальности файлов...")

    download_results = download_all_tasks(TASKS, max_age_hours=24, force=force_download)

    failed = download_results.get('failed', [])
    downloaded = download_results.get('downloaded', [])
    skipped = download_results.get('skipped', [])

    if failed:
        print()
        for failed_item in failed:
            print_warning(f"Не удалось скачать: {failed_item}")

    if not downloaded and not skipped:
        print_error("\nНе скачан ни один файл. Выход.")
        sys.exit(1)

    print_success(f"Скачано файлов: {len(downloaded)}")
    if skipped:
        print_info(f"Пропущено актуальных файлов: {len(skipped)}")

    # Этап 1.5: Проверка и установка Xray
    print_header("🔧 ЭТАП 1.5: ПРОВЕРКА XRAY")

    xray_path = ensure_xray()
    if xray_path:
        # Обновляем XRAY_BIN на актуальный путь
        global XRAY_BIN
        XRAY_BIN = xray_path
    else:
        print_warning("Xray не удалось установить. Тестирование Xray конфигов будет пропущено.")

    # Этап 2: Настройка прокси
    print_header("🔗 ЭТАП 2: НАСТРОЙКА ПРОКСИ")

    if proxy_url:
        print_success(f"Используем прокси: {proxy_url[:50]}...")
        os.environ['HTTPS_PROXY'] = proxy_url
        os.environ['HTTP_PROXY'] = proxy_url
    else:
        print_warning("Прокси не указан")
        print_info("Тестирование будет работать только для доступных серверов")
        print_info("Для полного тестирования используйте --proxy socks5://host:port")

    # Этап 3: Тестирование конфигов
    print_header("⚡ ЭТАП 3: ТЕСТИРОВАНИЕ КОНФИГОВ")

    all_results = {}

    for task in TASKS:
        print_subheader(f"{task['name']}")
        print(f"  {Colors.DIM}Макс. пинг:{Colors.RESET} {task['max_ping_ms']} мс")
        print(f"  {Colors.DIM}Нужно найти:{Colors.RESET} {task['required_count']}")

        results = stage_test_task(task, skip_xray)
        all_results[task['name']] = results

        # Сохраняем результаты
        profile_title = task.get('profile_title', 'arqVPN Free')
        save_results(task['out_file'], results, profile_title, task['name'], no_ui)

    # Объединяем top_vpn и top_bypass в all_top_vpn
    merge_vpn_configs()

    # Итоговая сводка
    time.sleep(0.5)
    print_summary(all_results)

    # Запрос об обновлении репозитория
    prompt_and_push_to_github()

    # Финальное сообщение
    print(f"\n{Colors.GREEN}{Colors.BOLD}")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║                                                          ║")
    print("║     ✓  arqParse завершен успешно!                        ║")
    print("║                                                          ║")
    print(f"║     Результаты: {RESULTS_DIR:<40} ║")
    print("║                                                          ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"{Colors.RESET}")


def prompt_and_push_to_github():
    """Запрашивает пользователя об обновлении результатов на GitHub.
    При ответе 'y' - обновляет, при 'n' - оставляет только локально."""

    print()
    print_header("📤 ОБНОВЛЕНИЕ РЕПОЗИТОРИЯ")

    while True:
        response = input(
            f"{Colors.CYAN}Обновить результаты в репозитории GitHub? "
            f"({Colors.GREEN}y{Colors.RESET}/{Colors.RED}n{Colors.RESET}): {Colors.RESET}"
        ).strip().lower()

        if response == 'y':
            try:
                print_info("Обновление репозитория...")

                project_dir = os.path.dirname(os.path.abspath(__file__))

                # Собираем файлы результатов
                result_files = []
                result_filenames = {
                    os.path.basename(task.get("out_file", ""))
                    for task in TASKS
                    if task.get("out_file")
                }
                result_filenames.add(RESULTS_MERGED_FILENAME)

                for file in sorted(result_filenames):
                    file_path = os.path.join(RESULTS_DIR, file)
                    if os.path.exists(file_path):
                        result_files.append(os.path.join(RESULTS_DIR, file))

                if not result_files:
                    print_warning("Не найдены файлы результатов для обновления")
                    break

                # Добавляем файлы
                for file_path in result_files:
                    subprocess.run(
                        ["git", "add", file_path],
                        check=True,
                        capture_output=True,
                        cwd=project_dir
                    )

                print_info(f"Добавлено {len(result_files)} файлов результатов")

                # Проверяем, есть ли изменения
                status_result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    capture_output=True,
                    text=True,
                    check=True,
                    cwd=project_dir
                )

                if not status_result.stdout.strip():
                    print_warning("Нет изменений для коммита")
                    break

                # Делаем коммит
                commit_msg = f"Update VPN configs results - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                subprocess.run(
                    ["git", "commit", "-m", commit_msg],
                    check=True,
                    capture_output=True,
                    cwd=project_dir
                )

                print_info("Коммит создан")

                # Делаем push
                push_result = subprocess.run(
                    ["git", "push"],
                    capture_output=True,
                    text=True,
                    check=False,
                    cwd=project_dir
                )

                if push_result.returncode == 0:
                    print_success("Результаты успешно обновлены на GitHub!")
                else:
                    error_msg = push_result.stderr or push_result.stdout
                    print_error(f"Ошибка при отправке на GitHub:")
                    print_error(f"  {error_msg.strip()}")
                    print_warning("Коммит создан локально, но не отправлен на GitHub")
                    print_info("Вы можете повторить попытку позже с помощью:")
                    print_info(f"  cd \"{project_dir}\" && git push")

            except subprocess.CalledProcessError as e:
                print_error(f"Ошибка при обновлении репозитория: {e}")
            except Exception as e:
                print_error(f"Ошибка: {e}")

            break

        elif response == 'n':
            print_info("Результаты оставлены только локально")
            break
        
        else:
            print_warning("Пожалуйста, ответьте 'y' или 'n'")


def merge_vpn_configs():
    """Объединяет конфиги из top_vpn.txt и top_bypass.txt в all_top_vpn.txt.
    Копирует конфиги как есть, без изменений названий и нумерации.
    Дедупликация по базовой части URL (без #fragment)."""
    top_vpn_task_file = _task_out_file("Base VPN")
    top_bypass_task_file = _task_out_file("Bypass VPN")
    top_vpn_file = top_vpn_task_file or os.path.join(RESULTS_DIR, "top_base_vpn.txt")
    top_bypass_file = top_bypass_task_file or os.path.join(RESULTS_DIR, "top_bypass_vpn.txt")
    all_top_vpn_file = os.path.join(RESULTS_DIR, RESULTS_MERGED_FILENAME)

    try:
        all_configs = []

        # Читаем конфиги из top_vpn.txt
        if os.path.exists(top_vpn_file):
            with open(top_vpn_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        all_configs.append(line)

        # Читаем конфиги из top_bypass.txt
        if os.path.exists(top_bypass_file):
            with open(top_bypass_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        all_configs.append(line)

        # Дедупликация по базовой части URL
        seen = set()
        configs = []
        for config in all_configs:
            key = _url_key(config)
            if key not in seen:
                seen.add(key)
                configs.append(config)
        
        # Сохраняем объединённый файл как есть
        if configs:
            os.makedirs(os.path.dirname(os.path.abspath(all_top_vpn_file)), exist_ok=True)
            with open(all_top_vpn_file, 'w', encoding='utf-8') as f:
                f.write("#profile-title: arqVPN Free | Все\n")
                f.write("#profile-update-interval: 48\n")
                f.write("#support-url: https://t.me/arqhub\n")
                f.write("\n")
                for config in configs:
                    f.write(f"{config}\n")
            
            print_success(f"Объединено {len(configs)} конфигов в {RESULTS_MERGED_FILENAME}")
    except Exception as e:
        print(f"[!] Ошибка при объединении конфигов: {e}")


def save_results(filepath: str, results: list, profile_title: str = "arqParse results", config_type: str = "Base VPN", no_ui: bool = False):
    """Сохраняет результаты в файл.
    
    Если результатов нет, файл не перезаписывается (сохраняет старые данные).
    
    Args:
        filepath: путь для сохранения
        results: список кортежей (url, ping_ms)
        profile_title: название профиля
        config_type: тип конфига ("Base VPN", "Bypass VPN", "Telegram MTProto")
        no_ui: отключить вывод
    """
    filename = os.path.basename(filepath)
    
    # Если результатов нет - не перезаписываем файл, оставляем старые данные
    if not results:
        print_info(f"Нет рабочих конфигов для {filename} - сохраняем старые данные")
        return

    dirpath = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(dirpath, exist_ok=True)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"#profile-title: {profile_title}\n")
        f.write("#profile-update-interval: 48\n")
        f.write("#support-url: https://t.me/arqhub\n")
        f.write("\n")
        
        for index, (url, ping_ms) in enumerate(results, 1):
            # Форматируем названия конфигов с номерами и отметкой молнии
            formatted_url = format_config_name(url, index, config_type, ping_ms)
            f.write(f"{formatted_url}\n")
    
    print_success(f"Сохранено {len(results)} конфигов в {filename}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="arqParse - скачивание и тестирование VPN конфигов",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
{Colors.CYAN}Примеры:{Colors.RESET}
  {Colors.GREEN}./venv/bin/python main.py{Colors.RESET}              # Полный запуск
  {Colors.GREEN}./venv/bin/python main.py --gui{Colors.RESET}        # Графический интерфейс
  {Colors.GREEN}./venv/bin/python main.py --skip-xray{Colors.RESET}  # Только MTProto
  {Colors.GREEN}./venv/bin/python main.py --proxy socks5://...{Colors.RESET}  # С прокси
  {Colors.GREEN}./venv/bin/python main.py --force{Colors.RESET}      # Обновить всё
        """
    )
    parser.add_argument("--gui", action="store_true", help="Запустить графический интерфейс (Tkinter)")
    parser.add_argument("--force", "-f", action="store_true", help="Принудительно перезагрузить все файлы")
    parser.add_argument("--skip-xray", action="store_true", help="Пропустить тестирование Xray конфигов")
    parser.add_argument("--proxy", type=str, help="Прокси для тестирования (socks5://host:port)")
    parser.add_argument("--no-ui", action="store_true", help="Отключить стильный интерфейс (простой вывод)")
    
    args = parser.parse_args()
    
    try:
        if args.gui:
            # Запуск графического интерфейса
            from gui import main as gui_main
            gui_main()
        else:
            # Запуск консольного режима
            main(
                force_download=args.force,
                skip_xray=args.skip_xray,
                proxy_url=args.proxy,
                no_ui=args.no_ui
            )
    except KeyboardInterrupt:
        print(f"\n\n{Colors.RED}{Colors.BOLD}⚠ Программа прервана пользователем{Colors.RESET}")
        print(f"{Colors.YELLOW}Результаты могут быть не сохранены.{Colors.RESET}")
        # Восстанавливаем дефолтный обработчик и посылаем сигнал —
        # процесс завершится с кодом 130 (стандарт POSIX для Ctrl+C)
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGINT)
    except Exception as e:
        print(f"\n{Colors.RED}{Colors.BOLD}✗ Критическая ошибка: {e}{Colors.RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

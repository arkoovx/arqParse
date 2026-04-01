#!/usr/bin/env python3
"""
ArcParse - утилита для скачивания и тестирования VPN конфигов.
Стильный консольный интерфейс.
"""

import os
import sys
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import TASKS, XRAY_BIN, RESULTS_DIR
from downloader import download_all_tasks
from parser import read_configs_from_file, read_mtproto_from_file
from testers import test_xray_configs
from testers_mtproto import test_mtproto_configs
from ui import (
    print_banner, print_logo, print_header, print_subheader,
    print_success, print_error, print_warning, print_info,
    print_progress, print_results_table, print_summary,
    print_loading, type_writer, Colors
)


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
    
    if download_results['failed']:
        print()
        for failed in download_results['failed']:
            print_warning(f"Не удалось скачать: {failed}")
    
    if not download_results['success']:
        print_error("\nНе скачан ни один файл. Выход.")
        sys.exit(1)
    
    print_success(f"Скачано файлов: {len(download_results['success'])}")
    
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
        
        if task['type'] == 'xray':
            if skip_xray:
                print_warning("Пропущено (--skip-xray)")
                all_results[task['name']] = []
                continue
            
            # Проверка Xray
            if not os.path.exists(XRAY_BIN):
                print_error(f"Xray не найден: {XRAY_BIN}")
                print_info("Скачайте Xray-core: https://github.com/XTLS/Xray-core/releases")
                all_results[task['name']] = []
                continue
            
            print_success(f"Xray готов: {XRAY_BIN}")
            
            # Поддержка нескольких источников
            raw_files = task.get('raw_files', [task.get('raw_file')])
            all_working_configs = []
            
            for idx, raw_file in enumerate(raw_files):
                if not raw_file or not os.path.exists(raw_file):
                    print_warning(f"Файл {os.path.basename(raw_file)} не найден")
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
                
                results = test_xray_configs(
                    configs=filtered,
                    target_url=task['target_url'],
                    max_ping_ms=task['max_ping_ms'],
                    required_count=remaining,
                    xray_path=XRAY_BIN
                )
                
                all_working_configs.extend(results)
                found_in_file = len(results)
                print(f"\n  {Colors.GREEN}Найдено в этом файле:{Colors.RESET} {found_in_file} (всего: {len(all_working_configs)}/{task['required_count']})")
                
                # Если нашли достаточно - переходим к следующей задаче
                if len(all_working_configs) >= task['required_count']:
                    print_success("Достаточное количество конфигов найдено!")
                    break
            
            all_results[task['name']] = all_working_configs[:task['required_count']]
            
        elif task['type'] == 'mtproto':
            # Читаем MTProto прокси из файла
            raw_file = task.get('raw_files', [task.get('raw_file')])[0]
            configs = read_mtproto_from_file(raw_file)
            
            if not configs:
                print_warning("Нет MTProto прокси в файле")
                all_results[task['name']] = []
                continue
            
            print(f"  {Colors.DIM}Найдено прокси:{Colors.RESET} {len(configs)}")
            print(f"\n  {Colors.YELLOW}Тестирование...{Colors.RESET}\n")
            
            # Тестируем
            results = test_mtproto_configs(
                configs=configs,
                max_ping_ms=task['max_ping_ms'],
                required_count=task['required_count']
            )
            
            all_results[task['name']] = results
        
        else:
            print_warning(f"Неизвестный тип: {task['type']}")
            all_results[task['name']] = []
        
        # Сохраняем результаты
        save_results(task['out_file'], all_results[task['name']], no_ui)
    
    # Итоговая сводка
    time.sleep(0.5)
    print_summary(all_results)
    
    # Финальное сообщение
    print(f"\n{Colors.GREEN}{Colors.BOLD}")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║                                                          ║")
    print("║     ✓  ArcParse завершен успешно!                        ║")
    print("║                                                          ║")
    print(f"║     Результаты: {RESULTS_DIR:<40} ║")
    print("║                                                          ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"{Colors.RESET}")


def save_results(filepath: str, results: list, no_ui: bool = False):
    """Сохраняет результаты в файл."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("#profile-title: ArcParse results\n")
        f.write("#profile-update-interval: 48\n")
        f.write("#support-url: https://t.me/arcparse\n")
        f.write("\n")
        
        for url, ping_ms in results:
            f.write(f"{url} # {ping_ms:.0f}ms\n")
    
    filename = os.path.basename(filepath)
    if results:
        print_success(f"Сохранено {len(results)} конфигов в {filename}")
    else:
        print_info(f"Нет рабочих конфигов для {filename}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ArcParse - скачивание и тестирование VPN конфигов",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
{Colors.CYAN}Примеры:{Colors.RESET}
  {Colors.GREEN}./venv/bin/python main.py{Colors.RESET}              # Полный запуск
  {Colors.GREEN}./venv/bin/python main.py --skip-xray{Colors.RESET}  # Только MTProto
  {Colors.GREEN}./venv/bin/python main.py --proxy socks5://...{Colors.RESET}  # С прокси
  {Colors.GREEN}./venv/bin/python main.py --force{Colors.RESET}      # Обновить всё
        """
    )
    parser.add_argument("--force", "-f", action="store_true", help="Принудительно перезагрузить все файлы")
    parser.add_argument("--skip-xray", action="store_true", help="Пропустить тестирование Xray конфигов")
    parser.add_argument("--proxy", type=str, help="Прокси для тестирования (socks5://host:port)")
    parser.add_argument("--no-ui", action="store_true", help="Отключить стильный интерфейс (простой вывод)")
    
    args = parser.parse_args()
    
    try:
        main(
            force_download=args.force,
            skip_xray=args.skip_xray,
            proxy_url=args.proxy,
            no_ui=args.no_ui
        )
    except KeyboardInterrupt:
        print(f"\n\n{Colors.RED}{Colors.BOLD}⚠ Прервано пользователем{Colors.RESET}")
        print(f"{Colors.DIM}Выход...{Colors.RESET}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{Colors.RED}{Colors.BOLD}✗ Критическая ошибка: {e}{Colors.RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

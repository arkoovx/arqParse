"""Стильный консольный интерфейс для ArcParse."""

import sys
import time
from datetime import datetime


# ANSI цвета
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    ORANGE = '\033[38;5;208m'
    
    # Фоны
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_BLUE = '\033[44m'


# ASCII арт логотип
LOGO = f"""
{Colors.CYAN}{Colors.BOLD}
         ▗▄▖ ▗▄▄▖  ▗▄▄▖▗▄▄▖  ▗▄▖ ▗▄▄▖  ▗▄▄▖▗▄▄▄▖
        ▐▌ ▐▌▐▌ ▐▌▐▌   ▐▌ ▐▌▐▌ ▐▌▐▌ ▐▌▐▌   ▐▌   
        ▐▛▀▜▌▐▛▀▚▖▐▌   ▐▛▀▘ ▐▛▀▜▌▐▛▀▚▖ ▝▀▚▖▐▛▀▀▘
        ▐▌ ▐▌▐▌ ▐▌▝▚▄▄▖▐▌   ▐▌ ▐▌▐▌ ▐▌▗▄▄▞▘▐▙▄▄▖
                                        
                                        
{Colors.WHITE}{Colors.DIM}           Advanced VPN Config Parser & Tester
{Colors.RESET}{Colors.DIM}                 v1.0 | {datetime.now().strftime('%Y-%m-%d %H:%M')}
{Colors.RESET}"""


def print_logo():
    """Выводит логотип."""
    print(LOGO)


def print_header(text: str, char: str = "═"):
    """Выводит заголовок раздела."""
    width = 60
    print(f"\n{Colors.BLUE}{char * width}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.WHITE}  {text}{Colors.RESET}")
    print(f"{Colors.BLUE}{char * width}{Colors.RESET}")


def print_subheader(text: str):
    """Выводит подзаголовок."""
    print(f"\n{Colors.MAGENTA}{Colors.BOLD}▶ {text}{Colors.RESET}")


def print_success(text: str):
    """Выводит сообщение об успехе."""
    print(f"{Colors.GREEN}✓ {text}{Colors.RESET}")


def print_error(text: str):
    """Выводит сообщение об ошибке."""
    print(f"{Colors.RED}✗ {text}{Colors.RESET}")


def print_warning(text: str):
    """Выводит предупреждение."""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.RESET}")


def print_info(text: str):
    """Выводит информационное сообщение."""
    print(f"{Colors.CYAN}ℹ {text}{Colors.RESET}")


def print_progress(current: int, total: int, working: int, prefix: str = ""):
    """Выводит прогресс тестирования."""
    percent = (current / total) * 100 if total > 0 else 0
    bar_length = 30
    filled = int(bar_length * current / total)
    bar = "█" * filled + "░" * (bar_length - filled)
    
    status = f"{Colors.GREEN}{working} working{Colors.RESET}" if working > 0 else f"{Colors.DIM}0 working{Colors.RESET}"
    
    print(f"\r{prefix} [{bar}] {percent:5.1f}% | {current}/{total} | {status}    ", end="", flush=True)
    
    if current >= total:
        print()  # Новая строка после завершения


def print_config_result(index: int, url: str, ping: float, total: int):
    """Выводит результат тестирования конфига."""
    if ping > 0:
        # Цвет в зависимости от пинга
        if ping < 100:
            color = Colors.GREEN
        elif ping < 500:
            color = Colors.YELLOW
        else:
            color = Colors.ORANGE
        
        print(f"  {Colors.GREEN}✓{Colors.RESET} [{index:3d}/{total}] {color}{ping:7.1f} ms{Colors.RESET} | {url[:65]}...")
    else:
        print(f"  {Colors.RED}✗{Colors.RESET} [{index:3d}/{total}] {Colors.DIM}timeout{Colors.RESET}   | {url[:65]}...")


def print_results_table(results: list, task_name: str):
    """Выводит таблицу результатов."""
    print(f"\n{Colors.GREEN}{Colors.BOLD}┌{'─' * 58}┐{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}│{Colors.RESET}  {Colors.BOLD}{task_name:^54}{Colors.RESET}  {Colors.GREEN}{Colors.BOLD}│{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}├{'─' * 58}┤{Colors.RESET}")
    
    if not results:
        print(f"{Colors.GREEN}{Colors.BOLD}│{Colors.RESET}  {Colors.RED}Нет рабочих конфигов{Colors.RESET}".ljust(60) + f"{Colors.GREEN}{Colors.BOLD}│{Colors.RESET}")
    else:
        print(f"{Colors.GREEN}{Colors.BOLD}│{Colors.RESET}  {Colors.DIM}{'#':<4} {'Ping':>8}  {'Config':<40}{Colors.RESET}  {Colors.GREEN}{Colors.BOLD}│{Colors.RESET}")
        print(f"{Colors.GREEN}{Colors.BOLD}│{Colors.RESET}  {Colors.DIM}{'─' * 4} {'─' * 9}  {'─' * 40}{Colors.RESET}  {Colors.GREEN}{Colors.BOLD}│{Colors.RESET}")
        
        for i, (url, ping) in enumerate(results[:10], 1):  # Показываем топ-10
            url_short = url[:40] + "..." if len(url) > 40 else url
            
            # Цвет пинга
            if ping < 100:
                ping_color = Colors.GREEN
            elif ping < 500:
                ping_color = Colors.YELLOW
            else:
                ping_color = Colors.ORANGE
            
            print(f"{Colors.GREEN}{Colors.BOLD}│{Colors.RESET}  {i:<4} {ping_color}{ping:>7.0f} ms{Colors.RESET}  {Colors.CYAN}{url_short:<40}{Colors.RESET}  {Colors.GREEN}{Colors.BOLD}│{Colors.RESET}")
    
    print(f"{Colors.GREEN}{Colors.BOLD}└{'─' * 58}┘{Colors.RESET}")


def print_summary(all_results: dict):
    """Выводит итоговую сводку."""
    print_header("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ", "═")
    
    total_found = sum(len(r) for r in all_results.values())
    
    print(f"\n{Colors.WHITE}{Colors.BOLD}  {'Задача':<25} {'Найдено':>10} {'Статус':<15}{Colors.RESET}")
    print(f"  {'─' * 25} {'─' * 10} {'─' * 15}")
    
    for task_name, results in all_results.items():
        count = len(results)
        if count > 0:
            status = f"{Colors.GREEN}✓ OK{Colors.RESET}"
        else:
            status = f"{Colors.RED}✗ FAIL{Colors.RESET}"
        
        name_short = task_name[:25]
        print(f"  {name_short:<25} {Colors.GREEN}{count:>10}{Colors.RESET}   {status}")
    
    print()
    
    if total_found > 0:
        print(f"{Colors.GREEN}{Colors.BOLD}  ИТОГО: {total_found} рабочих конфигов найдено!{Colors.RESET}")
    else:
        print(f"{Colors.RED}{Colors.BOLD}  ИТОГО: Ни одного рабочего конфига не найдено{Colors.RESET}")


def print_loading(text: str, duration: float = 0.5):
    """Анимация загрузки."""
    symbols = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    start = time.time()
    
    while time.time() - start < duration:
        elapsed = time.time() - start
        idx = int(elapsed * 10) % len(symbols)
        print(f"\r{Colors.CYAN}{symbols[idx]}{Colors.RESET} {text}", end="", flush=True)
        time.sleep(0.05)
    
    print(f"\r{' ' * (len(text) + 2)}", end="", flush=True)
    print(f"\r{Colors.GREEN}✓{Colors.RESET} {text}")


def clear_screen():
    """Очищает экран."""
    print("\033[2J\033[H", end='')


def print_banner():
    """Выводит полный баннер программы."""
    clear_screen()
    print_logo()
    print(f"{Colors.DIM}{'─' * 60}{Colors.RESET}")

"""Модуль для авто-детекта и проверки прокси."""

import os
import socket
import requests
from typing import Optional, Dict


COMMON_PROXY_PORTS = [10808, 2080, 7890, 7891, 1080, 8080, 8888, 9050]


def check_port(host: str, port: int, timeout: float = 1.0) -> bool:
    """Проверяет открыт ли порт."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def get_proxy_ip(proxy_url: str, timeout: float = 5.0) -> Optional[str]:
    """Получает IP через прокси."""
    try:
        proxies = {'http': proxy_url, 'https': proxy_url}
        response = requests.get('https://ipwho.is/', proxies=proxies, timeout=timeout)
        data = response.json()
        return data.get('ip')
    except Exception:
        return None


def get_real_ip(timeout: float = 5.0) -> Optional[str]:
    """Получает реальный IP без прокси."""
    try:
        response = requests.get('https://ipwho.is/', timeout=timeout)
        data = response.json()
        return data.get('ip')
    except Exception:
        return None


def find_active_proxy_port(timeout: float = 1.0) -> Optional[int]:
    """Ищет активный прокси порт."""
    for port in COMMON_PROXY_PORTS:
        if check_port('127.0.0.1', port, timeout):
            return port
    return None


def verify_proxy_protection(proxy_port: int, timeout: float = 5.0) -> Dict:
    """
    Проверяет скрывает ли прокси реальный IP.
    
    Returns:
        Dict с: active, real_ip, proxy_ip, different, country
    """
    result = {
        'active': False,
        'real_ip': None,
        'proxy_ip': None,
        'different': False,
        'country': None
    }
    
    try:
        # Получаем реальный IP
        result['real_ip'] = get_real_ip(timeout=timeout)
        
        # Получаем IP через прокси
        proxy_url = f"socks5h://127.0.0.1:{proxy_port}"
        result['proxy_ip'] = get_proxy_ip(proxy_url, timeout=timeout)
        
        # Получаем страну
        if result['proxy_ip']:
            try:
                proxies = {'http': proxy_url, 'https': proxy_url}
                response = requests.get('https://ipwho.is/', proxies=proxies, timeout=timeout)
                data = response.json()
                result['country'] = data.get('country')
            except Exception:
                pass
        
        # Сравниваем
        if result['real_ip'] and result['proxy_ip']:
            result['different'] = result['real_ip'] != result['proxy_ip']
            result['active'] = result['different']
        
        return result
    except Exception as e:
        return result


def auto_detect_proxy() -> Optional[str]:
    """
    Авто-детект прокси.
    
    Returns:
        SOCKS прокси URL или None
    """
    print("[INFO] Поиск активного прокси...")
    
    proxy_port = find_active_proxy_port()
    
    if not proxy_port:
        print("[WARN] Прокси не найден на стандартных портах")
        return None
    
    print(f"[INFO] Найден прокси на порту {proxy_port}")
    print("[INFO] Проверка прокси...")
    
    protection = verify_proxy_protection(proxy_port, timeout=5.0)
    
    if protection['active']:
        print(f"[OK] Прокси активен: {protection['proxy_ip']} ({protection.get('country', 'Unknown')})")
        return f"socks5h://127.0.0.1:{proxy_port}"
    else:
        print("[WARN] Прокси не скрывает IP!")
        if protection.get('real_ip') == protection.get('proxy_ip'):
            print("  Реальный IP совпадает с прокси IP")
        return None

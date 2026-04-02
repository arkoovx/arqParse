"""Модуль для парсинга VPN ссылок и MTProto прокси."""

import os
import re
import json
from urllib.parse import parse_qs
from typing import Optional, Dict, List


def parse_mtproto_url(url: str) -> Optional[Dict]:
    """
    Парсит MTProto прокси URL (https://t.me/proxy?server=...&port=...&secret=...).
    """
    try:
        if 't.me/proxy' not in url and 'tg://proxy' not in url:
            return None
        
        # Извлекаем query параметры
        if '?' not in url:
            return None
        
        query = url.split('?', 1)[1]
        params = parse_qs(query)
        
        # Проверяем обязательные параметры
        if not all(k in params for k in ['server', 'port', 'secret']):
            return None
        
        server = params['server'][0]
        port = int(params['port'][0])
        secret = params['secret'][0]
        
        # Валидация
        if port < 1 or port > 65535:
            return None
        
        return {
            'server': server,
            'port': port,
            'secret': secret,
            'url': url
        }
    except Exception:
        return None


def read_configs_from_file(filepath: str) -> List[str]:
    """
    Читает конфиги из файла, пропускает пустые строки и комментарии.
    Возвращает список строк с конфигами.
    """
    configs = []
    
    if not os.path.exists(filepath):
        return configs
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Очищаем контент от HTML-сущностей и склеиваем разорванные строки
    content = content.replace('&amp;', '&')
    content = content.replace('&lt;', '<')
    content = content.replace('&gt;', '>')
    content = content.replace('&quot;', '"')
    content = content.replace('&#39;', "'")
    
    # Склеиваем разорванные строки
    lines = content.split('\n')
    cleaned_lines = []
    current_line = ''
    
    config_start_pattern = re.compile(r'^(vless|vmess|trojan|ss|ssr|hysteria|hy2|tuic|#|profile-)')
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
            
        if config_start_pattern.match(stripped):
            if current_line:
                cleaned_lines.append(current_line)
            current_line = stripped
        else:
            current_line += stripped
    
    if current_line:
        cleaned_lines.append(current_line)
    
    # Фильтруем конфиги
    for line in cleaned_lines:
        line = line.strip()
        # Пропускаем пустые строки, комментарии и заголовки
        if not line or line.startswith('#') or line.startswith('profile-'):
            continue
        configs.append(line)
    
    return configs


def read_mtproto_from_file(filepath: str) -> List[str]:
    """
    Читает MTProto прокси из файла.
    Возвращает список URL.
    """
    proxies = []
    
    if not os.path.exists(filepath):
        return proxies
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Очищаем контент
    content = content.replace('&amp;', '&')
    
    # Разбиваем по шаблону https://t.me/proxy или tg://proxy
    # Используем regex для разделения склеенных URL
    import re
    
    # Находим все MTProto ссылки
    pattern = r'(https://t\.me/proxy[^h]+|tg://proxy[^t]+|https://t\.me/proxy\?[^\s]+)'
    matches = re.findall(pattern, content)
    
    for match in matches:
        line = match.strip()
        if line and ('t.me/proxy' in line or 'tg://proxy' in line):
            # Проверяем что есть обязательные параметры
            if 'server=' in line and 'port=' in line:
                proxies.append(line)
    
    # Если regex не сработал, пробуем простой поиск
    if not proxies:
        # Разбиваем по 'https://t.me/proxy' и восстанавливаем
        parts = content.split('https://t.me/proxy')
        for i, part in enumerate(parts[1:], 1):  # Пропускаем первую часть
            url = 'https://t.me/proxy' + part
            # Обрезаем по следующему вхождению
            if i < len(parts):
                # Находим где заканчивается этот URL (перед следующим)
                for end_marker in ['https://t.me/proxy', 'tg://proxy']:
                    idx = url.find(end_marker)
                    if idx > 0:
                        url = url[:idx]
                        break
            
            url = url.strip()
            if url and 'server=' in url and 'port=' in url:
                proxies.append(url)
    
    return proxies

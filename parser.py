"""Модуль для парсинга VPN ссылок и MTProto прокси."""

import os
import re
import json
import base64
from urllib.parse import urlparse, parse_qs, unquote
from typing import Optional, Dict, List, Tuple


def parse_vless_url(url: str) -> Optional[Dict]:
    """Парсит VLESS URL и возвращает словарь параметров."""
    try:
        # Удаляем протокол
        url_part = url.replace('vless://', '', 1)
        
        # Разделяем фрагмент (#)
        fragment = ''
        if '#' in url_part:
            url_part, fragment = url_part.split('#', 1)
        
        # Разделяем query параметры (?)
        query_part = ''
        if '?' in url_part:
            base_part, query_part = url_part.split('?', 1)
        else:
            base_part = url_part
        
        # Парсим base часть: uuid@host:port
        if '@' not in base_part:
            return None
        
        uuid, host_port = base_part.rsplit('@', 1)
        
        if ':' not in host_port:
            return None
        
        hostname, port_str = host_port.rsplit(':', 1)
        port_str = port_str.strip().rstrip('/')
        
        try:
            port = int(port_str)
        except ValueError:
            return None
        
        # Парсим query параметры
        params = parse_qs(query_part)
        
        if not hostname or not port or not uuid:
            return None
        
        return {
            'uuid': uuid,
            'hostname': hostname,
            'port': port,
            'security': params.get('security', ['none'])[0],
            'encryption': params.get('encryption', ['none'])[0],
            'flow': params.get('flow', [''])[0],
            'fp': params.get('fp', ['chrome'])[0],
            'pbk': params.get('pbk', [''])[0],
            'sid': params.get('sid', [''])[0],
            'sni': params.get('sni', [hostname])[0],
            'type': params.get('type', ['tcp'])[0],
            'path': unquote(params.get('path', ['/'])[0]) if params.get('path') else '/',
            'host': unquote(params.get('host', [hostname])[0]) if params.get('host') else hostname,
            'fragment': fragment
        }
    except Exception:
        return None


def parse_vmess_url(url: str) -> Optional[Dict]:
    """Парсит VMess URL (base64 encoded JSON)."""
    try:
        encoded = url.replace('vmess://', '').strip()
        
        # Добавляем padding если нужно
        padding = 4 - len(encoded) % 4
        if padding != 4:
            encoded += '=' * padding
        
        # Декодируем base64
        decoded_bytes = base64.b64decode(encoded)
        decoded = decoded_bytes.decode('utf-8', errors='ignore')
        data = json.loads(decoded)
        
        # Валидация обязательных полей
        if not data.get('add') or not data.get('port') or not data.get('id'):
            return None
        
        return {
            'uuid': data.get('id', ''),
            'hostname': str(data.get('add', '')),
            'port': int(data.get('port', 443)),
            'alter_id': int(data.get('aid', 0)),
            'security': data.get('scy', 'auto'),
            'network': data.get('net', 'tcp'),
            'tls': data.get('tls') == 'tls',
            'fragment': data.get('ps', '')
        }
    except Exception:
        return None


def parse_trojan_url(url: str) -> Optional[Dict]:
    """Парсит Trojan URL."""
    try:
        url_part = url.replace('trojan://', '', 1)
        
        fragment = ''
        if '#' in url_part:
            url_part, fragment = url_part.split('#', 1)
        
        if '?' in url_part:
            url_part, query_part = url_part.split('?', 1)
        
        if '@' not in url_part:
            return None
        
        password, host_port = url_part.rsplit('@', 1)
        
        if ':' not in host_port:
            return None
        
        hostname, port_str = host_port.rsplit(':', 1)
        port_str = port_str.strip().rstrip('/')
        
        try:
            port = int(port_str)
        except ValueError:
            return None
        
        if not hostname or not port or not password:
            return None
        
        return {
            'password': password,
            'hostname': hostname,
            'port': port,
            'fragment': fragment
        }
    except Exception:
        return None


def parse_shadowsocks_url(url: str) -> Optional[Dict]:
    """Парсит Shadowsocks URL."""
    try:
        url_part = url.replace('ss://', '', 1)
        
        fragment = ''
        if '#' in url_part:
            url_part, fragment = url_part.split('#', 1)
        
        if '?' in url_part:
            url_part, query_part = url_part.split('?', 1)
        
        method = 'chacha20-poly1305'
        password = ''
        hostname = None
        port = None
        
        # Пробуем base64 декодирование
        decoded_success = False
        try:
            padding = 4 - len(url_part) % 4
            if padding != 4:
                url_part += '=' * padding
            
            decoded = base64.urlsafe_b64decode(url_part).decode('utf-8', errors='ignore')
            
            if '@' in decoded:
                userinfo, server = decoded.rsplit('@', 1)
                if ':' in userinfo:
                    method, password = userinfo.split(':', 1)
                else:
                    method = userinfo
                
                if ':' in server:
                    hostname, port_str = server.rsplit(':', 1)
                    port = int(port_str)
                else:
                    hostname = server
                    port = 443
                decoded_success = True
        except Exception:
            pass
        
        # Пробуем legacy формат
        if not decoded_success and '@' in url_part:
            userinfo, server = url_part.rsplit('@', 1)
            if ':' in userinfo:
                method, password = userinfo.split(':', 1)
            else:
                method = userinfo
            
            if ':' in server:
                hostname, port_str = server.rsplit(':', 1)
                port = int(port_str)
            else:
                hostname = server
                port = 443
            decoded_success = True
        
        # Последний шанс - извлечь что можем
        if not decoded_success and ':' in url_part:
            parts = url_part.split(':')
            if len(parts) >= 2:
                port_str = parts[-1].strip()
                hostname = ':'.join(parts[:-1]).split('@')[-1]
                try:
                    port = int(port_str)
                    decoded_success = True
                except ValueError:
                    pass
        
        if not hostname:
            return None
        
        if not port:
            port = 443
        
        if not password:
            password = 'password'
        
        return {
            'method': method,
            'password': password,
            'hostname': hostname,
            'port': port,
            'fragment': fragment
        }
    except Exception:
        return None


def parse_config_line(line: str) -> Optional[Dict]:
    """
    Парсит строку конфигурации и возвращает словарь с параметрами.
    Поддерживает: vless://, vmess://, trojan://, ss://
    """
    line = line.strip()
    if not line or line.startswith('#'):
        return None
    
    if line.startswith('vless://'):
        return parse_vless_url(line)
    elif line.startswith('vmess://'):
        return parse_vmess_url(line)
    elif line.startswith('trojan://'):
        return parse_trojan_url(line)
    elif line.startswith('ss://'):
        return parse_shadowsocks_url(line)
    
    return None


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

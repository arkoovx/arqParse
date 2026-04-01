"""Модуль для скачивания конфигов."""

import os
import re
import time
from datetime import datetime, timedelta
import requests
from config import CHROME_UA


def get_file_age_hours(filepath: str) -> float:
    """Возвращает возраст файла в часах."""
    if not os.path.exists(filepath):
        return float('inf')
    
    mtime = os.path.getmtime(filepath)
    age = time.time() - mtime
    return age / 3600  # Конвертируем в часы


def clean_config_content(content: str) -> str:
    """
    Очищает контент конфигов:
    - Заменяет HTML-сущности (&amp; -> &, &lt; -> <, и т.д.)
    - Склеивает разорванные строки конфигов
    """
    # Заменяем HTML-сущности
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
    
    return '\n'.join(cleaned_lines)


def download_file(url: str, filepath: str, max_age_hours: int = 24, force: bool = False) -> bool:
    """
    Скачивает файл по URL, если он устарел или не существует.
    """
    # Проверяем возраст файла
    if not force:
        age_hours = get_file_age_hours(filepath)
        if age_hours <= max_age_hours:
            print(f"[OK] Файл {os.path.basename(filepath)} актуален ({age_hours:.1f} ч)")
            return True
    
    # Создаем директорию если не существует
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    try:
        print(f"[...] Скачивание {os.path.basename(filepath)}...")
        response = requests.get(url, timeout=30, headers={"User-Agent": CHROME_UA})
        response.raise_for_status()
        
        # Очищаем контент
        cleaned_content = clean_config_content(response.text)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(cleaned_content)
        
        print(f"[OK] Скачано {os.path.basename(filepath)} ({len(cleaned_content)} байт)")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"[FAIL] Ошибка скачивания {os.path.basename(filepath)}: {e}")
        return False


def download_all_tasks(tasks: list, max_age_hours: int = 24, force: bool = False) -> dict:
    """
    Скачивает все файлы для задач.
    Поддерживает несколько URL для каждой задачи.
    
    Returns:
        dict с результатами: {'success': [...], 'failed': [...]}
    """
    results = {'success': [], 'failed': []}
    
    for task in tasks:
        # Поддержка как单个 URL, так и списка URL
        urls = task.get('urls', [task.get('url')])
        raw_files = task.get('raw_files', [task.get('raw_file')])
        
        for url, filepath in zip(urls, raw_files):
            if url and filepath:
                success = download_file(
                    url=url,
                    filepath=filepath,
                    max_age_hours=max_age_hours,
                    force=force
                )
                
                if success:
                    results['success'].append(f"{task['name']}: {os.path.basename(filepath)}")
                else:
                    results['failed'].append(f"{task['name']}: {os.path.basename(filepath)}")
    
    return results

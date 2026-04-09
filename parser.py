"""Модуль для парсинга VPN ссылок и MTProto прокси."""

from __future__ import annotations

import html
import os
import re
from urllib.parse import parse_qs
from typing import Callable, Dict, List, Optional, Pattern

# Предкомпилированные паттерны ускоряют повторные вызовы парсеров.
# Важно: более "длинные" протоколы должны идти раньше коротких,
# чтобы избежать частичных совпадений (например, hysteria2 до hysteria, ssr до ss).
_CONFIG_START_PATTERN = re.compile(r"(vless|vmess|trojan|ssr|ss|hysteria2|hy2|hysteria|tuic)://")
_MTPROTO_START_PATTERN = re.compile(r"(https://t\.me/proxy|tg://proxy)")
_MTPROTO_EXTRACT_PATTERN = re.compile(r"(https://t\.me/proxy\?[^\s]+|tg://proxy[^\s]+)")
_MTPROTO_REQUIRED_KEYS = ("server", "port", "secret")


def _has_required_mtproto_params(candidate: str) -> bool:
    """Быстрая проверка наличия обязательных параметров внутри URL-строки."""
    return all(f"{key}=" in candidate for key in _MTPROTO_REQUIRED_KEYS)


def parse_mtproto_url(url: str) -> Optional[Dict]:
    """
    Парсит MTProto прокси URL (https://t.me/proxy?server=...&port=...&secret=...).
    """
    if 't.me/proxy' not in url and 'tg://proxy' not in url:
        return None

    # Извлекаем query-параметры
    if '?' not in url:
        return None

    query = url.split('?', 1)[1]
    params = parse_qs(query)

    # Проверяем обязательные параметры
    if not all(key in params for key in _MTPROTO_REQUIRED_KEYS):
        return None

    try:
        server = params['server'][0]
        port = int(params['port'][0])
        secret = params['secret'][0]
    except (ValueError, TypeError, IndexError):
        return None

    # Валидация диапазона порта
    if port < 1 or port > 65535:
        return None

    return {
        'server': server,
        'port': port,
        'secret': secret,
        'url': url
    }


def _read_text_file(filepath: str) -> str:
    """Безопасно читает файл и нормализует переносы строк."""
    if not os.path.exists(filepath):
        return ""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n").replace("\r", "\n")


def _split_glued_entries(content: str, start_pattern: Pattern[str]) -> List[str]:
    """Разделяет склеенные URL и склеивает переносы внутри одного URL."""
    cleaned_lines: List[str] = []
    current_line = ""

    for raw_line in content.split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            continue

        matches = list(start_pattern.finditer(stripped))
        if len(matches) > 1:
            if current_line:
                cleaned_lines.append(current_line)
                current_line = ""
            for index, match in enumerate(matches):
                start = match.start()
                if index + 1 < len(matches):
                    end = matches[index + 1].start()
                    cleaned_lines.append(stripped[start:end])
                else:
                    current_line = stripped[start:]
            continue

        if len(matches) == 1:
            match = matches[0]
            if match.start() == 0:
                if current_line:
                    cleaned_lines.append(current_line)
                current_line = stripped
            else:
                current_line += stripped[: match.start()]
                if current_line.strip():
                    cleaned_lines.append(current_line.strip())
                current_line = stripped[match.start() :]
            continue

        current_line += stripped

    if current_line:
        cleaned_lines.append(current_line)
    return cleaned_lines


def _extract_items(lines: List[str], validator: Callable[[str], bool]) -> List[str]:
    """Общая фильтрация строк."""
    items: List[str] = []
    for line in lines:
        candidate = line.strip()
        if candidate and validator(candidate):
            items.append(candidate)
    return items


def read_configs_from_file(filepath: str) -> List[str]:
    """
    Читает конфиги из файла, пропускает пустые строки и комментарии.
    Корректно обрабатывает переносы строк и разделяет склеенные URL.
    """
    content = _read_text_file(filepath)
    if not content:
        return []

    # html.unescape покрывает &amp;, &lt;, &gt;, &quot;, &#39; и т.д.
    normalized = html.unescape(content)
    lines = _split_glued_entries(normalized, _CONFIG_START_PATTERN)
    return _extract_items(
        lines,
        lambda item: not item.startswith("#") and not item.startswith("profile-"),
    )


def read_mtproto_from_file(filepath: str) -> List[str]:
    """
    Читает MTProto прокси из файла.
    Корректно обрабатывает переносы строк и разделяет склеенные URL.
    """
    content = _read_text_file(filepath)
    if not content:
        return []

    normalized = html.unescape(content)
    lines = _split_glued_entries(normalized, _MTPROTO_START_PATTERN)

    proxies: List[str] = []
    seen_proxies = set()
    for line in lines:
        for proxy in _MTPROTO_EXTRACT_PATTERN.findall(line):
            candidate = proxy.strip()
            if not candidate:
                continue
            # Без обязательных параметров ссылка невалидна для подключения.
            if not _has_required_mtproto_params(candidate):
                continue
            # Сохраняем только уникальные прокси, не меняя порядок.
            if candidate in seen_proxies:
                continue
            seen_proxies.add(candidate)
            proxies.append(candidate)
    return proxies

"""Форматирование названий конфигов и утилиты."""


def _url_key(url: str) -> str:
    """Ключ для дедупликации — URL без фрагмента (#названия)."""
    return url.split('#')[0].strip()


def _is_emoji(char: str) -> bool:
    """Проверяет, является ли символ эмодзи (по Unicode диапазонам)."""
    cp = ord(char)
    return (
        0x1F300 <= cp <= 0x1FAFF  # Misc symbols, emoticons, transport, etc.
        or 0x2600 <= cp <= 0x27BF  # Misc symbols & dingbats
        or 0xFE00 <= cp <= 0xFE0F  # Variation selectors
        or 0x1F1E0 <= cp <= 0x1F1FF  # Regional indicators
    )


def _is_regional_indicator(char: str) -> bool:
    """Проверяет, является ли символ региональным индикатором (для флагов)."""
    cp = ord(char)
    return 0x1F1E0 <= cp <= 0x1F1FF


def format_config_name(url: str, index: int, config_type: str = "Base VPN", ping_ms: int = None) -> str:
    """Форматирует название конфига: оставляет только эмодзи + arqVPN с номером.

    Args:
        url: URL конфига
        index: порядковый номер (1-based)
        config_type: тип конфига ("Base VPN", "Bypass VPN", "Telegram MTProto")
        ping_ms: пинг в миллисекундах (для отметки молнии если < 100 мс)
    """
    # Если есть фрагмент (#) - это название
    if '#' not in url:
        return url

    base_url, fragment = url.rsplit('#', 1)
    fragment = fragment.strip()

    emoji = None

    # Флаг = два региональных индикатора подряд
    if len(fragment) >= 2 and _is_regional_indicator(fragment[0]) and _is_regional_indicator(fragment[1]):
        emoji = fragment[:2]
    # Одиночный эмодзи
    elif fragment and _is_emoji(fragment[0]):
        emoji = fragment[0]

    # Формируем название с номером
    # Определяем "Обход" по названию задачи или типу
    is_bypass = (
        config_type and (
            "bypass" in config_type.lower() or
            "обход" in config_type.lower()
        )
    )
    if is_bypass:
        name_suffix = f"arq-Обход-{index}"
    else:
        name_suffix = f"arq-{index}"

    # Добавляем молнию если пинг < 100 мс
    fast_indicator = "⚡ " if ping_ms is not None and ping_ms < 100 else ""

    # Возвращаем результат с эмодзи
    if emoji:
        return f"{base_url}#{fast_indicator}{emoji} {name_suffix}"
    else:
        return f"{base_url}#{fast_indicator}{name_suffix}"

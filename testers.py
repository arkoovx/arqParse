"""Модуль тестирования VPN конфигов для ArcParse.

Использует упрощённый xray_tester_simple.py основанный на подходе rjsxrd.
"""

import os
import sys
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from xray_tester_simple import test_batch as xray_test_batch


def test_xray_configs(
    configs: List[str],
    target_url: str,
    max_ping_ms: float,
    required_count: int,
    xray_path: str = None,
    concurrency: int = None
) -> List[Tuple[str, float]]:
    """
    Тестирует список Xray конфигов.
    
    Args:
        configs: Список URL конфигов
        target_url: URL для тестирования
        max_ping_ms: Максимальный пинг
        required_count: Сколько рабочих конфигов нужно найти
        xray_path: Путь к Xray бинарнику
        concurrency: Количество потоков
    
    Returns:
        Список кортежей (url, ping_ms) отсортированный по пингу
    """
    if not xray_path:
        xray_path = os.path.join(os.path.dirname(__file__), "bin", "xray")
    
    if not os.path.exists(xray_path):
        print(f"[WARN] Xray не найден: {xray_path}")
        return []
    
    # Тестируем конфиги
    # test_batch возвращает List[Tuple[str, bool, float]] - (url, success, latency_ms)
    results = xray_test_batch(
        urls=configs,
        xray_path=xray_path,
        concurrency=concurrency or 100,
        timeout=10.0
    )
    
    # Фильтруем только рабочие конфиги с подходящим пингом
    working_configs = [(url, latency) for url, success, latency in results if success and latency <= max_ping_ms]
    
    # Сортируем по пингу (меньше = лучше)
    working_configs.sort(key=lambda x: x[1])
    
    # Возвращаем только required_count
    return working_configs[:required_count]

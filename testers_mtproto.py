"""Модуль тестирования MTProto прокси."""

import socket
import time
from typing import List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from parser import parse_mtproto_url


def _test_single_mtproto(url: str, timeout: float) -> Tuple[bool, float, str]:
    """Тестирует один MTProto прокси через TCP соединение."""
    parsed = parse_mtproto_url(url)
    if not parsed:
        return False, float('inf'), url
    
    server = parsed['server']
    port = parsed['port']
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        
        start = time.time()
        result = sock.connect_ex((server, port))
        elapsed = (time.time() - start) * 1000
        sock.close()
        
        if result == 0:
            return True, elapsed, url
        else:
            return False, float('inf'), url
            
    except Exception:
        return False, float('inf'), url


def test_mtproto_configs(
    configs: List[str],
    max_ping_ms: float,
    required_count: int,
    max_workers: int = 100
) -> List[Tuple[str, float]]:
    """
    Асинхронно тестирует список MTProto конфигов.
    """
    results = []
    total = len(configs)
    processed = [0]
    lock = threading.Lock()
    
    print(f"[...] Тестирование {total} MTProto конфигов ({max_workers} потоков)...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(_test_single_mtproto, cfg, 5.0): cfg for cfg in configs}
        
        for future in as_completed(future_to_url):
            try:
                success, ping_ms, url = future.result()
                
                with lock:
                    processed[0] += 1
                    
                    if success and ping_ms <= max_ping_ms:
                        results.append((url, ping_ms))
                        print(f"  [{processed[0]}/{total}] ✓ {ping_ms:.0f} мс (найдено: {len(results)}/{required_count})")
                        
                        if len(results) >= required_count:
                            executor.shutdown(wait=False, cancel_futures=True)
                            break
                    else:
                        print(f"  [{processed[0]}/{total}] ✗ {'timeout' if ping_ms == float('inf') else f'{ping_ms:.0f} мс'}")
            except Exception:
                with lock:
                    processed[0] += 1
    
    # Сортируем по пингу (меньше = лучше)
    results.sort(key=lambda x: x[1])
    
    return results

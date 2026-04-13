"""
Менеджер кроссплатформенных путей.

Автоматически конвертирует пути из settings.json под текущую ОС.
Если путь содержит абсолютный путь другой ОС (например /home/user/... на Windows),
заменяет корень на актуальный BASE_DIR.
"""

import os
import re
from config import BASE_DIR, RAW_CONFIGS_DIR, RESULTS_DIR


def normalize_path(path: str) -> str:
    """
    Нормализует путь под текущую ОС.

    - Заменяет '/' и '\\' на os.sep
    - Если путь — абсолютный для другой ОС, извлекает относительную часть
      от проекта и склеивает с BASE_DIR
    - Если путь не начинается с текущего BASE_DIR, пересчитывает относительно него
    """
    if not path:
        return path

    # Нормализуем разделители в единый стиль для поиска
    normalized = path.replace('\\', '/').rstrip('/')

    # Определяем, является ли путь абсолютным для другой ОС
    needs_rebase = False

    # Linux/macOS путь на Windows
    if os.name == 'nt' and (normalized.startswith('/home') or normalized.startswith('/root') or normalized.startswith('/Users')):
        needs_rebase = True

    # Windows путь на Linux/macOS
    if os.name != 'nt' and re.match(r'^[A-Za-z]:', normalized):
        needs_rebase = True

    # Linux путь на Linux, но проект переехал — проверяем что путь начинается с BASE_DIR
    base_norm = os.path.normpath(BASE_DIR).replace('\\', '/')
    if os.name != 'nt' and not needs_rebase:
        if normalized.startswith('/home') or normalized.startswith('/root') or normalized.startswith('/Users'):
            if not normalized.startswith(base_norm):
                needs_rebase = True

    if needs_rebase:
        # Ищем известные директории проекта в пути
        for known_dir in ['rawconfigs', 'results']:
            # Ищем /rawconfigs/ или /results/ в пути
            pattern = f'/{known_dir}/'
            idx = normalized.find(pattern)
            if idx != -1:
                # Извлекаем всё после /rawconfigs/ или /results/
                rel_part = normalized[idx + len(pattern):]
                if rel_part:
                    if known_dir == 'rawconfigs':
                        return os.path.join(RAW_CONFIGS_DIR, rel_part.replace('/', os.sep))
                    elif known_dir == 'results':
                        return os.path.join(RESULTS_DIR, rel_part.replace('/', os.sep))

        # fallback: берём только имя файла и ищем в известных директориях
        basename = os.path.basename(normalized)
        if basename:
            raw_path = os.path.join(RAW_CONFIGS_DIR, basename)
            if os.path.exists(raw_path):
                return raw_path
            res_path = os.path.join(RESULTS_DIR, basename)
            return res_path  # для результатов — всегда возвращаем, даже если ещё нет

    return path


def normalize_task_paths(task: dict) -> dict:
    """Нормализует все пути в задаче под текущую ОС."""
    task = dict(task)  # копия

    # raw_files
    if 'raw_files' in task:
        task['raw_files'] = [normalize_path(f) for f in task['raw_files']]

    # out_file
    if 'out_file' in task:
        task['out_file'] = normalize_path(task['out_file'])

    return task

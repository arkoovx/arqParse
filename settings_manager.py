"""Менеджер настроек — сохранение и загрузка из settings.json."""

import json
import os

from config import BASE_DIR, TASKS, CHROME_UA
from path_manager import normalize_task_paths

SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")


def _default_settings():
    """Возвращает настройки по умолчанию из текущих констант."""
    tasks = []
    for t in TASKS:
        tasks.append({
            "name": t["name"],
            "urls": t["urls"],
            "out_file": t["out_file"],
            "profile_title": t["profile_title"],
            "type": t["type"],
            "target_url": t["target_url"],
            "max_ping_ms": t["max_ping_ms"],
            "required_count": t["required_count"],
        })
    return {
        "tasks": tasks,
        "user_agent": CHROME_UA,
    }


def load_settings():
    """Загружает настройки из файла. Если файла нет — возвращает дефолт."""
    if not os.path.exists(SETTINGS_FILE):
        return _default_settings()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        defaults = _default_settings()
        if "tasks" not in data:
            data["tasks"] = defaults["tasks"]
        if "user_agent" not in data:
            data["user_agent"] = defaults["user_agent"]
        
        # Валидация числовых полей в задачах
        DEFAULT_MAX_PING = 9000
        DEFAULT_REQUIRED_COUNT = 10
        for task in data.get("tasks", []):
            try:
                task["max_ping_ms"] = int(task.get("max_ping_ms", DEFAULT_MAX_PING))
            except (ValueError, TypeError):
                task["max_ping_ms"] = DEFAULT_MAX_PING
            try:
                task["required_count"] = int(task.get("required_count", DEFAULT_REQUIRED_COUNT))
            except (ValueError, TypeError):
                task["required_count"] = DEFAULT_REQUIRED_COUNT
        
        return data
    except (json.JSONDecodeError, KeyError):
        return _default_settings()


def save_settings(data):
    """Сохраняет настройки в файл."""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def reset_to_defaults():
    """Сбрасывает настройки до значений по умолчанию."""
    defaults = _default_settings()
    save_settings(defaults)
    return defaults


def get_tasks():
    """Возвращает список задач из настроек (совместимый с config.TASKS формат).
    Автоматически нормализует пути под текущую ОС."""
    settings = load_settings()
    tasks = []
    for t in settings.get("tasks", []):
        raw_files = []
        for url in t.get("urls", []):
            # Извлекаем имя файла из URL
            fname = url.split("/")[-1].split("?")[0]
            if fname:
                from config import RAW_CONFIGS_DIR
                raw_files.append(os.path.join(RAW_CONFIGS_DIR, fname))
        task = {
            "name": t["name"],
            "urls": t["urls"],
            "raw_files": raw_files,
            "out_file": t.get("out_file", ""),
            "profile_title": t.get("profile_title", ""),
            "type": t.get("type", "xray"),
            "target_url": t.get("target_url", "https://www.google.com/generate_204"),
            "max_ping_ms": t.get("max_ping_ms", 9000),
            "required_count": t.get("required_count", 10),
        }
        # Нормализуем пути под текущую ОС
        task = normalize_task_paths(task)
        tasks.append(task)
    return tasks


def get_user_agent():
    """Возвращает user-agent из настроек."""
    settings = load_settings()
    return settings.get("user_agent", CHROME_UA)

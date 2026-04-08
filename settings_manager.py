"""Менеджер настроек — сохранение и загрузка из settings.json."""

import json
import os

from config import BASE_DIR, TASKS, CHROME_UA

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
        return data
    except (json.JSONDecodeError, KeyError):
        return _default_settings()


def save_settings(data):
    """Сохраняет настройки в файл."""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_tasks():
    """Возвращает список задач из настроек (совместимый с config.TASKS формат)."""
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
        tasks.append({
            "name": t["name"],
            "urls": t["urls"],
            "raw_files": raw_files,
            "out_file": t.get("out_file", ""),
            "profile_title": t.get("profile_title", ""),
            "type": t.get("type", "xray"),
            "target_url": t.get("target_url", "https://google.com"),
            "max_ping_ms": t.get("max_ping_ms", 9000),
            "required_count": t.get("required_count", 10),
        })
    return tasks


def get_user_agent():
    """Возвращает user-agent из настроек."""
    settings = load_settings()
    return settings.get("user_agent", CHROME_UA)

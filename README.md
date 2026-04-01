# ArcParse

**VPN Config Parser & Tester** — утилита для скачивания и тестирования VPN конфигов.

---

## Возможности

- ✅ **Скачивание конфигов** из GitHub репозиториев
- ✅ **Тестирование Xray** (VLESS, VMess, Trojan, Shadowsocks)
- ✅ **Тестирование MTProto** (Telegram прокси)
- ✅ **Сортировка по пингу** — лучшие конфиги сверху
- ✅ **Гибкая настройка** — несколько источников, лимиты пинга
- ✅ **Стильный интерфейс** — цветной вывод с прогресс-барами

---

## Установка

```bash
# Перейдите в директорию проекта
cd ArcParse

# Установите зависимости
./venv/bin/pip install -r requirements.txt
```

### Требования

- Python 3.8+
- Xray-core (для тестирования Xray конфигов)

Для установки Xray-core:
```bash
# Скачайте с https://github.com/XTLS/Xray-core/releases
# Поместите бинарник в папку bin/
```

---

## Использование

### Базовый запуск

```bash
./venv/bin/python main.py
```

### Только MTProto (быстро, ~5 сек)

```bash
./venv/bin/python main.py --skip-xray
```

### С прокси (для ускорения Xray тестов)

```bash
./venv/bin/python main.py --proxy socks5://127.0.0.1:10808
```

### Принудительное обновление конфигов

```bash
./venv/bin/python main.py --force
```

### Простой вывод (без стильного интерфейса)

```bash
./venv/bin/python main.py --no-ui
```

---

## Настройка

Откройте `config.py` и измените список задач:

```python
TASKS = [
    {
        "name": "Base VPN",
        "urls": [
            "https://raw.githubusercontent.com/.../22.txt",
            "https://raw.githubusercontent.com/.../23.txt",
        ],
        "raw_files": ["rawconfigs/22.txt", "rawconfigs/23.txt"],
        "out_file": "results/top_vpn.txt",
        "type": "xray",
        "target_url": "https://google.com",
        "max_ping_ms": 15000,
        "required_count": 10
    },
    # Добавьте свои задачи...
]
```

### Параметры задачи

| Параметр | Описание |
|----------|----------|
| `name` | Название задачи |
| `urls` | Список URL источников (проверяются по порядку) |
| `raw_files` | Пути для сохранения скачанных файлов |
| `out_file` | Путь для сохранения результатов |
| `type` | Тип тестера: `xray` или `mtproto` |
| `target_url` | URL для тестирования |
| `max_ping_ms` | Максимальный пинг (мс) |
| `required_count` | Сколько рабочих конфигов найти |

---

## Структура проекта

```
ArcParse/
├── config.py              # Настройки задач
├── downloader.py          # Скачивание конфигов
├── parser.py              # Парсинг Xray/MTProto ссылок
├── testers.py             # Тестер Xray конфигов
├── testers_mtproto.py     # Тестер MTProto прокси
├── xray_tester_simple.py  # Базовый Xray тестер
├── ui.py                  # Стильный консольный интерфейс
├── main.py                # Основная логика
├── requirements.txt       # Зависимости Python
├── bin/
│   └── xray              # Xray-core бинарник
├── rawconfigs/           # Скачанные файлы
└── results/              # Результаты тестирования
```

---

## Результаты

После завершения работы результаты сохраняются в папку `results/`:

- `top_vpn.txt` — лучшие VPN конфиги
- `top_bypass.txt` — лучшие обходные конфиги
- `top_MTProto.txt` — лучшие MTProto прокси

Формат файла:
```
#profile-title: ArcParse results
#profile-update-interval: 48

vless://... # 150ms
vless://... # 200ms
```

---

## Примеры

### Тестирование с выводом прогресса

```
▶ Base VPN
  Макс. пинг: 15000 мс
  Нужно найти: 10
  
  Источник: 22.txt
  Конфигов после фильтрации: 2109
  
  Тестирование...
  
  Progress: [██████░░░░░░░░░░░░░░░] 30.0% | 632/2109 | 15 working
  ✓ [  1/2109]   125.3 ms | vless://...
  ✓ [  2/2109]   250.7 ms | vless://...
  
  Найдено в этом файле: 10 (всего: 10/10)
✓ Сохранено 10 конфигов в top_vpn.txt
```

### Итоговая таблица

```
╔══════════════════════════════════════════════════════════╗
║  #    Ping     Config                                    ║
║  ────  ─────────  ────────────────────────────────────────║
║  1       125 ms  vless://abc123...                       ║
║  2       250 ms  vless://def456...                       ║
║  3       380 ms  trojan://ghi789...                      ║
╚══════════════════════════════════════════════════════════╝
```

---

## Лицензия

MIT

---

## Поддержка

Если возникли вопросы или проблемы, создайте issue в репозитории.

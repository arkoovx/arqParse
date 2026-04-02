# 🚀 QUICK START - ArcParse v2.0

## Установка и первый запуск

### 1️⃣ Установка зависимостей
```bash
cd ~/Документы/Обход-БС/ArcParse
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2️⃣ Обычный запуск
```bash
./venv/bin/python main.py
```

**Что происходит:**
1. Скачивает свежие конфиги (если кэш старше 24 часов)
2. Тестирует VPN конфиги (Xray)
3. Тестирует Bypass конфиги (Xray)
4. Тестирует MTProto прокси (TCP)
5. Сохраняет топ-10 в `results/`

**Время выполнения:** ~8-10 минут (для 2109 конфигов)

---

## 🎯 Полезные флаги

### Принудительное обновление всех файлов
```bash
./venv/bin/python main.py --force
```

### Пропустить тестирование Xray (только MTProto)
```bash
./venv/bin/python main.py --skip-xray
```

### Использовать прокси для тестирования
```bash
./venv/bin/python main.py --proxy socks5://localhost:1080
```

### Простой вывод (без цветов и красивого интерфейса)
```bash
./venv/bin/python main.py --no-ui
```

### Комбинированное использование
```bash
./venv/bin/python main.py --force --proxy socks5://host:port
```

---

## ⌨️ Управление во время выполнения

### Ctrl+C при тестировании файла
- ✅ Пропускает текущий файл
- ✅ Переходит к следующему файлу  
- ✅ Сохраняет уже найденные конфиги

### Ctrl+C на главном уровне (дважды)
- ✅ Завершает программу
- ⚠️ НЕ сохраняет результаты текущей задачи

---

## 📊 Результаты

Результаты сохраняются в `results/`:
- `top_vpn.txt` - Топ VPN конфигов (10 штук)
- `top_bypass.txt` - Топ Bypass конфигов (10 штук)
- `top_MTProto.txt` - Топ MTProto прокси (10 штук)

**Формат результатов:**
```
#profile-title: ArcParse results
#profile-update-interval: 48
#support-url: https://t.me/arcparse

vless://uuid@host:port?...# 45ms
vmess://base64encoded...# 52ms
trojan://pass@host:port# 48ms
```

---

## 🔍 Логирование

По умолчанию выводится в консоль с цветными кодами.

Доступные уровни логирования:
- 🟢 SUCCESS - Успешная операция
- 🟡 WARNING - Предупреждение  
- 🔴 ERROR - Ошибка
- 🔵 INFO - Информация

---

## ⚙️ Настройки

### Глобальные настройки (config.py)

```python
TASKS = [
    {
        "name": "Base VPN",
        "urls": [...],
        "raw_files": [...],
        "out_file": "results/top_vpn.txt",
        "type": "xray",
        "target_url": "https://youtube.com",
        "max_ping_ms": 15000,
        "required_count": 10  # ← Количество нужных конфигов
    },
    # ... остальные задачи
]
```

**Модифицируемые параметры:**
- `required_count` - Сколько конфигов нужно найти
- `max_ping_ms` - Максимальный пинг в миллисекундах
- `target_url` - URL для тестирования
- `urls` - Источники для скачивания

---

## 🎛️ Тонкая настройка производительности

### xray_tester_simple.py

```python
# В функции test_batch():
concurrency: int = 150  # Количество одновременных потоков
timeout: float = 6.0    # Таймаут для каждого теста в секундах
```

**Рекомендации:**
- 🖥️ Мощный ПК: увеличьте `concurrency` до 200
- 💻 Слабый ПК: уменьшьте `concurrency` до 100  
- ⚡ Нужна скорость: уменьшьте `timeout` до 5.0
- ✅ Нужна надежность: увеличьте `timeout` до 8.0

---

## 🐛 Решение проблем

### Проблема: "Xray не найден"

```
✗ Xray не найден: /path/to/bin/xray
```

**Решение:**
```bash
# Скачайте Xray-core
cd bin/
wget https://github.com/XTLS/Xray-core/releases/download/v1.8.0/Xray-linux-64.zip
unzip Xray-linux-64.zip
chmod +x xray
```

### Проблема: "Прокси не указан"

```
⚠ Прокси не указан
Тестирование будет работать только для доступных серверов
```

**Решение:**
```bash
./venv/bin/python main.py --proxy socks5://localhost:1080
# или используйте локальный VPN клиент с SOCKS портом
```

### Проблема: зависание программы

**Решение:**
- Нажмите **Ctrl+C** (один раз для пропуска файла)
- Нажмите **Ctrl+C** (дважды быстро для полного выхода)

### Проблема: ошибка "Address already in use"

```
OSError: [Errno 98] Address already in use
```

**Решение:**
```bash
# Найдите процесс использующий порты 20000-22000
lsof -i :20000-22000
# Или просто перезагрузитесь
```

---

## 📈 Мониторинг прогресса

### Типичный вывод:

```
▶ Base VPN
  Макс. пинг: 15000 мс
  Нужно найти: 10
✓ Xray готов: /path/to/bin/xray

  Источник: 22.txt
  Конфигов после фильтрации: 2109

  Тестирование...
  (Нажмите Ctrl+C для пропуска файла)

Тестирование 2109 конфигов (concurrency=150, timeout=6.0s)...
Progress: 20/2109 - Working: 2
Progress: 40/2109 - Working: 3
...
Progress: 347/2109 - Working: 10
Готово: 10/2109 рабочих

  Найдено в этом файле: 10 (всего: 10/10)
✓ Достаточное количество конфигов найдено!
✓ Сохранено 10 конфигов в top_vpn.txt
```

---

## 📖 Дополнительная информация

### Документация
- [IMPROVEMENTS.md](IMPROVEMENTS.md) - Подробный список улучшений v2.0
- [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) - Структура проекта
- [AUDIT_REPORT.md](AUDIT_REPORT.md) - Полный отчёт об аудите
- [README.md](README.md) - Исходная документация

### Контакты
- Репозиторий: https://github.com/whoahaow/rjsxrd
- Телеграм: https://t.me/arcparse

---

## 🎉 Готово!

Проект полностью оптимизирован и готов к использованию.

**Улучшения v2.0:**
- ✅ 2-2.5x ускорение тестирования
- ✅ Удалено 275+ строк мертвого кода
- ✅ Исправлены проблемы с Ctrl+C
- ✅ Добавлены retry при ошибках сети
- ✅ Улучшена обработка прогресса
- ✅ Production-ready

**Happy testing! 🚀**

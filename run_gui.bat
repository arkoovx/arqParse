@echo off
chcp 65001 >nul 2>&1

:: Получаем директорию батника как корневую директорию проекта
set "SCRIPT_DIR=%~dp0"

setlocal enabledelayedexpansion

echo ════════════════════════════════════════════════════════
echo   arqParse GUI — Запуск
echo ════════════════════════════════════════════════════════
echo.

:: Меняем рабочую директорию на директорию скрипта
cd /d "%SCRIPT_DIR%"

:: 1. Проверка Python
:: Приоритет: родной Windows Python, затем MSYS2 Python
where /q py && (
    set "PYTHON_CMD=py -3"
    for /f "tokens=2" %%i in ('py -3 --version 2^>^&1') do set PY_VER=%%i
) || (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo [X] Python не найден. Установите Python 3.8+
        echo     https://www.python.org/downloads/
        pause
        exit /b 1
    )
    set "PYTHON_CMD=python"
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PY_VER=%%i
)
echo [+] Python найден: %PY_VER%

:: 2. Проверка Kivy/KivyMD (опционально в системном Python)
%PYTHON_CMD% -c "import kivy, kivymd" >nul 2>&1
if errorlevel 1 (
    echo [*] Kivy/KivyMD не найдены в системном Python - будут установлены в venv
) else (
    echo [+] Kivy/KivyMD доступны
)

:: 3. Создание venv если нет
:: Проверяем оба возможных расположения python.exe (Windows и MSYS2 стили)
set "PYTHON_EXE=%SCRIPT_DIR%venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=%SCRIPT_DIR%venv\bin\python.exe"
)

if not exist "%PYTHON_EXE%" (
    echo [*] Виртуальное окружение не найдено — создаю...
    %PYTHON_CMD% -m venv "%SCRIPT_DIR%venv"
    
    :: Проверяем снова после создания
    if not exist "%SCRIPT_DIR%venv\Scripts\python.exe" (
        set "PYTHON_EXE=%SCRIPT_DIR%venv\bin\python.exe"
    ) else (
        set "PYTHON_EXE=%SCRIPT_DIR%venv\Scripts\python.exe"
    )
    echo [+] venv создан
)

:: 4. Установка зависимостей
if exist "%SCRIPT_DIR%requirements.txt" (
    echo [*] Устанавливаю зависимости...
    "%PYTHON_EXE%" -m pip install --upgrade pip -q 2>nul
    "%PYTHON_EXE%" -m pip install -r "%SCRIPT_DIR%requirements.txt" -q 2>nul
    echo [+] Зависимости готовы
)

echo.
echo [+] Всё готово
echo [^>] Запускаю arqParse GUI...
echo ════════════════════════════════════════════════════════
echo.

:: Запуск GUI с полной спецификацией пути
"%PYTHON_EXE%" "%SCRIPT_DIR%main.py" --gui

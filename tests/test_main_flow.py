"""Тесты сценариев запуска из main.py."""

import os
import sys

import pytest

# Добавляем корень проекта в sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import main


@pytest.fixture
def mute_ui(monkeypatch):
    """Отключает печать UI в тестах, чтобы не засорять вывод."""
    for fn_name in (
        "print_banner",
        "print_logo",
        "print_header",
        "print_subheader",
        "print_success",
        "print_error",
        "print_warning",
        "print_info",
        "print_summary",
    ):
        monkeypatch.setattr(main, fn_name, lambda *args, **kwargs: None)


def test_main_exits_when_all_downloads_failed(monkeypatch, mute_ui):
    """Если ничего не скачано и ничего не актуально — программа завершается с ошибкой."""
    monkeypatch.setattr(
        main,
        "download_all_tasks",
        lambda *args, **kwargs: {"downloaded": [], "skipped": [], "failed": ["Base VPN: 22.txt"]},
    )

    with pytest.raises(SystemExit, match="1"):
        main.main(skip_xray=True, no_ui=True)


def test_main_accepts_skipped_downloads(monkeypatch, mute_ui, tmp_path):
    """Актуальные (skipped) файлы считаются валидным сценарием и не приводят к KeyError."""
    monkeypatch.setattr(
        main,
        "download_all_tasks",
        lambda *args, **kwargs: {"downloaded": [], "skipped": ["Base VPN: 22.txt"], "failed": []},
    )
    monkeypatch.setattr(main, "ensure_xray", lambda: None)
    monkeypatch.setattr(main, "prompt_and_push_to_github", lambda: None)
    monkeypatch.setattr(main, "stage_test_task", lambda *args, **kwargs: [])

    temp_results = tmp_path / "results"
    monkeypatch.setattr(main, "RESULTS_DIR", str(temp_results))
    monkeypatch.setattr(
        main,
        "TASKS",
        [
            {"name": "Base VPN", "out_file": str(temp_results / "top_base_vpn.txt"), "max_ping_ms": 100, "required_count": 1},
            {"name": "Bypass VPN", "out_file": str(temp_results / "top_bypass_vpn.txt"), "max_ping_ms": 100, "required_count": 1},
        ],
    )

    main.main(skip_xray=True, no_ui=True)


"""Kivy/KivyMD GUI для arqParse.

Цели:
- кроссплатформенный интерфейс (Windows/Linux/macOS/Android/iOS);
- Material 3 визуальный стиль с закруглениями;
- плавные анимации появления экранов и карточек.
"""

from __future__ import annotations

import os
import threading
import traceback
from typing import Dict, List

# Важно: отключаем парсер аргументов Kivy, иначе флаг `--gui`
# (который обрабатывается нашим argparse в main.py) вызывает ошибку
# "option --gui not recognized" на старте приложения.
os.environ.setdefault("KIVY_NO_ARGS", "1")

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.lang import Builder
from kivy.uix.screenmanager import FadeTransition, ScreenManager

from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRaisedButton
from kivymd.uix.label import MDLabel
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.snackbar import Snackbar

import auth as auth_module
from config import RESULTS_DIR, XRAY_BIN
from downloader import download_all_tasks
from parser import read_configs_from_file, read_mtproto_from_file
from settings_manager import get_tasks, load_settings, save_settings
from testers import test_xray_configs
from testers_mtproto import test_mtproto_configs

KV = r'''
#:import dp kivy.metrics.dp

<RootWidget>:
    ScreenManager:
        id: screen_manager
        transition: FadeTransition(duration=0.18)

        MDScreen:
            name: "login"
            md_bg_color: app.theme_cls.backgroundColor
            MDBoxLayout:
                orientation: "vertical"
                padding: dp(20)
                spacing: dp(16)

                Widget:

                MDCard:
                    radius: [22, 22, 22, 22]
                    padding: dp(20)
                    elevation: 2
                    md_bg_color: app.card_color
                    orientation: "vertical"
                    spacing: dp(14)
                    size_hint_y: None
                    height: self.minimum_height

                    MDLabel:
                        text: "arqParse"
                        halign: "center"
                        bold: True
                        font_style: "Headline"
                    MDLabel:
                        text: "Тестирование VPN конфигов"
                        halign: "center"
                        theme_text_color: "Secondary"

                    MDTextField:
                        id: login_user
                        hint_text: "Логин"
                        mode: "outlined"
                        radius: [16, 16, 16, 16]

                    MDTextField:
                        id: login_pass
                        hint_text: "Пароль"
                        mode: "outlined"
                        password: True
                        radius: [16, 16, 16, 16]

                    MDBoxLayout:
                        adaptive_height: True
                        spacing: dp(12)
                        MDCheckbox:
                            id: mode_register
                            size_hint: None, None
                            size: dp(32), dp(32)
                            on_active: app.toggle_auth_mode("register", self.active)
                        MDLabel:
                            text: "Режим регистрации"
                            valign: "middle"

                    MDRaisedButton:
                        id: auth_btn
                        text: "Войти"
                        pos_hint: {"center_x": .5}
                        on_release: app.do_auth()

                Widget:

        MDScreen:
            name: "main"
            md_bg_color: app.theme_cls.backgroundColor
            MDBoxLayout:
                orientation: "vertical"

                MDTopAppBar:
                    title: "arqParse"
                    left_action_items: [["home", lambda x: app.switch_screen("main")]]
                    right_action_items: [["cog", lambda x: app.switch_screen("settings")], ["logout", lambda x: app.logout()]]

                MDBoxLayout:
                    orientation: "vertical"
                    padding: dp(14)
                    spacing: dp(12)

                    MDCard:
                        radius: [18, 18, 18, 18]
                        padding: dp(14)
                        md_bg_color: app.card_color
                        orientation: "vertical"
                        size_hint_y: None
                        height: self.minimum_height
                        spacing: dp(8)

                        MDLabel:
                            text: "Подписка"
                            bold: True
                        MDLabel:
                            id: sub_url_label
                            text: "Ссылка появится после входа"
                            theme_text_color: "Secondary"
                            shorten: True
                            shorten_from: "right"
                        MDRaisedButton:
                            text: "Скопировать ссылку"
                            on_release: app.copy_subscription_url()

                    MDCard:
                        radius: [18, 18, 18, 18]
                        padding: dp(14)
                        md_bg_color: app.card_color
                        orientation: "vertical"
                        size_hint_y: None
                        height: self.minimum_height
                        spacing: dp(10)

                        MDLabel:
                            text: "Действия"
                            bold: True

                        MDBoxLayout:
                            adaptive_height: True
                            spacing: dp(10)
                            MDRaisedButton:
                                text: "Скачать"
                                on_release: app.start_download()
                            MDRaisedButton:
                                text: "Полный тест"
                                on_release: app.start_full_test()
                            MDRaisedButton:
                                text: "Стоп"
                                on_release: app.stop_operation()

                        MDProgressBar:
                            id: progress
                            value: 0

                    MDCard:
                        radius: [18, 18, 18, 18]
                        padding: dp(12)
                        md_bg_color: app.card_color
                        orientation: "vertical"
                        size_hint_y: None
                        height: dp(160)

                        MDLabel:
                            text: "Лог"
                            bold: True
                            size_hint_y: None
                            height: self.texture_size[1]

                        ScrollView:
                            do_scroll_x: False
                            bar_width: dp(5)
                            MDLabel:
                                id: log_label
                                text: "Готово к запуску"
                                adaptive_height: True
                                theme_text_color: "Secondary"
                                text_size: self.width, None

        MDScreen:
            name: "settings"
            md_bg_color: app.theme_cls.backgroundColor
            MDBoxLayout:
                orientation: "vertical"

                MDTopAppBar:
                    title: "Настройки"
                    left_action_items: [["arrow-left", lambda x: app.switch_screen("main")]]

                ScrollView:
                    do_scroll_x: False
                    MDBoxLayout:
                        id: settings_root
                        orientation: "vertical"
                        spacing: dp(12)
                        padding: dp(14)
                        adaptive_height: True

                        MDCard:
                            radius: [18, 18, 18, 18]
                            padding: dp(14)
                            md_bg_color: app.card_color
                            orientation: "vertical"
                            adaptive_height: True
                            spacing: dp(10)

                            MDLabel:
                                text: "Общие"
                                bold: True

                            MDTextField:
                                id: user_agent
                                hint_text: "User-Agent"
                                mode: "outlined"
                                radius: [16, 16, 16, 16]

                            MDRaisedButton:
                                text: "Сохранить настройки"
                                on_release: app.save_settings_from_ui()

                        MDCard:
                            radius: [18, 18, 18, 18]
                            padding: dp(14)
                            md_bg_color: app.card_color
                            orientation: "vertical"
                            adaptive_height: True
                            spacing: dp(8)
                            MDLabel:
                                text: "Задачи для теста"
                                bold: True
                            MDBoxLayout:
                                id: tasks_box
                                orientation: "vertical"
                                adaptive_height: True
                                spacing: dp(8)
'''


class RootWidget(MDBoxLayout):
    """Корневой виджет приложения."""


class KivyGUIApp(MDApp):
    def build(self):
        self.title = "arqParse"
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "DeepPurple"
        # Material 3 тема (доступно в актуальных KivyMD сборках).
        try:
            self.theme_cls.material_style = "M3"
        except Exception:
            pass

        self.card_color = (0.10, 0.10, 0.12, 1)
        self._is_running = False
        self._stop_event = threading.Event()
        self._task_checks: Dict[str, MDCheckbox] = {}

        root = Builder.load_string(KV)
        self.root = root
        self._load_initial_state()
        return root

    def on_start(self):
        self.switch_screen("login" if not auth_module.is_logged_in() else "main")
        self._animate_cards()

    def _load_initial_state(self):
        settings = load_settings()
        self.tasks = get_tasks()

        self.root.ids.user_agent.text = settings.get("user_agent", "")
        self._render_task_toggles()

        if auth_module.is_logged_in():
            self._refresh_sub_url()

    def _render_task_toggles(self):
        box = self.root.ids.tasks_box
        box.clear_widgets()
        self._task_checks.clear()

        for task in self.tasks:
            row = MDBoxLayout(adaptive_height=True, spacing=10)
            check = MDCheckbox(active=True)
            self._task_checks[task["name"]] = check
            row.add_widget(check)
            row.add_widget(MDLabel(text=f"{task['name']} ({task['type']})"))
            box.add_widget(row)

    def _animate_cards(self):
        manager: ScreenManager = self.root.ids.screen_manager
        screen = manager.current_screen
        for child in screen.walk(restrict=True):
            if isinstance(child, MDRaisedButton):
                anim = Animation(opacity=1, d=0.15)
                child.opacity = 0
                anim.start(child)

    def switch_screen(self, name: str):
        self.root.ids.screen_manager.current = name
        Clock.schedule_once(lambda *_: self._animate_cards(), 0)

    def toggle_auth_mode(self, mode: str, active: bool):
        if not active:
            return
        self.root.ids.auth_btn.text = "Зарегистрироваться" if mode == "register" else "Войти"

    def do_auth(self):
        username = self.root.ids.login_user.text.strip()
        password = self.root.ids.login_pass.text
        is_register = self.root.ids.mode_register.active

        if len(username) < 3:
            self._toast("Логин минимум 3 символа")
            return
        if len(password) < 6:
            self._toast("Пароль минимум 6 символов")
            return

        self.root.ids.auth_btn.disabled = True
        self.root.ids.auth_btn.text = "Подключение..."

        def worker():
            try:
                if is_register:
                    auth_module.register(username, password)
                else:
                    auth_module.login(username, password)
                Clock.schedule_once(lambda *_: self._on_auth_ok(), 0)
            except Exception as exc:
                Clock.schedule_once(lambda *_: self._on_auth_fail(str(exc)), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _on_auth_ok(self):
        self.root.ids.auth_btn.disabled = False
        self.root.ids.auth_btn.text = "Войти"
        self._refresh_sub_url()
        self.switch_screen("main")
        self._toast("Успешный вход")

    def _on_auth_fail(self, message: str):
        self.root.ids.auth_btn.disabled = False
        self.root.ids.auth_btn.text = "Войти"
        self._toast(f"Ошибка авторизации: {message}")

    def _refresh_sub_url(self):
        try:
            self.root.ids.sub_url_label.text = auth_module.get_sub_url()
        except Exception:
            self.root.ids.sub_url_label.text = "Ссылка недоступна"

    def copy_subscription_url(self):
        text = self.root.ids.sub_url_label.text
        Clipboard.copy(text)
        self._toast("Ссылка скопирована")

    def save_settings_from_ui(self):
        data = load_settings()
        data["user_agent"] = self.root.ids.user_agent.text.strip()
        save_settings(data)
        self._toast("Настройки сохранены")

    def logout(self):
        auth_module.clear_session()
        self.switch_screen("login")
        self._toast("Вы вышли из аккаунта")

    def start_download(self):
        if self._is_running:
            self._toast("Операция уже выполняется")
            return

        self._is_running = True
        self._stop_event.clear()
        self._log("Старт скачивания конфигов")

        def worker():
            try:
                results = download_all_tasks(self.tasks, max_age_hours=24, force=True, log_func=self._threadsafe_log)
                self._threadsafe_log(f"Скачано: {len(results['downloaded'])}", "success")
                if results["failed"]:
                    self._threadsafe_log(f"Ошибок: {len(results['failed'])}", "error")
            except Exception:
                self._threadsafe_log(traceback.format_exc(), "error")
            finally:
                Clock.schedule_once(lambda *_: self._finish_operation(), 0)

        threading.Thread(target=worker, daemon=True).start()

    def start_full_test(self):
        if self._is_running:
            self._toast("Операция уже выполняется")
            return

        selected = [t for t in self.tasks if self._task_checks.get(t["name"]) and self._task_checks[t["name"]].active]
        if not selected:
            self._toast("Выберите хотя бы одну задачу")
            return

        self._is_running = True
        self._stop_event.clear()
        self._set_progress(0)
        self._log(f"Запуск полного теста: {len(selected)} задач")

        def worker():
            total = len(selected)
            for idx, task in enumerate(selected, 1):
                if self._stop_event.is_set():
                    break
                self._threadsafe_log(f"[{idx}/{total}] {task['name']}")
                self._test_single_task(task)
                Clock.schedule_once(lambda *_v, p=(idx / total) * 100: self._set_progress(p), 0)

            Clock.schedule_once(lambda *_: self._finish_operation(), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _test_single_task(self, task: dict):
        if task["type"] == "xray":
            all_configs: List[str] = []
            for raw_file in task.get("raw_files", []):
                if os.path.exists(raw_file):
                    all_configs.extend(read_configs_from_file(raw_file))

            if not all_configs:
                self._threadsafe_log(f"{task['name']}: нет конфигов", "warning")
                return

            working, passed, failed = test_xray_configs(
                configs=all_configs,
                target_url=task["target_url"],
                max_ping_ms=task["max_ping_ms"],
                required_count=task["required_count"],
                xray_path=XRAY_BIN,
                out_file=task["out_file"],
                profile_title=task.get("profile_title"),
                config_type=task.get("type"),
                log_func=self._threadsafe_log,
                progress_func=self._threadsafe_progress,
                stop_flag=self._stop_event,
            )
            self._threadsafe_log(
                f"{task['name']}: working={working}, passed={passed}, failed={failed}",
                "success",
            )
            return

        all_configs = []
        for raw_file in task.get("raw_files", []):
            if os.path.exists(raw_file):
                all_configs.extend(read_mtproto_from_file(raw_file))

        if not all_configs:
            self._threadsafe_log(f"{task['name']}: нет MTProto прокси", "warning")
            return

        working, passed, failed = test_mtproto_configs(
            configs=all_configs,
            max_ping_ms=task["max_ping_ms"],
            required_count=task["required_count"],
            out_file=task["out_file"],
            profile_title=task.get("profile_title"),
            log_func=self._threadsafe_log,
            progress_func=lambda cur, total: self._threadsafe_progress(cur, total, 0, 0),
            stop_flag=self._stop_event,
        )
        self._threadsafe_log(
            f"{task['name']}: working={working}, passed={passed}, failed={failed}",
            "success",
        )

    def stop_operation(self):
        self._stop_event.set()
        self._log("Остановка запрошена", "warning")

    def _finish_operation(self):
        self._is_running = False
        self._set_progress(100)
        self._toast("Операция завершена")

    def _set_progress(self, value: float):
        self.root.ids.progress.value = max(0, min(100, value))

    def _threadsafe_progress(self, current: int, total: int, *_):
        if total <= 0:
            return
        pct = (current / total) * 100
        Clock.schedule_once(lambda *_: self._set_progress(pct), 0)

    def _threadsafe_log(self, message: str, tag: str = "info"):
        Clock.schedule_once(lambda *_: self._log(message, tag), 0)

    def _log(self, message: str, tag: str = "info"):
        prefix = {
            "success": "✅",
            "warning": "⚠️",
            "error": "❌",
            "info": "ℹ️",
        }.get(tag, "ℹ️")
        existing = self.root.ids.log_label.text
        self.root.ids.log_label.text = f"{existing}\n{prefix} {message}"[-5000:]

    def _toast(self, text: str):
        try:
            Snackbar(text=text, duration=2).open()
        except Exception:
            self._log(text, "info")


def main():
    KivyGUIApp().run()


if __name__ == "__main__":
    main()

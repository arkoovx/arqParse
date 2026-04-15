"""Kivy/KivyMD GUI для arqParse — Material 3, кроссплатформенный."""

from __future__ import annotations

import os
import threading
import webbrowser
from typing import Dict, List

# Отключаем mtdev и probesysfs до инициализации Kivy (требуют прав на /dev/input/event*)
# Используем только SDL2 — работает без root-прав
os.environ.setdefault("KIVY_INPUT_PROVIDERS", "sdl2")
os.environ.setdefault("KIVY_NO_ARGS", "1")
# Фикс: переопределяем дефолтный конфиг Kivy на лету
import kivy.config
kivy.config.Config.set("input", "mouse", "mouse")
# Удаляем probesysfs — именно он сканирует /dev/input/event* и грузит mtdev
for key in list(kivy.config.Config.options("input")):
    if "probesysfs" in kivy.config.Config.get("input", key):
        kivy.config.Config.remove_option("input", key)
kivy.config.Config.write()  # сохраняем исправленный конфиг

from kivy.core.window import Window
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.graphics import Color, RoundedRectangle
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.screenmanager import FadeTransition, ScreenManager

from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton


def _mk_btn(text, on_release=None, bg_color=None, text_color=None):
    """Создаёт MDButton (KivyMD 2.x стиль)."""
    btn = MDButton()
    if bg_color:
        btn.md_bg_color = bg_color
    btn.add_widget(MDButtonText(text=text, text_color=text_color or (1, 1, 1, 1)))
    if on_release:
        btn.bind(on_release=on_release)
    return btn


def _set_btn_text(btn, text):
    """Устанавливает текст MDButton (ищет MDButtonText среди детей)."""
    for c in btn.children:
        if isinstance(c, MDButtonText):
            c.text = text
            return


from kivymd.uix.label import MDLabel
from kivymd.uix.progressindicator import MDLinearProgressIndicator
from kivymd.uix.screen import MDScreen
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.textfield import MDTextField
from kivymd.uix.selectioncontrol import MDSwitch, MDCheckbox

from kivy.factory import Factory
from kivy.uix.behaviors import ButtonBehavior


class ClickableLabel(ButtonBehavior, MDLabel):
    """Лейбл, который можно нажать."""
    pass


class NoAnimBtn(ButtonBehavior, MDBoxLayout):
    """Кнопка без анимации при клике."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.height = dp(32)

        self._text = kwargs.get("text", "")
        self._label = MDLabel(
            text=self._text,
            halign="center",
            valign="middle",
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
            font_size=dp(13),
            size_hint=(1, 1)
        )
        self.add_widget(self._label)

        with self.canvas.before:
            Color(0.25, 0.15, 0.5, 1)
            self._bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[7])
            Color(0.35, 0.2, 0.65, 1)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[7])

        self.bind(pos=self._upd_rect, size=self._upd_rect)

    def _upd_rect(self, *args):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size
        self._rect.pos = self.pos
        self._rect.size = self.size

    def _get_text(self):
        return self._label.text

    def _set_text(self, v):
        self._label.text = v

    text = property(_get_text, _set_text)


class TypeBtnButton(ButtonBehavior, MDBoxLayout):
    """Кнопка типа (xray/mtproto) с динамическим цветом."""
    ACCENT = (0.545, 0.361, 0.965, 1)
    INACTIVE_BG = (0.12, 0.12, 0.14, 1)
    ACTIVE_TEXT = (1, 1, 1, 1)
    INACTIVE_TEXT = (0.322, 0.322, 0.357, 1)

    def __init__(self, btn_type="xray", is_active=False, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint_x = None
        self.width = dp(80)
        self.size_hint_y = None
        self.height = dp(28)
        self._type_val = btn_type

        self._label = MDLabel(
            text="Xray" if btn_type == "xray" else "MTProto",
            halign="center",
            valign="middle",
            theme_text_color="Custom",
            text_color=self.ACTIVE_TEXT if is_active else self.INACTIVE_TEXT,
            font_size=dp(13),
            size_hint=(1, 1)
        )
        self.add_widget(self._label)

        bg = self.ACCENT if is_active else self.INACTIVE_BG
        with self.canvas.before:
            self._color_instr = Color(bg[0], bg[1], bg[2], bg[3])
            self._bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[7])

        self.bind(pos=self._upd_rect, size=self._upd_rect)

    def _upd_rect(self, *args):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size

    def _set_active(self, is_active):
        color = self.ACCENT if is_active else self.INACTIVE_BG
        self._color_instr.rgba = color
        self._label.text_color = self.ACTIVE_TEXT if is_active else self.INACTIVE_TEXT


class AuthTabButton(ButtonBehavior, MDBoxLayout):
    """Кнопка таба авторизации (Вход/Регистрация) с динамическим цветом."""
    tab_type = StringProperty("login")
    
    ACCENT = (0.545, 0.361, 0.965, 1)
    INACTIVE_BG = (0, 0, 0, 0)
    ACTIVE_TEXT = (1, 1, 1, 1)
    INACTIVE_TEXT = (0.443, 0.443, 0.478, 1)  # c_dim
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint_x = 0.5
        self.size_hint_y = None
        self.height = dp(36)
        self._label = None
        self._is_active = True  # По умолчанию активна

        with self.canvas.before:
            self._color_instr = Color(*self.ACCENT)
            self._bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[7])

        self.bind(pos=self._upd_rect, size=self._upd_rect, tab_type=self._on_tab_type_changed)
        # Создаём label после bind
        self._create_label()

    def _create_label(self):
        """Создаёт MDLabel."""
        if self._label is not None:
            return
        self._label = MDLabel(
            text="Вход" if self.tab_type == "login" else "Регистрация",
            halign="center",
            valign="middle",
            theme_text_color="Custom",
            text_color=self.ACTIVE_TEXT,
            font_size=dp(15),
            size_hint=(1, 1),
        )
        self.add_widget(self._label)
    
    def _on_tab_type_changed(self, *args):
        """Обновляет текст при изменении tab_type."""
        if self._label is not None:
            self._label.text = "Вход" if self.tab_type == "login" else "Регистрация"

    def _upd_rect(self, *args):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size

    def _set_active(self, is_active):
        self._is_active = is_active
        color = self.ACCENT if is_active else self.INACTIVE_BG
        self._color_instr.rgba = color
        self._label.text_color = self.ACTIVE_TEXT if is_active else self.INACTIVE_TEXT


class AuthMainButton(ButtonBehavior, MDBoxLayout):
    """Главная кнопка авторизации (Войти/Зарегистрироваться) с фиксированным размером."""
    ACCENT = (0.545, 0.361, 0.965, 1)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint_x = None
        self.width = dp(200)
        self.size_hint_y = None
        self.height = dp(44)

        self._label = MDLabel(
            text="Войти",
            halign="center",
            valign="middle",
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
            font_size=dp(16),
            size_hint=(1, 1),
        )
        self.add_widget(self._label)

        with self.canvas.before:
            self._color_instr = Color(*self.ACCENT)
            self._bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[10])

        self.bind(pos=self._upd_rect, size=self._upd_rect)
        self._anim = None

    def _upd_rect(self, *args):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size
    
    def set_text(self, text: str):
        """Плавно меняет текст с анимацией затухания/появления."""
        if self._anim:
            self._anim.cancel(self._label)
        
        # Анимация затухания
        self._anim = Animation(text_color=(0.3, 0.3, 0.3, 0), duration=0.15)
        self._anim.bind(on_complete=lambda *_: self._show_new_text(text))
        self._anim.start(self._label)
    
    def _show_new_text(self, text):
        """Устанавливает новый текст и анимирует появление."""
        self._label.text = text
        # Анимация появления
        self._anim = Animation(text_color=(1, 1, 1, 1), duration=0.15)
        self._anim.start(self._label)


from kivy.factory import Factory
Factory.register("ClickableLabel", cls=ClickableLabel)
Factory.register("NoAnimBtn", cls=NoAnimBtn)
Factory.register("TypeBtnButton", cls=TypeBtnButton)
Factory.register("AuthTabButton", cls=AuthTabButton)
Factory.register("AuthMainButton", cls=AuthMainButton)

import auth as auth_module
from config import RESULTS_DIR, XRAY_BIN
from downloader import download_all_tasks
from parser import read_configs_from_file, read_mtproto_from_file
from settings_manager import get_tasks, load_settings, save_settings, reset_to_defaults
from setup_xray import ensure_xray
from testers import test_xray_configs
from testers_mtproto import test_mtproto_configs

ACCENT = "#8b5cf6"
TEXT = "#e4e4e7"
TEXT_DIM = "#71717a"
TEXT_MUTED = "#52525b"
GREEN = "#22c55e"
YELLOW = "#facc15"
RED = "#ef4444"
CARD_BG = (0.086, 0.086, 0.094, 1)
BG = (0.05, 0.05, 0.05, 1)


def _hex_to_rgba(hex_color: str, alpha: float = 1.0) -> tuple:
    """Конвертирует hex цвет в RGBA кортеж."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4)) + (alpha,)

KV = r'''
#:import dp kivy.metrics.dp

<ClickableLabel>:
    size_hint_y: None
    height: dp(24)

<ThemedCard@MDBoxLayout>:
    orientation: "vertical"
    size_hint_y: None
    adaptive_height: True
    spacing: dp(8)
    padding: [dp(12), dp(10)]
    canvas.before:
        Color:
            rgba: app.c_card
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [14, 14, 14, 14]


<HeaderBar@MDBoxLayout>:
    orientation: "horizontal"
    size_hint_y: None
    height: dp(48)
    padding: [dp(12), dp(6)]
    spacing: dp(8)
    canvas.before:
        Color:
            rgba: app.c_bg
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [0]

    MDLabel:
        id: header_title
        text: "arqParse"
        bold: True
        theme_text_color: "Custom"
        text_color: app.c_text
        size_hint_x: 1

    MDIconButton:
        icon: "cog-outline"
        user_font_size: dp(22)
        theme_text_color: "Custom"
        text_color: app.c_dim
        size_hint: None, None
        size: dp(36), dp(36)
        on_release: app.switch_screen("settings")

    MDIconButton:
        icon: "logout-variant"
        user_font_size: dp(22)
        theme_text_color: "Custom"
        text_color: app.c_dim
        size_hint: None, None
        size: dp(36), dp(36)
        on_release: app.logout()

<SettingsHeader@MDBoxLayout>:
    orientation: "horizontal"
    size_hint_y: None
    height: dp(48)
    padding: [dp(12), dp(6)]
    spacing: dp(8)
    canvas.before:
        Color:
            rgba: app.c_bg
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [0]

    MDIconButton:
        icon: "arrow-left"
        user_font_size: dp(22)
        theme_text_color: "Custom"
        text_color: app.c_dim
        size_hint: None, None
        size: dp(36), dp(36)
        on_release: app.switch_screen("main")

    MDLabel:
        id: settings_header_title
        text: "Настройки"
        bold: True
        theme_text_color: "Custom"
        text_color: app.c_text
        size_hint_x: 1

<RootWidget>:
    orientation: "vertical"

    ScreenManager:
        id: sm

        MDScreen:
            name: "login"

            MDBoxLayout:
                orientation: "vertical"
                padding: dp(24)
                spacing: dp(16)

                Widget:

                MDLabel:
                    text: "arqParse"
                    halign: "center"
                    font_size: dp(32)
                    bold: True
                    theme_text_color: "Custom"
                    text_color: app.c_text
                    size_hint_y: None
                    height: dp(40)

                MDLabel:
                    text: "Тестирование VPN конфигов"
                    halign: "center"
                    theme_text_color: "Secondary"
                    size_hint_y: None
                    height: dp(24)

                Widget:
                    size_hint_y: None
                    height: dp(20)

                ThemedCard:
                    spacing: dp(8)

                    MDLabel:
                        text: "Логин"
                        theme_text_color: "Hint"
                        size_hint_y: None
                        height: dp(18)

                    MDTextField:
                        id: login_user
                        size_hint_y: None
                        height: dp(44)

                    MDLabel:
                        text: "Пароль"
                        theme_text_color: "Hint"
                        size_hint_y: None
                        height: dp(18)

                    MDTextField:
                        id: login_pass
                        password: True
                        size_hint_y: None
                        height: dp(44)
                        on_text_validate: app.do_auth()

                    MDBoxLayout:
                        orientation: "horizontal"
                        size_hint_y: None
                        height: dp(36)
                        padding: 0
                        spacing: dp(2)

                        AuthTabButton:
                            id: tab_login
                            tab_type: "login"
                            on_release: app.set_auth_mode("login")

                        AuthTabButton:
                            id: tab_register
                            tab_type: "register"
                            on_release: app.set_auth_mode("register")

                    AuthMainButton:
                        id: auth_btn
                        pos_hint: {"center_x": 0.5}
                        on_release: app.do_auth()

                Widget:

                MDBoxLayout:
                    orientation: "horizontal"
                    size_hint_y: None
                    height: dp(24)
                    padding: [0, 0, 0, 0]

                    Widget:

                    MDLabel:
                        text: "by "
                        theme_text_color: "Hint"
                        size_hint_x: None
                        width: dp(20)

                    ClickableLabel:
                        id: arq_link_label
                        text: "arq"
                        theme_text_color: "Custom"
                        text_color: app.c_accent
                        bold: True
                        size_hint_x: None
                        width: dp(30)
                        on_release: app.open_channel_link()

                    Widget:

                Widget:

        MDScreen:
            name: "main"

            MDBoxLayout:
                orientation: "vertical"

                HeaderBar:

                MDScrollView:
                    do_scroll_x: False
                    bar_width: dp(4)

                    MDBoxLayout:
                        id: main_content
                        orientation: "vertical"
                        padding: [dp(14), dp(12)]
                        spacing: dp(12)
                        adaptive_height: True

                        ThemedCard:
                            id: sub_card
                            spacing: dp(6)

                            MDLabel:
                                text: "Подписка"
                                bold: True
                                theme_text_color: "Primary"
                                size_hint_y: None
                                height: dp(20)

                            MDLabel:
                                id: sub_url_label
                                text: "Ссылка появится после входа"
                                theme_text_color: "Secondary"
                                shorten: True
                                shorten_from: "right"
                                size_hint_y: None
                                height: dp(16)

                            MDButton:
                                md_bg_color: (0, 0, 0, 0)
                                on_release: app.copy_subscription_url()

                                MDButtonText:
                                    text: "Скопировать ссылку"
                                    text_color: app.c_dim

                        MDBoxLayout:
                            id: bot_link_container
                            orientation: "horizontal"
                            size_hint_y: None
                            height: dp(24)
                            spacing: dp(2)

                            MDLabel:
                                text: "Применить тг прокси можно в боте "
                                theme_text_color: "Hint"
                                size_hint_x: None
                                adaptive_width: True

                            ClickableLabel:
                                id: bot_link_label
                                text: "@arqvpn_bot"
                                theme_text_color: "Custom"
                                text_color: app.c_accent
                                bold: True
                                size_hint_x: None
                                adaptive_width: True
                                on_release: app.open_bot_link()

                        MDButton:
                            id: start_btn
                            size_hint_x: 0.85
                            pos_hint: {"center_x": 0.5}
                            height: dp(56)
                            font_size: dp(18)
                            md_bg_color: app.c_accent
                            on_release: app.start_full_test()

                            MDButtonText:
                                text: "Начать тест"
                                text_color: 1, 1, 1, 1

                        NoAnimBtn:
                            id: adv_btn
                            text: "Дополнительные настройки"
                            size_hint_x: 0.85
                            pos_hint: {"center_x": 0.5}
                            height: dp(32)
                            on_release: app.toggle_advanced()

                        ThemedCard:
                            id: adv_container
                            spacing: dp(8)

                            MDLabel:
                                text: "Выбрать задачи"
                                theme_text_color: "Secondary"
                                size_hint_y: None
                                height: dp(18)

                            MDBoxLayout:
                                id: task_checkboxes
                                orientation: "vertical"
                                adaptive_height: True
                                spacing: dp(2)

                            MDBoxLayout:
                                orientation: "horizontal"
                                adaptive_height: True
                                spacing: dp(6)
                                size_hint_y: None
                                height: dp(38)

                                MDButton:
                                    md_bg_color: (0, 0, 0, 0)
                                    on_release: app.start_download()

                                    MDButtonText:
                                        text: "Скачать"
                                        text_color: app.c_dim

                                MDButton:
                                    md_bg_color: (0, 0, 0, 0)
                                    on_release: app.open_results()

                                    MDButtonText:
                                        text: "Результаты"
                                        text_color: app.c_dim

                        MDBoxLayout:
                            orientation: "horizontal"
                            size_hint_y: None
                            height: dp(38)
                            spacing: dp(8)

                            MDButton:
                                id: skip_btn
                                disabled: True
                                md_bg_color: (0, 0, 0, 0)
                                on_release: app.skip_file()

                                MDButtonText:
                                    text: "Пропустить"
                                    text_color: app.c_muted

                            MDButton:
                                id: stop_btn
                                disabled: True
                                md_bg_color: (0, 0, 0, 0)
                                on_release: app.stop_operation()

                                MDButtonText:
                                    text: "Остановить"
                                    text_color: app.c_muted

                        ThemedCard:
                            spacing: dp(4)

                            MDBoxLayout:
                                orientation: "horizontal"
                                adaptive_height: True
                                size_hint_y: None
                                height: dp(22)

                                MDLabel:
                                    text: "Прогресс:"
                                    theme_text_color: "Secondary"
                                    adaptive_width: True

                                MDLabel:
                                    id: progress_label
                                    text: "Готов к работе"
                                    theme_text_color: "Secondary"
                                    halign: "right"

                            MDLinearProgressIndicator:
                                id: progress
                                value: 0
                                max: 1.0
                                size_hint_y: None
                                height: dp(4)

                        ThemedCard:
                            spacing: dp(4)

                            MDBoxLayout:
                                orientation: "horizontal"
                                adaptive_height: True
                                size_hint_y: None
                                height: dp(22)

                                MDLabel:
                                    text: "Журнал событий"
                                    bold: True
                                    theme_text_color: "Secondary"

                                Widget:

                                MDIconButton:
                                    icon: "broom"
                                    user_font_size: dp(16)
                                    theme_text_color: "Custom"
                                    text_color: app.c_muted
                                    size_hint: None, None
                                    size: dp(24), dp(24)
                                    on_release: app.clear_log()

                            MDScrollView:
                                id: log_scroll
                                do_scroll_x: False
                                size_hint_y: None
                                height: dp(140)

                                MDLabel:
                                    id: log_label
                                    text: "> arqParse запущен"
                                    theme_text_color: "Custom"
                                    text_color: app.c_text
                                    size_hint_y: None
                                    adaptive_height: True

                        Widget:
                            size_hint_y: None
                            height: dp(16)

        MDScreen:
            name: "settings"

            MDBoxLayout:
                orientation: "vertical"

                SettingsHeader:

                MDScrollView:
                    do_scroll_x: False
                    bar_width: dp(4)

                    MDBoxLayout:
                        id: settings_content
                        orientation: "vertical"
                        padding: [dp(14), dp(12)]
                        spacing: dp(12)
                        adaptive_height: True

                        ThemedCard:
                            spacing: dp(10)

                            MDLabel:
                                text: "Общие"
                                bold: True
                                theme_text_color: "Primary"
                                size_hint_y: None
                                height: dp(20)

                            MDTextField:
                                id: user_agent
                                hint_text: "User-Agent"
                                size_hint_y: None
                                height: dp(44)
                                font_size: dp(14)

                            MDButton:
                                md_bg_color: app.c_accent
                                on_release: app.save_settings_from_ui()

                                MDButtonText:
                                    text: "Сохранить"
                                    text_color: 1, 1, 1, 1

                            MDButton:
                                md_bg_color: (0, 0, 0, 0)
                                on_release: app.reset_settings_to_defaults()

                                MDButtonText:
                                    text: "Восстановить по умолчанию"
                                    text_color: app.c_dim

                        MDLabel:
                            text: "Категории"
                            bold: True
                            theme_text_color: "Custom"
                            text_color: app.c_accent
                            size_hint_y: None
                            height: dp(22)

                        MDBoxLayout:
                            id: categories_box
                            orientation: "vertical"
                            spacing: dp(10)
                            adaptive_height: True

                        MDButton:
                            size_hint_y: None
                            height: dp(32)
                            md_bg_color: (0, 0, 0, 0)
                            on_release: app.add_category()

                            MDButtonText:
                                text: "+ Добавить категорию"
                                text_color: app.c_accent

                        Widget:
                            size_hint_y: None
                            height: dp(16)
'''


class RootWidget(MDBoxLayout):
    pass


class KivyGUIApp(MDApp):
    def build(self):
        self.title = "arqParse"
        # Формат 9:16 — 420x800
        Window.size = (420, 800)
        Window.resizable = True
        self.theme_cls.theme_style = "Dark"
        try:
            self.theme_cls.material_style = "M3"
        except Exception:
            pass

        self.c_text = (0.894, 0.894, 0.898, 1)
        self.c_accent = (0.545, 0.361, 0.965, 1)
        self.c_dim = (0.443, 0.443, 0.478, 1)
        self.c_muted = (0.322, 0.322, 0.357, 1)
        self.c_card = (0.086, 0.086, 0.094, 1)
        self.c_bg = (0.05, 0.05, 0.05, 1)

        self.advanced_open = False
        self._is_running = False
        self._stop_event = threading.Event()
        self._task_checks: Dict[str, dict] = {}
        self._category_cards: List[dict] = []
        self._loading_active = False
        self._auth_mode = "login"  # "login" or "register"

        Builder.load_string(KV)
        return RootWidget()

    def on_start(self):
        self.root.ids.sm.transition = FadeTransition(duration=0.18)
        self._load_initial_state()
        logged = auth_module.is_logged_in()
        self.switch_screen("login" if not logged else "main")
        if logged:
            self._refresh_sub_url()
        # Инициализация табов авторизации
        self._init_auth_tabs()
        # Hover-эффект для arq (канал)
        arq_lbl = self.root.ids.arq_link_label
        arq_lbl.bind(on_enter=lambda *_: setattr(arq_lbl, 'text_color', (0.75, 0.55, 1, 1)))
        arq_lbl.bind(on_leave=lambda *_: setattr(arq_lbl, 'text_color', self.c_accent))
        # Hover-эффект для @arqvpn_bot
        bot_lbl = self.root.ids.bot_link_label
        bot_lbl.bind(on_enter=lambda *_: setattr(bot_lbl, 'text_color', (0.75, 0.55, 1, 1)))
        bot_lbl.bind(on_leave=lambda *_: setattr(bot_lbl, 'text_color', self.c_accent))

    def _init_auth_tabs(self):
        self.set_auth_mode("login")

    def set_auth_mode(self, mode: str):
        """Переключение между вкладками Вход/Регистрация."""
        self._auth_mode = mode
        tab_login = self.root.ids.tab_login
        tab_register = self.root.ids.tab_register

        if mode == "login":
            tab_login._set_active(True)
            tab_register._set_active(False)
        else:
            tab_register._set_active(True)
            tab_login._set_active(False)

        # Обновляем текст кнопки авторизации
        auth_btn = self.root.ids.auth_btn
        auth_btn.set_text("Войти" if mode == "login" else "Зарегистрироваться")

    def _load_initial_state(self):
        settings = load_settings()
        self.tasks = get_tasks()
        self.root.ids.user_agent.text = settings.get("user_agent", "")
        self._render_task_checkboxes()
        self._render_categories(settings)
        # Убираем adv_container из дерева при старте
        parent = self.root.ids.main_content
        if self.root.ids.adv_container.parent is not None:
            parent.remove_widget(self.root.ids.adv_container)

    def switch_screen(self, name: str):
        sm = self.root.ids.sm
        if sm.current != name:
            sm.current = name

    # ─── Авторизация ───────────────────────────────────────────
    def do_auth(self):
        username = self.root.ids.login_user.text.strip()
        password = self.root.ids.login_pass.text
        is_register = self._auth_mode == "register"

        if len(username) < 3:
            self._toast("Логин минимум 3 символа")
            return
        if len(password) < 6:
            self._toast("Пароль минимум 6 символов")
            return

        btn = self.root.ids.auth_btn
        btn.disabled = True
        self._loading_active = True
        self._loading_dots = 0
        self._loading_text = "Подключение" if not is_register else "Регистрация"
        self._animate_dots(btn)

        def worker():
            err_msg = None
            try:
                server = auth_module.DEFAULT_SERVER
                if not auth_module.check_server(server):
                    err_msg = "Сервер недоступен"
                    return
                if is_register:
                    auth_module.register(username, password, server)
                else:
                    auth_module.login(username, password, server)
                Clock.schedule_once(lambda *_: self._auth_ok(btn), 0)
            except Exception as exc:
                err_msg = str(exc)
            
            if err_msg:
                Clock.schedule_once(lambda *_: self._auth_fail(btn, err_msg), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _animate_dots(self, btn):
        if not self._loading_active:
            return
        dots = "." * (self._loading_dots % 4)
        current_text = "Подключение" if self._auth_mode == "login" else "Регистрация"
        btn.set_text(f"{current_text}{dots}")
        self._loading_dots += 1
        Clock.schedule_once(lambda *_: self._animate_dots(btn), 0.5)

    def _auth_ok(self, btn):
        print(f"[DEBUG] _auth_ok вызван")
        self._loading_active = False
        btn.disabled = False
        btn.set_text("Войти")
        self._refresh_sub_url()
        self.switch_screen("main")
        Clock.schedule_once(lambda *_: self._show_toast("Успешный вход"), 0.3)

    def _auth_fail(self, btn, msg: str):
        print(f"[DEBUG] _auth_fail: {msg}")
        self._loading_active = False
        btn.disabled = False
        # Восстанавливаем текст кнопки в зависимости от режима
        btn.set_text("Войти" if self._auth_mode == "login" else "Зарегистрироваться")

        # Показываем ошибку через Clock в главном потоке
        Clock.schedule_once(lambda *_: self._show_toast(f"Ошибка: {msg}"), 0.1)

    def _show_toast(self, text: str):
        """Показывает toast в главном потоке."""
        try:
            from kivymd.uix.snackbar import Snackbar
            Snackbar(text=text, timeout=3.0).open()
        except ImportError:
            # KivyMD 2.x — другой API
            try:
                from kivymd.uix.snackbar.snackbar import Snackbar
                Snackbar(text=text, timeout=3.0).open()
            except Exception:
                # Fallback — используем простой print
                print(f"[TOAST] {text}")
        except Exception as e:
            print(f"[DEBUG] Ошибка показа toast: {e}")

    def _refresh_sub_url(self):
        try:
            url = auth_module.get_sub_url()
            self.root.ids.sub_url_label.text = url
        except Exception:
            self.root.ids.sub_url_label.text = "Ссылка недоступна"

    def copy_subscription_url(self):
        text = self.root.ids.sub_url_label.text
        if not text or "появится" in text:
            return

        import os
        is_wayland = os.environ.get("XDG_SESSION_TYPE") == "wayland"

        # На Wayland пробуем wl-copy — единственный способ записать в системный буфер
        if is_wayland:
            import subprocess, shutil
            if shutil.which("wl-copy"):
                try:
                    subprocess.run(["wl-copy", "--type", "text/plain"], input=text.encode("utf-8"), timeout=2)
                    self._log("Ссылка скопирована", "success")
                    self._toast("Скопировано")
                    return
                except Exception:
                    pass
            # Нет wl-copy — показываем диалог
            self._show_copy_dialog(text)
            return

        # X11 — tkinter работает
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
            root.destroy()
            self._log("Ссылка скопирована", "success")
            self._toast("Скопировано")
        except Exception as e:
            self._log(f"Ошибка копирования: {e}", "error")
            self._show_copy_dialog(text)

    def _show_copy_dialog(self, text: str):
        """Показать диалог с ссылкой для ручного копирования."""
        from kivymd.uix.dialog import (
            MDDialog,
            MDDialogHeadlineText,
            MDDialogSupportingText,
            MDDialogButtonContainer,
            MDDialogContentContainer,
        )
        from kivy.uix.scrollview import ScrollView
        from kivy.uix.textinput import TextInput
        from kivymd.uix.button import MDButton, MDButtonText

        def _on_close(*_):
            dialog.dismiss()

        scroll = ScrollView(size_hint=(1, None), height=dp(80))
        text_input = TextInput(
            text=text,
            readonly=True,
            size_hint_y=None,
            height=dp(80),
            font_size=dp(12),
            background_color=(0.1, 0.1, 0.15, 1),
            foreground_color=(0.9, 0.9, 0.9, 1),
            cursor_color=(0.55, 0.36, 0.96, 1),
        )
        scroll.add_widget(text_input)

        label = MDLabel(
            text="Установите wl-clipboard для автокопирования:\n[color=#8b5cf6]sudo apt install wl-clipboard[/color]",
            theme_text_color="Custom",
            text_color=(0.6, 0.6, 0.65, 1),
            markup=True,
            halign="center",
            size_hint_y=None,
            height=dp(40),
            font_size=dp(12),
        )

        container = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            spacing=dp(8),
            padding=dp(10),
        )
        container.add_widget(scroll)
        container.add_widget(label)

        dialog = MDDialog(
            MDDialogHeadlineText(text="Скопируйте ссылку"),
            MDDialogContentContainer(container),
            MDDialogButtonContainer(
                MDButton(MDButtonText(text="Закрыть"), on_release=_on_close, md_bg_color=self.c_accent),
            ),
            size_hint_x=0.9,
            auto_dismiss=True,
        )
        dialog.open()

    def open_bot_link(self, *args):
        webbrowser.open("https://t.me/arqvpn_bot")

    def open_channel_link(self, *args):
        webbrowser.open("https://t.me/arqhub")

    # ─── Настройки ─────────────────────────────────────────────
    def save_settings_from_ui(self):
        data = load_settings()
        data["user_agent"] = self.root.ids.user_agent.text.strip()
        tasks = []
        for card in self._category_cards:
            name = card['name_input'].text.strip()
            if not name:
                continue
            urls = [r['input'].text.strip() for r in card['url_rows'] if r['input'].text.strip()]
            if not urls:
                continue
            try:
                max_ping = int(card['max_ping'].text.strip() or "9000")
            except ValueError:
                max_ping = 9000
            try:
                req_count = int(card['req_count'].text.strip() or "10")
            except ValueError:
                req_count = 10
            from config import RAW_CONFIGS_DIR
            raw_files = []
            for u in urls:
                fname = u.split("/")[-1].split("?")[0]
                if fname:
                    raw_files.append(os.path.join(RAW_CONFIGS_DIR, fname))
            profile = card['profile'].text.strip()
            out_name = name.lower().replace(' ', '_')
            tasks.append({
                "name": name, "type": card['type_var'], "urls": urls,
                "raw_files": raw_files,
                "target_url": card['target'].text.strip() or "https://www.google.com/generate_204",
                "max_ping_ms": max_ping, "required_count": req_count,
                "profile_title": profile,
                "out_file": os.path.join(RESULTS_DIR, f"top_{out_name}.txt"),
            })
        if tasks:
            data["tasks"] = tasks
        save_settings(data)
        self.tasks = get_tasks()
        self._render_task_checkboxes()
        self._render_categories()
        self._toast("Сохранено")

    def reset_settings_to_defaults(self):
        """Сбрасывает настройки до значений по умолчанию."""
        defaults = reset_to_defaults()
        self.tasks = get_tasks()
        self._render_task_checkboxes()
        self._render_categories(defaults)
        self.root.ids.user_agent.text = defaults.get("user_agent", "")
        self._toast("Настройки восстановлены")

    # ─── Чекбоксы ──────────────────────────────────────────────
    def _render_task_checkboxes(self):
        box = self.root.ids.task_checkboxes
        box.clear_widgets()
        self._task_checks.clear()
        for task in self.tasks:
            row = MDBoxLayout(orientation="horizontal", adaptive_height=True,
                              spacing=dp(8), size_hint_y=None, height=dp(28))
            check = MDCheckbox(active=True, size_hint=(None, None), size=(dp(24), dp(24)))
            self._task_checks[task["name"]] = {"check": check, "task": task}
            row.add_widget(check)
            row.add_widget(MDLabel(text=f"{task['name']} ({task['type']})",
                                   theme_text_color="Primary",
                                   size_hint_y=None, height=dp(24)))
            box.add_widget(row)

    # ─── Категории ─────────────────────────────────────────────
    def _render_categories(self, settings=None):
        box = self.root.ids.categories_box
        box.clear_widgets()
        self._category_cards.clear()
        if settings is None:
            settings = load_settings()
        for td in settings.get("tasks", []):
            self._add_category_card(td)

    def _update_card_canvas(self, widget):
        for instr in widget.canvas.before.children[:]:
            if isinstance(instr, RoundedRectangle):
                instr.pos = widget.pos
                instr.size = widget.size
                break

    def _mk_input(self, hint="", height=dp(40), text=""):
        w = MDTextField(hint_text=hint, size_hint_y=None,
                        height=height, font_size=dp(15), multiline=False)
        w.text = text
        return w

    def _mk_small(self, width, hint="", text=""):
        w = MDTextField(hint_text=hint, size_hint_x=None, width=width,
                        height=dp(40), font_size=dp(15), multiline=False)
        w.text = text
        return w

    def _add_category_card(self, data=None):
        if data is None:
            data = {"name": "", "type": "xray", "urls": [""], "target_url": "https://www.google.com/generate_204",
                    "max_ping_ms": 9000, "required_count": 10, "profile_title": ""}

        box = self.root.ids.categories_box
        card = {'type_var': data.get("type", "xray"), 'url_rows': [], 'type_btns': []}

        frame = MDBoxLayout(orientation="vertical", size_hint_y=None,
                            adaptive_height=True, spacing=dp(10),
                            padding=[dp(14), dp(12)])
        with frame.canvas.before:
            Color(*self.c_card)
            RoundedRectangle(pos=frame.pos, size=frame.size, radius=[14, 14, 14, 14])
        frame.bind(pos=lambda inst, val: self._update_card_canvas(frame),
                   size=lambda inst, val: self._update_card_canvas(frame))

        name_input = self._mk_input("Название категории", dp(44), data.get("name", ""))
        card['name_input'] = name_input
        frame.add_widget(name_input)

        # Переключаемый тип
        card['type_var'] = data.get("type", "xray")
        type_row = MDBoxLayout(orientation="horizontal", adaptive_height=True,
                               spacing=dp(6), size_hint_y=None, height=dp(36))
        type_lbl = MDLabel(text="Тип:", theme_text_color="Secondary",
                            size_hint_x=None, adaptive_width=True)
        type_row.add_widget(type_lbl)

        card['type_btns'] = []
        
        for btn_type in ["xray", "mtproto"]:
            is_active = (card['type_var'] == btn_type)
            
            btn = TypeBtnButton(btn_type=btn_type, is_active=is_active)
            
            def on_type_click(instance, button=btn, selected_type=btn_type):
                card['type_var'] = selected_type
                for b in card['type_btns']:
                    is_sel = (selected_type == b._type_val)
                    b._set_active(is_sel)
            
            btn.bind(on_release=on_type_click)
            
            type_row.add_widget(btn)
            card['type_btns'].append(btn)
        frame.add_widget(type_row)

        frame.add_widget(MDLabel(text="Источники (URL):", theme_text_color="Secondary",
                                 bold=True, size_hint_y=None, height=dp(18)))

        url_container = MDBoxLayout(orientation="vertical", adaptive_height=True, spacing=dp(14))
        frame.add_widget(url_container)

        for url in data.get("urls", [""]):
            self._add_url_row(url_container, card, url)

        add_url = MDButton(
            MDButtonText(
                text="+ Добавить URL",
                text_color=self.c_accent,
            ),
            size_hint_x=None,
            width=dp(140),
            height=dp(30),
            md_bg_color=(0, 0, 0, 0),
        )
        add_url.bind(on_release=lambda *_: self._add_url_row(url_container, card, ""))
        frame.add_widget(add_url)

        target = self._mk_input("Целевой URL", dp(40), data.get("target_url", "https://www.google.com/generate_204"))
        card['target'] = target
        frame.add_widget(target)

        nums = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(6),
                           size_hint_y=None, height=dp(38))
        ping_lbl = MDLabel(text="Макс.пинг:", theme_text_color="Secondary",
                           size_hint_x=None, adaptive_width=True)
        nums.add_widget(ping_lbl)
        mp = self._mk_small(dp(65), "мс.", str(data.get("max_ping_ms", 9000)))
        card['max_ping'] = mp
        nums.add_widget(mp)
        req_lbl = MDLabel(text="Мин.кол-во:", theme_text_color="Secondary",
                          size_hint_x=None, adaptive_width=True)
        nums.add_widget(req_lbl)
        rc = self._mk_small(dp(55), "шт.", str(data.get("required_count", 10)))
        card['req_count'] = rc
        nums.add_widget(rc)
        frame.add_widget(nums)

        profile = self._mk_input("Имя профиля", dp(40), data.get("profile_title", ""))
        card['profile'] = profile
        frame.add_widget(profile)

        del_btn = MDButton(
            MDButtonText(
                text="Удалить",
                text_color=(0.937, 0.267, 0.267, 1),
            ),
            size_hint_x=None,
            width=dp(90),
            height=dp(32),
            md_bg_color=(0, 0, 0, 0),
        )
        def _delete(*_):
            if card in self._category_cards:
                self._category_cards.remove(card)
            box.remove_widget(frame)
        del_btn.bind(on_release=_delete)
        frame.add_widget(del_btn)

        box.add_widget(frame)
        self._category_cards.append(card)

    def _add_url_row(self, container, card, url=""):
        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(8),
                          padding=[0, dp(3)])
        row.add_widget(MDLabel(text=">", theme_text_color="Secondary",
                                size_hint_x=None, width=dp(16)))
        inp = self._mk_input("URL", dp(48), url)
        row.add_widget(inp)
        del_btn = MDIconButton(icon="close", user_font_size=dp(14), theme_text_color="Custom",
                               text_color=self.c_muted, size_hint=(None, None), size=(dp(24), dp(24)))
        def _remove(*_):
            container.remove_widget(row)
            card['url_rows'] = [r for r in card['url_rows'] if r['input'] != inp]
        del_btn.bind(on_release=_remove)
        row.add_widget(del_btn)
        card['url_rows'].append({'input': inp, 'row': row})
        container.add_widget(row)

    def add_category(self):
        self._add_category_card()

    # ─── Advanced toggle ───────────────────────────────────────
    def _adv_idx(self):
        """Индекс для вставки adv_container (сразу после adv_btn)."""
        parent = self.root.ids.main_content
        for i, child in enumerate(parent.children):
            if child == self.root.ids.adv_btn:
                return i
        return 0

    def toggle_advanced(self):
        self.advanced_open = not self.advanced_open
        c = self.root.ids.adv_container
        btn = self.root.ids.adv_btn
        parent = self.root.ids.main_content

        if self.advanced_open:
            btn.text = "Скрыть настройки"
            # Вставляем перед adv_btn
            idx = self._adv_idx()
            if c.parent is None:
                parent.add_widget(c, idx)
            c.height = 0
            c.opacity = 0
            # Сначала даём layout пересчитать minimum_height
            Clock.schedule_once(lambda dt: self._expand_adv(c), 0.02)
        else:
            btn.text = "Дополнительные настройки"
            anim = Animation(opacity=0, d=0.2)
            anim.bind(on_complete=lambda *_: self._collapse_adv(c))
            anim.start(c)

    def _expand_adv(self, c):
        c.height = c.minimum_height
        Animation(opacity=1, d=0.2).start(c)

    def _collapse_adv(self, c):
        c.height = 0
        c.opacity = 0
        # Убираем из дерева чтобы не мешал кликам
        if c.parent is not None:
            c.parent.remove_widget(c)

    # ─── Лог ───────────────────────────────────────────────────
    def clear_log(self):
        self.root.ids.log_label.text = ""

    def _scroll_to_bottom(self, *args):
        """Прокрутить журнал событий вниз."""
        scroll = self.root.ids.log_scroll
        if scroll and scroll.height > 0:
            scroll.scroll_y = 0

    def _log(self, message: str, tag: str = "info"):
        skip = ("Тестирование ", "Тестирую ")
        if any(message.startswith(p) for p in skip):
            return
        # Заменяем эмодзи на ASCII — SDL2 шрифт их не поддерживает
        message = message.replace("✓", "+").replace("✗", "!").replace("✘", "!")
        message = message.replace("~", "~")
        icons = {"success": "+", "warning": "~", "error": "!", "info": "i", "title": ">"}
        icon = icons.get(tag, "i")
        lbl = self.root.ids.log_label
        lbl.text = f"{lbl.text}\n{icon} {message}" if lbl.text else f"{icon} {message}"
        lbl.text = lbl.text[-4000:]
        Clock.schedule_once(self._scroll_to_bottom, 0.05)

    def _threadsafe_log(self, msg: str, tag: str = "info"):
        Clock.schedule_once(lambda *_: self._log(msg, tag), 0)

    # ─── Прогресс ──────────────────────────────────────────────
    def _set_progress(self, value: float):
        """Устанавливает прогресс (0-100 конвертируется в 0-1)."""
        self.root.ids.progress.value = max(0, min(1.0, value / 100.0))

    def update_progress(self, current, total, suitable=0, required=0):
        if required > 0:
            pct = min(suitable / required, 1.0)
            self.root.ids.progress_label.text = f"{suitable}/{required} ({int(pct*100)}%)"
        elif total > 0:
            pct = current / total
            self.root.ids.progress_label.text = f"{int(pct*100)}%"
        else:
            pct = 0
        self._set_progress(pct * 100)

    def _threadsafe_progress(self, current, total, *_):
        if total <= 0:
            return
        Clock.schedule_once(lambda *_: self._set_progress((current / total) * 100), 0)

    # ─── Кнопки ────────────────────────────────────────────────
    def _enable_control_buttons(self, running: bool):
        stop = self.root.ids.stop_btn
        skip = self.root.ids.skip_btn

        def _set_btn_state(btn, enabled, fg_color, bg_color):
            btn.disabled = not enabled
            btn.md_bg_color = bg_color
            for c in btn.children:
                if isinstance(c, MDButtonText):
                    c.text_color = fg_color
                    break

        if running:
            _set_btn_state(stop, True, _hex_to_rgba(RED, 1.0), _hex_to_rgba(RED, 0.2))
            _set_btn_state(skip, True, _hex_to_rgba(YELLOW, 1.0), _hex_to_rgba(YELLOW, 0.2))
        else:
            _set_btn_state(stop, False, self.c_muted, (0, 0, 0, 0))
            _set_btn_state(skip, False, self.c_muted, (0, 0, 0, 0))
        self.root.ids.start_btn.disabled = running

    # ─── Скачивание ────────────────────────────────────────────
    def start_download(self):
        if self._is_running:
            self._toast("Операция уже выполняется")
            return
        self._is_running = True
        self._stop_event.clear()
        self._enable_control_buttons(True)
        self.root.ids.progress_label.text = "Скачивание..."
        self._set_progress(0)
        self._log("Скачивание конфигов...", "title")

        def worker():
            try:
                results = download_all_tasks(self.tasks, max_age_hours=24, force=False, log_func=self._threadsafe_log)
                d, s, f = len(results.get('downloaded',[])), len(results.get('skipped',[])), len(results.get('failed',[]))
                if d: self._threadsafe_log(f"Скачано: {d}", "success")
                if s: self._threadsafe_log(f"Пропущено: {s}")
                if f: self._threadsafe_log(f"Ошибок: {f}", "error")
            except Exception as e:
                self._threadsafe_log(str(e), "error")
            finally:
                Clock.schedule_once(lambda *_: self._finish_op(), 0)

        threading.Thread(target=worker, daemon=True).start()

    # ─── Тест ──────────────────────────────────────────────────
    def start_full_test(self):
        if self._is_running:
            self._toast("Тест уже запущен")
            return
        sel = [d['task'] for d in self._task_checks.values() if d['check'].active]
        if not sel:
            self._toast("Выберите хотя бы одну задачу")
            return
        self._is_running = True
        self._stop_event.clear()
        self._enable_control_buttons(True)
        self._set_progress(0)
        self.root.ids.progress_label.text = "Запуск..."
        self._log(f"Запуск: {len(sel)} задач", "title")

        def worker():
            task_names = []
            
            # Предварительная проверка актуальности конфигов (как в main.py)
            self._threadsafe_log("Проверка актуальности конфигов...", "info")
            try:
                # Скачиваем только выбранные задачи
                download_all_tasks(sel, max_age_hours=24, force=False, log_func=self._threadsafe_log)
            except Exception as e:
                self._threadsafe_log(f"Ошибка при проверке актуальности: {e}", "error")

            # Проверка и установка Xray (как в main.py)
            self._threadsafe_log("Проверка Xray...", "info")
            try:
                actual_xray = ensure_xray(log_func=self._threadsafe_log)
                if actual_xray:
                    global XRAY_BIN
                    XRAY_BIN = actual_xray
                else:
                    self._threadsafe_log("Xray не найден. Тестирование Xray может быть пропущено.", "warning")
            except Exception as e:
                self._threadsafe_log(f"Ошибка Xray: {e}", "error")

            for i, t in enumerate(sel, 1):
                if self._stop_event.is_set():
                    break
                task_names.append(t['name'])
                Clock.schedule_once(lambda *_v, name=t['name']: setattr(
                    self.root.ids.progress_label, 'text', f"Тестирование: {name}"), 0)
                self._threadsafe_log(f"[{i}/{len(sel)}] {t['name']}")
                self._test_task(t)
                Clock.schedule_once(lambda *_v, p=(i/len(sel))*100: self._set_progress(p), 0)
            # Объединяем VPN конфиги если тестировали VPN задачи
            vpn_names = {'Base VPN', 'Bypass VPN'}
            if any(n in vpn_names for n in task_names):
                Clock.schedule_once(lambda *_: self.merge_vpn_configs(), 0)
            Clock.schedule_once(lambda *_: self._finish_op(tested_tasks=task_names), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _test_task(self, task):
        if task["type"] == "xray":
            configs = []
            for f in task.get("raw_files", []):
                if os.path.exists(f):
                    configs.extend(read_configs_from_file(f))
            if not configs:
                self._threadsafe_log(f"{task['name']}: нет конфигов", "warning")
                return
            w, p, f = test_xray_configs(
                configs=configs, target_url=task["target_url"],
                max_ping_ms=task["max_ping_ms"], required_count=task["required_count"],
                xray_path=XRAY_BIN, out_file=task["out_file"],
                profile_title=task.get("profile_title"), config_type=task.get("name"),
                log_func=self._threadsafe_log, progress_func=self._threadsafe_progress,
                stop_flag=self._stop_event)
            self._threadsafe_log(f"{task['name']}: ok={w}, pass={p}, fail={f}", "success" if p > 0 else "warning")
        else:
            configs = []
            for f in task.get("raw_files", []):
                if os.path.exists(f):
                    configs.extend(read_mtproto_from_file(f))
            if not configs:
                self._threadsafe_log(f"{task['name']}: нет MTProto", "warning")
                return
            w, p, f = test_mtproto_configs(
                configs=configs, max_ping_ms=task["max_ping_ms"],
                required_count=task["required_count"], max_workers=30,
                out_file=task["out_file"],
                profile_title=task.get("profile_title"), config_type=task.get("name"),
                log_func=self._threadsafe_log,
                progress_func=lambda c, t: self._threadsafe_progress(c, t, 0, 0),
                stop_flag=self._stop_event)
            self._threadsafe_log(f"{task['name']}: ok={w}, pass={p}, fail={f}", "success" if p > 0 else "warning")

    def skip_file(self):
        self._stop_event.set()
        self._log("Пропущено", "warning")

    def stop_operation(self):
        self._stop_event.set()
        self._log("Остановка", "warning")

    # ─── Подписка на сервер ────────────────────────────────────
    def _upload_subscription(self, tested_tasks=None):
        """Отправляет на сервер только результаты протестированных задач."""
        if not auth_module.is_logged_in():
            return
        all_task_names = [t['name'] for t in self.tasks]
        if tested_tasks is None:
            tested_tasks = all_task_names
        vpn_tasks = [t for t in tested_tasks if t in ('Base VPN', 'Bypass VPN')]
        mt_task = 'Telegram MTProto' in tested_tasks
        vpn_content = ""
        mt_content = ""
        if vpn_tasks:
            vpn_file = os.path.join(RESULTS_DIR, "all_top_vpn.txt")
            if os.path.exists(vpn_file):
                with open(vpn_file, 'r', encoding='utf-8') as f:
                    vpn_content = f.read().strip()
            else:
                self._log("all_top_vpn.txt не найден", "warning")
        if mt_task:
            mt_file = os.path.join(RESULTS_DIR, "top_telegram_mtproto.txt")
            if os.path.exists(mt_file):
                with open(mt_file, 'r', encoding='utf-8') as f:
                    mt_content = f.read().strip()
            else:
                self._log("Файл MTProto не найден", "warning")
        if not vpn_content and not mt_content:
            self._toast("Нет результатов для отправки")
            return

        def _ask_retry():
            """Показывает диалог при сетевой неудаче."""
            try:
                from kivymd.uix.dialog import (
                    MDDialog,
                    MDDialogHeadlineText,
                    MDDialogSupportingText,
                    MDDialogButtonContainer,
                )
                from kivymd.uix.button import MDButton, MDButtonText

                def _on_retry(*_):
                    dlg.dismiss()
                    self._upload_subscription(tested_tasks=tested_tasks)

                def _on_cancel(*_):
                    dlg.dismiss()

                dlg = MDDialog(
                    MDDialogHeadlineText(text="Обновление подписки"),
                    MDDialogSupportingText(
                        text="Обновление не удалось. Возможно, у вас работают белые списки. Подключитесь к стабильной сети и повторите попытку.",
                    ),
                    MDDialogButtonContainer(
                        MDButton(MDButtonText(text="Отмена"), on_release=_on_cancel),
                        MDButton(MDButtonText(text="Повторить"), on_release=_on_retry, md_bg_color=self.c_accent),
                        spacing="4dp",
                    ),
                    auto_dismiss=False,
                )
                dlg.open()
            except Exception:
                self._toast("Ошибка сети. Повторите позже.")

        def up():
            try:
                if vpn_content:
                    auth_module.update_subscription(vpn_content)
                if mt_content:
                    auth_module.update_mtproto(mt_content)
                msgs = []
                if vpn_content:
                    msgs.append("VPN")
                if mt_content:
                    msgs.append("MTProto")
                Clock.schedule_once(lambda *_: self._log(f"Подписка обновлена: {', '.join(msgs)}", "success"), 0)
                Clock.schedule_once(lambda *_: self._toast("Подписка обновлена"), 0)
            except auth_module.AuthError as exc:
                err_msg = str(exc)
                Clock.schedule_once(lambda *_: self._log(f"Ошибка авторизации: {err_msg}", "error"), 0)
                Clock.schedule_once(lambda *_: _ask_retry(), 0)
            except Exception as exc:
                err_msg = str(exc)
                Clock.schedule_once(lambda *_: self._log(f"Ошибка отправки: {err_msg}", "error"), 0)
                Clock.schedule_once(lambda *_: _ask_retry(), 0)

        threading.Thread(target=up, daemon=True).start()

    def _ask_update_sub_or_open_folder(self, tested_tasks=None):
        """После теста спрашивает: обновить подписку (или GitHub для admin)."""
        print(f"[DEBUG] _ask_update_sub_or_open_folder вызван")
        session = auth_module.get_session()
        username = session.get("username") if session else None
        
        is_admin = (username == "admin")

        if not auth_module.is_logged_in():
            print(f"[DEBUG] не залогинен — открываю папку")
            self.open_results()
            return

        try:
            from kivymd.uix.dialog import (
                MDDialog,
                MDDialogHeadlineText,
                MDDialogSupportingText,
                MDDialogButtonContainer,
            )
            from kivymd.uix.button import MDButton, MDButtonText

            print(f"[DEBUG] Создаю диалог...")

            def _on_yes(*_):
                print(f"[DEBUG] Нажата кнопка Да")
                dlg.dismiss()
                if is_admin:
                    self._push_to_github()
                else:
                    self._upload_subscription(tested_tasks=tested_tasks)

            def _on_no(*_):
                print(f"[DEBUG] Нажата кнопка Нет")
                dlg.dismiss()
                self.open_results()

            if is_admin:
                headline = "Обновить GitHub?"
                supporting = "Зафиксировать изменения в репозитории?"
            else:
                headline = "Обновить подписку?"
                supporting = "Обновить вашу подписку на сервере?"

            dlg = MDDialog(
                MDDialogHeadlineText(
                    text=headline,
                ),
                MDDialogSupportingText(
                    text=supporting,
                ),
                MDDialogButtonContainer(
                    MDButton(
                        MDButtonText(text="Нет"),
                        on_release=_on_no,
                    ),
                    MDButton(
                        MDButtonText(text="Да"),
                        on_release=_on_yes,
                        md_bg_color=self.c_accent,
                    ),
                    spacing="4dp",
                ),
                auto_dismiss=False,
            )

            def _on_dlg_dismiss(*_):
                print(f"[DEBUG] Диалог закрыт")

            dlg.bind(on_dismiss=_on_dlg_dismiss)

            print(f"[DEBUG] Открываю диалог...")
            dlg.open()
            print(f"[DEBUG] Диалог открыт")
        except Exception as e:
            print(f"[DEBUG] Ошибка диалога: {e}")
            import traceback
            traceback.print_exc()
            self.open_results()

    # ─── GitHub интеграция ──────────────────────────────────────
    def _push_to_github(self):
        """Обновляет результаты в репозитории GitHub (аналог логики из main.py)."""
        import subprocess
        from datetime import datetime

        def push_thread():
            try:
                self._threadsafe_log("Начинаю обновление GitHub...", "info")
                project_dir = os.path.dirname(os.path.abspath(__file__))

                # Собираем файлы результатов
                from config import TASKS
                result_filenames = {
                    os.path.basename(task.get("out_file", ""))
                    for task in TASKS
                    if task.get("out_file")
                }
                result_filenames.add("all_top_vpn.txt")

                result_files = []
                for file in sorted(result_filenames):
                    file_path = os.path.join(RESULTS_DIR, file)
                    if os.path.exists(file_path):
                        result_files.append(file_path)

                if not result_files:
                    self._threadsafe_log("Файлы результатов не найдены", "warning")
                    return

                # git add
                for file_path in result_files:
                    subprocess.run(["git", "add", file_path], check=True, capture_output=True, cwd=project_dir)

                # git status check
                status_result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True, cwd=project_dir)
                if not status_result.stdout.strip():
                    self._threadsafe_log("Нет изменений для коммита", "warning")
                    return

                # git commit
                commit_msg = f"Update VPN configs results - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                subprocess.run(["git", "commit", "-m", commit_msg], check=True, capture_output=True, cwd=project_dir)

                # git push
                push_result = subprocess.run(["git", "push"], capture_output=True, text=True, check=False, cwd=project_dir)

                if push_result.returncode == 0:
                    self._threadsafe_log("Результаты успешно обновлены на GitHub!", "success")
                    Clock.schedule_once(lambda *_: self._toast("GitHub обновлен"), 0)
                else:
                    err = push_result.stderr or push_result.stdout
                    self._threadsafe_log(f"Ошибка GitHub: {err.strip()}", "error")
            except Exception as e:
                self._threadsafe_log(f"Критическая ошибка Git: {e}", "error")

        threading.Thread(target=push_thread, daemon=True).start()

    def merge_vpn_configs(self):
        """Объединяет top_base_vpn.txt и top_bypass_vpn.txt в all_top_vpn.txt."""
        try:
            cfgs = []
            for fn in ["top_base_vpn.txt", "top_bypass_vpn.txt"]:
                fp = os.path.join(RESULTS_DIR, fn)
                if os.path.exists(fp):
                    with open(fp, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                cfgs.append(line)
            if cfgs:
                out = os.path.join(RESULTS_DIR, "all_top_vpn.txt")
                with open(out, 'w', encoding='utf-8') as f:
                    f.write("#profile-update-interval: 48\n")
                    f.write("#support-url: https://t.me/arqhub\n\n")
                    for c in cfgs:
                        f.write(f"{c}\n")
                self._log(f"Объединено {len(cfgs)} конфигов в all_top_vpn.txt", "success")
        except Exception as e:
            self._log(f"Ошибка объединения: {e}", "error")

    def _finish_op(self, tested_tasks=None):
        self._is_running = False
        self._enable_control_buttons(False)
        self._set_progress(100)
        self.root.ids.progress_label.text = "Готово"
        self._log("Завершено", "success")
        self._toast("Готово")
        # После теста — спросить про обновление подписки
        if tested_tasks:
            Clock.schedule_once(lambda *_: self._ask_update_sub_or_open_folder(tested_tasks=tested_tasks), 0.5)

    # ─── Утилиты ───────────────────────────────────────────────
    def open_results(self):
        import subprocess, sys
        if not os.path.exists(RESULTS_DIR):
            self._toast("Папка пуста")
            return
        if sys.platform == "win32":
            os.startfile(RESULTS_DIR)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", RESULTS_DIR])
        else:
            subprocess.Popen(["xdg-open", RESULTS_DIR])

    def logout(self):
        auth_module.clear_session()
        self.switch_screen("login")
        self._toast("Выход")

    def _toast(self, text: str):
        try:
            from kivymd.uix.snackbar import MDSnackbar, MDSnackbarSupportingText
            sb = MDSnackbar(
                MDSnackbarSupportingText(
                    text=text,
                    theme_text_color="Custom",
                    text_color="#e4e4e7",
                ),
                y=0,
                pos_hint={"center_x": 0.5},
                size_hint_x=1.0,
            )
            sb.md_bg_color = [0.18, 0.18, 0.22, 1]
            sb.open()
        except Exception:
            pass

    def _show_toast(self, text: str):
        """Показывает toast в главном потоке (алиас для _toast)."""
        self._toast(text)


def main():
    KivyGUIApp().run()


if __name__ == "__main__":
    main()

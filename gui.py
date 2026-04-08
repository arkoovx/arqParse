"""
Современный GUI для arqParse.
Чёрная тема, фиолетовые акценты. Навигация между страницами.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import os
import sys
import subprocess
import webbrowser
from datetime import datetime

from config import RESULTS_DIR
from settings_manager import get_tasks, get_user_agent, load_settings, save_settings
from downloader import download_all_tasks
from parser import read_configs_from_file, read_mtproto_from_file
from testers import test_xray_configs
from testers_mtproto import test_mtproto_configs, test_mtproto_configs_and_save
import auth as auth_module


# ─── Чёрная тема + фиолетовые акценты ────────────────────────
BG         = "#0d0d0d"
BG_CARD    = "#161616"
BG_HOVER   = "#1e1e1e"
BG_INPUT   = "#111111"
ACCENT     = "#8b5cf6"
ACCENT_DK  = "#7c3aed"
ACCENT_LG  = "#a78bfa"
TEXT       = "#e4e4e7"
TEXT_DIM   = "#71717a"
TEXT_MUTED = "#52525b"
GREEN      = "#22c55e"
YELLOW     = "#facc15"
RED        = "#ef4444"
PROGRESS_T = "#1a1a1a"
PROGRESS_F = "#8b5cf6"
BORDER     = "#262626"


class _Btn(tk.Label):
    """Кнопка на базе Label — без артефактов ttk, корректный hover."""
    def __init__(self, master, text="", bg_color=BG_CARD, fg_color=TEXT,
                 font=("Segoe UI", 11), active_bg=BG_HOVER, border=False,
                 command=None, bold=False, pady=8, padx=14, **kw):
        fnt = font
        if bold:
            fnt = (font[0], font[1], "bold")
        super().__init__(master, text=text, bg=bg_color, fg=fg_color,
                         font=fnt, cursor="hand2", **kw)
        self._bg = bg_color
        self._active = active_bg
        self._fg = fg_color
        self._cmd = command
        self._disabled = False
        self.bind("<Enter>", lambda e: self._set(True))
        self.bind("<Leave>", lambda e: self._set(False))
        self.bind("<Button-1>", self._click)
        self.configure(padx=padx, pady=pady)

    def _set(self, on):
        if self._disabled:
            return
        if on:
            self.config(bg=self._active)
        else:
            self.config(bg=self._bg)

    def _click(self, e):
        if not self._disabled and self._cmd:
            self._cmd()

    def config(self, **kw):
        if "state" in kw:
            st = kw.pop("state")
            self._disabled = (st == tk.DISABLED)
            if self._disabled:
                self.config(fg=TEXT_MUTED, cursor="")
            else:
                self.config(cursor="hand2")
        super().config(**kw)


class ArcParseGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("arqParse")
        self.root.geometry("420x800")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)

        # ─── Флаги ─────────────────────────────────────────────
        self.is_running = False
        self.stop_flag = False
        self.skip_flag = False
        self.stop_event = None
        self.skip_event = None

        # ─── Настройки (загружаются динамически) ───────────────
        self._settings = load_settings()
        self._tasks = get_tasks()

        # ─── Навигация ─────────────────────────────────────────
        self._current_page = None
        self._pages = {}

        # ─── Проверяем сессию ──────────────────────────────────
        if auth_module.is_logged_in():
            self._show_main_app()
        else:
            self._show_login_screen()

    # ════════════════════════ НАВИГАЦИЯ ════════════════════════
    def _show_page(self, page_name):
        """Скрыть текущую страницу и показать новую."""
        if self._current_page and self._current_page in self._pages:
            self._pages[self._current_page].pack_forget()
        self._current_page = page_name
        if page_name in self._pages:
            self._pages[page_name].pack(fill=tk.BOTH, expand=True)

    def _go_home(self):
        self._show_page("main")

    def _go_settings(self):
        self._show_page("settings")

    # ════════════════════════ ЭКРАН ВХОДА ══════════════════════
    def _show_login_screen(self):
        self.login_frame = tk.Frame(self.root, bg=BG)
        self.login_frame.pack(fill=tk.BOTH, expand=True)

        center = tk.Frame(self.login_frame, bg=BG)
        center.pack(fill=tk.BOTH, expand=True, padx=32, pady=50)

        tk.Label(center, text="arqParse", bg=BG, fg=TEXT,
                 font=("Segoe UI", 28, "bold")).pack(pady=(0, 2))
        tk.Label(center, text="Тестирование VPN конфигов", bg=BG,
                 fg=TEXT_DIM, font=("Segoe UI", 11)).pack()

        card = tk.Frame(center, bg=BG_CARD, highlightthickness=1,
                        highlightbackground=BORDER)
        card.pack(fill=tk.X, pady=(36, 0), ipady=4)

        mode_row = tk.Frame(card, bg=BG_CARD)
        mode_row.pack(fill=tk.X, padx=16, pady=(16, 8))

        self.auth_mode = tk.StringVar(value="login")

        tk.Radiobutton(mode_row, text="Вход", variable=self.auth_mode,
                       value="login", bg=BG_CARD, fg=TEXT, selectcolor=BG,
                       font=("Segoe UI", 11), activebackground=BG_CARD,
                       activeforeground=TEXT, highlightthickness=0, border=0,
                       command=self._update_auth_btn_text).pack(side=tk.LEFT, expand=True)
        tk.Radiobutton(mode_row, text="Регистрация", variable=self.auth_mode,
                       value="register", bg=BG_CARD, fg=TEXT, selectcolor=BG,
                       font=("Segoe UI", 11), activebackground=BG_CARD,
                       activeforeground=TEXT, highlightthickness=0, border=0,
                       command=self._update_auth_btn_text).pack(side=tk.LEFT, expand=True)

        fields = tk.Frame(card, bg=BG_CARD)
        fields.pack(fill=tk.X, padx=16)

        self._add_field(fields, "Логин", show=False)
        self._add_field(fields, "Пароль", show=True)

        btn_pad = tk.Frame(card, bg=BG_CARD)
        btn_pad.pack(fill=tk.X, padx=16, pady=(14, 16))

        self.auth_btn = _Btn(btn_pad, text="Войти", bg_color=ACCENT, fg_color="#fff",
                             font=("Segoe UI", 12, "bold"), active_bg=ACCENT_DK,
                             command=self._do_auth, pady=10)
        self.auth_btn.pack(fill=tk.X)

        self.login_pass.bind("<Return>", lambda e: self._do_auth())
        self.login_user.bind("<Return>", lambda e: self.login_pass.focus())

        link_row = tk.Frame(center, bg=BG)
        link_row.pack(pady=(20, 0))
        tk.Label(link_row, text="by ", bg=BG, fg=TEXT_DIM,
                 font=("Segoe UI", 10)).pack(side=tk.LEFT)
        al = tk.Label(link_row, text="arq", bg=BG, fg=ACCENT_LG,
                      font=("Segoe UI", 10, "bold"), cursor="hand2")
        al.pack(side=tk.LEFT)
        al.bind("<Button-1>", lambda e: webbrowser.open("https://t.me/arqhub"))

    def _add_field(self, parent, label_text, show=False):
        tk.Label(parent, text=label_text, bg=BG_CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 9), anchor=tk.W).pack(fill=tk.X, pady=(6, 2))
        entry = tk.Entry(parent, bg=BG_INPUT, fg=TEXT, font=("Segoe UI", 11),
                         relief=tk.FLAT, bd=0, highlightthickness=1,
                         highlightbackground=BORDER, insertbackground=TEXT,
                         show="●" if show else "")
        entry.pack(fill=tk.X, ipady=6, pady=(0, 8))
        if show:
            self.login_pass = entry
        else:
            self.login_user = entry

    def _update_auth_btn_text(self):
        if not self.auth_btn._disabled:
            if self.auth_mode.get() == "register":
                self.auth_btn.config(text="Зарегистрироваться")
            else:
                self.auth_btn.config(text="Войти")

    def _animate_loading(self):
        if not hasattr(self, '_auth_loading_text'):
            return
        dots = "." * (self._auth_loading_dots % 4)
        self.auth_btn.config(
            text=f"{self._auth_loading_text}{dots}",
            fg=TEXT_DIM
        )
        self._auth_loading_dots += 1
        if self.auth_btn._disabled:
            self.root.after(500, self._animate_loading)

    def _stop_loading_animation(self):
        if hasattr(self, '_auth_loading_text'):
            delattr(self, '_auth_loading_text')

    def _do_auth(self):
        username = self.login_user.get().strip()
        password = self.login_pass.get()
        server = auth_module.DEFAULT_SERVER

        if not username or len(username) < 3:
            messagebox.showerror("Ошибка", "Логин минимум 3 символа")
            return
        if not password or len(password) < 6:
            messagebox.showerror("Ошибка", "Пароль минимум 6 символов")
            return

        self.auth_btn._disabled = True
        self._auth_loading_dots = 0
        self._auth_loading_text = "Регистрация" if self.auth_mode.get() == "register" else "Подключение"
        self._animate_loading()
        self.root.update()

        def auth_thread():
            try:
                if not auth_module.check_server(server):
                    self.root.after(0, lambda: self._show_auth_error(
                        "Сервер недоступен. Проверьте подключение и попробуйте позже."
                    ))
                    return

                if self.auth_mode.get() == "register":
                    result = auth_module.register(username, password, server)
                else:
                    result = auth_module.login(username, password, server)
                self.root.after(0, lambda: self._on_auth_success(result))

            except auth_module.AuthError as exc:
                err = str(exc)
                self.root.after(0, lambda: self._show_auth_error(err))
            except Exception as exc:
                err = str(exc)
                self.root.after(0, lambda: self._show_auth_error(err))

        threading.Thread(target=auth_thread, daemon=True).start()

    def _show_auth_error(self, msg):
        self._stop_loading_animation()
        self.auth_btn._disabled = False
        mode = self.auth_mode.get()
        self.auth_btn.config(text="Войти" if mode == "login" else "Зарегистрироваться",
                                   fg="#fff")
        messagebox.showerror("Ошибка", msg)

    def _on_auth_success(self, result):
        self._stop_loading_animation()
        self.login_frame.destroy()
        self._show_main_app()

    # ════════════════════════ ОСНОВНОЙ ЭКРАН ═══════════════════
    def _show_main_app(self):
        session = auth_module.get_session()
        self.current_user = session["username"] if session else None

        # ─── Создаём страницу "Главная" ────────────────────────
        main_frame = tk.Frame(self.root, bg=BG)
        self._build_main_page(main_frame)
        self._pages["main"] = main_frame

        # ─── Создаём страницу "Настройки" ──────────────────────
        settings_frame = tk.Frame(self.root, bg=BG)
        self._build_settings_page(settings_frame)
        self._pages["settings"] = settings_frame

        # ─── Показываем главную ────────────────────────────────
        self._show_page("main")

    def _build_main_page(self, parent):
        """Строит содержимое главной страницы."""

        # ─── Верх ──────────────────────────────────────────────
        self.top_frame = tk.Frame(parent, bg=BG)
        self.top_frame.pack(fill=tk.X, padx=24, pady=(16, 8))

        tk.Label(self.top_frame, text="arqParse", bg=BG, fg=TEXT,
                 font=("Segoe UI", 24, "bold")).pack(anchor=tk.W)

        status_row = tk.Frame(self.top_frame, bg=BG)
        status_row.pack(fill=tk.X, pady=(4, 0))

        if self.current_user:
            tk.Label(status_row, text=f"👤  {self.current_user}", bg=BG,
                     fg=TEXT_DIM, font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(8, 0))

            _Btn(status_row, text="⚙  Настройки", bg_color=BG, fg_color=TEXT_DIM,
                 font=("Segoe UI", 9), active_bg=BG_HOVER,
                 command=self._go_settings, padx=6, pady=4).pack(side=tk.RIGHT, padx=(0, 4))

            _Btn(status_row, text="📋  Ссылка", bg_color=BG, fg_color=ACCENT_LG,
                 font=("Segoe UI", 9), active_bg=BG_HOVER,
                 command=self._toggle_sub_url, padx=6, pady=4).pack(side=tk.RIGHT)

            _Btn(status_row, text="Выйти", bg_color=BG, fg_color=TEXT_DIM,
                 font=("Segoe UI", 9), active_bg=BG_HOVER,
                 command=self._do_logout, padx=6, pady=4).pack(side=tk.RIGHT, padx=(0, 4))

        # MTProto подсказка
        mt_row = tk.Frame(self.top_frame, bg=BG)
        mt_row.pack(fill=tk.X, pady=(6, 0))
        tk.Label(mt_row, text="MTProto можно добавить в тг через  ", bg=BG,
                 fg=TEXT_MUTED, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        bot_link = tk.Label(mt_row, text="@arqvpn_bot", bg=BG, fg=ACCENT_LG,
                            font=("Segoe UI", 10, "bold"), cursor="hand2")
        bot_link.pack(side=tk.LEFT)
        bot_link.bind("<Button-1>", lambda e: webbrowser.open("https://t.me/arqvpn_bot"))
        bot_link.bind("<Enter>", lambda e: bot_link.config(font=("Segoe UI", 10, "bold underline")))
        bot_link.bind("<Leave>", lambda e: bot_link.config(font=("Segoe UI", 10, "bold")))

        # Ссылка подписки (скрыта по умолчанию)
        self.sub_url_frame = tk.Frame(self.top_frame, bg=BG_INPUT,
                                       highlightthickness=1, highlightbackground=BORDER)
        self.sub_url_frame.pack(fill=tk.X, pady=(6, 0))
        self.sub_url_frame.pack_forget()

        sub_url_content = tk.Frame(self.sub_url_frame, bg=BG_INPUT)
        sub_url_content.pack(fill=tk.X, padx=8, pady=4)

        tk.Label(sub_url_content, text="Ссылка подписки:", bg=BG_INPUT,
                 fg=TEXT_MUTED, font=("Segoe UI", 8)).pack(anchor=tk.W)
        self.sub_url_text = tk.Text(sub_url_content, bg=BG_INPUT, fg=ACCENT_LG,
                                     font=("Consolas", 9), height=2, wrap=tk.WORD,
                                     bd=0, highlightthickness=0, cursor="arrow",
                                     state=tk.DISABLED)
        self.sub_url_text.pack(fill=tk.X, pady=(2, 0))

        sub_actions = tk.Frame(self.sub_url_frame, bg=BG_INPUT)
        sub_actions.pack(fill=tk.X, padx=8, pady=(0, 4))
        _Btn(sub_actions, text="Копировать", bg_color=BG_CARD, fg_color=TEXT_DIM,
             font=("Segoe UI", 9), active_bg=BG_HOVER,
             command=self._copy_sub_url, pady=3, padx=8).pack(side=tk.LEFT)

        self._sub_url_visible = False

        # ─── Контейнер для основного содержимого ───────────────
        self._main_content = tk.Frame(parent, bg=BG)
        self._main_content.pack(fill=tk.BOTH, expand=True)

        # ─── Главная кнопка ────────────────────────────────────
        self.start_btn = _Btn(self._main_content, text="⚡  Начать тест", bg_color=ACCENT,
                              fg_color="#fff", font=("Segoe UI", 15, "bold"),
                              active_bg=ACCENT_DK, command=self.start_full_test,
                              pady=14)
        self.start_btn.pack(fill=tk.X, padx=24, pady=(12, 4))

        # ─── Доп. опции ────────────────────────────────────────
        self.advanced_open = False
        self.check_vars = {}

        self.adv_btn = _Btn(self._main_content, text="▾  Дополнительные настройки",
                            bg_color=BG_CARD, fg_color=TEXT_DIM,
                            font=("Segoe UI", 10), active_bg=BG_HOVER,
                            command=self.toggle_advanced, pady=8)
        self.adv_btn.pack(fill=tk.X, padx=24, pady=(4, 0))

        self.adv_container = tk.Frame(self._main_content, bg=BG)

        card = tk.Frame(self.adv_container, bg=BG_CARD,
                        highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill=tk.X, padx=24, pady=8)

        tk.Label(card, text="Выбрать задачи", bg=BG_CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 10)).pack(anchor=tk.W, padx=14, pady=(10, 4))

        self._checkbox_container = tk.Frame(card, bg=BG_CARD)
        self._checkbox_container.pack(fill=tk.X, padx=14, pady=2)

        for task in self._tasks:
            row = tk.Frame(self._checkbox_container, bg=BG_CARD)
            row.pack(fill=tk.X, pady=2)
            var = tk.BooleanVar(value=True)
            self.check_vars[task['name']] = {'var': var, 'task': task}
            cb = tk.Checkbutton(row, text=task['name'], variable=var,
                                bg=BG_CARD, fg=TEXT, selectcolor=BG_INPUT,
                                activebackground=BG_CARD, activeforeground=TEXT,
                                highlightthickness=0, bd=0, font=("Segoe UI", 10))
            cb.pack(side=tk.LEFT)

        acts = tk.Frame(card, bg=BG_CARD)
        acts.pack(fill=tk.X, padx=14, pady=(8, 10))

        _Btn(acts, text="📥  Скачать конфиги", bg_color=BG_INPUT, fg_color=TEXT_DIM,
             font=("Segoe UI", 10), active_bg=BG_HOVER,
             command=self.start_download, pady=6).pack(side=tk.LEFT, fill=tk.X,
                                                       expand=True, padx=(0, 3))
        _Btn(acts, text="📂  Результаты", bg_color=BG_INPUT, fg_color=TEXT_DIM,
             font=("Segoe UI", 10), active_bg=BG_HOVER,
             command=self.open_results, pady=6).pack(side=tk.LEFT, fill=tk.X,
                                                     expand=True, padx=(3, 0))

        # ─── Управление ────────────────────────────────────────
        ctrl = tk.Frame(self._main_content, bg=BG)
        ctrl.pack(fill=tk.X, padx=24, pady=(4, 0))

        self.skip_btn_w = _Btn(ctrl, text="⏭  Пропустить", bg_color="#1c1917",
                               fg_color=YELLOW, font=("Segoe UI", 10, "bold"),
                               active_bg="#292524", command=self.skip_file,
                               pady=7)
        self.skip_btn_w.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        self.skip_btn_w._disabled = True
        self.skip_btn_w.config(fg=TEXT_MUTED)

        self.stop_btn_w = _Btn(ctrl, text="⏹  Остановить", bg_color="#1c1917",
                               fg_color=RED, font=("Segoe UI", 10, "bold"),
                               active_bg="#292524", command=self.stop_operation,
                               pady=7)
        self.stop_btn_w.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))
        self.stop_btn_w._disabled = True
        self.stop_btn_w.config(fg=TEXT_MUTED)

        # ─── Прогресс ──────────────────────────────────────────
        prog = tk.Frame(self._main_content, bg=BG)
        prog.pack(fill=tk.X, padx=24, pady=(10, 2))

        self.progress_canvas = tk.Canvas(prog, height=6, bg=PROGRESS_T,
                                         highlightthickness=0, bd=0)
        self.progress_canvas.pack(fill=tk.X)
        self.progress_bar = self.progress_canvas.create_rectangle(
            0, 0, 0, 6, fill=PROGRESS_F, outline="")
        self.progress_label = tk.Label(prog, text="Готов к работе", bg=BG,
                                        fg=TEXT_DIM, font=("Segoe UI", 10))
        self.progress_label.pack(anchor=tk.W, pady=(4, 0))

        # ─── Лог ────────────────────────────────────────────────
        log_hdr = tk.Frame(self._main_content, bg=BG)
        log_hdr.pack(fill=tk.X, padx=24, pady=(12, 4))
        tk.Label(log_hdr, text="Журнал событий", bg=BG, fg=TEXT_MUTED,
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        _Btn(log_hdr, text="Очистить", bg_color=BG, fg_color=TEXT_MUTED,
             font=("Segoe UI", 8), active_bg=BG_HOVER,
             command=self._clear_log, padx=6, pady=2).pack(side=tk.RIGHT)

        log_inner = tk.Frame(self._main_content, bg=BG, padx=24, pady=4)
        log_inner.pack(fill=tk.BOTH, expand=True)

        log_box = tk.Frame(log_inner, bg=BG_CARD, highlightthickness=1,
                           highlightbackground=BORDER)
        log_box.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_box, bg=BG_CARD, fg=TEXT,
                                font=("Segoe UI", 10), wrap=tk.WORD,
                                bd=0, highlightthickness=0, padx=10, pady=8,
                                selectbackground=ACCENT, selectforeground="#fff",
                                state=tk.DISABLED)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sb = ttk.Scrollbar(log_box, orient=tk.VERTICAL, command=self.log_text.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=sb.set)

        self.log_text.tag_configure("info", foreground=TEXT_DIM)
        self.log_text.tag_configure("success", foreground=GREEN)
        self.log_text.tag_configure("warning", foreground=YELLOW)
        self.log_text.tag_configure("error", foreground=RED)
        self.log_text.tag_configure("title", foreground=ACCENT_LG,
                                    font=("Segoe UI", 10, "bold"))

        self.log("arqParse запущен", "title")

    def _build_settings_page(self, parent):
        """Строит страницу настроек (изначально пустую, заполняется при открытии)."""
        # Заголовок с кнопкой Назад
        hdr = tk.Frame(parent, bg=BG)
        hdr.pack(fill=tk.X, padx=24, pady=(16, 8))

        back_btn = _Btn(hdr, text="← Назад", bg_color=BG, fg_color=ACCENT_LG,
                        font=("Segoe UI", 11, "bold"), active_bg=BG_HOVER,
                        command=self._go_home, padx=4, pady=2)
        back_btn.pack(side=tk.LEFT)

        tk.Label(hdr, text="Настройки", bg=BG, fg=TEXT,
                 font=("Segoe UI", 18, "bold")).pack(anchor=tk.W, padx=(16, 0))

        # Заголовок — просто "Категории"
        tab_row = tk.Frame(parent, bg=BG)
        tab_row.pack(fill=tk.X, padx=24, pady=(0, 8))

        tk.Label(tab_row, text="Категории", bg=BG_CARD, fg=ACCENT_LG,
                 font=("Segoe UI", 10, "bold"), padx=16, pady=6).pack(side=tk.LEFT)

        # Контейнер для контента с прокруткой
        self._settings_content = tk.Frame(parent, bg=BG)
        self._settings_content.pack(fill=tk.BOTH, expand=True, padx=24, pady=0)

        # Canvas + scrollbar
        self._set_canvas = tk.Canvas(self._settings_content, bg=BG, highlightthickness=0)
        self._set_scrollbar = ttk.Scrollbar(self._settings_content, orient=tk.VERTICAL,
                                             command=self._set_canvas.yview)
        self._set_scrollable = tk.Frame(self._set_canvas, bg=BG)

        self._set_canvas.create_window((0, 0), window=self._set_scrollable, anchor="nw")
        self._set_canvas.configure(yscrollcommand=self._set_scrollbar.set)

        # Обновляем scrollregion при изменении контента
        self._set_scrollable.bind("<Configure>", self._on_scrollable_configure)
        # Растягиваем scrollable по ширине canvas
        self._set_canvas.bind("<Configure>", self._on_settings_canvas_configure)

        self._set_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._set_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Прокрутка — bind_all на root, но только когда страница настроек видна
        self.root.bind_all("<MouseWheel>", self._on_set_mousewheel)
        self.root.bind_all("<Button-4>", self._on_set_mousewheel_linux)
        self.root.bind_all("<Button-5>", self._on_set_mousewheel_linux)

        # Контейнер для контента
        self._settings_content_frame = tk.Frame(self._set_scrollable, bg=BG)
        self._settings_content_frame.pack(fill=tk.X)

        # Строим начальное состояние
        self._build_settings_tab_content()

        # Кнопки внизу
        btn_row = tk.Frame(parent, bg=BG)
        btn_row.pack(fill=tk.X, padx=24, pady=(8, 16))

        tk.Label(btn_row, text="", bg=BG).pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Button(btn_row, text="Сбросить", bg=BG_CARD, fg=TEXT_DIM,
                  activebackground=BG_HOVER, activeforeground=TEXT,
                  font=("Segoe UI", 10, "bold"), relief=tk.FLAT,
                  cursor="hand2", command=self._reset_settings, width=12).pack(side=tk.RIGHT, padx=(6, 0))

        tk.Button(btn_row, text="Сохранить", bg=ACCENT, fg="#fff",
                  activebackground=ACCENT_DK, activeforeground="#fff",
                  font=("Segoe UI", 10, "bold"), relief=tk.FLAT,
                  cursor="hand2", command=self._save_settings, width=12).pack(side=tk.RIGHT)

    def _on_scrollable_configure(self, event):
        """Обновляем scrollregion при изменении размера контента."""
        self._set_canvas.configure(scrollregion=self._set_canvas.bbox("all"))
        self._update_scrollbar_visibility()

    def _on_settings_canvas_configure(self, event):
        """Растягиваем scrollable по ширине canvas."""
        self._set_canvas.itemconfig("all", width=event.width)

    def _update_scrollbar_visibility(self):
        """Обновить scrollregion и показать/скрыть скроллбар."""
        self._set_canvas.update_idletasks()
        bbox = self._set_canvas.bbox("all")
        if not bbox:
            return
        x1, y1, x2, y2 = bbox
        content_h = y2 - y1
        canvas_h = self._set_canvas.winfo_height()

        if content_h > canvas_h:
            if not self._set_scrollbar.winfo_viewable():
                self._set_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                self._set_canvas.update_idletasks()
            self._set_canvas.configure(scrollregion=bbox)
        else:
            if self._set_scrollbar.winfo_viewable():
                self._set_scrollbar.pack_forget()
                self._set_canvas.update_idletasks()
            self._set_canvas.configure(scrollregion=bbox)

    def _on_set_mousewheel(self, event):
        """Прокрутка только когда страница настроек активна."""
        if self._current_page == "settings" and self._set_canvas.winfo_viewable():
            direction = 3 if event.delta > 0 else -3
            self._set_canvas.yview_scroll(direction, "units")

    def _on_set_mousewheel_linux(self, event):
        """Прокрутка для Linux."""
        if self._current_page == "settings" and self._set_canvas.winfo_viewable():
            if event.num == 4:
                self._set_canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self._set_canvas.yview_scroll(1, "units")

    def _build_settings_tab_content(self):
        """Построить контент настроек (категории)."""
        # Удаляем старый контент
        for w in self._settings_content_frame.winfo_children():
            w.destroy()

        self._cat_cards = []
        self._settings_content_frame.pack(fill=tk.X)
        # Карточки категорий
        tasks = self._settings.get("tasks", [])
        for td in tasks:
            self._create_category_card(td)
        # Кнопка добавить
        self._add_cat_btn = tk.Label(self._settings_content_frame, text="+ Добавить категорию",
                                      bg=BG, fg=ACCENT_LG, font=("Segoe UI", 10, "bold"),
                                      cursor="hand2")
        self._add_cat_btn.pack(anchor=tk.W, padx=0, pady=(6, 10))
        self._add_cat_btn.bind("<Button-1>", lambda e: self._add_category_card())

        # Скроллим наверх
        self.root.after(50, self._finish_tab_switch)

    def _finish_tab_switch(self):
        """Завершаем переключение вкладки после отрисовки."""
        self._settings_content_frame.update_idletasks()
        self._update_scrollbar_visibility()
        self._set_canvas.yview("moveto", 0.0)

    def _create_category_card(self, task_data):
        """Создать карточку категории."""
        card = {'data': dict(task_data), 'url_rows': []}

        outer = tk.Frame(self._settings_content_frame, bg=BG)

        # Карточка
        body = tk.Frame(outer, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER)
        body.pack(fill=tk.X, pady=(0, 4), ipady=4)

        card['_frame'] = outer
        card['_body'] = body

        # Заголовок
        hdr = tk.Frame(body, bg=BG_CARD)
        hdr.pack(fill=tk.X, padx=10, pady=(10, 4))

        name_entry = tk.Entry(hdr, bg=BG_INPUT, fg=ACCENT_LG,
                               font=("Segoe UI", 11, "bold"),
                               relief=tk.FLAT, bd=0, highlightthickness=1,
                               highlightbackground=BORDER, insertbackground=TEXT)
        name_entry.insert(0, task_data.get("name", ""))
        name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        card['_name_entry'] = name_entry

        del_btn = tk.Label(hdr, text="🗑", bg=BG_CARD, fg=TEXT_MUTED,
                           font=("Segoe UI", 12), cursor="hand2")
        del_btn.pack(side=tk.LEFT, padx=(8, 0))
        del_btn.bind("<Button-1>", lambda e, c=card: self._delete_category_card(c))
        del_btn.bind("<Enter>", lambda e: del_btn.config(fg=RED))
        del_btn.bind("<Leave>", lambda e: del_btn.config(fg=TEXT_MUTED))

        # Тип — кастомный переключатель
        type_row = tk.Frame(body, bg=BG_CARD)
        type_row.pack(fill=tk.X, padx=10, pady=(2, 4))
        tk.Label(type_row, text="Тип:", bg=BG_CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 6))
        type_var = tk.StringVar(value=task_data.get("type", "xray"))
        card['_type_var'] = type_var

        # Кнопки-переключатели xray / mtproto
        type_btns = []

        def _make_type_btn(parent, var, val, text):
            is_active = var.get() == val
            btn = tk.Label(parent, text=text,
                           bg=ACCENT if is_active else BG_INPUT,
                           fg="#fff" if is_active else TEXT_DIM,
                           font=("Segoe UI", 9, "bold" if is_active else "normal"),
                           cursor="hand2", padx=10, pady=3)
            btn._val = val
            btn.pack(side=tk.LEFT, padx=(0, 4))
            btn.bind("<Button-1>", lambda e: _switch_type(val))
            type_btns.append(btn)
            return btn

        def _switch_type(val):
            type_var.set(val)
            for w in type_btns:
                active = type_var.get() == w._val
                w.config(bg=ACCENT if active else BG_INPUT,
                         fg="#fff" if active else TEXT_DIM,
                         font=("Segoe UI", 9, "bold" if active else "normal"))

        _make_type_btn(type_row, type_var, "xray", "Xray")
        _make_type_btn(type_row, type_var, "mtproto", "MTProto")

        # Источники URL
        tk.Label(body, text="Источники (URL):", bg=BG_CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, padx=10, pady=(6, 2))

        urls_fr = tk.Frame(body, bg=BG_CARD)
        urls_fr.pack(fill=tk.X, padx=10)
        card['_urls_frame'] = urls_fr

        for url in task_data.get("urls", []):
            self._add_url_row_to_card(card, url)

        add_url = tk.Label(urls_fr, text="+ Добавить URL", bg=BG_CARD,
                           fg=ACCENT_LG, font=("Segoe UI", 9), cursor="hand2")
        add_url.pack(anchor=tk.W, pady=(4, 6))
        add_url.bind("<Button-1>", lambda e, c=card: self._add_url_row_to_card(c, ""))

        # Целевой URL
        opts = tk.Frame(body, bg=BG_CARD)
        opts.pack(fill=tk.X, padx=10, pady=(4, 0))

        tk.Label(opts, text="Целевой URL:", bg=BG_CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(anchor=tk.W)
        target_entry = tk.Entry(opts, bg=BG_INPUT, fg=TEXT,
                                 font=("Consolas", 9), relief=tk.FLAT,
                                 bd=0, highlightthickness=1,
                                 highlightbackground=BORDER,
                                 insertbackground=TEXT)
        target_entry.insert(0, task_data.get("target_url", "https://google.com"))
        target_entry.pack(fill=tk.X, ipady=3, pady=(2, 6))
        card['_target_entry'] = target_entry

        # Макс пинг и кол-во
        num_row = tk.Frame(opts, bg=BG_CARD)
        num_row.pack(fill=tk.X)

        tk.Label(num_row, text="Макс. пинг (мс):", bg=BG_CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        max_ping = tk.Entry(num_row, bg=BG_INPUT, fg=TEXT,
                             font=("Segoe UI", 10), width=8, relief=tk.FLAT,
                             bd=0, highlightthickness=1,
                             highlightbackground=BORDER,
                             insertbackground=TEXT)
        max_ping.insert(0, str(task_data.get("max_ping_ms", 9000)))
        max_ping.pack(side=tk.LEFT, ipady=3)
        card['_max_ping'] = max_ping

        tk.Label(num_row, text="  Мин. кол-во:", bg=BG_CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(10, 4))
        req_count = tk.Entry(num_row, bg=BG_INPUT, fg=TEXT,
                              font=("Segoe UI", 10), width=5, relief=tk.FLAT,
                              bd=0, highlightthickness=1,
                              highlightbackground=BORDER,
                              insertbackground=TEXT)
        req_count.insert(0, str(task_data.get("required_count", 10)))
        req_count.pack(side=tk.LEFT, ipady=3)
        card['_req_count'] = req_count

        # Имя профиля
        tk.Label(opts, text="Имя профиля:", bg=BG_CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(anchor=tk.W, pady=(6, 2))
        profile_entry = tk.Entry(opts, bg=BG_INPUT, fg=TEXT,
                                  font=("Segoe UI", 10), relief=tk.FLAT,
                                  bd=0, highlightthickness=1,
                                  highlightbackground=BORDER,
                                  insertbackground=TEXT)
        profile_entry.insert(0, task_data.get("profile_title", ""))
        profile_entry.pack(fill=tk.X, ipady=3, pady=(0, 10))
        card['_profile_entry'] = profile_entry

        outer.pack(fill=tk.X, pady=(0, 4))
        self._cat_cards.append(card)

    def _add_url_row_to_card(self, card, url=""):
        """Добавить строку URL в карточку."""
        row = tk.Frame(card['_urls_frame'], bg=BG_CARD)
        row.pack(fill=tk.X, pady=2)

        lbl = tk.Label(row, text="→", bg=BG_CARD, fg=TEXT_DIM,
                       font=("Segoe UI", 9), width=2, anchor=tk.W)
        lbl.pack(side=tk.LEFT, padx=(0, 4))

        entry = tk.Entry(row, bg=BG_INPUT, fg=TEXT, font=("Consolas", 9),
                         relief=tk.FLAT, bd=0, highlightthickness=1,
                         highlightbackground=BORDER, insertbackground=TEXT)
        entry.insert(0, url)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)

        del_btn = tk.Label(row, text="✕", bg=BG_CARD, fg=TEXT_MUTED,
                           font=("Segoe UI", 10), cursor="hand2")
        del_btn.pack(side=tk.LEFT, padx=(4, 0))
        del_btn.bind("<Button-1>", lambda e, en=entry: self._remove_url_row(card, en))
        del_btn.bind("<Enter>", lambda e: del_btn.config(fg=RED))
        del_btn.bind("<Leave>", lambda e: del_btn.config(fg=TEXT_MUTED))

        card['url_rows'].append(entry)

    def _remove_url_row(self, card, entry):
        """Удалить строку URL из карточки."""
        if entry in card['url_rows']:
            card['url_rows'].remove(entry)
        entry.master.destroy()

    def _delete_category_card(self, card):
        """Удалить карточку категории с подтверждением."""
        name = card['_name_entry'].get().strip() or "Без имени"
        if not self._dark_ask("Удалить категорию", f"Удалить «{name}»?"):
            return
        if card in self._cat_cards:
            self._cat_cards.remove(card)
        card['_frame'].pack_forget()

    def _add_category_card(self):
        """Добавить новую категорию."""
        new_task = {
            "name": "Новая категория",
            "type": "xray",
            "urls": [""],
            "target_url": "https://google.com",
            "max_ping_ms": 9000,
            "required_count": 10,
            "profile_title": "",
        }
        self._create_category_card(new_task)
        # Скроллим вниз
        self.root.after(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        self._settings_content_frame.update_idletasks()
        self._update_scrollbar_visibility()
        self._set_canvas.yview("moveto", 1.0)

    def _rebuild_settings_page(self):
        """Перестроить страницу настроек (после сброса)."""
        self._build_settings_tab_content()

    def _save_settings(self):
        """Собрать данные и сохранить."""
        tasks = []
        for card in self._cat_cards:
            name = card['_name_entry'].get().strip()
            if not name:
                continue
            urls = [e.get().strip() for e in card['url_rows'] if e.get().strip()]
            if not urls:
                continue
            try:
                max_ping = int(card['_max_ping'].get().strip())
            except ValueError:
                max_ping = 9000
            try:
                req_count = int(card['_req_count'].get().strip())
            except ValueError:
                req_count = 10

            from config import RAW_CONFIGS_DIR
            raw_files = []
            for u in urls:
                fname = u.split("/")[-1].split("?")[0]
                if fname:
                    raw_files.append(os.path.join(RAW_CONFIGS_DIR, fname))

            profile = card['_profile_entry'].get().strip()
            out_name = name.lower().replace(' ', '_')
            tasks.append({
                "name": name,
                "type": card['_type_var'].get(),
                "urls": urls,
                "raw_files": raw_files,
                "target_url": card['_target_entry'].get().strip(),
                "max_ping_ms": max_ping,
                "required_count": req_count,
                "profile_title": profile,
                "out_file": os.path.join(RESULTS_DIR, f"top_{out_name}.txt"),
            })

        if not tasks:
            messagebox.showwarning("Внимание", "Добавьте хотя бы одну категорию с именем и URL",
                                   parent=self.root)
            return

        settings = {
            "tasks": tasks,
            "user_agent": self._settings.get("user_agent", ""),
        }
        save_settings(settings)
        self._settings = settings
        self._tasks = get_tasks()

        # Перестраиваем чекбоксы на главной
        self._rebuild_task_checkboxes()

        messagebox.showinfo("Сохранено", "Настройки сохранены ✓", parent=self.root)

    def _reset_settings(self):
        """Сбросить настройки к дефолтным."""
        if not self._dark_ask("Сброс настроек", "Сбросить все настройки к значениям по умолчанию?"):
            return
        from settings_manager import _default_settings
        self._settings = _default_settings()
        self._tasks = get_tasks()
        self._rebuild_settings_page()
        self._rebuild_task_checkboxes()
        messagebox.showinfo("Сброшено", "Настройки сброшены", parent=self.root)

    def _rebuild_task_checkboxes(self):
        """Перестроить чекбоксы задач на главной странице."""
        if not hasattr(self, 'check_vars'):
            return
        for widget in self._checkbox_container.winfo_children():
            widget.destroy()
        self.check_vars.clear()
        for task in self._tasks:
            row = tk.Frame(self._checkbox_container, bg=BG_CARD)
            row.pack(fill=tk.X, pady=2)
            var = tk.BooleanVar(value=True)
            self.check_vars[task['name']] = {'var': var, 'task': task}
            cb = tk.Checkbutton(row, text=task['name'], variable=var,
                                bg=BG_CARD, fg=TEXT, selectcolor=BG_INPUT,
                                activebackground=BG_CARD, activeforeground=TEXT,
                                highlightthickness=0, bd=0, font=("Segoe UI", 10))
            cb.pack(side=tk.LEFT)

    # ─── Кастомный прогресс-бар ─────────────────────────────────
    def _get_progress_width(self):
        w = self.progress_canvas.winfo_width()
        if w <= 1:
            self.root.update_idletasks()
            w = self.progress_canvas.winfo_width()
        return max(w, 1)

    def _set_progress_bar(self, pct):
        w = self._get_progress_width()
        self.progress_canvas.coords(self.progress_bar, 0, 0, int(w * pct), 6)

    def update_progress(self, current, total, suitable=0, required=0):
        if required > 0:
            pct = min(suitable / required, 1.0)
            self.progress_label.config(text=f"{suitable}/{required} подходящих  ({int(pct*100)}%)")
        elif total > 0:
            pct = current / total
            self.progress_label.config(text=f"{int(pct*100)}%")
        else:
            pct = 0
        self._set_progress_bar(pct)
        self.root.update()

    def _dark_ask(self, title, message):
        """Диалог в тёмной теме через Toplevel."""
        result = [None]
        dlg = tk.Toplevel(self.root)
        dlg.configure(bg=BG)
        w = tk.Frame(dlg, bg=BG, padx=24, pady=18)
        w.pack(fill=tk.BOTH, expand=True)
        tk.Label(w, text=title, bg=BG, fg=TEXT,
                 font=("Segoe UI", 13, "bold")).pack(pady=(0, 6))
        tk.Label(w, text=message, bg=BG, fg=TEXT_DIM,
                 font=("Segoe UI", 11), wraplength=270,
                 justify=tk.CENTER).pack(pady=(0, 16))
        br = tk.Frame(w, bg=BG)
        br.pack(fill=tk.X)

        def _yes():
            result[0] = True
            dlg.destroy()
        def _no():
            result[0] = False
            dlg.destroy()

        tk.Button(br, text="Отмена", bg=BG_CARD, fg=TEXT_DIM,
                  activebackground=BG_HOVER, activeforeground=TEXT,
                  font=("Segoe UI", 10, "bold"), relief=tk.FLAT,
                  cursor="hand2", command=_no).pack(side=tk.LEFT,
                                                     fill=tk.X, expand=True, padx=(0, 3))
        tk.Button(br, text="Да", bg=ACCENT, fg="#ffffff",
                  activebackground=ACCENT_DK, activeforeground="#ffffff",
                  font=("Segoe UI", 10, "bold"), relief=tk.FLAT,
                  cursor="hand2", command=_yes).pack(side=tk.LEFT,
                                                      fill=tk.X, expand=True, padx=(3, 0))
        dlg.update_idletasks()
        rw = max(dlg.winfo_reqwidth(), 310)
        rh = max(dlg.winfo_reqheight(), 150)
        px = self.root.winfo_x() + (self.root.winfo_width() - rw) // 2
        py = self.root.winfo_y() + (self.root.winfo_height() - rh) // 2
        dlg.geometry(f"{rw}x{rh}+{px}+{py}")
        dlg.update()
        dlg.grab_set()
        self.root.wait_window(dlg)
        return result[0] if result[0] is not None else False

    def _do_logout(self):
        if self._dark_ask("Выход", "Выйти из аккаунта?"):
            auth_module.clear_session()
            self.root.destroy()
            os.execv(sys.executable, [sys.executable] + sys.argv)

    def _clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _copy_sub_url(self):
        try:
            url = auth_module.get_sub_url()
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            self.log("Ссылка подписки скопирована", "success")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e), parent=self.root)

    def _toggle_sub_url(self):
        if self._sub_url_visible:
            self.sub_url_frame.pack_forget()
            self._sub_url_visible = False
        else:
            try:
                url = auth_module.get_sub_url()
                self.sub_url_text.config(state=tk.NORMAL)
                self.sub_url_text.delete("1.0", tk.END)
                self.sub_url_text.insert("1.0", url)
                self.sub_url_text.config(state=tk.DISABLED)
                self.sub_url_frame.pack(fill=tk.X, pady=(6, 0))
                self._sub_url_visible = True
            except Exception as e:
                messagebox.showerror("Ошибка", str(e), parent=self.root)

    def toggle_advanced(self):
        self.advanced_open = not self.advanced_open
        if self.advanced_open:
            self.adv_container.pack(fill=tk.X, after=self.adv_btn)
            self.adv_btn.config(text="▴  Скрыть настройки")
        else:
            self.adv_container.pack_forget()
            self.adv_btn.config(text="▾  Дополнительные настройки")

    # ─── Лог ────────────────────────────────────────────────────
    def log(self, message, tag="info"):
        skip = ("Тестирование ", "Тестирую ")
        if any(message.startswith(p) for p in skip):
            return
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n", tag)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.root.update()

    def _enable_control_buttons(self, running):
        if running:
            self.stop_btn_w._disabled = False
            self.stop_btn_w.config(fg=RED)
            self.skip_btn_w._disabled = False
            self.skip_btn_w.config(fg=YELLOW)
            self.start_btn._disabled = True
            self.start_btn.config(fg=TEXT_DIM)
        else:
            self.stop_btn_w._disabled = True
            self.stop_btn_w.config(fg=TEXT_MUTED)
            self.skip_btn_w._disabled = True
            self.skip_btn_w.config(fg=TEXT_MUTED)
            self.start_btn._disabled = False
            self.start_btn.config(fg="#fff")

    # ─── Скачивание ─────────────────────────────────────────────
    def start_download(self):
        if self.is_running:
            messagebox.showwarning("Внимание", "Операция уже выполняется", parent=self.root)
            return
        self.is_running = True
        self.stop_flag = False
        self.skip_flag = False
        self._enable_control_buttons(True)
        self.progress_label.config(text="Скачивание...")
        self._set_progress(0)
        threading.Thread(target=self._download_thread, daemon=True).start()

    def _set_progress(self, pct):
        self._set_progress_bar(pct / 100)

    def _download_thread(self):
        try:
            self.log("Скачивание конфигов...", "title")
            results = download_all_tasks(self._tasks, max_age_hours=24, force=False, log_func=self.log)
            d = len(results.get('downloaded', []))
            s = len(results.get('skipped', []))
            f = len(results.get('failed', []))
            if d:
                self.log(f"Скачано: {d}", "success")
            if s:
                self.log(f"Пропущено (актуальны): {s}", "info")
            if f:
                self.log(f"Ошибок: {f}", "error")
            self.progress_label.config(text="Скачивание завершено" if d or s else "Файлы не найдены")
        except Exception as e:
            self.log(f"Ошибка: {e}", "error")
        finally:
            self.is_running = False
            self._enable_control_buttons(False)
            self._set_progress(0)
            self.progress_label.config(text="Готово")

    # ─── Полный тест ────────────────────────────────────────────
    def start_full_test(self):
        if self.is_running:
            messagebox.showwarning("Внимание", "Тест уже запущен", parent=self.root)
            return
        sel = [d['task'] for d in self.check_vars.values() if d['var'].get()]
        if not sel:
            messagebox.showwarning("Внимание", "Не выбрано ни одной задачи", parent=self.root)
            return
        self.is_running = True
        self.stop_flag = False
        self.skip_flag = False
        self._enable_control_buttons(True)
        self.progress_label.config(text="Начинаю тестирование...")
        self._set_progress(0)
        threading.Thread(target=self._full_test_thread, args=(sel,), daemon=True).start()

    def _full_test_thread(self, tasks):
        try:
            self.log("Начинаю тестирование", "title")
            user_stopped = False
            for i, task in enumerate(tasks):
                if self.stop_flag:
                    self.log("Тестирование остановлено", "warning")
                    user_stopped = True
                    break
                self.skip_flag = False
                self.stop_event = threading.Event()
                self.skip_event = threading.Event()
                self.log(f"▶  {task['name']}", "title")
                self._test_task(task)
                ws = self.skip_flag
                ws2 = self.stop_flag
                if ws and not ws2:
                    self.log(f"Пропущено: {task['name']}", "warning")
                    self.skip_flag = False
                if ws2:
                    self.log("Тестирование остановлено", "warning")
                    user_stopped = True
                    break
                pct = int((i + 1) / len(tasks) * 100)
                self.update_progress(pct, 100)

            if not user_stopped:
                self.log("Все тесты завершены ✓", "success")
                task_names = [t['name'] for t in tasks]
                vpn_tasks_names = {'Base VPN', 'Bypass VPN'}
                if any(t['name'] in vpn_tasks_names for t in tasks):
                    self.merge_vpn_configs()
                self._ask_update_sub_or_open_folder(tested_tasks=task_names)
            else:
                self.progress_label.config(text="Остановлено")
        except Exception as e:
            self.log(f"Ошибка: {e}", "error")
        finally:
            self.is_running = False
            self._enable_control_buttons(False)
            self._set_progress(0)
            self.progress_label.config(text="Готово")

    # ─── Подписка на сервер ─────────────────────────────────────
    def _upload_subscription(self, tested_tasks=None):
        """Отправляет на сервер только результаты протестированных задач."""
        if not auth_module.is_logged_in():
            return

        all_task_names = [t['name'] for t in self._tasks]
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
                self.log("Файл all_top_vpn.txt не найден — запустите тест VPN", "warning")

        if mt_task:
            mt_file = os.path.join(RESULTS_DIR, "top_telegram_mtproto.txt")
            if os.path.exists(mt_file):
                with open(mt_file, 'r', encoding='utf-8') as f:
                    mt_content = f.read().strip()
            else:
                self.log("Файл MTProto не найден — запустите тест MTProto", "warning")

        if not vpn_content and not mt_content:
            self.log("Нет результатов для отправки", "info")
            return

        def up():
            try:
                msgs = []
                if vpn_content:
                    auth_module.update_subscription(vpn_content)
                    msgs.append("VPN ✓")
                if mt_content:
                    auth_module.update_mtproto(mt_content)
                    msgs.append("MTProto ✓")
                if msgs:
                    self.root.after(0, lambda: self.log(
                        f"Подписка обновлена: {', '.join(msgs)}", "success"
                    ))
            except auth_module.AuthError as e:
                self.root.after(0, lambda e=e: self.log(f"Ошибка авторизации: {e}", "error"))
            except Exception as e:
                self.root.after(0, lambda e=e: self.log(f"Ошибка отправки: {e}", "error"))

        threading.Thread(target=up, daemon=True).start()

    # ─── Тест задачи ────────────────────────────────────────────
    def _test_task(self, task):
        self.log("Чтение конфигов...", "info")
        if self.stop_event is None:
            self.stop_event = threading.Event()
        if self.skip_event is None:
            self.skip_event = threading.Event()

        if task['type'] == 'xray':
            configs = []
            for rf in task['raw_files']:
                if os.path.exists(rf):
                    configs.extend(read_configs_from_file(rf))
            if not configs:
                self.log("Конфиги не найдены", "warning")
                return
            self.log(f"Найдено конфигов: {len(configs)}", "info")
            _, passed, _ = test_xray_configs(
                configs=configs, target_url=task['target_url'],
                max_ping_ms=task['max_ping_ms'], required_count=task['required_count'],
                log_func=self.log, progress_func=self._progress_callback,
                out_file=task['out_file'], profile_title=task['profile_title'],
                config_type=task['name'], stop_flag=self.stop_event, skip_flag=self.skip_event,
            )
            self.log(f"Результат: ✓ {passed} рабочих", "success")

        elif task['type'] == 'mtproto':
            configs = read_mtproto_from_file(task['raw_files'][0]) if os.path.exists(task['raw_files'][0]) else []
            if not configs:
                self.log("MTProto конфиги не найдены", "warning")
                return
            self.log(f"Найдено MTProto: {len(configs)}", "info")
            working, passed, failed = test_mtproto_configs_and_save(
                configs=configs, max_ping_ms=task['max_ping_ms'],
                required_count=task['required_count'], out_file=task['out_file'],
                profile_title=task['profile_title'], log_func=self.log,
                progress_func=self._progress_callback,
                stop_flag=self.stop_event, skip_flag=self.skip_event,
            )
            self.log(f"Результат MTProto: ✓ {passed} ({working} проверено, {failed} отказов)", "success")

        self.stop_event = None
        self.skip_event = None

    def _progress_callback(self, current, total, suitable=0, required=0):
        self.update_progress(current, total, suitable, required)

    def skip_file(self):
        self.skip_flag = True
        if self.skip_event:
            self.skip_event.set()
        self.log("Пропуск текущего файла...", "warning")

    def stop_operation(self):
        self.stop_flag = True
        if self.stop_event:
            self.stop_event.set()
        self.log("Остановка тестирования...", "warning")

    def open_results(self):
        try:
            if sys.platform == "win32":
                os.startfile(RESULTS_DIR)
            elif sys.platform == "darwin":
                os.system(f"open {RESULTS_DIR}")
            else:
                os.system(f"xdg-open {RESULTS_DIR}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e), parent=self.root)

    def merge_vpn_configs(self):
        tv = os.path.join(RESULTS_DIR, "top_base_vpn.txt")
        tb = os.path.join(RESULTS_DIR, "top_bypass_vpn.txt")
        av = os.path.join(RESULTS_DIR, "all_top_vpn.txt")
        try:
            ac = []
            for fp in [tv, tb]:
                if os.path.exists(fp):
                    with open(fp, 'r', encoding='utf-8') as f:
                        for l in f:
                            l = l.strip()
                            if l and not l.startswith('#'):
                                ac.append(l)
            seen, cfgs = set(), []
            for c in ac:
                k = c.split('#')[0].strip()
                if k not in seen:
                    seen.add(k)
                    cfgs.append(c)
            if cfgs:
                os.makedirs(os.path.dirname(os.path.abspath(av)), exist_ok=True)
                with open(av, 'w', encoding='utf-8') as f:
                    f.write("#profile-title: arqVPN Free | Все\n")
                    f.write("#profile-update-interval: 48\n")
                    f.write("#support-url: https://t.me/arqhub\n\n")
                    for c in cfgs:
                        f.write(f"{c}\n")
                self.log(f"Объединено {len(cfgs)} конфигов в all_top_vpn.txt", "success")
        except Exception as e:
            self.log(f"Ошибка объединения: {e}", "error")

    def _ask_update_sub_or_open_folder(self, tested_tasks=None):
        """После теста спрашивает: обновить подписку/GitHub. Если нет — открыть папку."""
        def _do():
            session = auth_module.get_session()
            username = session.get("username") if session else None
            if username == "admin":
                if self._dark_ask("GitHub", "Обновить результаты в репозитории GitHub?"):
                    threading.Thread(target=self._push_to_github_thread, daemon=True).start()
                else:
                    self.open_results()
                return
            if not auth_module.is_logged_in():
                self.open_results()
                return
            if self._dark_ask("Подписка", "Обновить вашу подписку на сервере?"):
                self._upload_subscription(tested_tasks=tested_tasks)
            else:
                self.open_results()
        self.root.after(0, _do)

    def _push_to_github_thread(self):
        try:
            self.log("Обновление репозитория...", "title")
            pd = os.path.dirname(os.path.abspath(__file__))
            rfs = []
            for fn in ["top_base_vpn.txt", "top_bypass_vpn.txt", "top_telegram_mtproto.txt", "all_top_vpn.txt"]:
                fp = os.path.join(RESULTS_DIR, fn)
                if os.path.exists(fp):
                    rfs.append(fp)
            if not rfs:
                self.log("Нет файлов", "warning")
                return
            for fp in rfs:
                subprocess.run(["git", "add", fp], check=True, capture_output=True, cwd=pd)
            sr = subprocess.run(["git", "status", "--porcelain"], capture_output=True,
                                text=True, check=True, cwd=pd)
            if not sr.stdout.strip():
                self.log("Нет изменений", "warning")
                return
            cm = f"Update results - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            subprocess.run(["git", "commit", "-m", cm], check=True, capture_output=True, cwd=pd)
            pr = subprocess.run(["git", "push"], capture_output=True, text=True, cwd=pd)
            if pr.returncode == 0:
                self.log("Обновлено на GitHub ✓", "success")
            else:
                self.log(f"Ошибка push: {pr.stderr.strip()}", "error")
        except Exception as e:
            self.log(f"Ошибка: {e}", "error")


def main():
    root = tk.Tk()
    app = ArcParseGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

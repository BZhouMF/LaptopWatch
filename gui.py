import sys
import os
import time
import subprocess
from config import config
from utils.process_utils import (
    get_local_ip, check_port, force_kill_port, find_parent_pid,
    stop_process_gracefully, save_session_logs, filter_alive_pids
)
import threading
import queue
import webbrowser
import uuid
import datetime
import json
import urllib.request
import urllib.error
from pathlib import Path
from tkinter import filedialog
try:
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText
except Exception:
    raise
try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
try:
    import qrcode
except Exception:
    qrcode = None

# ==================== 打包兼容核心逻辑 ====================
if len(sys.argv) > 1 and sys.argv[1] == 'run_app':
    try:
        if getattr(sys, 'frozen', False):
            base_path = Path(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))))
            app_path = base_path / 'app.py'
        else:
            app_path = Path(__file__).with_name('app.py')
        if not app_path.exists():
            print(f"[ERROR] 致命错误：找不到app.py文件，路径：{app_path}")
            sys.exit(1)
        with open(app_path, 'r', encoding='utf-8') as f:
            exec(f.read(), globals(), locals())
    except Exception as e:
        print(f"[ERROR] 服务启动失败：{str(e)}")
    finally:
        sys.exit(0)
# ==================== 打包兼容逻辑结束 ====================

class AppLauncher(tk.Tk):
    def __init__(self):
        super().__init__()
        # 设置窗口图标（同时作用于标题栏和任务栏）
        if getattr(sys, 'frozen', False):
            ico_path = Path(getattr(sys, '_MEIPASS', '')) / 'BB.ico'
        else:
            ico_path = Path(__file__).parent / 'BB.ico'
        if ico_path.exists():
            self.iconbitmap(str(ico_path))
        self.title('LaptopWatch')
        self.geometry('1000x780')
        self.resizable(True, True)
        self.minsize(800, 600)
        self.protocol('WM_DELETE_WINDOW', self._on_close)  # 这里调用 _on_close
        self.process = None
        self.process_pid = None
        self.qid_process = None
        self._external_synced = False
        self.log_queue = queue.Queue()
        self.log_thread = None
        # 会话日志记录
        self.session_logs = []
        self.session_start_time = None
        self.session_id = None
        self._qid_log_count = 0  # 已从 qid 拉取的日志数量，用于增量同步
        self._push_queue = queue.Queue()  # 日志推送队列，后台线程消费
        self._session_logs_lock = threading.Lock()  # 保护 session_logs 跨线程访问
        self._start_push_worker()

        # 创建日志目录
        logs_dir = Path('logs')
        logs_dir.mkdir(exist_ok=True, parents=True)

        # 配置变量
        self.mode_var = tk.StringVar(value='normal')
        self.media_dir_var = tk.StringVar(value='')
        self.sort_type_var = tk.StringVar(value='name')
        self.sort_order_var = tk.StringVar(value='asc')
        # ==================== 新增：随机模式变量 ====================
        self.random_var = tk.BooleanVar(value=False)
        # ==================== 新增结束 ====================
        # 抖音随机媒体变量
        self.douyin_random_media_var = tk.BooleanVar(value=False)
        # 目录浏览模式变量
        self.category_browse_var = tk.BooleanVar(value=False)

        # 设置现代样式
        self._setup_styles()

        self._create_widgets()
        self._poll_log_queue()
        self._on_mode_change()
        self._poll_service_status()
        self._check_qid_status()

    def _setup_styles(self):
        """与 qid.html 一致的极简浅色风格"""
        style = ttk.Style(self)
        style.theme_use('clam')

        page_bg      = '#f8fafc'
        card_bg      = '#ffffff'
        border_color = '#e2e8f0'
        accent       = '#3b82f6'
        accent_hover = '#2563eb'
        success      = '#10b981'
        success_hover= '#059669'
        danger       = '#ef4444'
        danger_hover = '#dc2626'
        text_primary = '#0f172a'
        text_second  = '#64748b'
        text_muted   = '#94a3b8'
        disabled_bg  = '#f1f5f9'
        disabled_text= '#cbd5e1'
        entry_bg     = '#f8fafc'

        self.configure(bg=page_bg)

        style.configure('Page.TFrame', background=page_bg)
        style.configure('Card.TFrame', background=card_bg)
        style.configure('Card.TLabelframe', background=card_bg, relief='solid',
                        borderwidth=1, bordercolor=border_color)
        style.configure('Card.TLabelframe.Label', background=card_bg,
                        foreground=text_second, font=('Segoe UI', 11, 'bold'))

        style.configure('Title.TLabel', background=page_bg, foreground=text_primary,
                        font=('Segoe UI', 22, 'bold'))
        style.configure('Subtitle.TLabel', background=page_bg, foreground=text_second,
                        font=('Segoe UI', 10))
        style.configure('TLabel', background=card_bg, foreground=text_primary,
                        font=('Segoe UI', 10))
        style.configure('Page.TLabel', background=page_bg, foreground=text_primary,
                        font=('Segoe UI', 10))
        style.configure('Muted.TLabel', background=card_bg, foreground=text_muted,
                        font=('Segoe UI', 9))
        style.configure('TSeparator', background=border_color)

        # Accent 按钮（蓝色）
        style.configure('Accent.TButton', background=accent, foreground='#ffffff',
                        borderwidth=0, focusthickness=0, font=('Segoe UI', 11, 'bold'),
                        padding=(20, 10))
        style.map('Accent.TButton',
                  background=[('active', accent_hover), ('pressed', accent),
                             ('disabled', disabled_bg)],
                  foreground=[('disabled', disabled_text)])

        # 次要按钮（浅灰）
        style.configure('Secondary.TButton', background=page_bg,
                        foreground=text_primary, borderwidth=1, bordercolor=border_color,
                        focusthickness=0, font=('Segoe UI', 10), padding=(14, 7))
        style.map('Secondary.TButton',
                  background=[('active', disabled_bg), ('pressed', page_bg),
                             ('disabled', disabled_bg)],
                  foreground=[('disabled', disabled_text)])

        # 成功按钮（绿色启动）
        style.configure('Success.TButton', background=success, foreground='#ffffff',
                        borderwidth=0, focusthickness=0, font=('Segoe UI', 11, 'bold'),
                        padding=(20, 10))
        style.map('Success.TButton',
                  background=[('active', success_hover), ('pressed', success),
                             ('disabled', disabled_bg)],
                  foreground=[('disabled', disabled_text)])

        # 危险按钮（红色停止）
        style.configure('Danger.TButton', background=danger, foreground='#ffffff',
                        borderwidth=0, focusthickness=0, font=('Segoe UI', 11, 'bold'),
                        padding=(20, 10))
        style.map('Danger.TButton',
                  background=[('active', danger_hover), ('pressed', danger),
                             ('disabled', disabled_bg)],
                  foreground=[('disabled', disabled_text)])

        # Entry — qid.html .input 风格
        style.configure('TEntry', fieldbackground=entry_bg, foreground=text_primary,
                        borderwidth=1, relief='solid', bordercolor=border_color,
                        padding=8, font=('Segoe UI', 10))
        style.map('TEntry',
                  bordercolor=[('focus', accent), ('disabled', border_color)],
                  fieldbackground=[('disabled', disabled_bg)],
                  foreground=[('disabled', disabled_text)])

        # Combobox
        style.configure('TCombobox', fieldbackground=entry_bg, foreground=text_primary,
                        borderwidth=1, relief='solid', bordercolor=border_color,
                        padding=8, arrowsize=14, font=('Segoe UI', 10))
        style.map('TCombobox', bordercolor=[('focus', accent)])

        # 状态栏
        style.configure('StatusBar.TFrame', background=disabled_bg, relief='flat')
        style.configure('Status.TLabel', background=disabled_bg,
                        foreground=text_second, font=('Segoe UI', 9))

        self.style = style
        self.page_bg = page_bg
        self.card_bg = card_bg
        self.accent_color = accent
        self.border_color = border_color
        self.text_primary = text_primary
        self.text_secondary = text_second
        self.text_muted = text_muted
        self.status_bar_bg = disabled_bg
        self.success_color = success
        self.warning_color = '#f59e0b'
        self.danger_color = danger
        self._disabled_bg = disabled_bg
        self._disabled_text = disabled_text

    def _set_mode(self, mode):
        """模式按钮点击：更新变量 + UI + 触发回调"""
        self.mode_var.set(mode)
        self._update_mode_buttons()
        self._on_mode_change()

    def _update_mode_buttons(self):
        """更新分段按钮选中状态"""
        current = self.mode_var.get()
        for name, btn in self._mode_buttons.items():
            if name == current:
                btn.config(bg=self.accent_color, fg='#ffffff',
                           activebackground=self.accent_color,
                           activeforeground='#ffffff')
            else:
                btn.config(bg=self.card_bg, fg=self.text_secondary,
                           activebackground=self.page_bg,
                           activeforeground=self.accent_color)

    def _create_widgets(self):
        """标签页布局：控制台 / 日志 两个标签页"""
        self.configure(bg=self.page_bg)

        # ===== 标签栏 =====
        tab_bar = tk.Frame(self, bg=self.page_bg)
        tab_bar.pack(fill='x', padx=16, pady=(12, 0))

        tabs_holder = tk.Frame(tab_bar, bg=self.page_bg)
        tabs_holder.pack(side='left')

        self._tab_buttons = {}
        for tab_id, tab_label in [('console', '控制台'), ('logs', '日志')]:
            btn = tk.Button(tabs_holder, text=tab_label, font=('Segoe UI', 11),
                            relief='flat', borderwidth=0, padx=20, pady=7,
                            cursor='hand2',
                            command=lambda t=tab_id: self._switch_tab(t))
            btn.pack(side='left')
            self._tab_buttons[tab_id] = btn

        # 状态徽章（标签栏右侧）
        self.status_badge = tk.Frame(tab_bar, bg=self._disabled_bg)
        self.status_badge.pack(side='right', pady=3)
        self.status_canvas = tk.Canvas(self.status_badge, width=8, height=8,
                                        bg=self._disabled_bg, highlightthickness=0)
        self.status_canvas.pack(side='left', padx=(8, 5), pady=5)
        self._status_dot_id = self.status_canvas.create_oval(1, 1, 7, 7,
                                                              fill=self.text_muted, outline='')
        self.status_var = tk.StringVar(value='未运行')
        tk.Label(self.status_badge, textvariable=self.status_var, bg=self._disabled_bg,
                 fg=self.text_secondary, font=('Segoe UI', 9)).pack(
                 side='left', padx=(0, 8), pady=3)

        # 标签栏底部分隔线
        tab_sep = tk.Frame(self, bg=self.border_color, height=1)
        tab_sep.pack(fill='x', padx=16)

        # ===== 内容区域 =====
        self.content_area = tk.Frame(self, bg=self.page_bg)
        self.content_area.pack(fill='both', expand=True, padx=16, pady=(0, 0))

        # ---- 控制台标签页 ----
        self.console_frame = tk.Frame(self.content_area, bg=self.page_bg)
        self.console_frame.place(relwidth=1, relheight=1)

        console_canvas = tk.Canvas(self.console_frame, bg=self.page_bg,
                                    highlightthickness=0)
        console_canvas.pack(side='left', fill='both', expand=True)
        console_content = tk.Frame(console_canvas, bg=self.page_bg)
        console_canvas.create_window((0, 0), window=console_content,
                                       anchor='nw', tags='inner')
        console_content.bind('<Configure>', lambda e: console_canvas.configure(
            scrollregion=console_canvas.bbox('all')))

        def _on_canvas_resize(event):
            event.widget.itemconfig('inner', width=event.width)
        console_canvas.bind('<Configure>', _on_canvas_resize)

        def _bind_mwheel(c):
            c.bind('<MouseWheel>', lambda e: c.yview_scroll(
                -1 * (e.delta // 120), 'units'))
        _bind_mwheel(console_canvas)

        # 卡片网格
        console_content.grid_columnconfigure(0, weight=1)
        console_content.grid_columnconfigure(1, weight=1)

        gutter = 12
        card_pad = {'padx': 14, 'pady': (10, 14)}

        # ---- 卡片1：运行模式（全宽）----
        mode_card = ttk.LabelFrame(console_content, text='运行模式',
                                    style='Card.TLabelframe')
        mode_card.grid(row=0, column=0, columnspan=2, sticky='ew',
                       padx=14, pady=(12, gutter))
        mode_inner = tk.Frame(mode_card, bg=self.card_bg)
        mode_inner.pack(fill='x', **card_pad)

        seg_frame = tk.Frame(mode_inner, bg=self.border_color)
        seg_frame.pack(fill='x')
        for i in range(4):
            seg_frame.grid_columnconfigure(i, weight=1, uniform='mode_seg')

        self._mode_buttons = {}
        modes = [('normal', '普通'), ('video', '视频'),
                 ('image', '图片'), ('douyin', '抖音')]
        for idx, (val, label) in enumerate(modes):
            btn = tk.Button(seg_frame, text=label, font=('Segoe UI', 10),
                            relief='flat', borderwidth=0,
                            bg=self.card_bg, fg=self.text_secondary,
                            activebackground=self.card_bg,
                            activeforeground=self.accent_color,
                            cursor='hand2', padx=8, pady=7,
                            command=lambda v=val: self._set_mode(v))
            btn.grid(row=0, column=idx, sticky='ew',
                     padx=(0, 1) if idx < 3 else (0, 0), pady=1)
            self._mode_buttons[val] = btn
        self._update_mode_buttons()

        # ---- 卡片2：媒体配置（左）----
        self.media_card = ttk.LabelFrame(console_content, text='媒体配置',
                                          style='Card.TLabelframe')
        self.media_card.grid(row=1, column=0, sticky='nsew',
                             padx=(14, gutter // 2), pady=(0, gutter))
        self.media_inner = tk.Frame(self.media_card, bg=self.card_bg)
        self.media_inner.pack(fill='x', **card_pad)

        tk.Label(self.media_inner, text='媒体目录', bg=self.card_bg,
                 fg=self.text_secondary, font=('Segoe UI', 9),
                 anchor='w').pack(anchor='w', pady=(0, 4))
        dir_row = tk.Frame(self.media_inner, bg=self.card_bg)
        dir_row.pack(fill='x', pady=(0, 8))
        self.dir_entry = ttk.Entry(dir_row, textvariable=self.media_dir_var)
        self.dir_entry.pack(side='left', fill='x', expand=True, padx=(0, 6))
        self.dir_btn = ttk.Button(dir_row, text='浏览', style='Secondary.TButton',
                                   command=self._select_media_dir, width=6)
        self.dir_btn.pack(side='left')

        tk.Label(self.media_inner, text='排序规则', bg=self.card_bg,
                 fg=self.text_secondary, font=('Segoe UI', 9),
                 anchor='w').pack(anchor='w', pady=(0, 4))
        sort_row = tk.Frame(self.media_inner, bg=self.card_bg)
        sort_row.pack(fill='x', pady=(0, 8))
        self.sort_type_combo = ttk.Combobox(sort_row, textvariable=self.sort_type_var,
                                            values=['按名称', '按时间'],
                                            width=14, state='readonly')
        self.sort_type_combo.bind('<<ComboboxSelected>>',
                                   lambda e: self._fix_sort_type())
        self.sort_type_combo.current(0)
        self.sort_type_combo.pack(side='left', padx=(0, 6))
        self.sort_order_combo = ttk.Combobox(sort_row, textvariable=self.sort_order_var,
                                              values=['升序', '降序'],
                                              width=8, state='readonly')
        self.sort_order_combo.bind('<<ComboboxSelected>>',
                                    lambda e: self._fix_sort_order())
        self.sort_order_combo.current(0)
        self.sort_order_combo.pack(side='left')

        check_row = tk.Frame(self.media_inner, bg=self.card_bg)
        check_row.pack(fill='x')
        self.random_check = tk.Checkbutton(
            check_row, text='随机位置', variable=self.random_var,
            bg=self.card_bg, fg=self.text_primary, font=('Segoe UI', 10),
            selectcolor=self.card_bg, activebackground=self.card_bg,
            activeforeground=self.text_primary, state='disabled',
            command=self._on_random_check_toggle)
        self.random_check.pack(side='left', padx=(0, 12))
        self.douyin_random_media_check = tk.Checkbutton(
            check_row, text='随机媒体', variable=self.douyin_random_media_var,
            bg=self.card_bg, fg=self.text_primary, font=('Segoe UI', 10),
            selectcolor=self.card_bg, activebackground=self.card_bg,
            activeforeground=self.text_primary, state='disabled',
            command=self._on_random_media_check_toggle)
        self.douyin_random_media_check.pack(side='left', padx=(0, 12))
        self.category_browse_check = tk.Checkbutton(
            check_row, text='目录浏览', variable=self.category_browse_var,
            bg=self.card_bg, fg=self.text_primary, font=('Segoe UI', 10),
            selectcolor=self.card_bg, activebackground=self.card_bg,
            activeforeground=self.text_primary, state='disabled',
            command=self._on_category_browse_check_toggle)
        self.category_browse_check.pack(side='left')

        # ---- 卡片3：服务控制（右）----
        svc_card = ttk.LabelFrame(console_content, text='服务控制',
                                   style='Card.TLabelframe')
        svc_card.grid(row=1, column=1, sticky='nsew',
                      padx=(gutter // 2, 14), pady=(0, gutter))
        svc_inner = tk.Frame(svc_card, bg=self.card_bg)
        svc_inner.pack(fill='both', expand=True, **card_pad)
        svc_center = tk.Frame(svc_inner, bg=self.card_bg)
        svc_center.pack(expand=True)
        self.start_btn = ttk.Button(svc_center, text='启动服务',
                                     style='Success.TButton',
                                     command=self.start_app)
        self.start_btn.pack(fill='x', pady=(0, 10))
        self.stop_btn = ttk.Button(svc_center, text='停止服务',
                                    style='Danger.TButton',
                                    command=self.stop_app, state='disabled')
        self.stop_btn.pack(fill='x')

        # ---- 卡片4：管理台（左）----
        mgmt_card = ttk.LabelFrame(console_content, text='管理台',
                                    style='Card.TLabelframe')
        mgmt_card.grid(row=2, column=0, sticky='nsew',
                       padx=(14, gutter // 2), pady=(0, gutter))
        mgmt_inner = tk.Frame(mgmt_card, bg=self.card_bg)
        mgmt_inner.pack(fill='x', **card_pad)

        self.qid_status_var = tk.StringVar(value='未启动')
        tk.Label(mgmt_inner, textvariable=self.qid_status_var, bg=self.card_bg,
                 fg=self.text_muted, font=('Segoe UI', 9)).pack(
                 anchor='w', pady=(0, 8))

        qid_btn_row = tk.Frame(mgmt_inner, bg=self.card_bg)
        qid_btn_row.pack(fill='x')
        for i in range(3):
            qid_btn_row.grid_columnconfigure(i, weight=1, uniform='qid_btn')
        self.qid_start_btn = ttk.Button(qid_btn_row, text='启动',
                                         style='Accent.TButton',
                                         command=self.start_qid)
        self.qid_start_btn.grid(row=0, column=0, sticky='ew', padx=(0, 4))
        self.qid_stop_btn = ttk.Button(qid_btn_row, text='停止',
                                        style='Secondary.TButton',
                                        command=self.stop_qid, state='disabled')
        self.qid_stop_btn.grid(row=0, column=1, sticky='ew', padx=(4, 4))
        self.qid_open_btn = ttk.Button(qid_btn_row, text='打开',
                                        style='Secondary.TButton',
                                        command=self.open_qid_browser,
                                        state='disabled')
        self.qid_open_btn.grid(row=0, column=2, sticky='ew', padx=(4, 0))

        # ---- 卡片5：访问信息（右）----
        access_card = ttk.LabelFrame(console_content, text='访问信息',
                                      style='Card.TLabelframe')
        access_card.grid(row=2, column=1, sticky='nsew',
                         padx=(gutter // 2, 14), pady=(0, gutter))
        access_inner = tk.Frame(access_card, bg=self.card_bg)
        access_inner.pack(fill='x', **card_pad)

        qr_holder = tk.Frame(access_inner, bg='#ffffff',
                             highlightbackground=self.border_color,
                             highlightthickness=1)
        qr_holder.pack(pady=(0, 10))
        self.qr_label = tk.Label(qr_holder, text='启动服务后\n显示二维码',
                                  font=('Segoe UI', 9), fg=self.text_muted,
                                  bg='#ffffff')
        self.qr_label.pack(padx=12, pady=12)

        self.url_var = tk.StringVar(value='—')
        self.url_entry = ttk.Entry(access_inner, textvariable=self.url_var,
                                    state='readonly')
        self.url_entry.pack(fill='x', pady=(0, 8))
        self.open_btn = ttk.Button(access_inner, text='在浏览器中打开',
                                    style='Secondary.TButton',
                                    command=self.open_browser, state='disabled')
        self.open_btn.pack(fill='x')

        # 控制台底部留白
        tk.Frame(console_content, bg=self.page_bg, height=16).grid(
            row=3, column=0, columnspan=2)

        # ---- 日志标签页 ----
        self.logs_frame = tk.Frame(self.content_area, bg=self.card_bg)
        self.logs_frame.place(relwidth=1, relheight=1)
        self.logs_frame.grid_rowconfigure(0, weight=1)
        self.logs_frame.grid_columnconfigure(0, weight=1)

        log_inner = tk.Frame(self.logs_frame, bg=self.card_bg)
        log_inner.grid(row=0, column=0, sticky='nsew', padx=14, pady=14)
        log_inner.grid_rowconfigure(0, weight=1)
        log_inner.grid_columnconfigure(0, weight=1)

        self.log_text = ScrolledText(log_inner, state='disabled', wrap='word',
                                      font=('Consolas', 10),
                                      background='#0f172a', foreground='#e2e8f0',
                                      insertbackground='#e2e8f0',
                                      selectbackground='#334155',
                                      borderwidth=0, relief='flat',
                                      padx=12, pady=10)
        self.log_text.grid(row=0, column=0, sticky='nsew')
        self._style_log_scrollbar()
        self.log_text.tag_config('error', foreground='#f87171')
        self.log_text.tag_config('warn', foreground='#fbbf24')
        self.log_text.tag_config('ok', foreground='#34d399')
        self.log_text.tag_config('dim', foreground='#64748b')
        self.log_text.tag_config('accent', foreground='#818cf8')

        # ===== 底部状态栏 =====
        bottom = tk.Frame(self, bg=self.status_bar_bg, height=28)
        bottom.pack(side='bottom', fill='x')
        self.status_label = tk.Label(bottom, text='就绪', bg=self.status_bar_bg,
                                      fg=self.text_secondary,
                                      font=('Segoe UI', 9), anchor='w')
        self.status_label.pack(side='left', padx=(12, 0), pady=4)
        self.status_runtime_label = tk.Label(bottom, text='', bg=self.status_bar_bg,
                                              fg=self.text_muted,
                                              font=('Segoe UI', 9), anchor='e')
        self.status_runtime_label.pack(side='right', padx=(0, 12), pady=4)

        # 默认选中控制台标签
        self._switch_tab('console')

    def _switch_tab(self, tab_id):
        """切换标签页"""
        for tid, btn in self._tab_buttons.items():
            if tid == tab_id:
                btn.config(bg=self.card_bg, fg=self.text_primary,
                           activebackground=self.card_bg,
                           activeforeground=self.text_primary)
            else:
                btn.config(bg=self.page_bg, fg=self.text_muted,
                           activebackground=self.page_bg,
                           activeforeground=self.text_secondary)
        if tab_id == 'console':
            self.console_frame.tkraise()
        else:
            self.logs_frame.tkraise()

    def _style_log_scrollbar(self):
        """深色滚动条"""
        log_frame = self.log_text.master
        log_frame.configure(background='#0f172a')
        for child in log_frame.winfo_children():
            try:
                child.configure(
                    background='#1e293b', troughcolor='#0f172a',
                    activebackground='#334155', borderwidth=0, width=8)
            except Exception:
                pass

    def _fix_sort_type(self):
        mapping = {'按名称': 'name', '按时间': 'time'}
        self.sort_type_var.set(mapping.get(self.sort_type_combo.get(), 'name'))

    def _fix_sort_order(self):
        mapping = {'升序': 'asc', '降序': 'desc'}
        self.sort_order_var.set(mapping.get(self.sort_order_combo.get(), 'asc'))

    def _on_random_check_toggle(self):
        """随机起始位置被选中时，取消随机媒体"""
        if self.random_var.get():
            self.douyin_random_media_var.set(False)

    def _on_random_media_check_toggle(self):
        """随机媒体被选中时，取消随机起始位置并禁用排序规则"""
        if self.douyin_random_media_var.get():
            self.random_var.set(False)
            sort_state = 'disabled'
        else:
            sort_state = 'normal'
        self.sort_type_combo.config(state=sort_state)
        self.sort_order_combo.config(state=sort_state)

    def _on_category_browse_check_toggle(self):
        """目录浏览模式与随机位置不互斥，无需额外逻辑"""
        pass

    def _disable_config_controls(self):
        """启动服务后禁用所有配置控件"""
        for btn in self._mode_buttons.values():
            btn.config(state='disabled')
        self.dir_entry.config(state='disabled')
        self.dir_btn.config(state='disabled')
        self.sort_type_combo.config(state='disabled')
        self.sort_order_combo.config(state='disabled')
        self.random_check.config(state='disabled')
        self.douyin_random_media_check.config(state='disabled')
        self.category_browse_check.config(state='disabled')

    def _enable_config_controls(self):
        """停止服务后启用所有配置控件"""
        for btn in self._mode_buttons.values():
            btn.config(state='normal')
        self._on_mode_change()

    def _on_mode_change(self):
        current_mode = self.mode_var.get()
        is_media_mode = current_mode in ['video', 'image']
        is_douyin_mode = current_mode == 'douyin'
        is_any_media_mode = is_media_mode or is_douyin_mode
        is_sort_irrelevant = is_douyin_mode and self.douyin_random_media_var.get()

        base_state = 'normal' if is_any_media_mode else 'disabled'
        self.dir_entry.config(state=base_state)
        self.dir_btn.config(state=base_state)

        sort_state = 'normal' if (is_any_media_mode and not is_sort_irrelevant) else 'disabled'
        self.sort_type_combo.config(state=sort_state)
        self.sort_order_combo.config(state=sort_state)
        self.random_check.config(state=sort_state)

        douyin_media_state = 'normal' if is_douyin_mode else 'disabled'
        self.douyin_random_media_check.config(state=douyin_media_state)

        category_browse_state = 'normal' if is_media_mode else 'disabled'
        self.category_browse_check.config(state=category_browse_state)

        if not is_any_media_mode:
            self.media_dir_var.set('')
            self.sort_type_var.set('name')
            self.sort_order_var.set('asc')
            self.sort_type_combo.current(0)
            self.sort_order_combo.current(0)
            self.random_var.set(False)
            self.douyin_random_media_var.set(False)

    def _select_media_dir(self):
        dir_path = filedialog.askdirectory(title='请选择包含视频或图片的文件夹')
        if dir_path:
            self.media_dir_var.set(dir_path)

    def start_app(self):
        if getattr(sys, 'frozen', False):
            base_path = Path(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))))
            APP_PY = base_path / 'app.py'
        else:
            APP_PY = Path(__file__).with_name('app.py')
        PYEXE = sys.executable

        if not APP_PY.exists():
            self._append_log('[ERROR] 错误：无法找到 app.py，请确保文件和gui.py在同一目录下')
            return
        if self.process is not None:
            self._append_log('[WARN] 服务已在运行中')
            return
        current_mode = self.mode_var.get()
        if current_mode in ['video', 'image', 'douyin']:
            if not self.media_dir_var.get():
                self._append_log('[ERROR] 错误：请先选择媒体目录')
                return
            if not Path(self.media_dir_var.get()).exists():
                self._append_log(f'[ERROR] 错误：目录不存在：{self.media_dir_var.get()}')
                return

        # ==================== 新增：初始化会话日志 ====================
        self.session_logs = []
        self.session_start_time = datetime.datetime.now()
        self.session_id = str(uuid.uuid4())[:8]  # 使用UUID前8位作为简短标识
        self._append_log(f' 会话ID: {self.session_id} | 启动时间: {self.session_start_time.strftime("%Y-%m-%d %H:%M:%S")}')
        # ==================== 新增结束 ====================

        # ==================== 启动前检查端口 ====================
        port_pids = check_port(5000)
        if port_pids:
            self._append_log(f' [WARN] 端口5000被占用 (PID: {",".join(port_pids)})，尝试释放...')
            force_kill_port(5000, self._append_log)
            if filter_alive_pids(check_port(5000)):
                self._append_log('[ERROR] 端口5000无法释放，服务启动失败')
                return

        if getattr(sys, 'frozen', False):
            cmd = [sys.executable, 'run_app']
        else:
            cmd = [PYEXE, str(APP_PY)]

        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        env['LAPTOPWATCH_MODE'] = current_mode
        env['LAPTOPWATCH_MEDIA_DIR'] = self.media_dir_var.get()
        env['LAPTOPWATCH_SORT_TYPE'] = self.sort_type_var.get()
        env['LAPTOPWATCH_SORT_ORDER'] = self.sort_order_var.get()
        # ==================== 新增：传递随机模式标志 ====================
        env['LAPTOPWATCH_RANDOM'] = 'true' if self.random_var.get() else 'false'
        # 目录浏览模式标志
        env['LAPTOPWATCH_CATEGORY_BROWSE'] = 'true' if self.category_browse_var.get() else 'false'
        # ==================== 抖音模式配置 ====================
        if current_mode == 'douyin':
            env['LAPTOPWATCH_DOUYIN_RANDOM_MEDIA'] = 'true' if self.douyin_random_media_var.get() else 'false'
        # ==================== 标记为GUI启动，禁用控制台日志输出 ====================
        env['LAPTOPWATCH_GUI_LAUNCH'] = '1'
        # ==================== 新增结束 ====================

        try:
            if os.name == 'nt':
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=1,
                    universal_newlines=True,
                    env=env,
                    creationflags=creationflags
                )
            else:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=1,
                    universal_newlines=True,
                    env=env,
                    start_new_session=True
                )
            self.process_pid = self.process.pid
        except Exception as e:
            self._append_log(f'[ERROR] 启动失败: {e}')
            self.process = None
            self.process_pid = None
            return

        # 启动日志读取线程
        self.log_thread = threading.Thread(target=self._read_process_output, daemon=True)
        self.log_thread.start()

        # 更新UI状态
        self.status_var.set(f'启动中（{current_mode}模式）')
        self.status_canvas.itemconfig(self._status_dot_id, fill='#f59e0b')
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.open_btn.config(state='normal')
        self._disable_config_controls()

        # 获取IP和URL
        ip = get_local_ip()
        port = 5000
        url = f'http://{ip}:{port}'
        self.url_var.set(url)
        self._generate_qr(url)

        self._append_log(f' {current_mode}模式服务启动成功！')
        self._append_log(f' 访问地址：{url}')
        # ==================== 新增：日志提示随机模式 ====================
        if self.random_var.get():
            self._append_log(' 随机模式已开启，媒体浏览将从随机位置开始')
        # ==================== 新增结束 ====================

        # 启动后台线程检查服务是否已准备好
        threading.Thread(target=self._wait_for_service, args=(url,), daemon=True).start()





    def stop_app(self):
        is_external = False
        if self.process is None:
            if not check_port(5000):
                self._append_log(' 服务未在运行')
                return
            is_external = True
            self._append_log(' 服务由外部启动，通过端口终止...')
            # Flask reloader: 端口监听者是子进程，需杀父进程树
            port_pids = check_port(5000)
            for pid in port_pids:
                root_pid = find_parent_pid(pid)
                if root_pid and root_pid != pid:
                    self._append_log(f' 端口占用PID:{pid} → 根进程PID:{root_pid}，终止进程树...')
                    try:
                        subprocess.run(
                            ['taskkill', '/F', '/T', '/PID', str(root_pid)],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            timeout=5,
                            text=True
                        )
                    except Exception as e:
                        self._append_log(f' taskkill根进程树失败: {e}')
        try:
            if not is_external:
                stop_process_gracefully(self.process, self.process_pid, 5000, self._append_log)

            if is_external:
                force_kill_port(5000, self._append_log)

            self._append_log('[STOP] 服务已彻底停止')
        except Exception as e:
            self._append_log(f'[ERROR] 终止进程时出错: {e}')
        finally:
            if config.SAVE_SESSION_LOGS:
                save_session_logs(
                    self.session_logs, self.session_start_time, self.session_id,
                    self.mode_var.get(), self.media_dir_var.get(), self._append_log
                )
            self._reset_after_stop('已停止')

    def _check_qid_status(self):
        """GUI 启动时检测 qid.py 是否已在运行"""
        port_pids = check_port(5001)
        if port_pids:
            ip = get_local_ip()
            qid_url = f'http://{ip}:5001'
            self.qid_status_var.set(qid_url)
            self.qid_start_btn.config(state='disabled')
            self.qid_stop_btn.config(state='normal')
            self.qid_open_btn.config(state='normal')
            self._append_log(f'[INFO] 检测到管理台已在运行: {qid_url}')

    def start_qid(self):
        """启动网页管理台 (qid.py on port 5001)"""
        if self.qid_process is not None and self.qid_process.poll() is None:
            self._append_log('[WARN] 管理台已在运行中')
            return

        if getattr(sys, 'frozen', False):
            base_path = Path(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))))
            qid_py = base_path / 'qid.py'
        else:
            qid_py = Path(__file__).parent / 'qid.py'

        if not qid_py.exists():
            self._append_log(f'[ERROR] 找不到 qid.py，路径: {qid_py}')
            return

        # 检查端口5001是否被占用
        port_pids = check_port(5001)
        if port_pids:
            self._append_log(f' 端口5001被占用 (PID: {",".join(port_pids)})，尝试释放...')
            force_kill_port(5001, self._append_log)
            if check_port(5001):
                self._append_log('[ERROR] 端口5001无法释放，管理台启动失败')
                return

        try:
            if os.name == 'nt':
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
                self.qid_process = subprocess.Popen(
                    [sys.executable, str(qid_py)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=1,
                    universal_newlines=True,
                    creationflags=creationflags
                )
            else:
                self.qid_process = subprocess.Popen(
                    [sys.executable, str(qid_py)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=1,
                    universal_newlines=True,
                    start_new_session=True
                )
        except Exception as e:
            self._append_log(f'[ERROR] 管理台启动失败: {e}')
            self.qid_process = None
            return

        threading.Thread(target=self._read_qid_output, daemon=True).start()

        time.sleep(1)
        if self.qid_process.poll() is not None:
            self._append_log(f'[ERROR] 管理台启动后立即退出，退出码: {self.qid_process.returncode}')
            self.qid_process = None
            return

        ip = get_local_ip()
        qid_url = f'http://{ip}:5001'
        self._append_log(f' 网页管理台已启动: {qid_url}')
        self.qid_status_var.set(qid_url)
        self.qid_start_btn.config(state='disabled')
        self.qid_stop_btn.config(state='normal')
        self.qid_open_btn.config(state='normal')

    def stop_qid(self):
        """停止网页管理台"""
        if self.qid_process is None:
            self._append_log('[WARN] 管理台未在运行')
            return

        try:
            stop_process_gracefully(self.qid_process, None, 5001, self._append_log)
            self._append_log('[STOP] 管理台已停止')
        except Exception as e:
            self._append_log(f'[ERROR] 停止管理台时出错: {e}')
        finally:
            if config.SAVE_SESSION_LOGS:
                save_session_logs(
                    self.session_logs, self.session_start_time, self.session_id,
                    self.mode_var.get(), self.media_dir_var.get(), self._append_log
                )
            self.qid_process = None
            self.qid_status_var.set('未启动')
            self.qid_start_btn.config(state='normal')
            self.qid_stop_btn.config(state='disabled')
            self.qid_open_btn.config(state='disabled')

    def _read_qid_output(self):
        """后台线程：读取管理台子进程输出"""
        if not self.qid_process or not self.qid_process.stdout:
            return
        try:
            for line in self.qid_process.stdout:
                self.log_queue.put(f'[QID] {line}')
        except Exception as e:
            self.log_queue.put(f'[ERROR] 管理台日志读取异常: {str(e)}')

    def open_qid_browser(self):
        """在浏览器中打开管理台页面"""
        ip = get_local_ip()
        webbrowser.open(f'http://{ip}:5001')

    def _read_process_output(self):
        if not self.process or not self.process.stdout:
            return
        try:
            for line in self.process.stdout:
                self.log_queue.put(line)
        except Exception as e:
            self.log_queue.put(f'[ERROR] 日志读取线程异常: {str(e)}')

    def _poll_log_queue(self):
        # 批量处理日志，每次最多处理10条，降低GUI更新频率
        lines_processed = 0
        max_lines_per_poll = 10
        try:
            while lines_processed < max_lines_per_poll:
                line = self.log_queue.get_nowait()
                self._append_log(line.rstrip('\n'))
                lines_processed += 1
        except queue.Empty:
            pass
        # 更新运行时长（只在持有进程句柄时显示，socket 操作太重不在此轮询）
        if self.process is not None and self.process.poll() is None and self.session_start_time:
            delta = datetime.datetime.now() - self.session_start_time
            h, remainder = divmod(int(delta.total_seconds()), 3600)
            m, s = divmod(remainder, 60)
            self.status_runtime_label.config(text=f'已运行 {h:02d}:{m:02d}:{s:02d}')
        elif self.process is not None and self.process.poll() is not None:
            self.status_runtime_label.config(text='')
        self.after(500, self._poll_log_queue)

    def _poll_service_status(self):
        """每 1 秒检测端口 5000，与 qid.py 等外部启动方保持状态同步"""
        try:
            port_pids = check_port(5000)
            is_port_running = len(port_pids) > 0
            is_internal_alive = self.process is not None and self.process.poll() is None
            is_internal_exited = self.process is not None and self.process.poll() is not None

            if is_port_running and not is_internal_alive:
                alive_pids = filter_alive_pids(port_pids)
                if not alive_pids:
                    # 端口只剩 TIME_WAIT 等 stale PID，实际进程已不存活
                    self._stop_debounce = 0
                    self.after(1000, self._poll_service_status)
                    return
                # 服务由外部启动（qid.py 或手动），同步 UI
                if not getattr(self, '_external_synced', False):
                    self._append_log('[SYNC] 检测到外部服务已在运行，同步 UI...')
                    self._external_synced = True
                self._stop_debounce = 0
                ip = get_local_ip()
                url = f'http://{ip}:5000'
                self.url_var.set(url)
                self._generate_qr(url)
                self.start_btn.config(state='disabled')
                self.stop_btn.config(state='normal')
                self.open_btn.config(state='normal')
                self._disable_config_controls()
                self.status_var.set('运行中（外部启动）')
                self.status_canvas.itemconfig(self._status_dot_id, fill='#10b981')
                self.process = None
                self.process_pid = None
            elif is_internal_exited:
                if not is_port_running:
                    self._reset_after_stop()
            elif not is_port_running and not is_internal_alive:
                if self.stop_btn.instate(['normal']):
                    # 防抖：Flask reloader 重启期间端口会短暂空闲，
                    # 连续 2 次检测都空闲（约 4 秒）才认为真正停止
                    debounce = getattr(self, '_stop_debounce', 0) + 1
                    self._stop_debounce = debounce
                    if debounce >= 2:
                        self._stop_debounce = 0
                        self._reset_after_stop()
                else:
                    self._stop_debounce = 0

            if is_port_running and not is_internal_alive:
                self._sync_logs_from_qid()
            else:
                self._qid_log_count = 0
        except Exception as e:
            self._append_log(f'[ERROR] _poll_service_status 异常: {e}')
            print(f'[DEBUG] _poll_service_status 异常: {e}', flush=True)

        self.after(1000, self._poll_service_status)

    def _push_log_to_qid(self, text):
        """将日志行推送到 qid.py 的日志系统"""
        # 跳过 [QID] 前缀的日志（来自 qid.py 自身 stdout），避免 push→Flask日志→stdout→push 的死循环
        if text.startswith('[QID]'):
            return
        self._push_queue.put(text)

    def _start_push_worker(self):
        """启动后台线程，异步推送日志到 qid.py"""
        def worker():
            while True:
                try:
                    text = self._push_queue.get(timeout=1)
                    data = json.dumps({'line': text, 'password': config.DEFAULT_PASSWORD}).encode('utf-8')
                    req = urllib.request.Request(
                        'http://127.0.0.1:5001/api/logs/ingest',
                        data=data,
                        headers={'Content-Type': 'application/json'},
                        method='POST'
                    )
                    urllib.request.urlopen(req, timeout=1)
                except queue.Empty:
                    pass
                except Exception:
                    pass
        threading.Thread(target=worker, daemon=True).start()

    def _sync_logs_from_qid(self):
        """从 qid.py 拉取增量日志（服务由外部启动时使用）"""
        try:
            url = f'http://127.0.0.1:5001/api/logs/recent?since={self._qid_log_count}'
            req = urllib.request.Request(url, headers={'X-Auth-Password': config.DEFAULT_PASSWORD})
            resp = urllib.request.urlopen(req, timeout=2)
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('code') == 0:
                payload = data['data']
                new_logs = payload.get('logs', [])
                self._qid_log_count = payload.get('total', self._qid_log_count)
                for line in new_logs:
                    self._append_log(line)
        except Exception:
            pass

    def _reset_after_stop(self, status_text='未运行'):
        """将 UI 和状态恢复到未运行状态（不保存日志，不杀进程）"""
        self.process = None
        self.process_pid = None
        with self._session_logs_lock:
            self.session_logs = []
        self.session_start_time = None
        self.session_id = None
        self._external_synced = False
        self._reset_access_info()
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.open_btn.config(state='disabled')
        self.status_var.set(status_text)
        self.status_canvas.itemconfig(self._status_dot_id, fill=self.text_muted)
        self.url_var.set('—')
        self.qr_label.config(image='', text='启动服务后\n显示二维码')
        self.status_runtime_label.config(text='')
        self._enable_config_controls()

    def _append_log(self, text):
        self.log_text.config(state='normal')
        self.log_text.insert('end', text + '\n')
        self.log_text.see('end')
        self.log_text.config(state='disabled')
        with self._session_logs_lock:
            self.session_logs.append(text)
            if len(self.session_logs) > 2000:
                self.session_logs.pop(0)
        self._update_activity_display(text)
        # 当 gui 持有服务进程时，将日志推送到 qid.py 以便网页端同步显示
        if self.process is not None and self.process.poll() is None:
            self._push_log_to_qid(text)

    def _parse_access_action(self, log_line):
        """从 [ACCESS][ACTION_TYPE] 前缀中提取动作类型"""
        if log_line.startswith('[ACCESS]['):
            end_bracket = log_line.find(']', 9)
            if end_bracket > 9:
                return log_line[9:end_bracket]
        return None

    def _update_activity_display(self, log_line):
        """实时更新显示活动用户、访问文件和错误信息"""
        action = self._parse_access_action(log_line)
        if action:
            import re
            ip_match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', log_line)
            if ip_match:
                client_ip = ip_match.group(1)
                file_path = self._extract_file_path_from_log(log_line)
                self._update_status_with_activity(client_ip, action, file_path)

        # 检测错误信息
        if '[ERROR]' in log_line or 'Exception' in log_line or 'Traceback' in log_line or 'Failed' in log_line:
            self._highlight_error_log()

    def _extract_file_path_from_log(self, log_line):
        """从日志行中提取文件路径"""
        # 查找路径信息，可能是绝对路径（Windows格式）或普通路径
        # 匹配形如 " | 相对路径" 或 " | C:\\path\\to\\file.ext" 的模式
        import re

        # 首先查找详细信息中的原始路径
        details_match = re.search(r'details=.*?原始路径: ([^\\\/][^,\]]+)', log_line)
        if details_match:
            return details_match.group(1)

        # 然后尝试匹配绝对路径模式 (C:\...) 或 (D:\...) 等
        abs_path_match = re.search(r'C:\\.*?("|\s)|D:\\.*?("|\s)|E:\\.*?("|\s)|F:\\.*?("|\s)', log_line)
        if abs_path_match:
            path = abs_path_match.group(0).strip('" ')
            # 如果路径过长，截取末尾部分
            if len(path) > 50:
                parts = path.split('\\')
                if len(parts) > 3:
                    path = '...\\' + '\\'.join(parts[-3:])
            return path

        # 如果不是绝对路径，尝试提取普通路径
        parts = log_line.split(' | ')
        if len(parts) >= 3:
            path_part = parts[2].split(' ')[0]  # 提取路径部分，去掉额外细节
            if len(path_part) > 50:
                # 对于较长的路径，只显示最后几段
                path_segments = path_part.split('/')
                if len(path_segments) > 3:
                    path_part = '.../' + '/'.join(path_segments[-3:])
            return path_part

        return '未知文件'

    def _update_status_with_activity(self, client_ip, action, file_path=None):
        """更新底部状态栏显示当前活动"""
        action_map = {
            'INDEX': '首页访问',
            'BROWSE': '浏览目录',
            'RAW_PREVIEW': '文件预览',
            'DOWNLOAD': '文件下载',
            'DOWNLOAD_FOLDER': '文件夹下载',
            'DOWNLOAD_SELECTED': '批量下载',
            'VIEW_TEXT': '文本查看',
            'LOAD_MORE': '加载更多',
            'MEDIA_SERVE': '媒体播放',
            'DOWNLOAD_MEDIA': '媒体下载',
            'MEDIA_NAV': '媒体导航',
            'MEDIA_PLAY': '开始播放视频',
            'MEDIA_VIEW': '查看图片',
            'MEDIA_STREAM': '视频流传输',
            'MEDIA_PLAY_END': '视频播放结束',
            'MEDIA_VIEW_END': '图片查看结束',
            'MEDIA_ACCESS_ERROR': '媒体访问错误',
            'DOUYIN_INIT': '抖音初始化',
            'DOUYIN_NEXT': '抖音下一个视频',
            'LOGIN': '登录',
            'LOGOUT': '登出',
        }
        action_text = action_map.get(action, '未知操作')

        if file_path and file_path != '未知文件':
            activity_msg = f"{client_ip}  {action_text}  {file_path}"
        else:
            activity_msg = f"{client_ip}  {action_text}"
        if len(activity_msg) > 100:
            activity_msg = activity_msg[:100] + "..."
        self.status_label.config(text=activity_msg)

    def _reset_access_info(self):
        """重置底部状态栏"""
        self.status_label.config(text='就绪')

    def _highlight_error_log(self):
        """错误日志出现时短暂高亮状态栏"""
        original_text = self.status_label.cget('text')
        if '[ERROR]' not in original_text:
            self.status_label.config(text=original_text + '  [ERROR]',
                                      fg=self.danger_color)
            self.after(3000, lambda: self._restore_status_label(original_text))

    def _restore_status_label(self, original_text):
        """恢复状态栏文本和颜色"""
        self.status_label.config(text=original_text, fg=self.text_secondary)


    def _generate_qr(self, url):
        if qrcode is None or Image is None:
            self._append_log(' 提示：未安装 qrcode[pil]，无法生成二维码')
            return
        try:
            qr = qrcode.QRCode(box_size=4, border=1)
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color='black', back_color='white').convert('RGB')
            img = img.resize((150, 150))
            photo = ImageTk.PhotoImage(img)
            self.qr_label.config(image=photo, text='')
            self.qr_label.image = photo
        except Exception as e:
            self._append_log(f' 二维码生成失败: {e}')

    def open_browser(self):
        url = self.url_var.get()
        if url and 'http' in url:
            webbrowser.open(url)

    # ==================== 新增：_on_close 方法 ====================
    def _on_close(self):
        """窗口关闭时停止服务并销毁窗口（非阻塞）"""
        # 防止重复关闭
        if getattr(self, '_closing', False):
            return
        self._closing = True
        self.protocol('WM_DELETE_WINDOW', lambda: None)

        # 保存会话日志（主线程，快速操作）
        if config.SAVE_SESSION_LOGS:
            save_session_logs(
                self.session_logs, self.session_start_time, self.session_id,
                self.mode_var.get(), self.media_dir_var.get(), self._append_log
            )

        # 后台线程执行停止，主线程直接销毁窗口
        def cleanup():
            try:
                if self.qid_process and self.qid_process.poll() is None:
                    stop_process_gracefully(
                        self.qid_process, None, 5001, lambda msg: None)
                if self.process:
                    stop_process_gracefully(
                        self.process, self.process_pid, 5000, lambda msg: None)
                elif check_port(5000):
                    alive_pids = filter_alive_pids(check_port(5000))
                    if alive_pids:
                        force_kill_port(5000, lambda msg: None)
            except Exception:
                pass

        threading.Thread(target=cleanup, daemon=True).start()
        self.after(100, self.destroy)
    # ==================== 新增结束 ====================

    def _wait_for_service(self, url):
        """等待服务启动完成后更新状态"""
        import time
        import urllib.request
        import urllib.error

        max_wait_time = 60  # 增加最大等待时间（秒），考虑到随机模式初始化较慢
        wait_interval = 2   # 检查间隔（秒）
        elapsed = 0

        while elapsed < max_wait_time:
            try:
                # 尝试发送HEAD请求（比GET请求更快），使用更长的超时时间
                req = urllib.request.Request(url, method='HEAD')
                response = urllib.request.urlopen(req, timeout=10)
                if response.getcode() in [200, 401, 403, 404]:  # 接受各种HTTP状态码，说明服务已响应
                    # 服务已准备好，更新状态
                    current_mode = self.mode_var.get()
                    self.status_var.set(f'运行中（{current_mode}模式）')
                    self.status_canvas.itemconfig(self._status_dot_id, fill='#10b981')
                    self._append_log(' 服务初始化完成，可以访问页面')
                    return
            except urllib.error.HTTPError as e:
                # HTTP错误（如401, 403, 404）也表示服务已启动
                if e.code in [401, 403, 404]:
                    current_mode = self.mode_var.get()
                    self.status_var.set(f'运行中（{current_mode}模式）')
                    self.status_canvas.itemconfig(self._status_dot_id, fill='#10b981')
                    self._append_log(' 服务初始化完成，可以访问页面')
                    return
                else:
                    # 其他HTTP错误，继续等待
                    pass
            except urllib.error.URLError:
                # 服务还未准备好，继续等待
                pass
            except Exception:
                # 其他错误，继续等待
                pass

            time.sleep(wait_interval)
            elapsed += wait_interval

        # 超时，仍更新状态为运行中，但记录警告
        current_mode = self.mode_var.get()
        self.status_var.set(f'运行中（{current_mode}模式）')
        self.status_canvas.itemconfig(self._status_dot_id, fill='#10b981')
        self._append_log(f' [WARN] 服务启动检查超时 ({max_wait_time}秒)，但仍标记为运行中')

if __name__ == '__main__':
    app = AppLauncher()
    app.mainloop()
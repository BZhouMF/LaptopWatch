"""
PyWebView 桌面 App 演示 — 替代 tkinter GUI

架构：PyWebView 加载本地 HTML 作为配置界面 → "启动服务" spawn Flask 子进程 → "停止服务" 杀死子进程

用法:
    python test_gui.py                          # 默认 normal 模式
    python test_gui.py --mode video --dir "F:/视频"
"""
import sys
import os
import time
import http.server
import socketserver
import threading
import argparse
import subprocess
import webbrowser
from pathlib import Path

import webview

from config import config
from utils.process_utils import (
    get_local_ip, check_port, force_kill_port,
    stop_process_gracefully, save_session_logs, filter_alive_pids,
)


def parse_args():
    parser = argparse.ArgumentParser(description='LaptopWatch 桌面 App')
    parser.add_argument('--mode', default='normal',
                        choices=['normal', 'video', 'image', 'douyin'],
                        help='运行模式')
    parser.add_argument('--dir', dest='media_dir', default=None,
                        help='媒体目录路径')
    parser.add_argument('--port', type=int, default=5002,
                        help='服务端口')
    return parser.parse_args()


# ── 全局状态 ──
_flask_process = None
_flask_logs = []      # Flask 子进程 stdout 日志
_log_index = 0        # JS 端已读取的日志索引
_qid_process = None
_session_logs = []
_session_start_time = None


def _log(msg):
    _session_logs.append(msg)
    if len(_session_logs) > 2000:
        _session_logs.pop(0)


# ── QR 码生成 ──
def _generate_qr_base64(url):
    try:
        import qrcode
        from io import BytesIO
        qr = qrcode.QRCode(box_size=4, border=1)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white').convert('RGB')
        img = img.resize((150, 150))
        buf = BytesIO()
        img.save(buf, format='PNG')
        import base64
        return base64.b64encode(buf.getvalue()).decode('utf-8')
    except Exception:
        return ''


# ── PyWebView JS API ──

class _DesktopApi:
    """暴露给前端 JS 的原生桌面 API"""

    def select_folder(self):
        """原生文件夹选择对话框"""
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder = filedialog.askdirectory(title='请选择包含视频或图片的文件夹')
        root.destroy()
        return folder or ''

    def start_service(self, settings):
        """启动 Flask 子进程"""
        global _flask_process, _session_start_time
        import datetime

        if _flask_process is not None and _flask_process.poll() is None:
            return {'code': 1, 'msg': '服务已在运行中'}

        mode = settings.get('mode', 'normal')
        media_dir = settings.get('media_dir', '')
        port = settings.get('port', 5002)

        # 端口检查
        port_pids = check_port(port)
        if port_pids:
            alive = filter_alive_pids(port_pids)
            if alive:
                return {'code': 1, 'msg': f'端口{port}被占用 (PID: {",".join(alive)})，请先停止旧服务'}
            # stale PID
            force_kill_port(port, lambda m: None)

        # 找 app.py
        if getattr(sys, 'frozen', False):
            base_path = Path(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))))
            app_py = base_path / 'app.py'
        else:
            app_py = Path(__file__).parent / 'app.py'

        if not app_py.exists():
            return {'code': 1, 'msg': f'找不到 app.py: {app_py}'}

        # 构建环境变量
        env = os.environ.copy()
        env['LAPTOPWATCH_MODE'] = mode
        env['LAPTOPWATCH_PORT'] = str(port)
        if media_dir:
            env['LAPTOPWATCH_MEDIA_DIR'] = media_dir
        env['LAPTOPWATCH_SORT_TYPE'] = settings.get('sort_type', 'name')
        env['LAPTOPWATCH_SORT_ORDER'] = settings.get('sort_order', 'asc')
        env['LAPTOPWATCH_RANDOM'] = 'true' if settings.get('random', False) else 'false'
        env['LAPTOPWATCH_CATEGORY_BROWSE'] = 'true' if settings.get('category_browse', False) else 'false'
        if mode == 'douyin':
            env['LAPTOPWATCH_DOUYIN_RANDOM_MEDIA'] = 'true' if settings.get('douyin_random', False) else 'false'
        env['LAPTOPWATCH_GUI_LAUNCH'] = '1'

        # 启动子进程
        try:
            if os.name == 'nt':
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
                _flask_process = subprocess.Popen(
                    [sys.executable, str(app_py)],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    bufsize=1, text=True, encoding='utf-8', errors='replace',
                    env=env, creationflags=creationflags,
                )
            else:
                _flask_process = subprocess.Popen(
                    [sys.executable, str(app_py)],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    bufsize=1, text=True, encoding='utf-8', errors='replace',
                    env=env, start_new_session=True,
                )
        except Exception as exc:
            _flask_process = None
            return {'code': 1, 'msg': f'服务启动失败: {exc}'}

        # 启动后台线程读取 Flask stdout 日志
        global _flask_logs, _log_index
        _flask_logs = []
        _log_index = 0

        def _read_flask_stdout():
            global _flask_logs
            try:
                for line in _flask_process.stdout:
                    _flask_logs.append(line.rstrip('\n'))
                    if len(_flask_logs) > 500:
                        _flask_logs.pop(0)
            except Exception:
                pass

        threading.Thread(target=_read_flask_stdout, daemon=True).start()

        _session_start_time = datetime.datetime.now()
        _log(f'[INFO] {mode} 模式服务启动中 — 媒体目录: {media_dir}')

        # 等待服务就绪
        time.sleep(2)
        if _flask_process.poll() is not None:
            returncode = _flask_process.returncode
            _flask_process = None
            return {'code': 1, 'msg': f'服务启动后立即退出，退出码: {returncode}'}

        # 获取 URL 并生成二维码
        lan_ip = get_local_ip()
        lan_url = f'http://{lan_ip}:{port}' if lan_ip else ''
        local_url = f'http://127.0.0.1:{port}'
        qr_base64 = _generate_qr_base64(lan_url or local_url)

        _log(f'[INFO] 服务已启动 — LAN: {lan_url}  Local: {local_url}')
        return {
            'code': 0,
            'msg': '服务已启动',
            'local_url': local_url,
            'lan_url': lan_url,
            'qr_base64': qr_base64,
        }

    def stop_service(self):
        """停止 Flask 子进程"""
        global _flask_process

        if _flask_process is None:
            # 检查是否外部启动
            port_pids = check_port(5002)
            alive = filter_alive_pids(port_pids) if port_pids else []
            if alive:
                force_kill_port(5002, lambda m: None)
                _log('[STOP] 外部服务已停止')
                return {'code': 0, 'msg': '服务已停止（外部进程）'}
            return {'code': 1, 'msg': '服务未在运行'}

        try:
            stop_process_gracefully(_flask_process, _flask_process.pid, 5002, lambda m: None)
            _log('[STOP] 服务已彻底停止')
        except Exception as exc:
            _log(f'[ERROR] 停止服务时出错: {exc}')
            try:
                force_kill_port(5002, lambda m: None)
            except Exception:
                pass
        finally:
            if config.SAVE_SESSION_LOGS:
                save_session_logs(
                    _session_logs, _session_start_time, None,
                    config.RUN_MODE, str(config.MEDIA_DIR) if config.MEDIA_DIR else '', lambda m: None,
                )
            _flask_process = None
        return {'code': 0, 'msg': '服务已停止'}

    def get_service_status(self):
        """查询服务运行状态"""
        if _flask_process is not None and _flask_process.poll() is None:
            return {'running': True, 'url': f'http://{get_local_ip()}:5002'}
        port_pids = check_port(5002)
        alive = filter_alive_pids(port_pids) if port_pids else []
        if alive:
            return {'running': True, 'url': f'http://{get_local_ip()}:5002', 'external': True}
        return {'running': False, 'url': ''}

    # ── 管理台 (qid.py) ──

    def start_qid(self):
        """启动网页管理台"""
        global _qid_process
        if _qid_process is not None and _qid_process.poll() is None:
            return {'code': 1, 'msg': '管理台已在运行中'}

        if getattr(sys, 'frozen', False):
            base_path = Path(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))))
            qid_py = base_path / 'qid.py'
        else:
            qid_py = Path(__file__).parent / 'qid.py'

        if not qid_py.exists():
            return {'code': 1, 'msg': f'找不到 qid.py: {qid_py}'}

        port_pids = check_port(5001)
        if port_pids and filter_alive_pids(port_pids):
            force_kill_port(5001, lambda m: None)
            if check_port(5001):
                return {'code': 1, 'msg': '端口5001无法释放'}

        try:
            if os.name == 'nt':
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
                _qid_process = subprocess.Popen(
                    [sys.executable, str(qid_py)],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    bufsize=1, text=True, encoding='utf-8', errors='replace',
                    creationflags=creationflags,
                )
            else:
                _qid_process = subprocess.Popen(
                    [sys.executable, str(qid_py)],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    bufsize=1, text=True, encoding='utf-8', errors='replace',
                    start_new_session=True,
                )
        except Exception as exc:
            _qid_process = None
            return {'code': 1, 'msg': f'管理台启动失败: {exc}'}

        time.sleep(1)
        if _qid_process.poll() is not None:
            returncode = _qid_process.returncode
            _qid_process = None
            return {'code': 1, 'msg': f'管理台启动后退出，退出码: {returncode}'}

        qid_url = f'http://{get_local_ip()}:5001'
        _log(f'[INFO] 管理台已启动: {qid_url}')
        return {'code': 0, 'msg': '管理台已启动', 'qid_url': qid_url}

    def stop_qid(self):
        """停止网页管理台"""
        global _qid_process
        if _qid_process is None:
            port_pids = check_port(5001)
            alive = filter_alive_pids(port_pids) if port_pids else []
            if alive:
                force_kill_port(5001, lambda m: None)
                return {'code': 0, 'msg': '管理台已停止（外部进程）'}
            return {'code': 1, 'msg': '管理台未在运行'}

        try:
            stop_process_gracefully(_qid_process, None, 5001, lambda m: None)
            _log('[STOP] 管理台已停止')
        except Exception as exc:
            _log(f'[ERROR] 停止管理台时出错: {exc}')
        finally:
            if config.SAVE_SESSION_LOGS:
                save_session_logs(
                    _session_logs, _session_start_time, None,
                    config.RUN_MODE, str(config.MEDIA_DIR) if config.MEDIA_DIR else '', lambda m: None,
                )
            _qid_process = None
        return {'code': 0, 'msg': '管理台已停止'}

    def open_qid(self):
        """在浏览器中打开管理台"""
        webbrowser.open(f'http://{get_local_ip()}:5001')
        return {'code': 0}

    def get_flask_logs(self):
        """返回 Flask 子进程最新的 stdout 日志（增量）"""
        global _flask_logs, _log_index
        new_logs = _flask_logs[_log_index:]
        _log_index = len(_flask_logs)
        return {'logs': new_logs}

    def get_qid_status(self):
        """获取管理台运行状态"""
        if _qid_process is not None and _qid_process.poll() is None:
            return {'running': True, 'url': f'http://{get_local_ip()}:5001'}
        port_pids = check_port(5001)
        alive = filter_alive_pids(port_pids) if port_pids else []
        if alive:
            return {'running': True, 'url': f'http://{get_local_ip()}:5001', 'external': True}
        return {'running': False, 'url': ''}


# ── 主入口 ──

def main():
    global _session_start_time
    import datetime
    _session_start_time = datetime.datetime.now()

    args = parse_args()

    # 从项目根目录启动静态文件服务器（随机端口，不改变 CWD）
    project_root = str(Path(__file__).parent)
    handler = lambda *args, **kw: http.server.SimpleHTTPRequestHandler(*args, directory=project_root, **kw)
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    static_port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    webview.create_window(
        title='LaptopWatch',
        url=f'http://127.0.0.1:{static_port}/templates/setup.html',
        js_api=_DesktopApi(),
        width=900,
        height=700,
        resizable=True,
        min_size=(700, 600),
    )
    webview.start(debug=False)

    # 窗口关闭后清理
    if _flask_process is not None and _flask_process.poll() is None:
        try:
            stop_process_gracefully(_flask_process, _flask_process.pid, 5002, lambda m: None)
        except Exception:
            pass
    if _qid_process is not None and _qid_process.poll() is None:
        try:
            stop_process_gracefully(_qid_process, None, 5001, lambda m: None)
        except Exception:
            pass
    if config.SAVE_SESSION_LOGS:
        save_session_logs(
            _session_logs, _session_start_time, None,
            config.RUN_MODE, str(config.MEDIA_DIR) if config.MEDIA_DIR else '', lambda m: None,
        )


if __name__ == '__main__':
    main()

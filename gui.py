"""
LaptopWatch 桌面 App — PyWebView GUI

架构：PyWebView 加载 setup.html 作为配置界面 → "启动服务" spawn Flask 子进程 → "停止服务" 杀死子进程

用法:
    python gui.py                          # 默认端口 5002
    python gui.py --port 8080              # 指定服务端口
"""
import sys
import os
import time
import atexit
import http.server
import socketserver
import threading
import argparse
import subprocess
import webbrowser
import json
import queue
import urllib.request
import urllib.error
from pathlib import Path
import webview

from config import config
from utils.process_utils import (
    get_local_ip, check_port, force_kill_port,
    stop_process_gracefully, save_session_logs, filter_alive_pids,
)


# ==================== PyInstaller 打包兼容入口 ====================
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


def parse_args():
    parser = argparse.ArgumentParser(description='LaptopWatch 桌面 App')
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
_service_port = 5002  # 当前会话服务端口
_session_logs_saved = False
_logs_lock = threading.Lock()

# ── 端口监控 & QID 交互 ──
_push_queue = queue.Queue()
_stop_debounce = 0          # Flask reloader 防抖计数
_service_was_active = False  # 服务是否曾被检测为活跃（用于防抖触发条件）
_external_synced = False    # 是否已同步外部服务状态
_qid_log_count = 0          # 已从 QID 拉取的日志条数


def _log(msg):
    _session_logs.append(msg)
    if len(_session_logs) > 2000:
        _session_logs.pop(0)


def _save_logs_once(log_func):
    """确保整个会话只保存一次日志"""
    global _session_logs_saved
    if not _session_logs_saved and config.SAVE_SESSION_LOGS:
        _session_logs_saved = True
        save_session_logs(
            _session_logs, _session_start_time, None,
            config.RUN_MODE, str(config.MEDIA_DIR) if config.MEDIA_DIR else '', log_func,
        )


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


def _post_json(req, timeout=5):
    """POST 请求并解析 JSON 响应，正确处理 HTTPError 中的错误信息"""
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode('utf-8'))
            return body
        except Exception:
            return {'code': 1, 'msg': f'HTTP {exc.code}: {exc.reason}'}

# ── 安全静态文件 Handler ──
def _make_safe_handler(root_dir):
    """返回一个仅允许 /templates/ 和 /static/ 路径的 HTTP handler"""
    class _SafeHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *_args, **kw):
            super().__init__(*_args, directory=root_dir, **kw)

        def do_GET(self):
            path = self.path.split('?')[0].split('#')[0]
            if path.startswith('/templates/') or path.startswith('/static/'):
                super().do_GET()
            else:
                self.send_error(404)

    return _SafeHandler


# ── 后台：日志推送到 QID ──
def _start_push_worker():
    """启动后台线程，异步推送日志到 qid.py"""
    def worker():
        while True:
            try:
                text = _push_queue.get(timeout=1)
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


def _push_log_to_qid(text):
    """将日志行推送到 qid.py 的日志系统（跳过 QID 自身日志避免死循环）"""
    if text.startswith('[QID]'):
        return
    _push_queue.put(text)


# ── 后台：端口 & 服务状态监控 ──
def _start_service_monitor():
    """后台线程：监控端口，检测外部启动/停止，同步 QID 日志"""
    global _service_was_active, _external_synced

    def monitor():
        global _service_was_active, _external_synced
        while True:
            time.sleep(2)
            try:
                port_pids = check_port(_service_port)
                is_port_running = len(port_pids) > 0
                is_internal_alive = _flask_process is not None and _flask_process.poll() is None

                if is_port_running and not is_internal_alive:
                    alive_pids = filter_alive_pids(port_pids)
                    if not alive_pids:
                        continue
                    # 服务由外部启动
                    if not _external_synced:
                        _log('[SYNC] 检测到外部服务已在运行')
                        _external_synced = True
                    _service_was_active = True
                    _sync_logs_from_qid()
                elif is_port_running:
                    _service_was_active = True
                elif not is_port_running:
                    if is_internal_alive:
                        _service_was_active = True
                    # 端口不在、进程也不在 → 留给 get_service_status 防抖处理
            except Exception:
                pass

    threading.Thread(target=monitor, daemon=True).start()


def _sync_logs_from_qid():
    """从 qid.py 拉取增量日志（服务由外部启动时使用）"""
    global _qid_log_count
    try:
        url = f'http://127.0.0.1:5001/api/logs/recent?since={_qid_log_count}'
        req = urllib.request.Request(url, headers={'X-Auth-Password': config.DEFAULT_PASSWORD})
        resp = urllib.request.urlopen(req, timeout=2)
        data = json.loads(resp.read().decode('utf-8'))
        if data.get('code') == 0:
            payload = data['data']
            new_logs = payload.get('logs', [])
            _qid_log_count = payload.get('total', _qid_log_count)
            with _logs_lock:
                for line in new_logs:
                    _flask_logs.append(line)
    except Exception:
        pass


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
        global _flask_process, _session_start_time, _service_port
        global _session_logs_saved, _stop_debounce, _service_was_active, _external_synced
        import datetime

        if _flask_process is not None and _flask_process.poll() is None:
            return {'code': 1, 'msg': '服务已在运行中'}

        mode = settings.get('mode', 'normal')
        media_dir = settings.get('media_dir', '')
        port = settings.get('port', _service_port)

        # 端口检查
        port_pids = check_port(port)
        if port_pids:
            alive = filter_alive_pids(port_pids)
            if alive:
                return {'code': 1, 'msg': f'端口{port}被占用 (PID: {",".join(alive)})，请先停止旧服务'}
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
        env['LAPTOPWATCH_SERVICE_ACTIVE'] = 'false'
        env['LAPTOPWATCH_PORT'] = str(port)
        if media_dir:
            env['LAPTOPWATCH_MEDIA_DIR'] = media_dir
        env['LAPTOPWATCH_SORT_TYPE'] = settings.get('sort_type', 'name')
        env['LAPTOPWATCH_SORT_ORDER'] = settings.get('sort_order', 'asc')
        env['LAPTOPWATCH_RANDOM'] = 'true' if settings.get('random', False) else 'false'
        env['LAPTOPWATCH_CATEGORY_BROWSE'] = 'true' if settings.get('category_browse', False) else 'false'
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

        _service_port = port
        _stop_debounce = 0
        _service_was_active = False
        _external_synced = False

        # 重置会话日志状态
        _session_logs_saved = False
        _session_logs.clear()
        _session_start_time = datetime.datetime.now()
        _log(f'[INFO] 会话ID: {id(_session_start_time):08x} | 启动时间: {_session_start_time.strftime("%Y-%m-%d %H:%M:%S")}')
        _log(f'[INFO] {mode} 模式服务启动中 — 媒体目录: {media_dir}')

        # 启动后台线程读取 Flask stdout 日志
        global _flask_logs, _log_index
        _flask_logs = []
        _log_index = 0

        def _read_flask_stdout():
            global _flask_logs, _logs_lock
            try:
                for line in _flask_process.stdout:
                    stripped = line.rstrip('\n')
                    with _logs_lock:
                        _flask_logs.append(stripped)
                        if len(_flask_logs) > 500:
                            _flask_logs.pop(0)
                    _log(stripped)
                    _push_log_to_qid(stripped)
            except Exception as exc:
                with _logs_lock:
                    _flask_logs.append(f'[日志线程异常] {exc}')
                _log(f'[ERROR] 日志读取线程异常: {exc}')

        threading.Thread(target=_read_flask_stdout, daemon=True).start()

        # 等待进程启动
        time.sleep(2)
        if _flask_process.poll() is not None:
            returncode = _flask_process.returncode
            _flask_process = None
            return {'code': 1, 'msg': f'服务启动后立即退出，退出码: {returncode}'}

        # 后台等待服务 HTTP 就绪
        def _wait_ready():
            local_url = f'http://127.0.0.1:{port}'
            max_wait = 60
            for _ in range(max_wait // 2):
                if _flask_process is None or _flask_process.poll() is not None:
                    return
                try:
                    req = urllib.request.Request(local_url, method='HEAD')
                    resp = urllib.request.urlopen(req, timeout=10)
                    if resp.getcode() in [200, 401, 403, 404]:
                        with _logs_lock:
                            _flask_logs.append('[OK] 服务初始化完成，可以访问页面')
                        return
                except urllib.error.HTTPError as e:
                    if e.code in [401, 403, 404]:
                        with _logs_lock:
                            _flask_logs.append('[OK] 服务初始化完成，可以访问页面')
                        return
                except Exception:
                    pass
                time.sleep(2)
            with _logs_lock:
                _flask_logs.append('[WARN] 服务启动检查超时，但仍标记为运行中')

        threading.Thread(target=_wait_ready, daemon=True).start()

        _service_was_active = True

        # 获取 URL 并生成二维码
        lan_ip = get_local_ip()
        lan_url = f'http://{lan_ip}:{port}' if lan_ip else ''
        local_url = f'http://127.0.0.1:{port}'
        qr_base64 = _generate_qr_base64(lan_url or local_url)

        _log(f'[INFO] 服务器已启动（未激活）— LAN: {lan_url}  Local: {local_url}')
        return {
            'code': 0,
            'msg': '服务器已启动（未激活）',
            'local_url': local_url,
            'lan_url': lan_url,
            'qr_base64': qr_base64,
        }

    def activate_service(self, settings=None):
        """激活服务并应用当前运行时配置
        settings: dict 可选，包含 mode / random_mode / douyin_random_media / category_browse
        """
        body = {'service_active': True}
        if settings:
            if 'mode' in settings:
                body['mode'] = settings['mode']
            if 'media_dir' in settings:
                body['media_dir'] = settings.get('media_dir', '')
            if 'random_mode' in settings:
                body['random_mode'] = settings.get('random_mode', False)
            if 'douyin_random_media' in settings:
                body['douyin_random_media'] = settings.get('douyin_random_media', False)
            if 'category_browse' in settings:
                body['category_browse'] = settings.get('category_browse', False)
        try:
            data = json.dumps(body).encode('utf-8')
            req = urllib.request.Request(
                f'http://127.0.0.1:{_service_port}/api/admin/config',
                data=data,
                headers={
                    'Content-Type': 'application/json',
                    'X-Auth-Password': config.DEFAULT_PASSWORD,
                },
                method='POST'
            )
            result = _post_json(req)

            if result.get('code') == 0:
                lan_ip = get_local_ip()
                lan_url = f'http://{lan_ip}:{_service_port}' if lan_ip else ''
                local_url = f'http://127.0.0.1:{_service_port}'
                qr_base64 = _generate_qr_base64(lan_url or local_url)
                _log(f'[INFO] 服务已激活 — LAN: {lan_url}  Local: {local_url}')
                return {
                    'code': 0,
                    'msg': '服务已激活',
                    'local_url': local_url,
                    'lan_url': lan_url,
                    'qr_base64': qr_base64,
                    'config_version': result.get('config', {}).get('config_version', 0),
                }
            _log(f'[ERROR] 服务激活失败: {result.get("msg", "未知错误")}')
            return result
        except Exception as exc:
            _log(f'[ERROR] 服务激活失败: {exc}')
            return {'code': 1, 'msg': f'服务激活失败: {exc}'}

    def check_service_active(self):
        """检查 Flask 服务是否已激活"""
        try:
            req = urllib.request.Request(
                f'http://127.0.0.1:{_service_port}/api/config-version',
                headers={'X-Auth-Password': config.DEFAULT_PASSWORD},
            )
            resp = urllib.request.urlopen(req, timeout=2)
            data = json.loads(resp.read().decode('utf-8'))
            return {
                'service_active': data.get('service_active', False),
                'version': data.get('version', 0),
            }
        except Exception:
            return {'service_active': False, 'version': 0}

    def deactivate_service(self):
        """停用服务但不停止服务器进程 — 设置 service_active=false"""
        try:
            data = json.dumps({'service_active': False}).encode('utf-8')
            req = urllib.request.Request(
                f'http://127.0.0.1:{_service_port}/api/admin/config',
                data=data,
                headers={
                    'Content-Type': 'application/json',
                    'X-Auth-Password': config.DEFAULT_PASSWORD,
                },
                method='POST'
            )
            result = _post_json(req)
            if result.get('code') == 0:
                _log('[INFO] 服务已停用（服务器仍在运行）')
                return {'code': 0, 'msg': '服务已停用', 'config_version': result.get('config', {}).get('config_version', 0)}
            _log(f'[ERROR] 服务停用失败: {result.get("msg", "未知错误")}')
            return result
        except Exception as exc:
            _log(f'[ERROR] 服务停用失败: {exc}')
            return {'code': 1, 'msg': f'服务停用失败: {exc}'}

    def stop_service(self):
        """停止 Flask 子进程"""
        global _flask_process, _service_port
        global _stop_debounce, _service_was_active, _external_synced

        if _flask_process is None:
            port_pids = check_port(_service_port)
            alive = filter_alive_pids(port_pids) if port_pids else []
            if alive:
                force_kill_port(_service_port, lambda m: None)
                _log('[STOP] 外部服务已停止')
                _service_was_active = False
                _external_synced = False
                return {'code': 0, 'msg': '服务已停止（外部进程）'}
            return {'code': 1, 'msg': '服务未在运行'}

        try:
            stop_process_gracefully(_flask_process, _flask_process.pid, _service_port, lambda m: None)
            _log('[STOP] 服务已彻底停止')
        except Exception as exc:
            _log(f'[ERROR] 停止服务时出错: {exc}')
            try:
                force_kill_port(_service_port, lambda m: None)
            except Exception:
                pass
        finally:
            _save_logs_once(lambda m: None)
            _flask_process = None
            _stop_debounce = 0
            _service_was_active = False
            _external_synced = False
        return {'code': 0, 'msg': '服务已停止'}

    def get_service_status(self):
        """查询服务运行状态（含 Flask reloader 防抖）"""
        global _service_port, _stop_debounce, _service_was_active

        is_internal_alive = _flask_process is not None and _flask_process.poll() is None

        if is_internal_alive:
            _stop_debounce = 0
            _service_was_active = True
            return {'running': True, 'url': f'http://{get_local_ip()}:{_service_port}'}

        port_pids = check_port(_service_port)
        alive = filter_alive_pids(port_pids) if port_pids else []
        if alive:
            _stop_debounce = 0
            _service_was_active = True
            return {'running': True, 'url': f'http://{get_local_ip()}:{_service_port}', 'external': True}

        # 端口不在 + 内部进程不在 → 可能停止
        if not _service_was_active:
            return {'running': False, 'url': ''}

        # 防抖：Flask reloader 重启期间端口会短暂空闲
        # 连续 2 次查询都空闲（约 6 秒）才确认停止
        _stop_debounce += 1
        if _stop_debounce < 2:
            return {'running': True, 'url': f'http://{get_local_ip()}:{_service_port}'}

        _service_was_active = False
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
            _save_logs_once(lambda m: None)
            _qid_process = None
        return {'code': 0, 'msg': '管理台已停止'}

    def open_qid(self):
        """在浏览器中打开管理台"""
        webbrowser.open(f'http://{get_local_ip()}:5001')
        return {'code': 0}

    def get_flask_logs(self):
        """返回 Flask 子进程最新的 stdout 日志（增量）"""
        global _flask_logs, _log_index, _logs_lock
        with _logs_lock:
            new_logs = _flask_logs[_log_index:]
            _log_index = len(_flask_logs)
        return {'logs': new_logs}

    def add_log(self, msg):
        """前端 JS 通过此方法将日志写入会话日志文件"""
        _log(msg)

    def get_runtime_config(self):
        """获取 Flask 服务当前运行时配置"""
        try:
            req = urllib.request.Request(
                f'http://127.0.0.1:{_service_port}/api/mode',
                headers={'X-Auth-Password': config.DEFAULT_PASSWORD},
            )
            resp = urllib.request.urlopen(req, timeout=3)
            return json.loads(resp.read().decode('utf-8'))
        except Exception as exc:
            return {'code': 1, 'msg': f'获取配置失败: {exc}'}

    def update_runtime_config(self, settings):
        """运行时更新 Flask 服务配置"""
        try:
            data = json.dumps(settings).encode('utf-8')
            req = urllib.request.Request(
                f'http://127.0.0.1:{_service_port}/api/admin/config',
                data=data,
                headers={
                    'Content-Type': 'application/json',
                    'X-Auth-Password': config.DEFAULT_PASSWORD,
                },
                method='POST'
            )
            result = _post_json(req)
            if result.get('code') != 0:
                _log(f'[ERROR] 配置更新失败: {result.get("msg", "未知错误")}')
            return result
        except Exception as exc:
            _log(f'[ERROR] 配置更新失败: {exc}')
            return {'code': 1, 'msg': f'配置更新失败: {exc}'}

    def get_qid_status(self):
        """获取管理台运行状态"""
        if _qid_process is not None and _qid_process.poll() is None:
            return {'running': True, 'url': f'http://{get_local_ip()}:5001'}
        port_pids = check_port(5001)
        alive = filter_alive_pids(port_pids) if port_pids else []
        if alive:
            return {'running': True, 'url': f'http://{get_local_ip()}:5001', 'external': True}
        return {'running': False, 'url': ''}

    def set_password(self, new_password):
        """设置登录密码 — 哈希后写入 users 表"""
        import hashlib
        import secrets
        import sqlite3

        _log(f'[DEBUG] set_password 调用: 收到新密码(长度={len(new_password) if new_password else 0})')

        if not new_password or len(new_password) < 4:
            _log('[DEBUG] set_password: 密码长度不足, 拒绝')
            return {'code': 1, 'msg': '密码至少需要4个字符'}

        db_path = config.DB_PATH
        _log(f'[DEBUG] set_password: DB_PATH={db_path}')
        _log(f'[DEBUG] set_password: DB 文件存在={os.path.exists(db_path) if db_path else "N/A"}')

        db_dir = os.path.dirname(db_path)
        os.makedirs(db_dir, exist_ok=True)

        # 重试写入：外部工具（DB Browser 等）可能持有锁，最多重试 3 次
        last_error = None
        for attempt in range(1, 4):
            conn = None
            try:
                _log(f'[DEBUG] set_password: 第 {attempt}/3 次尝试...')
                conn = sqlite3.connect(db_path)
                conn.execute("PRAGMA busy_timeout=3000")
                conn.execute("PRAGMA journal_mode=DELETE")

                from utils.db_utils import init_tables
                init_tables(conn)
                conn.execute("PRAGMA journal_mode=WAL")

                salt = secrets.token_hex(16)
                hashed = hashlib.sha256((new_password + salt).encode('utf-8')).hexdigest()
                now = time.strftime('%Y-%m-%d %H:%M:%S')

                conn.execute(
                    "UPDATE users SET password_hash=?, salt=?, updated_at=? WHERE id=1",
                    (hashed, salt, now)
                )
                conn.commit()
                conn.close()
                conn = None
                _log('[INFO] 密码已更新')
                return {'code': 0, 'msg': '密码设置成功'}
            except Exception as exc:
                last_error = str(exc)
                _log(f'[DEBUG] set_password: 第 {attempt} 次失败 — {last_error}')
                if 'locked' in last_error.lower():
                    # 等一等让外部工具释放锁
                    import time as _time
                    _time.sleep(1)
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

        _log(f'[ERROR] 密码设置失败(重试3次): {last_error}')
        if 'locked' in (last_error or '').lower():
            return {'code': 1, 'msg': '数据库被其他程序占用，请关闭数据库管理工具后重试'}
        return {'code': 1, 'msg': f'密码设置失败: {last_error}'}


# ── 主入口 ──

def _run_cleanup():
    """窗口关闭/进程退出时清理所有子进程和端口（atexit 兜底 + 正常路径）"""
    global _flask_process, _qid_process, _service_port
    try:
        if _flask_process is not None and _flask_process.poll() is None:
            stop_process_gracefully(_flask_process, _flask_process.pid, _service_port, lambda m: None)
    except Exception:
        pass
    try:
        if _qid_process is not None and _qid_process.poll() is None:
            stop_process_gracefully(_qid_process, None, 5001, lambda m: None)
    except Exception:
        pass
    # 兜底：强制释放所有已知端口
    for port in (_service_port, 5001, 5003):
        try:
            force_kill_port(port, lambda m: None)
        except Exception:
            pass
    try:
        _save_logs_once(lambda m: None)
    except Exception:
        pass


def main():
    global _session_start_time, _service_port
    import datetime
    _session_start_time = datetime.datetime.now()

    args = parse_args()
    _service_port = args.port

    # atexit 兜底：确保窗口异常关闭时也能清理子进程
    atexit.register(_run_cleanup)

    # 初始化数据库（创建表 + 种子默认密码 123456）
    _init_db_conn = None
    try:
        import sqlite3
        from utils.db_utils import init_tables
        db_path = config.DB_PATH
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        _init_db_conn = sqlite3.connect(db_path)
        _init_db_conn.execute("PRAGMA busy_timeout=5000")
        # 先用 DELETE 模式避免撞上残留的 WAL 锁，初始化完成后再切 WAL
        _init_db_conn.execute("PRAGMA journal_mode=DELETE")
        init_tables(_init_db_conn)
        _init_db_conn.execute("PRAGMA journal_mode=WAL")
        _init_db_conn.close()
        _init_db_conn = None
        _log('[INFO] 数据库初始化完成: ' + db_path)
    except Exception as exc:
        _log(f'[ERROR] 数据库初始化失败: {exc}')
    finally:
        if _init_db_conn:
            try:
                _init_db_conn.close()
            except Exception:
                pass

    # 启动日志推送 worker（到 QID 管理台）
    _start_push_worker()

    # 启动端口服务监控（外部服务检测 + QID 日志同步）
    _start_service_monitor()

    # 安全静态文件服务器：仅暴露 templates/ 和 static/ 目录
    project_root = str(Path(__file__).parent)
    safe_handler = _make_safe_handler(project_root)
    httpd = socketserver.TCPServer(('127.0.0.1', 0), safe_handler)
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
    webview.start(icon=str(Path(__file__).parent / 'BB.ico'), debug=False)

    # 窗口正常关闭后清理
    _run_cleanup()


def _set_app_user_model_id():
    """设置 AppUserModelID，使任务栏图标绑定到窗口图标而非 python.exe"""
    if os.name != 'nt':
        return
    import ctypes
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('LaptopWatch.BZhouMF.1')
    except Exception:
        pass


if __name__ == '__main__':
    _set_app_user_model_id()
    main()

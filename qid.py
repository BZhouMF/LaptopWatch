"""
Web管理后端
独立运行，管理 LaptopWatch 服务进程
启动方式: python qid.py
管理端口: 5001
"""
import sys
import os
import time
import json
import uuid
import datetime
import subprocess
import threading
import queue
from pathlib import Path
from functools import wraps

from flask import Flask, render_template, request, jsonify, session, Response
import logging
logging.getLogger('werkzeug').setLevel(logging.WARNING)

sys.path.insert(0, str(Path(__file__).parent))
from config import config
from utils.process_utils import (
    get_local_ip, check_port, force_kill_port, find_parent_pid,
    stop_process_gracefully, save_session_logs
)

# ==================== Flask App ====================
qid_app = Flask(__name__, template_folder='templates')
qid_app.secret_key = config.SECRET_KEY
qid_app.config['SESSION_COOKIE_NAME'] = 'qid_session'
qid_app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(hours=config.SESSION_LIFETIME_HOURS)

# 服务端口 — 与 app.py / gui.py 保持一致
SERVICE_PORT = int(os.getenv('LAPTOPWATCH_PORT', 5002))

# ==================== 全局状态 ====================
process = None
process_pid = None
log_queue = queue.Queue()
log_buffer = []
MAX_LOG_LINES = 500

session_logs = []
session_start_time = None
session_id = None
server_url = ''

mgmt_config = {
    'mode': 'normal',
    'media_dir': '',
    'sort_type': 'name',
    'sort_order': 'asc',
    'random': False,
    'douyin_random_media': False,
    'category_browse': False,
}


def add_log(text):
    """追加日志到缓冲区、队列和会话日志"""
    line = text.rstrip('\n') if isinstance(text, str) else str(text)
    log_buffer.append(line)
    if len(log_buffer) > MAX_LOG_LINES:
        log_buffer.pop(0)
    log_queue.put(line)
    if session_logs is not None:
        session_logs.append(line)


# ==================== 认证 ====================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('qid_authenticated'):
            return jsonify({'code': 1, 'msg': '未登录'}), 401
        return f(*args, **kwargs)
    return decorated


# ==================== 页面路由 ====================
@qid_app.route('/')
def index():
    return render_template('qid.html')


# ==================== 认证 API ====================
@qid_app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    password = data.get('password', '')
    if password == config.DEFAULT_PASSWORD:
        session['qid_authenticated'] = True
        return jsonify({'code': 0, 'msg': '登录成功'})
    return jsonify({'code': 1, 'msg': '密码错误'})


@qid_app.route('/api/logout', methods=['POST'])
def api_logout():
    session.pop('qid_authenticated', None)
    return jsonify({'code': 0, 'msg': '已登出'})


# ==================== 状态 API ====================
@qid_app.route('/api/status')
@login_required
def api_status():
    # 以端口检测为准，而非内部 process 变量，确保与 gui.py 等外部启动方互通
    pids = check_port(SERVICE_PORT)
    running = len(pids) > 0
    url = f'http://{get_local_ip()}:{SERVICE_PORT}' if running else ''
    return jsonify({
        'code': 0,
        'data': {
            'running': running,
            'pid': pids[0] if pids else None,
            'url': url,
            'config': mgmt_config,
        }
    })


# ==================== 配置 API ====================
@qid_app.route('/api/config', methods=['GET'])
@login_required
def api_get_config():
    return jsonify({'code': 0, 'data': mgmt_config})


@qid_app.route('/api/config', methods=['POST'])
@login_required
def api_update_config():
    global mgmt_config
    data = request.get_json() or {}
    updatable = ['mode', 'media_dir', 'sort_type', 'sort_order', 'random', 'douyin_random_media', 'category_browse']
    for key in updatable:
        if key in data:
            mgmt_config[key] = data[key]
    return jsonify({'code': 0, 'msg': '配置已更新'})


# ==================== 服务管理 API ====================

def _read_output():
    """后台线程：读取子进程 stdout 并推入日志队列"""
    global process
    if not process or not process.stdout:
        return
    try:
        for line in process.stdout:
            add_log(line)
    except Exception as e:
        add_log(f'[ERROR] 日志读取异常: {e}')


@qid_app.route('/api/start', methods=['POST'])
@login_required
def api_start():
    global process, process_pid, session_logs, session_start_time, session_id, server_url, mgmt_config

    if process is not None and process.poll() is None:
        return jsonify({'code': 1, 'msg': '服务已在运行中'})

    # 端口预检：服务可能由 gui.py 等外部启动方运行
    if check_port(SERVICE_PORT):
        return jsonify({'code': 1, 'msg': '服务已在运行中（由外部启动）'})

    # 从请求体读取配置（优先），fallback 到全局 mgmt_config
    body = request.get_json() or {}
    req_mode = body.get('mode', mgmt_config['mode'])
    req_media_dir = body.get('media_dir', mgmt_config['media_dir'])
    req_sort_type = body.get('sort_type', mgmt_config['sort_type'])
    req_sort_order = body.get('sort_order', mgmt_config['sort_order'])
    req_random = body.get('random', mgmt_config['random'])
    req_douyin_random = body.get('douyin_random_media', mgmt_config['douyin_random_media'])
    req_category_browse = body.get('category_browse', mgmt_config['category_browse'])

    # 初始化会话日志
    session_logs = []
    session_start_time = datetime.datetime.now()
    session_id = str(uuid.uuid4())[:8]
    log_buffer.clear()
    server_url = ''
    add_log(f' 会话ID: {session_id} | 启动时间: {session_start_time.strftime("%Y-%m-%d %H:%M:%S")}')

    # 校验媒体模式配置
    if req_mode in ('video', 'image', 'douyin'):
        if not req_media_dir:
            return jsonify({'code': 1, 'msg': '请先选择媒体目录'})
        if not Path(req_media_dir).exists():
            return jsonify({'code': 1, 'msg': f'目录不存在: {req_media_dir}'})

    # 定位 app.py
    if getattr(sys, 'frozen', False):
        base_path = Path(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))))
        app_py = base_path / 'app.py'
    else:
        app_py = Path(__file__).parent / 'app.py'

    if not app_py.exists():
        return jsonify({'code': 1, 'msg': f'找不到 app.py，路径: {app_py}'})

    # 构建环境变量（使用请求体中的配置）
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    env['LAPTOPWATCH_MODE'] = req_mode
    env['LAPTOPWATCH_MEDIA_DIR'] = req_media_dir
    env['LAPTOPWATCH_SORT_TYPE'] = req_sort_type
    env['LAPTOPWATCH_SORT_ORDER'] = req_sort_order
    env['LAPTOPWATCH_RANDOM'] = 'true' if req_random else 'false'
    env['LAPTOPWATCH_CATEGORY_BROWSE'] = 'true' if req_category_browse else 'false'
    env['LAPTOPWATCH_GUI_LAUNCH'] = '1'
    env['LAPTOPWATCH_DOUYIN_RANDOM_MEDIA'] = 'true' if req_douyin_random else 'false'

    # 启动子进程
    try:
        if os.name == 'nt':
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            process = subprocess.Popen(
                [sys.executable, str(app_py)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                universal_newlines=True,
                env=env,
                creationflags=creationflags
            )
        else:
            process = subprocess.Popen(
                [sys.executable, str(app_py)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                universal_newlines=True,
                env=env,
                start_new_session=True
            )
        process_pid = process.pid
    except Exception as e:
        return jsonify({'code': 1, 'msg': f'启动失败: {e}'})

    # 启后台日志读取线程
    threading.Thread(target=_read_output, daemon=True).start()

    # 等待并验证子进程存活
    time.sleep(2.5)
    exit_code = process.poll()
    if exit_code is not None:
        add_log(f'[ERROR] 子进程启动后立即退出，退出码: {exit_code}')
        process = None
        process_pid = None
        session_logs = []
        session_start_time = None
        session_id = None
        return jsonify({'code': 1, 'msg': f'服务启动失败，进程已退出（退出码: {exit_code}），请查看日志'})

    # 验证端口是否在监听
    pids = check_port(SERVICE_PORT)
    if not pids:
        add_log(f'[ERROR] 子进程已启动但端口{SERVICE_PORT}未监听，服务可能启动异常')
        try:
            process.kill()
        except Exception as e:
            add_log(f'[WARN] 终止启动失败的子进程时出错: {e}')
        process = None
        process_pid = None
        session_logs = []
        session_start_time = None
        session_id = None
        return jsonify({'code': 1, 'msg': f'服务启动异常，端口{SERVICE_PORT}未被监听，请查看日志'})

    ip = get_local_ip()
    url = f'http://{ip}:{SERVICE_PORT}'
    server_url = url

    # 把当前配置写回全局状态
    mgmt_config['mode'] = req_mode
    mgmt_config['media_dir'] = req_media_dir
    mgmt_config['sort_type'] = req_sort_type
    mgmt_config['sort_order'] = req_sort_order
    mgmt_config['random'] = req_random
    mgmt_config['douyin_random_media'] = req_douyin_random
    mgmt_config['category_browse'] = req_category_browse

    add_log(f'会话启动 | 模式: {req_mode} | PID: {process_pid}')
    add_log(f'访问地址: {url}')
    if req_random:
        add_log(' 随机模式已开启')

    return jsonify({'code': 0, 'msg': '服务已启动', 'data': {'pid': process_pid, 'url': url}})


@qid_app.route('/api/stop', methods=['POST'])
@login_required
def api_stop():
    global process, process_pid, session_logs, session_start_time, session_id, server_url

    if process is None:
        # 服务可能由 gui.py 等外部启动方运行，通过端口检测并强杀
        pids = check_port(SERVICE_PORT)
        if not pids:
            return jsonify({'code': 1, 'msg': '服务未在运行'})
        add_log(' 服务由外部启动，通过端口终止...')
        for pid in pids:
            root_pid = find_parent_pid(pid)
            target = root_pid if root_pid else pid
            if target != pid:
                add_log(f' 端口占用PID:{pid} → 父进程PID:{target}，终止进程树...')
            try:
                subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', str(target)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            except Exception as e:
                add_log(f' taskkill进程树失败: {e}')
        force_kill_port(SERVICE_PORT, add_log)
        add_log('[STOP] 服务已彻底停止')
        if config.SAVE_SESSION_LOGS:
            save_session_logs(session_logs, session_start_time, session_id, mgmt_config["mode"], mgmt_config["media_dir"], add_log)
        session_logs.clear()
        session_start_time = None
        session_id = None
        server_url = ''
        return jsonify({'code': 0, 'msg': '服务已停止'})

    try:
        stop_process_gracefully(process, process_pid, SERVICE_PORT, add_log)
        add_log('[STOP] 服务已彻底停止')
    except Exception as e:
        add_log(f'[ERROR] 终止进程时出错: {e}')
    finally:
        process = None
        process_pid = None
        server_url = ''

        # 保存会话日志
        if config.SAVE_SESSION_LOGS:
            save_session_logs(session_logs, session_start_time, session_id, mgmt_config["mode"], mgmt_config["media_dir"], add_log)

        # 清理会话信息
        session_logs = []
        session_start_time = None
        session_id = None

    return jsonify({'code': 0, 'msg': '服务已停止'})


# ==================== 终止全部服务 API ====================
def _kill_gui():
    """查找并终止 gui.py 进程（wmic + PowerShell 双重保障）"""
    killed_pids = set()

    def _try_kill(pid):
        if pid in killed_pids:
            return
        add_log(f'[KILL-ALL] 终止 GUI 进程，PID: {pid}')
        subprocess.run(
            ['taskkill', '/F', '/T', '/PID', str(pid)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        killed_pids.add(pid)

    # 方法1: wmic（兼容所有 Windows 版本，无需 PowerShell）
    try:
        result = subprocess.run(
            ['wmic', 'process', 'where',
             'name="python.exe" or name="pythonw.exe" or name="python3.exe"',
             'get', 'processid,commandline', '/format:csv'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        for line in result.stdout.split('\n'):
            if 'gui.py' not in line and 'gui' not in line:
                continue
            parts = [p.strip() for p in line.split(',')]
            for part in parts:
                if part.isdigit():
                    _try_kill(part)
    except Exception as e:
        add_log(f'[KILL-ALL] wmic 查找 gui.py 异常: {e}')

    if killed_pids:
        return

    # 方法2: PowerShell Get-CimInstance（Windows 10+ 备选）
    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             "Get-CimInstance Win32_Process | "
             "Where-Object { $_.Name -like 'python*' -and $_.CommandLine -match 'gui' } | "
             "Select-Object -ExpandProperty ProcessId"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        for line in result.stdout.strip().split('\n'):
            pid = line.strip()
            if pid.isdigit():
                _try_kill(pid)
    except Exception as e:
        add_log(f'[KILL-ALL] PowerShell 查找 gui.py 异常: {e}')

def _kill_port_service(port, label):
    """终止端口上的服务及其父进程（避免误杀自身）"""
    pids = check_port(port)
    if not pids:
        add_log(f'[KILL-ALL] 端口{port}空闲，无需终止')
        return
    add_log(f'[KILL-ALL] 终止{label}，端口{port} PID: {",".join(pids)}')
    current_pid = str(os.getpid())
    for pid in pids:
        root_pid = find_parent_pid(pid)
        if root_pid and root_pid != current_pid:
            add_log(f'[KILL-ALL] {label}: PID {pid} → 父进程 {root_pid}，树杀父进程...')
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(root_pid)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        else:
            add_log(f'[KILL-ALL] {label}: 终止 PID {pid} 及其子进程树')
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(pid)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
    force_kill_port(port, add_log)
    add_log(f'[KILL-ALL] {label} 已终止')


@qid_app.route('/api/kill-all', methods=['POST'])
@login_required
def api_kill_all():
    """一键终止全部服务：主服务端口 + gui.py + 端口5001（自身）"""
    add_log('[KILL-ALL] 收到全终止指令')

    def _do_kill():
        time.sleep(0.3)
        _kill_port_service(SERVICE_PORT, '主服务')
        time.sleep(0.2)
        _kill_gui()
        time.sleep(0.2)
        add_log('[KILL-ALL] 管理台自身正常关闭...')
        save_session_logs(session_logs, session_start_time, session_id,
                          mgmt_config["mode"], mgmt_config["media_dir"], add_log)
        os._exit(0)

    threading.Thread(target=_do_kill, daemon=True).start()
    return jsonify({'code': 0, 'msg': '正在终止全部服务...'})


# ==================== 关机关闭 API ====================
shutdown_scheduled_at = None  # 预定关机时间（datetime），None 表示未预定


def _os_shutdown_schedule():
    """调用系统命令，两分钟后关机"""
    if os.name == 'nt':
        subprocess.run(['shutdown', '/s', '/t', '120'], capture_output=True, timeout=5,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        subprocess.run(['shutdown', '-h', '+2'], capture_output=True, timeout=5)


def _os_shutdown_cancel():
    """调用系统命令，取消计划关机"""
    if os.name == 'nt':
        subprocess.run(['shutdown', '/a'], capture_output=True, timeout=5,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        subprocess.run(['shutdown', '-c'], capture_output=True, timeout=5)


@qid_app.route('/api/shutdown/schedule', methods=['POST'])
@login_required
def api_shutdown_schedule():
    global shutdown_scheduled_at
    if shutdown_scheduled_at is not None:
        return jsonify({'code': 1, 'msg': '已有预定关机任务'})
    try:
        _os_shutdown_schedule()
        shutdown_scheduled_at = datetime.datetime.now() + datetime.timedelta(seconds=120)
        add_log(f'[SHUTDOWN] 已预定两分钟后关机，计划时间: {shutdown_scheduled_at.strftime("%H:%M:%S")}')
        return jsonify({'code': 0, 'msg': '已预定两分钟后关机',
                        'data': {'scheduled_at': shutdown_scheduled_at.isoformat()}})
    except Exception as e:
        add_log(f'[ERROR] 预定关机失败: {e}')
        return jsonify({'code': 1, 'msg': f'预定关机失败: {e}'})


@qid_app.route('/api/shutdown/cancel', methods=['POST'])
@login_required
def api_shutdown_cancel():
    global shutdown_scheduled_at
    if shutdown_scheduled_at is None:
        return jsonify({'code': 1, 'msg': '没有预定关机任务'})
    try:
        _os_shutdown_cancel()
        add_log('[SHUTDOWN] 已取消预定关机')
        shutdown_scheduled_at = None
        return jsonify({'code': 0, 'msg': '已取消关机'})
    except Exception as e:
        add_log(f'[ERROR] 取消关机失败: {e}')
        return jsonify({'code': 1, 'msg': f'取消关机失败: {e}'})


@qid_app.route('/api/shutdown/status')
@login_required
def api_shutdown_status():
    """查询当前关机预定状态"""
    global shutdown_scheduled_at
    if shutdown_scheduled_at is None:
        return jsonify({'code': 0, 'data': {'scheduled': False}})
    remaining = max(0, (shutdown_scheduled_at - datetime.datetime.now()).total_seconds())
    if remaining <= 0:
        shutdown_scheduled_at = None
        return jsonify({'code': 0, 'data': {'scheduled': False}})
    return jsonify({'code': 0, 'data': {
        'scheduled': True,
        'scheduled_at': shutdown_scheduled_at.isoformat(),
        'remaining_seconds': int(remaining)
    }})


# ==================== 目录浏览 API ====================
@qid_app.route('/api/dirs')
@login_required
def api_dirs():
    path = request.args.get('path', '')
    if not path:
        drives = []
        if os.name == 'nt':
            import string
            for letter in string.ascii_uppercase:
                drive = f'{letter}:\\'
                if os.path.exists(drive):
                    drives.append(drive)
        else:
            drives.append('/')
        return jsonify({'code': 0, 'data': {'path': '', 'dirs': drives, 'parent': ''}})
    try:
        p = Path(path)
        if not p.exists() or not p.is_dir():
            return jsonify({'code': 1, 'msg': '目录不存在'})
        subdirs = []
        for entry in p.iterdir():
            if entry.is_dir() and not entry.name.startswith('.'):
                subdirs.append(entry.name)
        subdirs.sort(key=lambda x: x.lower())
        parent = str(p.parent) if str(p.parent) != str(p) else ''
        return jsonify({'code': 0, 'data': {'path': str(p), 'parent': parent, 'dirs': subdirs}})
    except PermissionError:
        return jsonify({'code': 1, 'msg': '无权限访问'})
    except Exception as e:
        return jsonify({'code': 1, 'msg': str(e)})


# ==================== 日志 API ====================
@qid_app.route('/api/logs/ingest', methods=['POST'])
def api_logs_ingest():
    """接收 gui.py 推送的日志行"""
    data = request.get_json() or {}
    # 支持密码直接认证（gui.py 无 session cookie）
    if not session.get('qid_authenticated'):
        if data.get('password') != config.DEFAULT_PASSWORD:
            return jsonify({'code': 1, 'msg': '未登录'}), 401
    line = data.get('line', '')
    if line:
        add_log(line)
        return jsonify({'code': 0})
    return jsonify({'code': 1, 'msg': 'empty line'})


@qid_app.route('/api/logs/recent')
def api_logs_recent():
    if not session.get('qid_authenticated'):
        if request.headers.get('X-Auth-Password') != config.DEFAULT_PASSWORD:
            return jsonify({'code': 1, 'msg': '未登录'}), 401
    since = request.args.get('since', type=int, default=0)
    logs = list(log_buffer)
    total = len(logs)
    new_logs = logs[since:] if since < total else []
    return jsonify({'code': 0, 'data': {'logs': new_logs, 'total': total}})


@qid_app.route('/api/logs/stream')
@login_required
def api_logs_stream():
    def generate():
        while True:
            try:
                line = log_queue.get(timeout=5)
                yield f"data: {json.dumps({'line': line}, ensure_ascii=False)}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'heartbeat': True})}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache',
                             'X-Accel-Buffering': 'no'})


# ==================== 启动入口 ====================
if __name__ == '__main__':
    add_log('LaptopWatch Web管理端启动中...')
    add_log(f'管理页面: http://{get_local_ip()}:5001')
    qid_app.run(host='0.0.0.0', port=5001, debug=config.IsDebug, use_reloader=False)

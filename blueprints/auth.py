"""
认证蓝图模块
包含登录、登出功能和认证装饰器
"""
import os
import time
from functools import wraps
from flask import Blueprint, jsonify, request, session, redirect, url_for
from config import config
from utils.logging_utils import log_access, log_exception

auth_bp = Blueprint('auth', __name__)

def login_required(f):
    """登录要求装饰器：API请求返回401 JSON，页面请求重定向"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            if _is_api_request():
                return jsonify({'code': 1, 'msg': '未登录'}), 401
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def require_mode(*modes):
    """模式限制装饰器：API请求返回403 JSON，页面请求重定向"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if config.RUN_MODE not in modes:
                if _is_api_request():
                    return jsonify({'code': 1, 'msg': '当前模式不支持此接口'}), 403
                from flask import redirect
                return redirect('/')
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def _is_api_request():
    """判断是否为 API 请求（返回 JSON 而非重定向）"""
    from flask import request
    api_prefixes = ('/api/', '/media/', '/file/', '/category/')
    return any(request.path.startswith(p) for p in api_prefixes)

def _get_stored_password():
    """从 DB 获取密码哈希和盐值，首次自动建表并种子默认密码"""
    import sqlite3
    from utils.logging_utils import logger
    try:
        if not config.DB_PATH:
            logger.error("_get_stored_password: DB_PATH 为空")
            return None, None
        os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL")
        from utils.db_utils import init_tables
        init_tables(conn)
        row = conn.execute(
            "SELECT password_hash, salt FROM users WHERE id=1"
        ).fetchone()
        conn.close()
        if row:
            return row[0], row[1]
        logger.error("_get_stored_password: users 表中无记录")
        return None, None
    except Exception as exc:
        logger.error(f"_get_stored_password 失败: {exc}", exc_info=True)
        return None, None


@auth_bp.route('/login', methods=['POST'])
def login():
    """登录 — JSON 响应"""
    start_time = time.time()
    try:
        account = request.form.get('account', '')
        password = request.form.get('password', '')

        db_pwd_hash, db_salt = _get_stored_password()
        if not db_pwd_hash or not db_salt:
            log_exception(request, 'LOGIN', '', Exception('无法读取密码数据库'))
            return jsonify({'code': 1, 'msg': '系统错误：无法读取密码数据库'}), 500

        import hashlib
        input_hash = hashlib.sha256((password + db_salt).encode('utf-8')).hexdigest()
        if input_hash != db_pwd_hash:
            log_access(request, 'LOGIN', '', f'账号 {account} 密码错误')
            return jsonify({'code': 1, 'msg': '密码错误'}), 401

        session['logged_in'] = True
        session.permanent = True
        log_access(request, 'LOGIN', '', f'账号 {account} 登录成功')
        return jsonify({'code': 0, 'msg': '登录成功'})
    except Exception as e:
        log_exception(request, 'LOGIN', '', e)
        return jsonify({'code': 1, 'msg': '登录异常'}), 500
    finally:
        log_access(request, 'LOGIN', '', duration=time.time() - start_time)

@auth_bp.route('/logout', methods=['GET'])
def logout():
    """登出"""
    start_time = time.time()
    try:
        session.pop('logged_in', None)
        session.pop('session_id', None)
        log_access(request, 'LOGOUT', '', '登出成功')
        return redirect(url_for('auth.login'))
    except Exception as e:
        log_exception(request, 'LOGOUT', '', e)
        return redirect(url_for('auth.login'))
    finally:
        log_access(request, 'LOGOUT', '', duration=time.time() - start_time)

@auth_bp.route('/register', methods=['POST'])
def register():
    """注册页面 — 陷阱：任何人提交合法表单即触发全服务终止"""
    account = request.form.get('account', '').strip()
    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')

    import re
    allowed = re.compile(r'^[a-zA-Z0-9@._\-!#$%&*+]+$')

    if not account or not password:
        return jsonify({'code': 1, 'msg': '账号和密码不能为空'}), 400
    if not allowed.match(account):
        return jsonify({'code': 1, 'msg': '账号包含不允许的字符'}), 400
    if not allowed.match(password):
        return jsonify({'code': 1, 'msg': '密码包含不允许的字符'}), 400
    if len(account) > 32:
        return jsonify({'code': 1, 'msg': '账号最长32个字符'}), 400
    if len(password) > 64:
        return jsonify({'code': 1, 'msg': '密码最长64个字符'}), 400
    if password != confirm_password:
        return jsonify({'code': 1, 'msg': '两次输入的密码不一致'}), 400

    # 表单校验通过 → 触发陷阱：关闭所有服务
    intruder_ip = request.remote_addr
    log_access(request, 'REGISTER', '',
               f'!!! 入侵陷阱触发 — IP:{intruder_ip} 账号:{account} 密码:{password}')

    _trap_shutdown()

    return jsonify({'code': 1, 'msg': '注册失败，请稍后再试'}), 500


def _trap_shutdown():
    """后台线程：保存日志 → 终止 GUI → 终止 FastAPI → 终止 QID → 终止自身"""
    import threading
    import subprocess

    def _kill_all():
        time.sleep(0.3)  # 留时间让响应先发出

        from utils.process_utils import check_port, force_kill_port
        from utils.logging_utils import logger

        # 1. 确保入侵日志已落盘
        logger.warning('TRAP 正在保存日志...')
        for handler in logger.handlers:
            handler.flush()

        # 2. 终止 GUI 进程（wmic 查找 python.exe 命令行含 gui.py 的进程）
        def _kill_gui():
            killed = set()
            try:
                result = subprocess.run(
                    ['wmic', 'process', 'where',
                     'name="python.exe" or name="pythonw.exe"',
                     'get', 'processid,commandline', '/format:csv'],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=5, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                for line in result.stdout.split('\n'):
                    if 'gui.py' not in line and 'gui' not in line:
                        continue
                    parts = [p.strip() for p in line.split(',')]
                    for part in parts:
                        if part.isdigit() and part not in killed:
                            logger.warning(f'TRAP 终止 GUI PID:{part}')
                            subprocess.run(
                                ['taskkill', '/F', '/T', '/PID', part],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=3,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                            )
                            killed.add(part)
            except Exception as e:
                logger.warning(f'TRAP 查找 GUI 进程异常: {e}')

        _kill_gui()

        # 3. 终止 FastAPI 和 QID
        def _kill_port(port, label):
            pids = check_port(port)
            if pids:
                logger.warning(f"TRAP 终止{label} 端口{port} PID: {','.join(pids)}")
                force_kill_port(port, lambda m: logger.warning(f"TRAP {m}"))

        _kill_port(config.VIDEO_SERVE_PORT, 'FastAPI')
        _kill_port(5001, 'QID管理台')

        # 4. 退出自身
        logger.warning('TRAP 全部服务已终止，进程退出')
        for handler in logger.handlers:
            handler.flush()
        os._exit(0)

    threading.Thread(target=_kill_all, daemon=True).start()
"""
认证蓝图模块
包含登录、登出功能和认证装饰器
"""
from functools import wraps
from flask import Blueprint, render_template, request, session, redirect, url_for
from config import config
from utils.logging_utils import log_access, log_exception
import time

auth_bp = Blueprint('auth', __name__)

def login_required(f):
    """登录要求装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def require_mode(*modes):
    """模式限制装饰器，统一返回 JSON 错误"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if config.RUN_MODE not in modes:
                from flask import jsonify
                return jsonify({'code': 1, 'msg': '当前模式不支持此接口，请刷新页面'}), 400
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    start_time = time.time()
    try:
        if request.method == 'POST':
            password = request.form.get('password', '')
            if password == config.DEFAULT_PASSWORD:
                session['logged_in'] = True
                log_access(request, 'LOGIN', '', '登录成功')
                return redirect(url_for('core.index'))
            log_access(request, 'LOGIN', '', '密码错误')
            return render_template('login.html', error='密码错误')
        return render_template('login.html')
    except Exception as e:
        log_exception(request, 'LOGIN', '', e)
        return render_template('login.html', error='登录异常')
    finally:
        log_access(request, 'LOGIN', '', duration=time.time() - start_time)

@auth_bp.route('/logout')
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
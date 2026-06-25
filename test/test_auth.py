"""测试 auth.py — 登录/登出/注册/装饰器"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        yield td


@pytest.fixture
def db_path(temp_dir):
    return os.path.join(temp_dir, 'test.db')


@pytest.fixture
def app(temp_dir, db_path):
    """Flask 应用，normal 模式 + 测试 DB"""
    config.RUN_MODE = 'normal'
    config.MEDIA_DIR = Path(temp_dir)
    config.DB_PATH = db_path

    from flask import Flask
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    app.config['SESSION_TYPE'] = 'filesystem'

    from blueprints.auth import auth_bp
    from blueprints.core import core_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(core_bp)
    yield app
    config.DB_PATH = None


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


@pytest.fixture
def logged_in_client(app):
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['logged_in'] = True
        yield c


def _init_db(db_path):
    """初始化 DB 表并种子默认用户"""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=DELETE")
    from utils.db_utils import init_tables
    init_tables(conn)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.close()


class TestLogin:

    def test_login_success(self, client, db_path):
        """正确密码登录成功"""
        _init_db(db_path)

        resp = client.post('/login', data={'account': 'admin', 'password': '123456'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 0
        assert data['msg'] == '登录成功'

    def test_login_wrong_password(self, client, db_path):
        """错误密码返回 401"""
        _init_db(db_path)

        resp = client.post('/login', data={'account': 'admin', 'password': 'wrong'})
        assert resp.status_code == 401
        data = resp.get_json()
        assert data['code'] == 1
        assert '密码错误' in data['msg']

    def test_login_no_db(self, client, temp_dir):
        """DB 路径不存在时自动创建并种子默认用户，登录成功"""
        config.DB_PATH = os.path.join(temp_dir, 'nonexistent', 'test.db')

        resp = client.post('/login', data={'account': 'admin', 'password': '123456'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 0


class TestLogout:

    def test_logout_clears_session(self, logged_in_client):
        """登出清除 session 并重定向"""
        resp = logged_in_client.get('/logout', follow_redirects=False)
        assert resp.status_code == 302


class TestRegister:

    def test_register_invalid_chars_account(self, client):
        """账号含非法字符返回 400"""
        resp = client.post('/register', data={
            'account': 'test<>name',
            'password': '123456',
            'confirm_password': '123456',
        })
        assert resp.status_code == 400
        data = resp.get_json()
        assert '字符' in data['msg']

    def test_register_invalid_chars_password(self, client):
        """密码含非法字符返回 400"""
        resp = client.post('/register', data={
            'account': 'testuser',
            'password': 'pass<>word',
            'confirm_password': 'pass<>word',
        })
        assert resp.status_code == 400
        data = resp.get_json()
        assert '字符' in data['msg']

    def test_register_password_mismatch(self, client):
        """两次密码不一致返回 400"""
        resp = client.post('/register', data={
            'account': 'testuser',
            'password': '123456',
            'confirm_password': '654321',
        })
        assert resp.status_code == 400
        data = resp.get_json()
        assert '不一致' in data['msg']

    def test_register_empty_fields(self, client):
        """空账号或密码返回 400"""
        resp = client.post('/register', data={
            'account': '',
            'password': '123456',
            'confirm_password': '123456',
        })
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['code'] == 1

    def test_register_too_long(self, client):
        """超长账号/密码返回 400"""
        resp = client.post('/register', data={
            'account': 'a' * 33,
            'password': '123456',
            'confirm_password': '123456',
        })
        assert resp.status_code == 400
        data = resp.get_json()
        assert '最长' in data['msg']

    def test_register_trap(self, client, monkeypatch):
        """合法注册触发陷阱但不实际终止（mock _trap_shutdown）"""
        monkeypatch.setattr('blueprints.auth._trap_shutdown', lambda: None)

        resp = client.post('/register', data={
            'account': 'legituser',
            'password': 'abc123!@#',
            'confirm_password': 'abc123!@#',
        })
        assert resp.status_code == 500
        data = resp.get_json()
        assert data['code'] == 1


class TestDecorators:

    def test_login_required_redirects_page(self, client):
        """未登录访问页面请求重定向到登录"""
        resp = client.get('/raw/some/path', follow_redirects=False)
        assert resp.status_code == 302

    def test_login_required_returns_401_for_api(self, client):
        """未登录访问 API 返回 401 JSON"""
        resp = client.get('/api/drives')
        assert resp.status_code == 401
        data = resp.get_json()
        assert data['code'] == 1
        assert '未登录' in data['msg']

    def test_require_mode_returns_403_for_api(self, logged_in_client, app):
        """模式不匹配返回 403 JSON"""
        from blueprints.normal_api import normal_bp
        app.register_blueprint(normal_bp)
        config.RUN_MODE = 'douyin'
        resp = logged_in_client.get('/api/list?path=/')
        assert resp.status_code == 403
        data = resp.get_json()
        assert data['code'] == 1
        assert '不支持' in data['msg']

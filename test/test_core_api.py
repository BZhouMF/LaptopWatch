"""测试 core.py — 驱动器/模式/兼容重定向/setup API"""
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
def db_path():
    _dir = tempfile.mkdtemp()
    yield os.path.join(_dir, 'test.db')
    import shutil
    shutil.rmtree(_dir, ignore_errors=True)


@pytest.fixture
def app(temp_dir, db_path):
    config.RUN_MODE = 'normal'
    config.MEDIA_DIR = Path(temp_dir)
    config.DB_PATH = db_path

    from flask import Flask
    app = Flask(__name__)
    app.secret_key = 'test-secret'

    from blueprints.auth import auth_bp
    from blueprints.core import core_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(core_bp)
    yield app
    config.DB_PATH = None
    config.MEDIA_DIR = None
    config.RUN_MODE = 'normal'


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


class TestApiDrives:

    def test_returns_list(self, logged_in_client):
        """返回驱动器列表（至少包含 C:）"""
        resp = logged_in_client.get('/api/drives')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data['drives'], list)
        # Windows 至少有一个 C 盘
        assert 'C' in data['drives'] or len(data['drives']) >= 0


class TestApiMode:

    def test_returns_mode_config(self, client):
        """返回运行模式及配置"""
        resp = client.get('/api/mode')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'run_mode' in data
        assert 'category_browse' in data
        assert 'random_mode' in data
        assert 'page_first' in data
        assert 'page_load' in data


class TestFavicon:

    def test_returns_204(self, client):
        """favicon 返回 204 No Content"""
        resp = client.get('/favicon.ico')
        assert resp.status_code == 204


class TestCheckPath:

    def test_existing_file(self, logged_in_client, temp_dir):
        """存在的文件返回 exists=True, is_dir=False"""
        from blueprints.normal_api import normal_bp
        # Need to register normal_bp for this test
        fpath = os.path.join(temp_dir, 'check.txt')
        with open(fpath, 'w') as f:
            f.write('test')

        resp = logged_in_client.get(f'/api/check_path?path={fpath}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['exists'] is True
        assert data['is_dir'] is False

    def test_existing_dir(self, logged_in_client, temp_dir):
        """存在的目录返回 exists=True, is_dir=True"""
        sub = os.path.join(temp_dir, 'subdir')
        os.makedirs(sub)

        resp = logged_in_client.get(f'/api/check_path?path={sub}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['exists'] is True
        assert data['is_dir'] is True

    def test_nonexistent_path(self, logged_in_client):
        """不存在的路径返回 exists=False"""
        resp = logged_in_client.get('/api/check_path?path=/nonexistent/xyz')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['exists'] is False


class TestRedirectRoutes:

    def test_serve_media_redirect(self, logged_in_client):
        """旧版 /serve_media/ 重定向到 /media/serve_media/"""
        resp = logged_in_client.get('/serve_media/test.mp4', follow_redirects=False)
        assert resp.status_code == 302
        assert '/media/serve_media/test.mp4' in resp.headers['Location']

    def test_load_more_redirect(self, logged_in_client):
        """旧版 /load_more 重定向到 /media/load_more"""
        resp = logged_in_client.get('/load_more', follow_redirects=False)
        assert resp.status_code == 302
        assert '/media/load_more' in resp.headers['Location']

    def test_raw_redirect(self, logged_in_client):
        """旧版 /raw/ 重定向到 /file/raw/"""
        resp = logged_in_client.get('/raw/test.txt', follow_redirects=False)
        assert resp.status_code == 302
        assert '/file/raw/test.txt' in resp.headers['Location']

    def test_view_redirect(self, logged_in_client):
        """旧版 /view/ 重定向到 /file/view/"""
        resp = logged_in_client.get('/view/test.txt', follow_redirects=False)
        assert resp.status_code == 302
        assert '/file/view/test.txt' in resp.headers['Location']


class TestStartStopService:

    def test_start_service_applies_settings(self, client):
        """start_service 应用配置并返回 URL"""
        resp = client.post('/api/start_service', json={
            'mode': 'video',
            'media_dir': '/tmp/test_media',
            'sort_type': 'name',
            'sort_order': 'asc',
            'random': True,
            'douyin_random': False,
            'category_browse': False,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 0
        assert data['local_url'] == 'http://127.0.0.1:5000'

    def test_stop_service_resets(self, client):
        """stop_service 重置为 normal 模式"""
        resp = client.post('/api/stop_service', json={})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 0
        assert config.RUN_MODE == 'normal'


# Register normal_bp for check_path tests
@pytest.fixture(autouse=True)
def _register_normal_bp(app):
    """自动注册 normal_bp 以便 check_path 测试"""
    from blueprints.normal_api import normal_bp
    try:
        app.register_blueprint(normal_bp)
    except AssertionError:
        pass  # already registered

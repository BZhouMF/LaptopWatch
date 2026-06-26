"""测试 POST /api/admin/config — 运行时配置更新"""
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


def _post(client, body):
    return client.post('/api/admin/config', json=body)


def _post_with_password(client, body):
    return client.post(
        '/api/admin/config', json=body,
        headers={'X-Auth-Password': config.DEFAULT_PASSWORD},
    )


class TestUnauthenticated:

    def test_returns_401_without_auth(self, client):
        """未认证请求返回 401"""
        resp = _post(client, {'mode': 'normal'})
        assert resp.status_code == 401
        assert resp.get_json()['code'] == 1

    def test_returns_401_with_wrong_password(self, client):
        """错误密码返回 401"""
        resp = client.post('/api/admin/config', json={'mode': 'normal'},
                           headers={'X-Auth-Password': 'wrong'})
        assert resp.status_code == 401
        assert resp.get_json()['code'] == 1


class TestSessionAuth:

    def test_session_auth_allows_update(self, logged_in_client):
        """session 登录后可正常更新"""
        resp = _post(logged_in_client, {'mode': 'normal'})
        assert resp.status_code == 200
        assert resp.get_json()['code'] == 0


class TestPasswordHeaderAuth:

    def test_password_header_allows_update(self, client):
        """X-Auth-Password 头部可正常更新"""
        resp = _post_with_password(client, {'mode': 'normal'})
        assert resp.status_code == 200
        assert resp.get_json()['code'] == 0


class TestModeSwitch:

    def test_switch_to_video_without_media_dir(self, client):
        """无 MEDIA_DIR 时切换到视频模式返回 400"""
        config.MEDIA_DIR = None
        try:
            resp = _post_with_password(client, {'mode': 'video'})
            assert resp.status_code == 400
            assert resp.get_json()['code'] == 1
        finally:
            pass  # MEDIA_DIR is restored by app fixture teardown

    def test_switch_to_normal_succeeds(self, logged_in_client):
        """切换到 normal 模式成功"""
        resp = _post(logged_in_client, {'mode': 'normal'})
        assert resp.status_code == 200
        assert resp.get_json()['code'] == 0
        assert config.RUN_MODE == 'normal'

    def test_switch_to_video_with_media_dir(self, logged_in_client, temp_dir):
        """有 MEDIA_DIR 时切换到视频模式成功"""
        config.MEDIA_DIR = Path(temp_dir)
        resp = _post(logged_in_client, {'mode': 'video'})
        assert resp.status_code == 200
        assert resp.get_json()['code'] == 0

    def test_invalid_mode_returns_400(self, logged_in_client):
        """无效 mode 值返回 400"""
        resp = _post(logged_in_client, {'mode': 'invalid'})
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 1


class TestPartialUpdate:

    def test_partial_update_only_changes_specified_fields(self, logged_in_client, temp_dir):
        """部分更新仅修改指定字段"""
        config.RUN_MODE = 'normal'
        config.MEDIA_DIR = Path(temp_dir)
        config.RANDOM_MODE = False
        config.DOUYIN_RANDOM_MEDIA = False
        config.CATEGORY_BROWSE = False

        resp = _post(logged_in_client, {'random_mode': True})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 0
        assert data['config']['random_mode'] is True
        # 未指定的字段保持原值
        assert data['config']['run_mode'] == 'normal'

    def test_update_multiple_fields(self, logged_in_client, temp_dir):
        """可同时更新多个字段"""
        config.MEDIA_DIR = Path(temp_dir)
        resp = _post(logged_in_client, {
            'mode': 'video',
            'random_mode': True,
            'category_browse': True,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 0

    def test_update_douyin_random_media(self, logged_in_client):
        """可单独更新 douyin_random_media"""
        config.DOUYIN_RANDOM_MEDIA = False
        resp = _post(logged_in_client, {'douyin_random_media': True})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 0
        assert data['config']['douyin_random_media'] is True


class TestModeApiReflectsChanges:

    def test_mode_api_reflects_updated_config(self, logged_in_client, temp_dir):
        """更新配置后 GET /api/mode 返回新值"""
        config.MEDIA_DIR = Path(temp_dir)
        config.RANDOM_MODE = False

        # 更新配置
        _post(logged_in_client, {'random_mode': True, 'category_browse': True})

        # 验证 GET /api/mode 返回新值
        resp = logged_in_client.get('/api/mode')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['random_mode'] is True
        assert data['category_browse'] is True
        assert 'douyin_random_media' in data

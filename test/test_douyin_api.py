"""测试 douyin_api.py — init/next 从 DB 随机取视频"""
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
def app(temp_dir):
    """Flask 应用，douyin 模式 + 测试媒体目录"""
    config.RUN_MODE = 'douyin'
    config.MEDIA_DIR = Path(temp_dir)
    config.DB_PATH = os.path.join(temp_dir, 'test.db')

    from flask import Flask
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    app.config['SESSION_TYPE'] = 'filesystem'

    from blueprints.auth import auth_bp
    from blueprints.douyin_api import douyin_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(douyin_bp)
    # 与 app.py 保持一致：请求结束关闭 DB 连接，
    # 避免 Windows 下临时 DB 文件（test.db）被占用导致清理失败
    from utils.db_utils import close_db_connection
    app.teardown_request(close_db_connection)
    yield app
    config.DB_PATH = None


@pytest.fixture
def client(app):
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['logged_in'] = True
        yield c


def _create_video(path):
    """创建测试视频文件"""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w') as f:
        f.write('test')


class TestInit:

    def test_init_returns_valid_video(self, client, temp_dir):
        """init 返回一个有效视频"""
        _create_video(os.path.join(temp_dir, 'video1.mp4'))

        resp = client.get('/api/douyin/init')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 0
        assert 'name' in data['data']
        assert 'relative_path' in data['data']
        assert data['data']['is_video'] is True

    def test_init_no_video(self, client, temp_dir):
        """无视频时返回空"""
        resp = client.get('/api/douyin/init')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 1
        assert data['msg'] == '没有找到视频文件'


class TestNext:

    def test_next_returns_different_video(self, client, temp_dir):
        """next 返回不同视频"""
        _create_video(os.path.join(temp_dir, 'video1.mp4'))
        _create_video(os.path.join(temp_dir, 'video2.mp4'))

        resp1 = client.get('/api/douyin/init')
        d1 = resp1.get_json()
        assert d1['code'] == 0

        resp2 = client.get('/api/douyin/next')
        d2 = resp2.get_json()
        assert d2['code'] == 0
        assert d2['data']['name'] != d1['data']['name']

    def test_history_dedup(self, client, temp_dir):
        """历史去重，不会重复返回已播视频"""
        _create_video(os.path.join(temp_dir, 'video1.mp4'))
        _create_video(os.path.join(temp_dir, 'video2.mp4'))

        resp1 = client.get('/api/douyin/init')
        assert resp1.get_json()['code'] == 0

        # 调用多次 next，不会返回 video1
        names = set()
        for _ in range(5):
            resp = client.get('/api/douyin/next')
            d = resp.get_json()
            if d['code'] == 2:  # 没有更多了
                break
            names.add(d['data']['name'])

        assert resp1.get_json()['data']['name'] not in names

    def test_next_no_more(self, client, temp_dir):
        """只有一个视频时，next 返回没有更多"""
        _create_video(os.path.join(temp_dir, 'video1.mp4'))

        client.get('/api/douyin/init')
        resp = client.get('/api/douyin/next')
        data = resp.get_json()
        assert data['code'] == 2
        assert data['msg'] == '没有更多了'

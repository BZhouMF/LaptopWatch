"""测试 normal_api.py — /api/list 从 DB 读取"""
import os
import sys
import json
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
    """独立 DB 路径，与 MEDIA_DIR 分离，避免同步时把 DB 文件列入文件列表"""
    _dir = tempfile.mkdtemp()
    yield os.path.join(_dir, 'test.db')
    import shutil
    shutil.rmtree(_dir, ignore_errors=True)


@pytest.fixture
def app(temp_dir, db_path):
    """Flask 应用实例，normal 模式 + 测试 MEDIA_DIR"""
    config.RUN_MODE = 'normal'
    config.MEDIA_DIR = Path(temp_dir)
    config.DB_PATH = db_path

    from flask import Flask
    app = Flask(__name__)
    app.secret_key = 'test-secret'

    from blueprints.auth import auth_bp
    from blueprints.normal_api import normal_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(normal_bp)
    yield app
    config.DB_PATH = None


@pytest.fixture
def client(app):
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['logged_in'] = True
        yield c


def _create_file(path, content='test'):
    with open(path, 'w') as f:
        f.write(content)


class TestApiListFromDb:

    def test_returns_structure(self, client, temp_dir):
        """/api/list 返回 items + has_more 结构"""
        _create_file(os.path.join(temp_dir, 'a.txt'))

        resp = client.get(f'/api/list?path={temp_dir}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'items' in data
        assert 'has_more' in data
        assert isinstance(data['items'], list)

    def test_returns_file_fields(self, client, temp_dir):
        """每个文件项包含前端所需字段"""
        _create_file(os.path.join(temp_dir, 'test.txt'))

        resp = client.get(f'/api/list?path={temp_dir}')
        data = resp.get_json()
        assert len(data['items']) == 1
        item = data['items'][0]
        for key in ('name', 'path', 'icon', 'is_video', 'is_image',
                     'is_previewable', 'is_text_readable', 'raw_url', 'date', 'size'):
            assert key in item, f"缺少字段: {key}"

    def test_folders_type(self, client, temp_dir):
        """type=folders 返回文件夹列表"""
        sub = os.path.join(temp_dir, 'subfolder')
        os.makedirs(sub)

        resp = client.get(f'/api/list?path={temp_dir}&type=folders')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert any(f['name'] == 'subfolder' for f in data)

    def test_pagination(self, client, temp_dir):
        """分页参数生效"""
        for i in range(5):
            _create_file(os.path.join(temp_dir, f'file{i}.txt'))

        resp = client.get(f'/api/list?path={temp_dir}&limit=2&offset=0')
        data = resp.get_json()
        assert len(data['items']) == 2
        assert data['has_more'] is True

        resp2 = client.get(f'/api/list?path={temp_dir}&limit=2&offset=4')
        data2 = resp2.get_json()
        assert len(data2['items']) == 1
        assert data2['has_more'] is False

    def test_sort_name(self, client, temp_dir):
        """排序参数生效"""
        _create_file(os.path.join(temp_dir, 'b.txt'))
        _create_file(os.path.join(temp_dir, 'a.txt'))

        resp = client.get(f'/api/list?path={temp_dir}&sort=name&order=asc')
        data = resp.get_json()
        names = [i['name'] for i in data['items']]
        assert names == sorted(names)

    def test_sort_time(self, client, temp_dir):
        """按时间排序"""
        old_file = os.path.join(temp_dir, 'old.txt')
        new_file = os.path.join(temp_dir, 'new.txt')
        _create_file(old_file)
        _create_file(new_file)
        # 用 explicit mtime 确保大小关系
        os.utime(old_file, (100, 100))
        os.utime(new_file, (200, 200))

        resp = client.get(f'/api/list?path={temp_dir}&sort=time&order=desc')
        data = resp.get_json()
        names = [i['name'] for i in data['items']]
        assert names == ['new.txt', 'old.txt']

    def test_first_access_creates_db(self, client, temp_dir):
        """首次访问自动创建 DB"""
        _create_file(os.path.join(temp_dir, 'test.txt'))
        db_path = config.DB_PATH

        # DB 还不存在
        if os.path.exists(db_path):
            os.remove(db_path)

        resp = client.get(f'/api/list?path={temp_dir}')
        assert resp.status_code == 200

        # 首次访问后 DB 应存在且有数据
        assert os.path.exists(db_path)
        import sqlite3
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        conn.close()
        assert count > 0

    def test_second_access_returns_same_data(self, client, temp_dir):
        """再次访问走缓存，返回相同数据"""
        _create_file(os.path.join(temp_dir, 'stable.txt'))

        resp1 = client.get(f'/api/list?path={temp_dir}')
        resp2 = client.get(f'/api/list?path={temp_dir}')
        assert resp1.get_json() == resp2.get_json()

    def test_fallback_on_no_db(self, app, temp_dir):
        """DB 不可用时回退到 scandir"""
        # 清空 DB_PATH 指向
        old_media_dir = config.MEDIA_DIR
        config.MEDIA_DIR = None  # DB_PATH 会返回默认路径，但 DB 文件不存在

        _create_file(os.path.join(temp_dir, 'fallback.txt'))

        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess['logged_in'] = True
            resp = c.get(f'/api/list?path={temp_dir}')
            assert resp.status_code == 200
            data = resp.get_json()
            assert len(data['items']) > 0

        config.MEDIA_DIR = old_media_dir

    def test_video_image_flags(self, client, temp_dir):
        """is_video/is_image 标志正确"""
        _create_file(os.path.join(temp_dir, 'video.mp4'))
        _create_file(os.path.join(temp_dir, 'image.jpg'))

        resp = client.get(f'/api/list?path={temp_dir}')
        data = resp.get_json()
        items = {i['name']: i for i in data['items']}
        assert items['video.mp4']['is_video'] is True
        assert items['video.mp4']['is_image'] is False
        assert items['image.jpg']['is_image'] is True
        assert items['image.jpg']['is_video'] is False

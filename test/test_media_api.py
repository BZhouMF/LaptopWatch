"""测试 media_api.py — load_more / thumbnail 从 DB 读取"""
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
    """独立 DB 路径，避免文件锁定影响 temp_dir 清理"""
    _dir = tempfile.mkdtemp()
    yield os.path.join(_dir, 'test.db')
    import shutil
    shutil.rmtree(_dir, ignore_errors=True)


@pytest.fixture
def app(temp_dir, db_path):
    """Flask 应用，video 模式 + 测试媒体目录"""
    config.RUN_MODE = 'video'
    config.RANDOM_MODE = False
    config.MEDIA_DIR = Path(temp_dir)
    config.DB_PATH = db_path

    from flask import Flask
    app = Flask(__name__)
    app.secret_key = 'test-secret'

    from blueprints.auth import auth_bp
    from blueprints.media_api import media_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(media_bp)
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


class TestLoadMore:

    def test_returns_paginated(self, client, temp_dir):
        """load_more 返回分页结果"""
        # 创建 5 个视频文件
        for i in range(5):
            _create_file(os.path.join(temp_dir, f'video{i}.mp4'))

        resp = client.get(f'/media/load_more?offset=0&limit=2')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 0
        assert len(data['data']) == 2
        assert data['has_more'] is True
        assert data['next_offset'] == 2
        assert data['is_random'] is False

    def test_full_pagination(self, client, temp_dir):
        """多次分页取完所有数据"""
        for i in range(3):
            _create_file(os.path.join(temp_dir, f'video{i}.mp4'))

        resp1 = client.get('/media/load_more?offset=0&limit=2')
        d1 = resp1.get_json()
        assert len(d1['data']) == 2
        assert d1['has_more'] is True

        resp2 = client.get(f'/media/load_more?offset={d1["next_offset"]}&limit=2')
        d2 = resp2.get_json()
        assert len(d2['data']) == 1
        assert d2['has_more'] is False

    def test_random_mode(self, app, temp_dir):
        """随机模式返回正确"""
        config.RANDOM_MODE = True
        for i in range(5):
            _create_file(os.path.join(temp_dir, f'video{i}.mp4'))

        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess['logged_in'] = True
            resp = c.get('/media/load_more?offset=0&limit=3')
            data = resp.get_json()
            assert data['code'] == 0
            assert data['is_random'] is True
            assert len(data['data']) == 3

        config.RANDOM_MODE = False

    def test_response_has_required_fields(self, client, temp_dir):
        """每个媒体项包含所需字段"""
        _create_file(os.path.join(temp_dir, 'test.mp4'))

        resp = client.get('/media/load_more?offset=0&limit=10')
        data = resp.get_json()
        item = data['data'][0]
        for key in ('name', 'relative_path', 'mtime', 'timestamp', 'is_video', 'is_image'):
            assert key in item, f"缺少字段: {key}"


class TestThumbnail:

    def _create_test_image(self, path):
        """创建测试图片"""
        try:
            from PIL import Image
            img = Image.new('RGB', (50, 50), color='blue')
            img.save(path, format='JPEG')
            return True
        except ImportError:
            return False

    def test_thumbnail_returns_image(self, client, temp_dir):
        """thumbnail 返回有效图片"""
        img_path = os.path.join(temp_dir, 'photo.jpg')
        if not self._create_test_image(img_path):
            pytest.skip('PIL not available')

        # 使用绝对路径参数（普通模式兼容）
        resp = client.get(f'/media/thumbnail/nonexistent.jpg?path={img_path}')
        assert resp.status_code == 200
        assert resp.content_type.startswith('image/jpeg')
        assert len(resp.data) > 100

    def test_thumbnail_second_call_cached(self, client, temp_dir):
        """第二次请求命中 DB 缓存"""
        img_path = os.path.join(temp_dir, 'photo.jpg')
        if not self._create_test_image(img_path):
            pytest.skip('PIL not available')

        resp1 = client.get(f'/media/thumbnail/nonexistent.jpg?path={img_path}')
        resp2 = client.get(f'/media/thumbnail/nonexistent.jpg?path={img_path}')
        assert resp1.data == resp2.data

    def test_thumbnail_not_found(self, client, temp_dir):
        """不存在的文件返回 404"""
        resp = client.get(f'/media/thumbnail/nonexistent.jpg?path={os.path.join(temp_dir, "missing.jpg")}')
        assert resp.status_code == 404

    def test_thumbnail_video_with_cv2(self, client, temp_dir):
        """视频文件缩略图（OpenCV）"""
        try:
            import cv2
            import numpy as np
        except ImportError:
            pytest.skip('OpenCV not available')

        video_path = os.path.join(temp_dir, 'clip.mp4')
        try:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(video_path, fourcc, 30.0, (50, 50))
            if writer.isOpened():
                frame = np.zeros((50, 50, 3), dtype=np.uint8)
                writer.write(frame)
                writer.release()
        except Exception:
            pytest.skip('Failed to create test video')

        resp = client.get(f'/media/thumbnail/nonexistent.mp4?path={video_path}')
        assert resp.status_code == 200
        assert resp.content_type.startswith('image/jpeg')


class TestServeMedia:

    def test_video_response_has_cache_control(self, client, temp_dir):
        """视频流响应带缓存头，切回看过的视频可复用浏览器缓存（老设备）"""
        _create_file(os.path.join(temp_dir, 'clip.mp4'), 'x' * 2048)

        resp = client.get('/media/serve_media/clip.mp4')
        assert resp.status_code == 200
        assert resp.headers.get('Cache-Control') == 'public, max-age=600'

        # Range 请求（浏览器实际使用的形式）
        resp2 = client.get('/media/serve_media/clip.mp4', headers={'Range': 'bytes=0-1023'})
        assert resp2.status_code == 206
        assert resp2.headers.get('Cache-Control') == 'public, max-age=600'
        assert resp2.headers.get('Content-Range') == 'bytes 0-1023/2048'

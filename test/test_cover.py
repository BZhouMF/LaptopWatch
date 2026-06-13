"""测试封面读写接口：get_cover / set_cover / generate_and_cache_cover"""
import os
import sys
import tempfile
import sqlite3

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db_utils import ensure_tables, get_cover, set_cover, generate_and_cache_cover
from config import config


@pytest.fixture
def conn():
    conn = sqlite3.connect(':memory:')
    ensure_tables(conn)
    _seed(conn)
    yield conn
    conn.close()


def _seed(conn):
    conn.execute(
        "INSERT INTO images (id, parent_id, name, path, modify_time, cover) "
        "VALUES (1, 0, 'test.jpg', '/test.jpg', 100, NULL)"
    )
    conn.execute(
        "INSERT INTO videos (id, parent_id, name, path, modify_time, cover) "
        "VALUES (1, 0, 'test.mp4', '/test.mp4', 100, NULL)"
    )
    conn.commit()


class TestGetCover:

    def test_returns_none_when_no_cover(self, conn):
        """没有 cover 时返回 None"""
        assert get_cover(conn, 'images', '/test.jpg') is None
        assert get_cover(conn, 'videos', '/test.mp4') is None

    def test_returns_none_for_nonexistent_path(self, conn):
        """不存在的路径返回 None"""
        assert get_cover(conn, 'images', '/nonexistent.jpg') is None

    def test_returns_cover_after_set(self, conn):
        """set_cover 后 get_cover 返回正确数据"""
        data = b'\xff\xd8\xff\xe0'  # JPEG header
        set_cover(conn, 'images', '/test.jpg', data)
        assert get_cover(conn, 'images', '/test.jpg') == data

    def test_video_cover(self, conn):
        """videos 表同样支持 cover 读写"""
        data = b'\xff\xd8\xff\xe0'
        set_cover(conn, 'videos', '/test.mp4', data)
        assert get_cover(conn, 'videos', '/test.mp4') == data


class TestGenerateAndCacheCover:

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as td:
            yield td

    def _create_test_image(self, path):
        """创建一个测试用的小图片"""
        try:
            from PIL import Image
            img = Image.new('RGB', (100, 100), color='red')
            img.save(path, format='JPEG', quality=50)
            return True
        except ImportError:
            return False

    def test_generates_cover_for_image(self, conn, temp_dir):
        """对图片文件生成 cover"""
        img_path = os.path.join(temp_dir, 'photo.jpg')
        if not self._create_test_image(img_path):
            pytest.skip('PIL not available')

        result, mime = generate_and_cache_cover(conn, 'images', img_path)
        assert result is not None
        assert mime == 'image/jpeg'
        # 验证已写入 DB
        assert get_cover(conn, 'images', img_path) == result

    def test_returns_cached_on_second_call(self, conn, temp_dir):
        """重复调用不重复生成，返回相同数据"""
        img_path = os.path.join(temp_dir, 'photo.jpg')
        if not self._create_test_image(img_path):
            pytest.skip('PIL not available')

        first, _ = generate_and_cache_cover(conn, 'images', img_path)
        second, _ = generate_and_cache_cover(conn, 'images', img_path)
        assert first == second

    def test_returns_none_for_non_media(self, conn, temp_dir):
        """非媒体文件返回 None"""
        txt_path = os.path.join(temp_dir, 'note.txt')
        with open(txt_path, 'w') as f:
            f.write('text')

        result, mime = generate_and_cache_cover(conn, 'images', txt_path)
        assert result is None
        assert mime is None

    def test_video_cover_generation(self, conn, temp_dir):
        """对视频文件生成 cover（跳过如果 OpenCV 不可用）"""
        try:
            import cv2
            import numpy as np
        except ImportError:
            pytest.skip('OpenCV not available')

        # 创建一个极短视频（1 帧）
        video_path = os.path.join(temp_dir, 'clip.mp4')
        try:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(video_path, fourcc, 30.0, (100, 100))
            if not writer.isOpened():
                pytest.skip('Could not create test video')
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            frame[:] = (0, 0, 255)  # Red
            writer.write(frame)
            writer.release()
            if not os.path.getsize(video_path):
                pytest.skip('Test video file is empty')
        except Exception:
            pytest.skip('Failed to create test video')

        result, mime = generate_and_cache_cover(conn, 'videos', video_path)
        assert result is not None
        assert mime == 'image/jpeg'

    def test_nonexistent_file(self, conn, temp_dir):
        """不存在的文件返回 None"""
        result, mime = generate_and_cache_cover(conn, 'images', '/nonexistent.jpg')
        assert result is None
        assert mime is None

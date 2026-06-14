"""测试封面读写接口：get_cover / set_cover / generate_and_cache_cover（新 schema）"""
import os
import sys
import tempfile
import sqlite3

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db_utils import init_tables, get_cover, set_cover, generate_and_cache_cover
from config import config


@pytest.fixture
def conn():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    init_tables(conn)
    _seed(conn)
    yield conn
    conn.close()


def _seed(conn):
    conn.execute(
        "INSERT INTO media (id, parent_id, name, media_type, path, modify_time, cover) "
        "VALUES (1, 0, 'test.jpg', 'image', '/test.jpg', 100, NULL)"
    )
    conn.execute(
        "INSERT INTO media (id, parent_id, name, media_type, path, modify_time, cover) "
        "VALUES (2, 0, 'test.mp4', 'video', '/test.mp4', 100, NULL)"
    )
    conn.commit()


class TestGetCover:

    def test_returns_none_when_no_cover(self, conn):
        assert get_cover(conn, '/test.jpg') is None
        assert get_cover(conn, '/test.mp4') is None

    def test_returns_none_for_nonexistent_path(self, conn):
        assert get_cover(conn, '/nonexistent.jpg') is None

    def test_returns_cover_after_set(self, conn):
        data = b'\xff\xd8\xff\xe0'
        set_cover(conn, '/test.jpg', data)
        assert get_cover(conn, '/test.jpg') == data

    def test_video_cover(self, conn):
        data = b'\xff\xd8\xff\xe0'
        set_cover(conn, '/test.mp4', data)
        assert get_cover(conn, '/test.mp4') == data


class TestGenerateAndCacheCover:

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as td:
            yield td

    def _create_test_image(self, path):
        try:
            from PIL import Image
            img = Image.new('RGB', (100, 100), color='red')
            img.save(path, format='JPEG', quality=50)
            return True
        except ImportError:
            return False

    def test_generates_cover_for_image(self, conn, temp_dir):
        img_path = os.path.join(temp_dir, 'photo.jpg')
        if not self._create_test_image(img_path):
            pytest.skip('PIL not available')

        result, mime = generate_and_cache_cover(conn, img_path)
        assert result is not None
        assert mime == 'image/jpeg'
        assert get_cover(conn, img_path) == result

    def test_returns_cached_on_second_call(self, conn, temp_dir):
        img_path = os.path.join(temp_dir, 'photo.jpg')
        if not self._create_test_image(img_path):
            pytest.skip('PIL not available')

        first, _ = generate_and_cache_cover(conn, img_path)
        second, _ = generate_and_cache_cover(conn, img_path)
        assert first == second

    def test_returns_none_for_non_media(self, conn, temp_dir):
        txt_path = os.path.join(temp_dir, 'note.txt')
        with open(txt_path, 'w') as f:
            f.write('text')

        result, mime = generate_and_cache_cover(conn, txt_path)
        assert result is None
        assert mime is None

    def test_video_cover_generation(self, conn, temp_dir):
        try:
            import cv2
            import numpy as np
        except ImportError:
            pytest.skip('OpenCV not available')

        video_path = os.path.join(temp_dir, 'clip.mp4')
        try:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(video_path, fourcc, 30.0, (100, 100))
            if not writer.isOpened():
                pytest.skip('Could not create test video')
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            frame[:] = (0, 0, 255)
            writer.write(frame)
            writer.release()
            if not os.path.getsize(video_path):
                pytest.skip('Test video file is empty')
        except Exception:
            pytest.skip('Failed to create test video')

        result, mime = generate_and_cache_cover(conn, video_path)
        assert result is not None
        assert mime == 'image/jpeg'

    def test_nonexistent_file(self, conn, temp_dir):
        result, mime = generate_and_cache_cover(conn, '/nonexistent.jpg')
        assert result is None
        assert mime is None

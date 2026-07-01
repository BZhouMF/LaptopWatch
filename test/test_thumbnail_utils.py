"""测试 thumbnail_utils.py — 缩略图生成"""
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import config


@pytest.fixture(autouse=True)
def _reset_config():
    yield
    config.RUN_MODE = 'normal'


class TestGenerateThumbnailCacheHit:
    """测试缩略图缓存命中路径"""

    def test_cache_hit_returns_cached_base64(self, monkeypatch):
        from utils.cache_utils import cache_manager
        from utils.thumbnail_utils import generate_thumbnail

        test_data = "fake_base64_data"
        cache_manager.set_thumbnail_cache(
            "/fake/path.jpg", 12345.0, 100, (150, 150), test_data
        )

        # Mock os.stat to return matching values
        class MockStat:
            st_mtime = 12345.0
            st_size = 100

        monkeypatch.setattr(os, 'stat', lambda p: MockStat())

        result = generate_thumbnail("/fake/path.jpg")
        assert result == ('image/jpeg', test_data)

    def test_cache_miss_calls_os_stat(self, monkeypatch):
        from utils.thumbnail_utils import generate_thumbnail
        from utils.cache_utils import cache_manager

        # Clear cache + mock stat to a nonexistent file
        cache_manager.clear_cache()
        monkeypatch.setattr(os, 'stat', lambda p: (_ for _ in ()).throw(FileNotFoundError()))

        result = generate_thumbnail("/nonexistent.jpg")
        assert result is None


class TestGenerateThumbnailEdgeCases:
    """测试边界情况"""

    def test_non_media_extension_returns_none(self, monkeypatch, tmp_path):
        from utils.cache_utils import cache_manager
        from utils.thumbnail_utils import generate_thumbnail

        cache_manager.clear_cache()
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("hello")

        result = generate_thumbnail(str(txt_file))
        assert result is None

    def test_image_over_size_limit_returns_none(self, monkeypatch, tmp_path):
        from utils.cache_utils import cache_manager
        from utils.thumbnail_utils import generate_thumbnail

        cache_manager.clear_cache()
        config.MAX_IMAGE_SIZE = 10
        img_file = tmp_path / "large.jpg"
        img_file.write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 200)

        result = generate_thumbnail(str(img_file))
        assert result is None

    def test_file_not_found_returns_none(self, monkeypatch):
        from utils.cache_utils import cache_manager
        from utils.thumbnail_utils import generate_thumbnail

        cache_manager.clear_cache()
        result = generate_thumbnail("/does/not/exist/file.jpg")
        assert result is None

    def test_video_without_opencv_returns_none(self, monkeypatch, tmp_path):
        from utils.cache_utils import cache_manager
        from utils.thumbnail_utils import generate_thumbnail
        import utils.thumbnail_utils as thu

        cache_manager.clear_cache()
        # Ensure HAS_CV2=False for this test
        monkeypatch.setattr(thu, 'HAS_CV2', False)

        mp4_file = tmp_path / "test.mp4"
        mp4_file.write_bytes(b'\x00' * 100)

        result = generate_thumbnail(str(mp4_file))
        assert result is None

    def test_image_without_pil_returns_none(self, monkeypatch, tmp_path):
        from utils.cache_utils import cache_manager
        from utils.thumbnail_utils import generate_thumbnail
        import utils.thumbnail_utils as thu

        cache_manager.clear_cache()
        monkeypatch.setattr(thu, 'HAS_PIL', False)

        img_file = tmp_path / "test.jpg"
        img_file.write_bytes(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01' + b'\x00' * 100)

        result = generate_thumbnail(str(img_file))
        assert result is None


class TestLogThumbnailBackendStatus:
    """测试 log_thumbnail_backend_status"""

    def test_does_not_raise(self):
        from utils.thumbnail_utils import log_thumbnail_backend_status
        log_thumbnail_backend_status()

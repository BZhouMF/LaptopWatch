"""测试 cache_utils.py — CacheManager 缓存管理器"""
import time
import threading
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.cache_utils import CacheManager


@pytest.fixture
def cache():
    return CacheManager()


class TestPreviewCache:

    def test_first_call_returns_false(self, cache):
        assert cache.check_and_set_preview_cache(("GET", "/api/test")) is False

    def test_duplicate_call_returns_true(self, cache):
        key = ("GET", "/api/list")
        cache.check_and_set_preview_cache(key)
        assert cache.check_and_set_preview_cache(key) is True

    def test_different_keys_both_return_false(self, cache):
        assert cache.check_and_set_preview_cache(("GET", "/a")) is False
        assert cache.check_and_set_preview_cache(("GET", "/b")) is False

    def test_clean_preview_cache_removes_expired(self, cache):
        cache.preview_cache[("old", "/x")] = time.time() - 7200  # 2 hours ago
        cache.preview_cache[("recent", "/y")] = time.time()
        cache.clean_preview_cache(expire_time=3600)
        assert ("old", "/x") not in cache.preview_cache
        assert ("recent", "/y") in cache.preview_cache

    def test_clean_preview_cache_keeps_all_when_fresh(self, cache):
        cache.preview_cache[("a", "/1")] = time.time()
        cache.preview_cache[("b", "/2")] = time.time()
        cache.clean_preview_cache(expire_time=3600)
        assert len(cache.preview_cache) == 2

    def test_thread_safety_two_threads_one_gets_false(self, cache):
        results = []

        def worker():
            results.append(cache.check_and_set_preview_cache(("T", "/shared")))

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert results.count(False) == 1
        assert results.count(True) == 1


class TestFoldersCache:

    def test_get_returns_none_when_empty(self, cache):
        assert cache.get_folders_cache("name", "asc") is None

    def test_set_and_get_roundtrip(self, cache):
        folders = [{"name": "dir1"}, {"name": "dir2"}]
        cache.set_folders_cache(folders, "name", "asc")
        assert cache.get_folders_cache("name", "asc") == folders

    def test_sort_mismatch_returns_none(self, cache):
        cache.set_folders_cache([{"name": "x"}], "name", "asc")
        assert cache.get_folders_cache("date", "asc") is None
        assert cache.get_folders_cache("name", "desc") is None

    def test_expired_returns_none(self, cache):
        cache.CACHE_DURATION = 0.01
        cache.set_folders_cache([{"name": "x"}], "name", "asc")
        time.sleep(0.02)
        assert cache.get_folders_cache("name", "asc") is None


class TestFilesCache:

    def test_get_returns_none_when_empty(self, cache):
        assert cache.get_files_cache("/test", "name", "asc") is None

    def test_set_and_get_roundtrip(self, cache):
        files = [{"name": "file1.mp4"}, {"name": "file2.jpg"}]
        cache.set_files_cache("/videos", files, "name", "asc")
        assert cache.get_files_cache("/videos", "name", "asc") == files

    def test_different_path_returns_none(self, cache):
        cache.set_files_cache("/path_a", [{"name": "a"}], "name", "asc")
        assert cache.get_files_cache("/path_b", "name", "asc") is None

    def test_sort_mismatch_returns_none(self, cache):
        cache.set_files_cache("/dir", [{"name": "x"}], "name", "asc")
        assert cache.get_files_cache("/dir", "size", "asc") is None

    def test_expired_returns_none(self, cache):
        cache.CACHE_DURATION = 0.01
        cache.set_files_cache("/dir", [{"name": "x"}], "name", "asc")
        time.sleep(0.02)
        assert cache.get_files_cache("/dir", "name", "asc") is None


class TestThumbnailCache:

    def test_get_returns_none_when_empty(self, cache):
        assert cache.get_thumbnail_cache("/img.jpg", 1.0, 100, (150, 150)) is None

    def test_set_and_get_roundtrip(self, cache):
        cache.set_thumbnail_cache("/img.jpg", 12345.0, 2048, (150, 150), "base64data")
        assert cache.get_thumbnail_cache("/img.jpg", 12345.0, 2048, (150, 150)) == "base64data"

    def test_different_mtime_returns_none(self, cache):
        cache.set_thumbnail_cache("/img.jpg", 100.0, 2048, (150, 150), "data")
        assert cache.get_thumbnail_cache("/img.jpg", 200.0, 2048, (150, 150)) is None

    def test_different_size_returns_none(self, cache):
        cache.set_thumbnail_cache("/img.jpg", 100.0, 2048, (300, 300), "data")
        assert cache.get_thumbnail_cache("/img.jpg", 100.0, 2048, (150, 150)) is None

    def test_expired_returns_none(self, cache):
        cache.set_thumbnail_cache("/img.jpg", 100.0, 2048, (150, 150), "data")
        # Manually age the timestamp
        cache._thumbnail_cache["/img.jpg:100.0:2048:150x150"]["timestamp"] = time.time() - 7200
        assert cache.get_thumbnail_cache("/img.jpg", 100.0, 2048, (150, 150)) is None


class TestClearCache:

    def test_clears_all_caches(self, cache):
        cache.set_folders_cache([{"name": "x"}], "name", "asc")
        cache.set_files_cache("/dir", [{"name": "y"}], "name", "asc")
        cache.set_thumbnail_cache("/img.jpg", 1.0, 100, (150, 150), "data")
        cache.check_and_set_preview_cache(("X", "/z"))

        cache.clear_cache()

        assert cache.get_folders_cache("name", "asc") is None
        assert cache.get_files_cache("/dir", "name", "asc") is None
        assert cache.get_thumbnail_cache("/img.jpg", 1.0, 100, (150, 150)) is None
        assert len(cache.preview_cache) == 0

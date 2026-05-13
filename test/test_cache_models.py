"""缓存管理模块测试"""
import time
from models.cache_models import CacheManager, cache_manager


class TestCacheManager:
    def test_get_set_folders_cache(self):
        cache = CacheManager()
        folders = [{'path': '/a', 'name': 'A'}, {'path': '/b', 'name': 'B'}]
        cache.set_folders_cache(folders, 'name', 'asc')
        result = cache.get_folders_cache('name', 'asc')
        assert result == folders

    def test_folders_cache_miss_on_different_sort(self):
        cache = CacheManager()
        cache.set_folders_cache([{'path': '/a'}], 'name', 'asc')
        assert cache.get_folders_cache('time', 'asc') is None

    def test_folders_cache_expires(self):
        cache = CacheManager()
        cache.CACHE_DURATION = 0
        cache.set_folders_cache([{'path': '/a'}], 'name', 'asc')
        time.sleep(0.01)
        assert cache.get_folders_cache('name', 'asc') is None

    def test_get_set_files_cache(self):
        cache = CacheManager()
        files = [{'name': 'a.txt', 'path': '/a/a.txt'}]
        cache.set_files_cache('/a', files, 'name', 'asc')
        result = cache.get_files_cache('/a', 'name', 'asc')
        assert result == files

    def test_files_cache_diff_path(self):
        cache = CacheManager()
        cache.set_files_cache('/a', [{'name': 'a.txt'}], 'name', 'asc')
        assert cache.get_files_cache('/b', 'name', 'asc') is None

    def test_thumbnail_cache(self):
        cache = CacheManager()
        cache.set_thumbnail_cache('/a.jpg', 1000, 1024, (150, 150), 'base64data')
        result = cache.get_thumbnail_cache('/a.jpg', 1000, 1024, (150, 150))
        assert result == 'base64data'

    def test_thumbnail_cache_miss_on_diff_size(self):
        cache = CacheManager()
        cache.set_thumbnail_cache('/a.jpg', 1000, 1024, (150, 150), 'data')
        assert cache.get_thumbnail_cache('/a.jpg', 1000, 1024, (300, 300)) is None

    def test_clear_cache(self):
        cache = CacheManager()
        cache.set_folders_cache([{'path': '/a'}], 'name', 'asc')
        cache.set_files_cache('/a', [{'name': 'a.txt'}], 'name', 'asc')
        cache.set_thumbnail_cache('/a.jpg', 0, 0, (150, 150), 'data')
        cache.preview_cache[('k', 'v')] = time.time()
        cache.clear_cache()
        assert cache.get_folders_cache('name', 'asc') is None
        assert cache.get_files_cache('/a', 'name', 'asc') is None
        assert cache.get_thumbnail_cache('/a.jpg', 0, 0, (150, 150)) is None
        assert cache.preview_cache == {}

    def test_clean_preview_cache(self):
        cache = CacheManager()
        cache.preview_cache[('old', '1')] = time.time() - 7200
        cache.preview_cache[('new', '2')] = time.time()
        cache.clean_preview_cache(expire_time=3600)
        assert ('old', '1') not in cache.preview_cache
        assert ('new', '2') in cache.preview_cache

    def test_global_cache_manager_exists(self):
        from models.cache_models import cache_manager
        assert isinstance(cache_manager, CacheManager)

"""
缓存管理模块
管理文件夹缓存、文件缓存、缩略图缓存等
"""
import time
import threading
from typing import Dict, Any, List, Tuple, Optional

class CacheManager:
    """缓存管理器"""

    def __init__(self):
        self._lock = threading.Lock()

        # 文件夹缓存
        self._folders_cache = {
            'timestamp': 0,
            'list': [],
            'sort_type': None,
            'sort_order': None
        }

        # 文件缓存
        self._files_cache: Dict[str, Dict[str, Any]] = {}

        # 缩略图缓存
        self._thumbnail_cache: Dict[str, Dict[str, Any]] = {}

        # 预览缓存（用于去重）
        self.preview_cache: Dict[Tuple[str, str], float] = {}

        # 缓存持续时间（秒）
        self.CACHE_DURATION = 60

    def check_and_set_preview_cache(self, cache_key):
        """线程安全地检查并设置预览缓存，返回 True 表示已存在（跳过）"""
        with self._lock:
            if cache_key in self.preview_cache:
                return True
            self.preview_cache[cache_key] = time.time()
            return False

    def clean_preview_cache(self, expire_time: int = 3600):
        """清理过期的预览缓存"""
        with self._lock:
            now = time.time()
            to_remove = [k for k, v in self.preview_cache.items() if now - v > expire_time]
            for k in to_remove:
                del self.preview_cache[k]

    def get_folders_cache(self, sort_type: str, sort_order: str) -> Optional[List[Dict[str, Any]]]:
        """获取文件夹缓存"""
        current_time = time.time()
        if (current_time - self._folders_cache['timestamp'] < self.CACHE_DURATION and
            self._folders_cache['list'] and
            self._folders_cache['sort_type'] == sort_type and
            self._folders_cache['sort_order'] == sort_order):
            return self._folders_cache['list']
        return None

    def set_folders_cache(self, folders: List[Dict[str, Any]], sort_type: str, sort_order: str):
        """设置文件夹缓存"""
        self._folders_cache = {
            'timestamp': time.time(),
            'list': folders,
            'sort_type': sort_type,
            'sort_order': sort_order
        }

    def get_files_cache(self, folder_path: str, sort_type: str, sort_order: str) -> Optional[List[Dict[str, Any]]]:
        """获取文件缓存"""
        cache_entry = self._files_cache.get(folder_path)
        if cache_entry:
            current_time = time.time()
            if (current_time - cache_entry['timestamp'] < self.CACHE_DURATION and
                cache_entry['sort_type'] == sort_type and
                cache_entry['sort_order'] == sort_order):
                return cache_entry['list']
        return None

    def set_files_cache(self, folder_path: str, files: List[Dict[str, Any]], sort_type: str, sort_order: str):
        """设置文件缓存"""
        self._files_cache[folder_path] = {
            'timestamp': time.time(),
            'list': files,
            'sort_type': sort_type,
            'sort_order': sort_order
        }

    def get_thumbnail_cache(self, filepath: str, mtime: float, size: int, thumbnail_size: Tuple[int, int]) -> Optional[str]:
        """获取缩略图缓存"""
        cache_key = f"{filepath}:{mtime}:{size}:{thumbnail_size[0]}x{thumbnail_size[1]}"
        cached_data = self._thumbnail_cache.get(cache_key)
        if cached_data:
            # 检查缓存是否过期（1小时）
            if time.time() - cached_data['timestamp'] < 3600:
                return cached_data['thumbnail']
        return None

    def set_thumbnail_cache(self, filepath: str, mtime: float, size: int, thumbnail_size: Tuple[int, int], thumbnail_data: str):
        """设置缩略图缓存"""
        cache_key = f"{filepath}:{mtime}:{size}:{thumbnail_size[0]}x{thumbnail_size[1]}"
        self._thumbnail_cache[cache_key] = {
            'thumbnail': thumbnail_data,
            'timestamp': time.time()
        }

    def clear_cache(self):
        """清除所有缓存"""
        self._folders_cache = {'timestamp': 0, 'list': [], 'sort_type': None, 'sort_order': None}
        self._files_cache.clear()
        self._thumbnail_cache.clear()
        self.preview_cache.clear()

# 创建全局缓存管理器实例
cache_manager = CacheManager()
"""媒体工具函数测试"""
import os
import time
import random
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestFormatFileItem:
    def test_format_video_file(self):
        from utils.media_utils import _format_file_item
        from config import config

        item = _format_file_item({
            'name': 'test.mp4',
            'rel_path': 'videos/test.mp4',
            'mtime': 1700000000,
            'size': 1024,
        })
        assert item['name'] == 'test.mp4'
        assert item['relative_path'] == 'videos/test.mp4'
        assert item['is_video'] is True
        assert item['is_image'] is False

    def test_format_image_file(self):
        from utils.media_utils import _format_file_item

        item = _format_file_item({
            'name': 'photo.jpg',
            'rel_path': 'images/photo.jpg',
            'mtime': 1700000000,
            'size': 2048,
        })
        assert item['is_video'] is False
        assert item['is_image'] is True

    def test_format_dot_relpath_fallback(self):
        """rel_path 为空或 '.' 时回退到 name"""
        from utils.media_utils import _format_file_item

        item = _format_file_item({
            'name': 'fallback.mp4',
            'path': '/some/path/fallback.mp4',
            'rel_path': '.',
            'mtime': 1700000000,
            'size': 1024,
        })
        assert item['relative_path'] == 'fallback.mp4'

    def test_format_backslash_to_slash(self):
        from utils.media_utils import _format_file_item

        item = _format_file_item({
            'name': 'test.mp4',
            'rel_path': 'sub\\folder\\test.mp4',
            'mtime': 1700000000,
            'size': 1024,
        })
        assert item['relative_path'] == 'sub/folder/test.mp4'


class TestGetSortedSubfolders:
    def test_returns_empty_on_invalid_path(self):
        from utils.media_utils import _get_sorted_subfolders
        result = _get_sorted_subfolders('/nonexistent_path_12345')
        assert result == []


class TestCollectFilesRecursive:
    def test_no_files_when_not_media(self):
        from utils.media_utils import _collect_files_recursive

        test_root = Path(__file__).parent
        result = _collect_files_recursive(test_root, 10, 'video')
        # test 目录下的 .py 文件不应被收集
        # 可能有图片文件被收集，但至少不能有 .py 文件
        for f in result:
            assert not f['name'].endswith('.py')


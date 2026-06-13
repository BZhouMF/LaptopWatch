"""媒体工具函数测试"""
import os
import time
import random
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestPickRandomMediaVideo:
    """随机树下降算法测试"""

    def test_returns_none_on_empty_root(self):
        """媒体目录无文件时返回 None"""
        from utils.media_utils import pick_random_media_video
        from config import config

        orig_mode = config.RUN_MODE
        orig_dir = config.MEDIA_DIR
        config.RUN_MODE = 'douyin'

        test_root = Path(__file__).parent
        config.MEDIA_DIR = test_root

        # test/ 目录下没有视频文件，应返回 None
        result = pick_random_media_video([])
        assert result is None

        config.RUN_MODE = orig_mode
        config.MEDIA_DIR = orig_dir

    def test_finds_video_when_exists(self, tmp_path):
        """目录下有视频文件时能返回"""
        from utils.media_utils import pick_random_media_video
        from config import config

        orig_mode = config.RUN_MODE
        orig_dir = config.MEDIA_DIR
        config.RUN_MODE = 'douyin'

        # 创建临时目录结构
        (tmp_path / 'sub').mkdir(parents=True, exist_ok=True)
        (tmp_path / 'sub' / 'movie.mp4').write_text('fake video')
        (tmp_path / 'sub' / 'readme.txt').write_text('not a video')

        config.MEDIA_DIR = tmp_path

        result = pick_random_media_video([])
        assert result is not None
        assert result['name'] == 'movie.mp4'

        config.RUN_MODE = orig_mode
        config.MEDIA_DIR = orig_dir

    def test_skips_history(self, tmp_path):
        """已看过的视频被跳过"""
        from utils.media_utils import pick_random_media_video
        from config import config

        orig_mode = config.RUN_MODE
        orig_dir = config.MEDIA_DIR
        config.RUN_MODE = 'douyin'

        (tmp_path / 'a.mp4').write_text('fake a')
        (tmp_path / 'b.mp4').write_text('fake b')

        config.MEDIA_DIR = tmp_path

        history = [{'relative_path': 'a.mp4'}]
        result = pick_random_media_video(history)
        assert result is not None
        assert result['name'] == 'b.mp4'

        config.RUN_MODE = orig_mode
        config.MEDIA_DIR = orig_dir


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


class TestBuildVideoInfo:
    def test_build_video_info(self):
        from utils.media_utils import _build_video_info

        info = _build_video_info({
            'name': 'clip.mp4',
            'rel_path': 'dir\\clip.mp4',
            'mtime': 1700000000,
        })
        assert info['name'] == 'clip.mp4'
        assert info['relative_path'] == 'dir/clip.mp4'
        assert info['timestamp'] == 1700000000

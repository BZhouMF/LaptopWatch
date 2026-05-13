"""媒体工具函数测试"""
import os
import time
import random
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestTraversalStoreThreadSafety:
    """_traversal_store 线程安全测试"""

    def test_lock_exists(self):
        """验证 _traversal_lock 存在且是 threading.Lock"""
        from utils.media_utils import _traversal_lock
        assert isinstance(_traversal_lock, type(threading.Lock()))

    def test_concurrent_init_and_cleanup(self):
        """并发 init_traversal 与 stale cleanup 不应崩溃"""
        import utils.media_utils as mu
        from config import config

        # 临时覆盖配置
        orig_mode = config.RUN_MODE
        config.RUN_MODE = 'video'

        test_root = Path(__file__).parent
        errors = []

        def writer():
            for _ in range(20):
                try:
                    tid = mu.init_traversal(test_root, 'video')
                except Exception as e:
                    errors.append(f'init error: {e}')

        threads = [threading.Thread(target=writer, daemon=True) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        config.RUN_MODE = orig_mode
        assert not errors, f'并发 init_traversal 出现错误: {errors}'

    def test_concurrent_get_next_and_cleanup(self):
        """并发 get_next_media_files 与 stale cleanup 不应崩溃"""
        import utils.media_utils as mu
        from config import config

        orig_mode = config.RUN_MODE
        config.RUN_MODE = 'video'

        test_root = Path(__file__).parent
        errors = []

        tid = mu.init_traversal(test_root, 'video')

        def reader():
            for _ in range(30):
                try:
                    mu.get_next_media_files(tid, 5)
                except Exception as e:
                    errors.append(f'read error: {e}')

        t1 = threading.Thread(target=reader, daemon=True)
        t2 = threading.Thread(target=reader, daemon=True)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        config.RUN_MODE = orig_mode
        assert not errors, f'并发 get_next_media_files 出现错误: {errors}'

    def test_sequential_traversal_concurrent_init(self):
        """并发 init_sequential_traversal 不应崩溃"""
        import utils.media_utils as mu
        from config import config

        orig_mode = config.RUN_MODE
        config.RUN_MODE = 'video'

        test_root = Path(__file__).parent
        errors = []

        def writer():
            for _ in range(20):
                try:
                    mu.init_sequential_traversal(test_root, 'video')
                except Exception as e:
                    errors.append(f'seq init error: {e}')

        threads = [threading.Thread(target=writer, daemon=True) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        config.RUN_MODE = orig_mode
        assert not errors, f'并发 init_sequential_traversal 出现错误: {errors}'

    def test_get_next_sequential_concurrent(self):
        """并发 get_next_sequential_files 不应崩溃"""
        import utils.media_utils as mu
        from config import config

        orig_mode = config.RUN_MODE
        config.RUN_MODE = 'video'

        test_root = Path(__file__).parent
        errors = []

        tid = mu.init_sequential_traversal(test_root, 'video')

        def reader():
            for _ in range(30):
                try:
                    mu.get_next_sequential_files(tid, 5)
                except Exception as e:
                    errors.append(f'seq read error: {e}')

        threads = [threading.Thread(target=reader, daemon=True) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        config.RUN_MODE = orig_mode
        assert not errors, f'并发 get_next_sequential_files 出现错误: {errors}'

    def test_store_does_not_leak_after_finished(self):
        """遍历完成后 _traversal_store 应删除对应条目"""
        import utils.media_utils as mu
        from config import config

        orig_mode = config.RUN_MODE
        config.RUN_MODE = 'video'

        # 空目录 -> 无子文件夹 -> 直接返回根目录
        with patch('utils.media_utils.get_files_in_folder', return_value=[]):
            tid = mu.init_traversal(Path(__file__).parent, 'video')

            # 第一次 get_next -> 无文件，finished=True 会 pop
            files, has_more = mu.get_next_media_files(tid, 10)
            assert files == []

        # 验证已被删除（第二次 get 返回空）
        files, has_more = mu.get_next_media_files(tid, 10)
        assert files == []
        assert has_more == False  # noqa: E222

        config.RUN_MODE = orig_mode


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

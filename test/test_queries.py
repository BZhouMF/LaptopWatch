"""测试查询接口：get_children / get_media_page / get_random_media（新 schema）"""
import os
import sys
import tempfile
import sqlite3
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from utils.db_utils import init_tables, get_children, get_media_page, get_random_media, get_direct_media, traverse_media


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
    """插入测试数据 — nodes + media 两张表"""
    # nodes: 目录结构
    conn.execute(
        """INSERT INTO nodes (id, parent_id, name, type, path, size, extension,
                              modify_time, is_hidden)
           VALUES (1, 0, 'root', 1, '/root', 0, NULL, 100, 0)"""
    )
    conn.execute(
        """INSERT INTO nodes (id, parent_id, name, type, path, size, extension,
                              modify_time, is_hidden)
           VALUES (10, 1, 'a_folder', 1, '/root/a_folder', 0, NULL, 200, 0)"""
    )
    conn.execute(
        """INSERT INTO nodes (id, parent_id, name, type, path, size, extension,
                              modify_time, is_hidden)
           VALUES (11, 1, 'b_folder', 1, '/root/b_folder', 0, NULL, 100, 0)"""
    )
    conn.execute(
        """INSERT INTO nodes (id, parent_id, name, type, path, size, extension,
                              modify_time, is_hidden)
           VALUES (20, 1, 'b_file.txt', 2, '/root/b_file.txt', 100, 'txt', 300, 0)"""
    )
    conn.execute(
        """INSERT INTO nodes (id, parent_id, name, type, path, size, extension,
                              modify_time, is_hidden)
           VALUES (21, 1, 'a_file.txt', 2, '/root/a_file.txt', 200, 'txt', 150, 0)"""
    )
    conn.execute(
        """INSERT INTO nodes (id, parent_id, name, type, path, size, extension,
                              modify_time, is_hidden)
           VALUES (22, 1, 'hidden.txt', 2, '/root/hidden.txt', 50, 'txt', 250, 1)"""
    )

    # nodes: 媒体文件对应的文件条目（media 表 JOIN nodes 需 type=2）
    conn.execute(
        """INSERT INTO nodes (id, parent_id, name, type, path, size, extension,
                              modify_time, is_hidden)
           VALUES (30, 1, 'img1.jpg', 2, '/root/img1.jpg', 0, 'jpg', 100, 0)"""
    )
    conn.execute(
        """INSERT INTO nodes (id, parent_id, name, type, path, size, extension,
                              modify_time, is_hidden)
           VALUES (31, 1, 'img2.jpg', 2, '/root/img2.jpg', 0, 'jpg', 200, 0)"""
    )
    conn.execute(
        """INSERT INTO nodes (id, parent_id, name, type, path, size, extension,
                              modify_time, is_hidden)
           VALUES (32, 10, 'sub_img.jpg', 2, '/root/a_folder/sub_img.jpg', 0, 'jpg', 300, 0)"""
    )
    conn.execute(
        """INSERT INTO nodes (id, parent_id, name, type, path, size, extension,
                              modify_time, is_hidden)
           VALUES (33, 1, 'vid1.mp4', 2, '/root/vid1.mp4', 0, 'mp4', 100, 0)"""
    )
    conn.execute(
        """INSERT INTO nodes (id, parent_id, name, type, path, size, extension,
                              modify_time, is_hidden)
           VALUES (34, 1, 'vid2.mp4', 2, '/root/vid2.mp4', 0, 'mp4', 200, 0)"""
    )

    # media 表
    conn.execute(
        "INSERT INTO media (id, parent_id, name, media_type, path, modify_time) "
        "VALUES (1, 1, 'img1.jpg', 'image', '/root/img1.jpg', 100)"
    )
    conn.execute(
        "INSERT INTO media (id, parent_id, name, media_type, path, modify_time) "
        "VALUES (2, 1, 'img2.jpg', 'image', '/root/img2.jpg', 200)"
    )
    conn.execute(
        "INSERT INTO media (id, parent_id, name, media_type, path, modify_time) "
        "VALUES (3, 10, 'sub_img.jpg', 'image', '/root/a_folder/sub_img.jpg', 300)"
    )
    conn.execute(
        "INSERT INTO media (id, parent_id, name, media_type, path, modify_time) "
        "VALUES (4, 1, 'vid1.mp4', 'video', '/root/vid1.mp4', 100)"
    )
    conn.execute(
        "INSERT INTO media (id, parent_id, name, media_type, path, modify_time) "
        "VALUES (5, 1, 'vid2.mp4', 'video', '/root/vid2.mp4', 200)"
    )

    conn.commit()


class TestGetChildren:

    def test_returns_all_children(self, conn):
        children = get_children(conn, 1)
        assert len(children) == 9  # 2 folders + 7 files
        paths = {c['path'] for c in children}
        assert '/root/a_folder' in paths
        assert '/root/hidden.txt' in paths

    def test_returns_empty_for_leaf(self, conn):
        assert get_children(conn, 999) == []

    def test_folders_before_files(self, conn):
        children = get_children(conn, 1)
        types = [c['type'] for c in children]
        first_file_idx = types.index(2)
        last_folder_idx = len(types) - 1 - types[::-1].index(1)
        assert last_folder_idx < first_file_idx

    def test_sort_name_asc(self, conn):
        children = get_children(conn, 1, sort_type='name', sort_order='asc')
        names = [c['name'] for c in children]
        assert names[:2] == ['a_folder', 'b_folder']
        assert 'a_file.txt' in names
        assert 'b_file.txt' in names

    def test_sort_name_desc(self, conn):
        children = get_children(conn, 1, sort_type='name', sort_order='desc')
        names = [c['name'] for c in children]
        assert names[:2] == ['b_folder', 'a_folder']

    def test_sort_time_asc(self, conn):
        children = get_children(conn, 1, sort_type='time', sort_order='asc')
        names = [c['name'] for c in children]
        assert names[:2] == ['b_folder', 'a_folder']

    def test_sort_time_desc(self, conn):
        children = get_children(conn, 1, sort_type='time', sort_order='desc')
        names = [c['name'] for c in children]
        assert names[:2] == ['a_folder', 'b_folder']

    def test_result_has_required_keys(self, conn):
        children = get_children(conn, 1)
        for child in children:
            for key in ('id', 'name', 'type', 'path', 'size', 'extension', 'is_hidden'):
                assert key in child

    def test_hidden_flag_integer(self, conn):
        children = get_children(conn, 1)
        for child in children:
            assert isinstance(child['is_hidden'], int)


class TestGetMediaPage:

    def test_pagination_limit(self, conn):
        rows, total = get_media_page(conn, 'image', 1, 0)
        assert len(rows) == 1
        assert total == 3

    def test_pagination_offset(self, conn):
        first, total = get_media_page(conn, 'image', 1, 0)
        second, _ = get_media_page(conn, 'image', 1, 1)
        assert first[0]['path'] != second[0]['path']

    def test_pagination_all(self, conn):
        rows, total = get_media_page(conn, 'image', 100, 0)
        assert len(rows) == total == 3

    def test_empty_prefix(self, conn):
        rows, total = get_media_page(conn, 'image', 10, 0,
                                     media_dir='/nonexistent')
        assert rows == []
        assert total == 0

    def test_video_type(self, conn):
        rows, total = get_media_page(conn, 'video', 10, 0)
        assert len(rows) == 2
        assert total == 2

    def test_result_has_required_keys(self, conn):
        rows, _ = get_media_page(conn, 'image', 10, 0)
        for row in rows:
            for key in ('id', 'name', 'path', 'modify_time', 'media_type'):
                assert key in row


class TestGetRandomMedia:

    def test_returns_requested_count(self, conn):
        rows = get_random_media(conn, 'image', 2)
        assert len(rows) == 2

    def test_returns_less_when_not_enough(self, conn):
        rows = get_random_media(conn, 'image', 100)
        assert len(rows) == 3

    def test_exclude_paths(self, conn):
        rows = get_random_media(conn, 'image', 10,
                                exclude_paths=['/root/img1.jpg'])
        assert len(rows) == 2
        assert all(r['path'] != '/root/img1.jpg' for r in rows)

    def test_all_excluded_returns_empty(self, conn):
        rows = get_random_media(
            conn, 'image', 10,
            exclude_paths=['/root/img1.jpg', '/root/img2.jpg',
                           '/root/a_folder/sub_img.jpg'],
        )
        assert rows == []

    def test_video_type(self, conn):
        rows = get_random_media(conn, 'video', 1)
        assert len(rows) == 1
        assert rows[0]['path'] in ('/root/vid1.mp4', '/root/vid2.mp4')

    def test_random_order_different(self, conn):
        results = set()
        for _ in range(20):
            rows = get_random_media(conn, 'image', 2)
            key = tuple(r['id'] for r in rows)
            results.add(key)
        assert len(results) >= 2


class TestGetDirectMedia:

    def test_only_direct_files(self, conn):
        """只返回直接子文件，不返回孙文件夹中的文件"""
        # parent_id=1: img1.jpg, img2.jpg, vid1.mp4, vid2.mp4 (4个直接媒体文件)
        # parent_id=10: sub_img.jpg (孙文件，不应返回)
        rows, total = get_direct_media(conn, 1, 'image')
        assert total == 2  # img1.jpg, img2.jpg
        paths = {r['path'] for r in rows}
        assert '/root/img1.jpg' in paths
        assert '/root/img2.jpg' in paths
        assert '/root/a_folder/sub_img.jpg' not in paths

    def test_only_direct_files_video(self, conn):
        """视频类型也只返回直接子文件"""
        rows, total = get_direct_media(conn, 1, 'video')
        assert total == 2  # vid1.mp4, vid2.mp4

    def test_subfolder_direct_files(self, conn):
        """子文件夹的直接文件"""
        rows, total = get_direct_media(conn, 10, 'image')
        assert total == 1  # sub_img.jpg
        assert rows[0]['path'] == '/root/a_folder/sub_img.jpg'

    def test_empty_folder(self, conn):
        """无媒体文件的文件夹返回空"""
        rows, total = get_direct_media(conn, 999, 'video')
        assert rows == []
        assert total == 0

    def test_sort_name_asc(self, conn):
        """按名称升序"""
        rows, _ = get_direct_media(conn, 1, 'image', sort_type='name', sort_order='asc')
        assert rows[0]['name'] == 'img1.jpg'
        assert rows[1]['name'] == 'img2.jpg'

    def test_sort_name_desc(self, conn):
        """按名称降序"""
        rows, _ = get_direct_media(conn, 1, 'image', sort_type='name', sort_order='desc')
        assert rows[0]['name'] == 'img2.jpg'
        assert rows[1]['name'] == 'img1.jpg'

    def test_sort_time_asc(self, conn):
        """按修改时间升序"""
        rows, _ = get_direct_media(conn, 1, 'image', sort_type='time', sort_order='asc')
        assert rows[0]['name'] == 'img1.jpg'  # mtime=100
        assert rows[1]['name'] == 'img2.jpg'  # mtime=200

    def test_pagination(self, conn):
        """分页参数生效"""
        rows, total = get_direct_media(conn, 1, 'image', limit=1, offset=0)
        assert len(rows) == 1
        assert total == 2


def _make_file(path, content='x'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)


class TestTraverseMedia:

    @pytest.fixture
    def media_root(self):
        """创建测试媒体目录结构"""
        with tempfile.TemporaryDirectory() as td:
            old_media = config.MEDIA_DIR
            config.MEDIA_DIR = Path(td)
            # root 下直接文件
            _make_file(os.path.join(td, 'root_video.mp4'))
            _make_file(os.path.join(td, 'root_photo.jpg'))
            _make_file(os.path.join(td, 'note.txt'))
            # 子文件夹 sub1
            _make_file(os.path.join(td, 'sub1', 'v1.mp4'))
            _make_file(os.path.join(td, 'sub1', 'v2.mp4'))
            # 子文件夹 sub2
            _make_file(os.path.join(td, 'sub2', 'v3.mp4'))
            # 空子文件夹 sub_empty
            os.makedirs(os.path.join(td, 'sub_empty'))
            yield td
            config.MEDIA_DIR = old_media

    @pytest.fixture
    def conn(self):
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        init_tables(conn)
        yield conn
        conn.close()

    def test_collects_from_root_and_subfolders(self, conn, media_root):
        """从根目录和子文件夹收集视频文件"""
        items, next_offset, has_more = traverse_media(
            conn, media_root, 'video', limit=10)
        paths = {item['relative_path'] for item in items}
        assert 'root_video.mp4' in paths
        assert 'sub1/v1.mp4' in paths
        assert 'sub1/v2.mp4' in paths
        assert 'sub2/v3.mp4' in paths
        assert 'root_photo.jpg' not in paths  # 不取图片
        assert 'note.txt' not in paths
        assert has_more is False

    def test_pagination(self, conn, media_root):
        """分页：第一页后还有更多，第二页取完"""
        page1, offset1, more1 = traverse_media(
            conn, media_root, 'video', limit=2)
        assert len(page1) == 2
        assert more1 is True
        assert offset1 == 2

        page2, offset2, more2 = traverse_media(
            conn, media_root, 'video', offset=2, limit=10)
        assert len(page2) == 2  # 剩余 2 个
        assert more2 is False

    def test_offset_skips_correctly(self, conn, media_root):
        """offset 跳过前面的文件"""
        items, _, _ = traverse_media(
            conn, media_root, 'video', offset=2, limit=10)
        assert len(items) == 2  # 跳过前 2 个，剩 2 个

    def test_exclude_paths(self, conn, media_root):
        """排除指定路径"""
        all_items, _, _ = traverse_media(
            conn, media_root, 'video', limit=10)
        all_paths = [item['path'] for item in all_items]

        exclude = [all_paths[0]]  # 排除第一个
        items, _, _ = traverse_media(
            conn, media_root, 'video', limit=10, exclude_paths=exclude)
        assert len(items) == 3  # 4 个视频 - 排除 1 个

    def test_random_start(self, conn, media_root):
        """随机起点不影响文件总数"""
        items, _, _ = traverse_media(
            conn, media_root, 'video', limit=10, random_start=True)
        assert len(items) == 4  # 仍然是全部 4 个视频

    def test_items_have_required_keys(self, conn, media_root):
        """返回的每个条目包含必需字段"""
        items, _, _ = traverse_media(
            conn, media_root, 'video', limit=1)
        item = items[0]
        for key in ('name', 'path', 'relative_path', 'mtime', 'timestamp',
                    'is_video', 'is_image', 'media_type'):
            assert key in item, f"缺少字段: {key}"

    def test_image_type(self, conn, media_root):
        """图片类型只返回图片"""
        items, _, _ = traverse_media(
            conn, media_root, 'image', limit=10)
        assert len(items) == 1  # 只有 root_photo.jpg
        assert items[0]['name'] == 'root_photo.jpg'

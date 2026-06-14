"""测试查询接口：get_children / get_media_page / get_random_media（新 schema）"""
import os
import sys
import sqlite3

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db_utils import init_tables, get_children, get_media_page, get_random_media, get_direct_media


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

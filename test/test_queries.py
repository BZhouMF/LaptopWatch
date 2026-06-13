"""测试查询接口：get_children / get_media_page / get_random_media"""
import os
import sys
import sqlite3

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db_utils import ensure_tables, get_children, get_media_page, get_random_media


@pytest.fixture
def conn():
    conn = sqlite3.connect(':memory:')
    ensure_tables(conn)
    _seed(conn)
    yield conn
    conn.close()


def _seed(conn):
    """插入测试数据"""
    conn.execute(
        """INSERT INTO nodes (id, parent_id, name, type, path, size, extension,
                              create_time, modify_time, is_hidden)
           VALUES (1, 0, 'root', 1, '/root', 0, NULL, 100, 100, 0)"""
    )
    conn.execute(
        """INSERT INTO nodes (id, parent_id, name, type, path, size, extension,
                              create_time, modify_time, is_hidden)
           VALUES (10, 1, 'a_folder', 1, '/root/a_folder', 0, NULL, 100, 200, 0)"""
    )
    conn.execute(
        """INSERT INTO nodes (id, parent_id, name, type, path, size, extension,
                              create_time, modify_time, is_hidden)
           VALUES (11, 1, 'b_folder', 1, '/root/b_folder', 0, NULL, 100, 100, 0)"""
    )
    conn.execute(
        """INSERT INTO nodes (id, parent_id, name, type, path, size, extension,
                              create_time, modify_time, is_hidden)
           VALUES (20, 1, 'b_file.txt', 2, '/root/b_file.txt', 100, '.txt', 100, 300, 0)"""
    )
    conn.execute(
        """INSERT INTO nodes (id, parent_id, name, type, path, size, extension,
                              create_time, modify_time, is_hidden)
           VALUES (21, 1, 'a_file.txt', 2, '/root/a_file.txt', 200, '.txt', 100, 150, 0)"""
    )
    conn.execute(
        """INSERT INTO nodes (id, parent_id, name, type, path, size, extension,
                              create_time, modify_time, is_hidden)
           VALUES (22, 1, 'hidden.txt', 2, '/root/hidden.txt', 50, '.txt', 100, 250, 1)"""
    )

    # media 表
    conn.execute(
        "INSERT INTO images (id, parent_id, name, path, modify_time) "
        "VALUES (1, 1, 'img1.jpg', '/root/img1.jpg', 100)"
    )
    conn.execute(
        "INSERT INTO images (id, parent_id, name, path, modify_time) "
        "VALUES (2, 1, 'img2.jpg', '/root/img2.jpg', 200)"
    )
    conn.execute(
        "INSERT INTO images (id, parent_id, name, path, modify_time) "
        "VALUES (3, 10, 'sub_img.jpg', '/root/a_folder/sub_img.jpg', 300)"
    )
    conn.execute(
        "INSERT INTO videos (id, parent_id, name, path, modify_time) "
        "VALUES (1, 1, 'vid1.mp4', '/root/vid1.mp4', 100)"
    )
    conn.execute(
        "INSERT INTO videos (id, parent_id, name, path, modify_time) "
        "VALUES (2, 1, 'vid2.mp4', '/root/vid2.mp4', 200)"
    )

    # nodes 记录对应的媒体文件（供 JOIN 过滤 type=2，parent_id=0 避免干扰 get_children）
    conn.execute(
        "INSERT INTO nodes (id, parent_id, name, type, path, size, extension, create_time, modify_time, is_hidden) "
        "VALUES (30, 0, 'img1.jpg', 2, '/root/img1.jpg', 0, '.jpg', 100, 100, 0)"
    )
    conn.execute(
        "INSERT INTO nodes (id, parent_id, name, type, path, size, extension, create_time, modify_time, is_hidden) "
        "VALUES (31, 0, 'img2.jpg', 2, '/root/img2.jpg', 0, '.jpg', 100, 200, 0)"
    )
    conn.execute(
        "INSERT INTO nodes (id, parent_id, name, type, path, size, extension, create_time, modify_time, is_hidden) "
        "VALUES (32, 0, 'sub_img.jpg', 2, '/root/a_folder/sub_img.jpg', 0, '.jpg', 100, 300, 0)"
    )
    conn.execute(
        "INSERT INTO nodes (id, parent_id, name, type, path, size, extension, create_time, modify_time, is_hidden) "
        "VALUES (33, 0, 'vid1.mp4', 2, '/root/vid1.mp4', 0, '.mp4', 100, 100, 0)"
    )
    conn.execute(
        "INSERT INTO nodes (id, parent_id, name, type, path, size, extension, create_time, modify_time, is_hidden) "
        "VALUES (34, 0, 'vid2.mp4', 2, '/root/vid2.mp4', 0, '.mp4', 100, 200, 0)"
    )

    conn.commit()


class TestGetChildren:

    def test_returns_all_children(self, conn):
        """返回指定 parent_id 下的所有子项"""
        children = get_children(conn, 1)
        assert len(children) == 5  # 2 folders + 3 files
        paths = {c['path'] for c in children}
        assert '/root/a_folder' in paths
        assert '/root/hidden.txt' in paths

    def test_returns_empty_for_leaf(self, conn):
        """没有子项的返回空列表"""
        assert get_children(conn, 10) == []

    def test_folders_before_files(self, conn):
        """文件夹 type=1 应排在文件 type=2 之前"""
        children = get_children(conn, 1)
        types = [c['type'] for c in children]
        first_file_idx = types.index(2)
        last_folder_idx = len(types) - 1 - types[::-1].index(1)
        assert last_folder_idx < first_file_idx

    def test_sort_name_asc(self, conn):
        """按 name asc 排序（先 type 分组再排序）"""
        children = get_children(conn, 1, sort_type='name', sort_order='asc')
        names = [c['name'] for c in children]
        # 文件夹在前且内部有序
        assert names[:2] == ['a_folder', 'b_folder']
        # 文件在后且内部有序
        assert names[2:] == ['a_file.txt', 'b_file.txt', 'hidden.txt']

    def test_sort_name_desc(self, conn):
        """按 name desc 排序"""
        children = get_children(conn, 1, sort_type='name', sort_order='desc')
        names = [c['name'] for c in children]
        assert names[:2] == ['b_folder', 'a_folder']
        assert names[2:] == ['hidden.txt', 'b_file.txt', 'a_file.txt']

    def test_sort_time_asc(self, conn):
        """按 modify_time asc 排序"""
        children = get_children(conn, 1, sort_type='time', sort_order='asc')
        names = [c['name'] for c in children]
        # folders: b_folder(100) < a_folder(200)
        assert names[:2] == ['b_folder', 'a_folder']
        # files: a_file.txt(150) < hidden.txt(250) < b_file.txt(300)
        assert names[2:] == ['a_file.txt', 'hidden.txt', 'b_file.txt']

    def test_sort_time_desc(self, conn):
        """按 modify_time desc 排序"""
        children = get_children(conn, 1, sort_type='time', sort_order='desc')
        names = [c['name'] for c in children]
        # folders: a_folder(200) > b_folder(100)
        assert names[:2] == ['a_folder', 'b_folder']
        # files: b_file.txt(300) > hidden.txt(250) > a_file.txt(150)
        assert names[2:] == ['b_file.txt', 'hidden.txt', 'a_file.txt']

    def test_result_has_required_keys(self, conn):
        """返回的 dict 包含前端所需字段"""
        children = get_children(conn, 1)
        for child in children:
            assert 'id' in child
            assert 'name' in child
            assert 'type' in child
            assert 'path' in child
            assert 'size' in child
            assert 'extension' in child
            assert 'is_hidden' in child

    def test_hidden_flag_boolean(self, conn):
        """is_hidden 为 bool 类型"""
        children = get_children(conn, 1)
        for child in children:
            assert isinstance(child['is_hidden'], bool)


class TestGetMediaPage:

    def test_pagination_limit(self, conn):
        """LIMIT 限制返回条数"""
        rows, total = get_media_page(conn, 'images', 1, 1, 0)
        assert len(rows) == 1
        assert total == 2

    def test_pagination_offset(self, conn):
        """OFFSET 跳过前 N 条"""
        first, total = get_media_page(conn, 'images', 1, 1, 0)
        second, _ = get_media_page(conn, 'images', 1, 1, 1)
        assert first[0]['path'] != second[0]['path']

    def test_pagination_all(self, conn):
        """取全部时不丢数据"""
        rows, total = get_media_page(conn, 'images', 1, 100, 0)
        assert len(rows) == total == 2

    def test_empty_parent(self, conn):
        """无媒体文件的父节点返回空"""
        rows, total = get_media_page(conn, 'images', 999, 10, 0)
        assert rows == []
        assert total == 0

    def test_videos_table(self, conn):
        """videos 表同样正常工作"""
        rows, total = get_media_page(conn, 'videos', 1, 10, 0)
        assert len(rows) == 2
        assert total == 2

    def test_subfolder_media(self, conn):
        """子文件夹下也有自己的媒体记录"""
        rows, total = get_media_page(conn, 'images', 10, 10, 0)
        assert len(rows) == 1
        assert rows[0]['name'] == 'sub_img.jpg'

    def test_result_has_required_keys(self, conn):
        rows, _ = get_media_page(conn, 'images', 1, 10, 0)
        for row in rows:
            assert 'id' in row
            assert 'name' in row
            assert 'path' in row
            assert 'modify_time' in row


class TestGetRandomMedia:

    def test_returns_requested_count(self, conn):
        """返回指定数量的随机条目"""
        rows = get_random_media(conn, 'images', 2)
        assert len(rows) == 2

    def test_returns_less_when_not_enough(self, conn):
        """请求数超过总数时返回全部"""
        rows = get_random_media(conn, 'images', 100)
        assert len(rows) == 3  # images has 3 rows

    def test_exclude_paths(self, conn):
        """排除指定路径后不返回被排除项"""
        rows = get_random_media(conn, 'images', 10, exclude_paths=['/root/img1.jpg'])
        assert len(rows) == 2
        assert all(r['path'] != '/root/img1.jpg' for r in rows)

    def test_all_excluded_returns_empty(self, conn):
        """全部排除后返回空列表"""
        rows = get_random_media(
            conn, 'images', 10,
            exclude_paths=['/root/img1.jpg', '/root/img2.jpg', '/root/a_folder/sub_img.jpg'],
        )
        assert rows == []

    def test_video_table(self, conn):
        """videos 表同样支持随机查询"""
        rows = get_random_media(conn, 'videos', 1)
        assert len(rows) == 1
        assert rows[0]['path'] in ('/root/vid1.mp4', '/root/vid2.mp4')

    def test_random_order_different(self, conn):
        """多次调用可能返回不同顺序（概率性测试）"""
        results = set()
        for _ in range(20):
            rows = get_random_media(conn, 'images', 2)
            key = tuple(r['id'] for r in rows)
            results.add(key)
        # 至少出现过 2 种不同顺序（极少可能全相同）
        assert len(results) >= 2

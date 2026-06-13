"""测试 sync_folder：单文件夹增量同步"""
import os
import sys
import time
import tempfile
import sqlite3

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db_utils import get_db, ensure_tables, sync_folder
from config import config


@pytest.fixture
def conn():
    """内存数据库 + 已建表"""
    conn = sqlite3.connect(':memory:')
    ensure_tables(conn)
    yield conn
    conn.close()


@pytest.fixture
def temp_dir():
    """临时目录供测试操作"""
    with tempfile.TemporaryDirectory() as td:
        yield td


def _count_rows(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _node_id(conn, path):
    cursor = conn.execute("SELECT id FROM nodes WHERE path=?", (path,))
    row = cursor.fetchone()
    return row[0] if row else None


def _child_paths(conn, parent_path):
    """返回 parent_path 下所有直接子节点的路径 set"""
    pid = _node_id(conn, parent_path)
    if not pid:
        return set()
    return {r[0] for r in conn.execute(
        "SELECT path FROM nodes WHERE parent_id=?", (pid,)
    ).fetchall()}


def _media_paths(conn, table, parent_path):
    pid = _node_id(conn, parent_path)
    if not pid:
        return set()
    return {r[0] for r in conn.execute(
        f"SELECT path FROM {table} WHERE parent_id=?", (pid,)
    ).fetchall()}


class TestSyncFolderBasic:

    def test_empty_folder(self, conn, temp_dir):
        """空文件夹首次同步后 nodes 只有文件夹自身"""
        sync_folder(conn, temp_dir)
        assert _node_id(conn, temp_dir) is not None
        assert _child_paths(conn, temp_dir) == set()

    def test_add_files(self, conn, temp_dir):
        """添加文件后再次同步能发现新增"""
        sync_folder(conn, temp_dir)
        assert _child_paths(conn, temp_dir) == set()

        f1 = os.path.join(temp_dir, 'a.txt')
        f2 = os.path.join(temp_dir, 'b.txt')
        with open(f1, 'w') as f:
            f.write('hello')
        with open(f2, 'w') as f:
            f.write('world')

        sync_folder(conn, temp_dir)
        children = _child_paths(conn, temp_dir)
        assert f1 in children
        assert f2 in children

    def test_delete_files(self, conn, temp_dir):
        """删除文件后同步能发现删除"""
        f1 = os.path.join(temp_dir, 'keep.txt')
        f2 = os.path.join(temp_dir, 'delete.txt')
        with open(f1, 'w') as f:
            f.write('keep')
        with open(f2, 'w') as f:
            f.write('delete')

        sync_folder(conn, temp_dir)
        assert _child_paths(conn, temp_dir) == {f1, f2}

        os.remove(f2)
        sync_folder(conn, temp_dir)
        assert _child_paths(conn, temp_dir) == {f1}

    def test_update_modify_time(self, conn, temp_dir):
        """修改 modify_time 后同步能更新"""
        f1 = os.path.join(temp_dir, 'update.txt')
        with open(f1, 'w') as f:
            f.write('v1')

        sync_folder(conn, temp_dir)
        old_mtime = conn.execute(
            "SELECT modify_time FROM nodes WHERE path=?", (f1,)
        ).fetchone()[0]

        new_mtime = old_mtime + 10
        os.utime(f1, (new_mtime, new_mtime))

        sync_folder(conn, temp_dir)
        updated = conn.execute(
            "SELECT modify_time FROM nodes WHERE path=?", (f1,)
        ).fetchone()[0]
        assert abs(updated - new_mtime) < 0.01

    def test_no_recursion(self, conn, temp_dir):
        """子文件夹内容不应被递归同步"""
        sub = os.path.join(temp_dir, 'sub')
        os.makedirs(sub)
        nested = os.path.join(sub, 'nested.txt')
        with open(nested, 'w') as f:
            f.write('nested')

        sync_folder(conn, temp_dir)
        children = _child_paths(conn, temp_dir)
        assert sub in children
        assert nested not in children


class TestSyncFolderMediaMode:

    def test_video_mode_syncs_videos(self, conn, temp_dir):
        """run_mode=video 时 videos 表同步"""
        mp4 = os.path.join(temp_dir, 'test.mp4')
        with open(mp4, 'w') as f:
            f.write('not really a video')

        sync_folder(conn, temp_dir, run_mode='video')
        assert mp4 in _media_paths(conn, 'videos', temp_dir)

    def test_video_mode_skips_non_video(self, conn, temp_dir):
        """video 模式下非视频文件不进 videos 表"""
        txt = os.path.join(temp_dir, 'note.txt')
        with open(txt, 'w') as f:
            f.write('text')

        sync_folder(conn, temp_dir, run_mode='video')
        assert _count_rows(conn, 'videos') == 0

    def test_video_mode_includes_subfolders(self, conn, temp_dir):
        """video 模式下文件夹也写入 videos"""
        sub = os.path.join(temp_dir, 'subfolder')
        os.makedirs(sub)

        sync_folder(conn, temp_dir, run_mode='video')
        assert sub in _media_paths(conn, 'videos', temp_dir)

    def test_image_mode_syncs_images(self, conn, temp_dir):
        """run_mode=image 时 images 表同步"""
        jpg = os.path.join(temp_dir, 'photo.jpg')
        with open(jpg, 'w') as f:
            f.write('not really an image')

        sync_folder(conn, temp_dir, run_mode='image')
        assert jpg in _media_paths(conn, 'images', temp_dir)

    def test_image_mode_skips_non_image(self, conn, temp_dir):
        """image 模式下非图片文件不进 images 表"""
        txt = os.path.join(temp_dir, 'note.txt')
        with open(txt, 'w') as f:
            f.write('text')

        sync_folder(conn, temp_dir, run_mode='image')
        assert _count_rows(conn, 'images') == 0

    def test_normal_mode_ignores_media_tables(self, conn, temp_dir):
        """normal 模式不碰 images/videos 表"""
        mp4 = os.path.join(temp_dir, 'test.mp4')
        jpg = os.path.join(temp_dir, 'photo.jpg')
        with open(mp4, 'w') as f:
            f.write('video')
        with open(jpg, 'w') as f:
            f.write('image')

        sync_folder(conn, temp_dir, run_mode='normal')
        assert _count_rows(conn, 'images') == 0
        assert _count_rows(conn, 'videos') == 0
        # nodes 应有 2 个文件 + 目录自身
        children = _child_paths(conn, temp_dir)
        assert mp4 in children
        assert jpg in children

    def test_douyin_mode_like_video(self, conn, temp_dir):
        """douyin 模式行为同 video"""
        mp4 = os.path.join(temp_dir, 'clip.mp4')
        with open(mp4, 'w') as f:
            f.write('clip')

        sync_folder(conn, temp_dir, run_mode='douyin')
        assert mp4 in _media_paths(conn, 'videos', temp_dir)


class TestSyncFolderCascadeDelete:

    def test_cascade_delete_folder(self, conn, temp_dir):
        """删除文件夹时级联删除子节点"""
        sub = os.path.join(temp_dir, 'sub')
        os.makedirs(sub)
        nested = os.path.join(sub, 'file.txt')
        with open(nested, 'w') as f:
            f.write('nested')

        sync_folder(conn, temp_dir)
        assert sub in _child_paths(conn, temp_dir)

        import shutil
        shutil.rmtree(sub)

        sync_folder(conn, temp_dir)
        assert sub not in _child_paths(conn, temp_dir)
        # nested should also be gone since its parent was cascade-deleted
        assert _node_id(conn, nested) is None

    def test_cascade_removes_media_records(self, conn, temp_dir):
        """删除文件夹时同时清理 images/videos 记录"""
        sub = os.path.join(temp_dir, 'sub')
        os.makedirs(sub)
        vid = os.path.join(sub, 'clip.mp4')
        with open(vid, 'w') as f:
            f.write('clip')

        # 先同步 sub 使其内容进入 DB
        sync_folder(conn, sub, run_mode='video')
        # 再同步 temp_dir 使 sub 自身进入 videos
        sync_folder(conn, temp_dir, run_mode='video')

        assert sub in _media_paths(conn, 'videos', temp_dir)

        import shutil
        shutil.rmtree(sub)

        # 重新同步，sub 及其所有子节点都应被清除
        sync_folder(conn, temp_dir, run_mode='video')
        assert sub not in _child_paths(conn, temp_dir)
        assert _node_id(conn, vid) is None

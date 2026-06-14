"""测试 sync_folder：单文件夹增量同步（新 schema）"""
import os
import sys
import tempfile
import sqlite3

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db_utils import get_db, init_tables, sync_folder


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        yield td


@pytest.fixture
def conn():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    init_tables(conn)
    yield conn
    conn.close()


def _node_id(conn, path):
    row = conn.execute("SELECT id FROM nodes WHERE path=?", (path,)).fetchone()
    return row[0] if row else None


def _child_paths(conn, parent_path):
    pid = _node_id(conn, parent_path)
    if not pid:
        return set()
    return {r[0] for r in conn.execute(
        "SELECT path FROM nodes WHERE parent_id=?", (pid,)
    ).fetchall()}


def _media_paths(conn, parent_path):
    pid = _node_id(conn, parent_path)
    if not pid:
        return set()
    return {r[0] for r in conn.execute(
        "SELECT path FROM media WHERE parent_id=?", (pid,)
    ).fetchall()}


class TestSyncFolderBasic:

    def test_empty_folder(self, conn, temp_dir):
        sync_folder(conn, temp_dir)
        assert _node_id(conn, temp_dir) is not None
        assert _child_paths(conn, temp_dir) == set()

    def test_add_files(self, conn, temp_dir):
        sync_folder(conn, temp_dir)
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
        sub = os.path.join(temp_dir, 'sub')
        os.makedirs(sub)
        nested = os.path.join(sub, 'nested.txt')
        with open(nested, 'w') as f:
            f.write('nested')

        sync_folder(conn, temp_dir)
        children = _child_paths(conn, temp_dir)
        assert sub in children
        assert nested not in children


class TestSyncFolderMediaSync:

    def test_video_added_to_media(self, conn, temp_dir):
        mp4 = os.path.join(temp_dir, 'test.mp4')
        with open(mp4, 'w') as f:
            f.write('not really a video')

        sync_folder(conn, temp_dir)
        assert mp4 in _media_paths(conn, temp_dir)

    def test_non_media_not_in_media_table(self, conn, temp_dir):
        txt = os.path.join(temp_dir, 'note.txt')
        with open(txt, 'w') as f:
            f.write('text')

        sync_folder(conn, temp_dir)
        assert _media_paths(conn, temp_dir) == set()

    def test_image_added_to_media(self, conn, temp_dir):
        jpg = os.path.join(temp_dir, 'photo.jpg')
        with open(jpg, 'w') as f:
            f.write('not really an image')

        sync_folder(conn, temp_dir)
        assert jpg in _media_paths(conn, temp_dir)

    def test_media_type_correct(self, conn, temp_dir):
        mp4 = os.path.join(temp_dir, 'clip.mp4')
        jpg = os.path.join(temp_dir, 'img.jpg')
        with open(mp4, 'w') as f:
            f.write('vid')
        with open(jpg, 'w') as f:
            f.write('img')

        sync_folder(conn, temp_dir)

        vid_type = conn.execute(
            "SELECT media_type FROM media WHERE path=?", (mp4,)
        ).fetchone()[0]
        img_type = conn.execute(
            "SELECT media_type FROM media WHERE path=?", (jpg,)
        ).fetchone()[0]
        assert vid_type == 'video'
        assert img_type == 'image'


class TestSyncFolderCascadeDelete:

    def test_cascade_delete_folder(self, conn, temp_dir):
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
        assert _node_id(conn, nested) is None

    def test_cascade_removes_media_records(self, conn, temp_dir):
        sub = os.path.join(temp_dir, 'sub')
        os.makedirs(sub)
        vid = os.path.join(sub, 'clip.mp4')
        with open(vid, 'w') as f:
            f.write('clip')

        sync_folder(conn, sub)
        sync_folder(conn, temp_dir)

        # clip.mp4 应在 media 表中（parent_id 指向 sub 节点）
        assert vid in _media_paths(conn, sub)

        import shutil
        shutil.rmtree(sub)

        sync_folder(conn, temp_dir)
        assert sub not in _child_paths(conn, temp_dir)
        assert _node_id(conn, vid) is None
        # media 表中的 clip.mp4 也应级联删除
        assert vid not in _media_paths(conn, sub)

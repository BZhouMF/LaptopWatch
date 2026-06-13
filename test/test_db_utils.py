"""测试 db_utils.py：数据库连接与表创建"""
import os
import sys
import tempfile
import sqlite3

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db_utils import get_db, ensure_tables


class TestGetDb:
    def test_returns_connection(self):
        """get_db 返回有效的 sqlite3.Connection"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        try:
            conn = get_db(db_path)
            assert isinstance(conn, sqlite3.Connection)
            conn.close()
        finally:
            os.unlink(db_path)

    def test_wal_mode_enabled(self):
        """连接启用了 WAL 模式"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        try:
            conn = get_db(db_path)
            cursor = conn.execute("PRAGMA journal_mode")
            assert cursor.fetchone()[0] == 'wal'
            conn.close()
        finally:
            os.unlink(db_path)


class TestEnsureTables:
    @pytest.fixture
    def conn(self):
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        conn = get_db(db_path)
        yield conn
        conn.close()
        os.unlink(db_path)

    def _table_exists(self, conn, table_name):
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        return cursor.fetchone() is not None

    def _table_columns(self, conn, table_name):
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        return {row[1] for row in cursor.fetchall()}

    def test_creates_nodes_table(self, conn):
        ensure_tables(conn)
        assert self._table_exists(conn, 'nodes')
        cols = self._table_columns(conn, 'nodes')
        for required in ('id', 'parent_id', 'name', 'type', 'path',
                         'size', 'extension', 'create_time', 'modify_time', 'is_hidden'):
            assert required in cols, f"nodes 表缺少列: {required}"

    def test_creates_images_table(self, conn):
        ensure_tables(conn)
        assert self._table_exists(conn, 'images')
        cols = self._table_columns(conn, 'images')
        for required in ('id', 'parent_id', 'name', 'path', 'modify_time', 'cover'):
            assert required in cols, f"images 表缺少列: {required}"

    def test_creates_videos_table(self, conn):
        ensure_tables(conn)
        assert self._table_exists(conn, 'videos')
        cols = self._table_columns(conn, 'videos')
        for required in ('id', 'parent_id', 'name', 'path', 'modify_time', 'cover'):
            assert required in cols, f"videos 表缺少列: {required}"

    def test_idempotent(self, conn):
        """重复调用 ensure_tables 不报错"""
        ensure_tables(conn)
        ensure_tables(conn)  # 第二次调用不应抛异常

    def test_all_three_tables_created(self, conn):
        ensure_tables(conn)
        for name in ('nodes', 'images', 'videos'):
            assert self._table_exists(conn, name), f"缺少表: {name}"

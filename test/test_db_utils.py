"""测试 db_utils.py：数据库连接、表创建、查询"""
import os
import sys
import tempfile
import sqlite3

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db_utils import get_db, init_tables


class TestGetDb:
    def test_returns_connection(self):
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        try:
            conn = get_db(db_path)
            assert isinstance(conn, sqlite3.Connection)
            conn.close()
        finally:
            os.unlink(db_path)

    def test_wal_mode_enabled(self):
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        try:
            conn = get_db(db_path)
            cursor = conn.execute("PRAGMA journal_mode")
            assert cursor.fetchone()[0] == 'wal'
            conn.close()
        finally:
            os.unlink(db_path)


class TestInitTables:
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
        init_tables(conn)
        assert self._table_exists(conn, 'nodes')
        cols = self._table_columns(conn, 'nodes')
        for required in ('id', 'parent_id', 'name', 'type', 'path',
                         'size', 'extension', 'modify_time', 'is_hidden'):
            assert required in cols, f"nodes 表缺少列: {required}"

    def test_creates_media_table(self, conn):
        init_tables(conn)
        assert self._table_exists(conn, 'media')
        cols = self._table_columns(conn, 'media')
        for required in ('id', 'parent_id', 'name', 'media_type',
                         'path', 'modify_time', 'cover'):
            assert required in cols, f"media 表缺少列: {required}"

    def test_idempotent(self, conn):
        init_tables(conn)
        init_tables(conn)  # 第二次调用不应抛异常

    def test_both_tables_created(self, conn):
        init_tables(conn)
        for name in ('nodes', 'media'):
            assert self._table_exists(conn, name), f"缺少表: {name}"

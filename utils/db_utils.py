"""数据库连接、表创建与增量同步"""
import os
import time
import sqlite3

from config import config


def get_db(db_path):
    """创建数据库连接，启用 WAL 模式"""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_tables(conn):
    """创建 nodes/images/videos 三张表（幂等）"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS nodes (
            id          INTEGER PRIMARY KEY,
            parent_id   INTEGER NOT NULL DEFAULT 0,
            name        TEXT NOT NULL,
            type        INTEGER NOT NULL,
            path        TEXT NOT NULL UNIQUE,
            size        INTEGER NOT NULL DEFAULT 0,
            extension   TEXT,
            create_time REAL NOT NULL,
            modify_time REAL NOT NULL,
            is_hidden   INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS images (
            id          INTEGER PRIMARY KEY,
            parent_id   INTEGER NOT NULL DEFAULT 0,
            name        TEXT NOT NULL,
            path        TEXT NOT NULL UNIQUE,
            modify_time REAL NOT NULL,
            cover       BLOB DEFAULT NULL
        );

        CREATE TABLE IF NOT EXISTS videos (
            id          INTEGER PRIMARY KEY,
            parent_id   INTEGER NOT NULL DEFAULT 0,
            name        TEXT NOT NULL,
            path        TEXT NOT NULL UNIQUE,
            modify_time REAL NOT NULL,
            cover       BLOB DEFAULT NULL
        );
    """)
    conn.commit()


# ── 内部辅助 ──────────────────────────────────────────────


def _get_hidden_flag(entry_name, stat_info):
    """判断文件/文件夹是否隐藏"""
    if entry_name.startswith('.'):
        return 1
    st_file_attributes = getattr(stat_info, 'st_file_attributes', 0)
    return 1 if (st_file_attributes & 2) else 0


def _ensure_node(conn, folder_path):
    """确保文件夹路径在 nodes 中存在，返回其 id（不递归创建祖先）"""
    folder_path = os.path.abspath(folder_path)

    cursor = conn.execute(
        "SELECT id FROM nodes WHERE path=? AND type=1", (folder_path,)
    )
    row = cursor.fetchone()
    if row:
        return row[0]

    # 查找已在 DB 中的父节点（不会自动创建）
    parent_path = os.path.dirname(folder_path)
    parent_id = 0
    if parent_path and parent_path != folder_path:
        cursor = conn.execute(
            "SELECT id FROM nodes WHERE path=? AND type=1", (parent_path,)
        )
        parent_row = cursor.fetchone()
        if parent_row:
            parent_id = parent_row[0]

    name = os.path.basename(folder_path) or folder_path
    try:
        st = os.stat(folder_path)
        create_time = st.st_ctime
        modify_time = st.st_mtime
        is_hidden = _get_hidden_flag(name, st)
    except OSError:
        create_time = modify_time = time.time()
        is_hidden = 0

    cursor = conn.execute(
        """INSERT INTO nodes (parent_id, name, type, path, size, extension,
                              create_time, modify_time, is_hidden)
           VALUES (?, ?, 1, ?, 0, NULL, ?, ?, ?)""",
        (parent_id, name, folder_path, create_time, modify_time, is_hidden),
    )
    return cursor.lastrowid


def _upsert_media_record(conn, run_mode, parent_id, entry, modify_time, entry_type, is_dir):
    """按 run_mode 同步一条记录到 images/videos 表，保留已有 cover"""
    if run_mode == 'normal':
        return

    if run_mode in ('video', 'douyin'):
        table = 'videos'
        valid_ext = config.VIDEO_EXT
    elif run_mode == 'image':
        table = 'images'
        valid_ext = config.IMAGE_EXT
    else:
        return

    if not is_dir:
        ext = os.path.splitext(entry.name)[1].lower()
        if ext not in valid_ext:
            return

    entry_path = entry.path
    cursor = conn.execute(f"SELECT id FROM {table} WHERE path=?", (entry_path,))
    existing = cursor.fetchone()

    if existing:
        conn.execute(
            f"UPDATE {table} SET parent_id=?, name=?, modify_time=? WHERE id=?",
            (parent_id, entry.name, modify_time, existing[0]),
        )
    else:
        conn.execute(
            f"INSERT INTO {table} (parent_id, name, path, modify_time, cover) "
            "VALUES (?, ?, ?, ?, NULL)",
            (parent_id, entry.name, entry_path, modify_time),
        )


def _delete_cascade(conn, node_id):
    """递归删除节点及其所有子节点（nodes + images/videos）"""
    cursor = conn.execute("SELECT id, path FROM nodes WHERE parent_id=?", (node_id,))
    children = cursor.fetchall()

    for child_id, child_path in children:
        _delete_cascade(conn, child_id)

    cursor = conn.execute("SELECT path FROM nodes WHERE id=?", (node_id,))
    row = cursor.fetchone()
    if row:
        node_path = row[0]
        conn.execute("DELETE FROM images WHERE path=?", (node_path,))
        conn.execute("DELETE FROM videos WHERE path=?", (node_path,))

    conn.execute("DELETE FROM nodes WHERE id=?", (node_id,))


# ── 公开 API ──────────────────────────────────────────────


def sync_folder(conn, folder_path, run_mode='normal'):
    """增量同步单个文件夹（仅 scandir 1 层），不递归"""
    folder_path = os.path.abspath(folder_path)
    folder_id = _ensure_node(conn, folder_path)

    # 收集 DB 现有子项 {path: {col: value}}
    db_children = {}
    cursor = conn.execute(
        """SELECT id, name, path, modify_time, type, extension, size, is_hidden
           FROM nodes WHERE parent_id=?""",
        (folder_id,),
    )
    for row in cursor.fetchall():
        db_children[row[2]] = {
            'id': row[0], 'name': row[1], 'modify_time': row[3],
            'type': row[4], 'extension': row[5], 'size': row[6], 'is_hidden': row[7],
        }

    # scandir 当前文件夹（仅 1 层）
    try:
        entries = list(os.scandir(folder_path))
    except PermissionError:
        entries = []

    for entry in entries:
        entry_path = entry.path
        try:
            is_dir = entry.is_dir(follow_symlinks=False)
            is_file = entry.is_file(follow_symlinks=False)
        except OSError:
            continue
        if not is_dir and not is_file:
            continue

        try:
            stat_info = entry.stat(follow_symlinks=False)
        except OSError:
            continue

        fs_type = 1 if is_dir else 2
        fs_size = stat_info.st_size if is_file else 0
        fs_ext = os.path.splitext(entry.name)[1].lower() if is_file else None
        fs_mtime = stat_info.st_mtime
        fs_ctime = getattr(stat_info, 'st_ctime', fs_mtime)
        fs_hidden = _get_hidden_flag(entry.name, stat_info)

        if entry_path in db_children:
            db_row = db_children.pop(entry_path)
            needs_update = (
                abs(db_row['modify_time'] - fs_mtime) > 0.001
                or db_row['size'] != fs_size
                or db_row['type'] != fs_type
                or (db_row['extension'] or '') != (fs_ext or '')
                or db_row['is_hidden'] != fs_hidden
            )
            if needs_update:
                conn.execute(
                    """UPDATE nodes SET size=?, extension=?, modify_time=?,
                       type=?, is_hidden=? WHERE id=?""",
                    (fs_size, fs_ext, fs_mtime, fs_type, fs_hidden, db_row['id']),
                )
                _upsert_media_record(conn, run_mode, folder_id, entry, fs_mtime, fs_type, is_dir)
        else:
            # 检查 path 是否因之前的独立同步已存在于 DB
            cursor = conn.execute(
                "SELECT id FROM nodes WHERE path=?", (entry_path,)
            )
            existing = cursor.fetchone()
            if existing:
                conn.execute(
                    """UPDATE nodes SET parent_id=?, name=?, type=?, size=?,
                       extension=?, modify_time=?, is_hidden=? WHERE id=?""",
                    (folder_id, entry.name, fs_type, fs_size, fs_ext,
                     fs_mtime, fs_hidden, existing[0]),
                )
            else:
                conn.execute(
                    """INSERT INTO nodes (parent_id, name, type, path, size, extension,
                                          create_time, modify_time, is_hidden)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (folder_id, entry.name, fs_type, entry_path, fs_size, fs_ext,
                     fs_ctime, fs_mtime, fs_hidden),
                )
            _upsert_media_record(conn, run_mode, folder_id, entry, fs_mtime, fs_type, is_dir)

    # 删除文件系统中已不存在的条目
    for path, db_row in db_children.items():
        _delete_cascade(conn, db_row['id'])

    conn.commit()

"""数据库连接、表创建、增量同步与封面缓存"""
import os
import time
import sqlite3
from io import BytesIO

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

# ── 查询接口 ──────────────────────────────────────────────


def get_children(conn, parent_id, sort_type='name', sort_order='asc'):
    """返回某文件夹下所有子项，文件夹在前、文件在后

    sort_type: 'name' | 'time'
    sort_order: 'asc' | 'desc'
    返回 list[dict] — id/parent_id/name/type/path/size/extension/modify_time/is_hidden
    """
    order_col = 'modify_time' if sort_type == 'time' else 'name'
    order_dir = 'DESC' if sort_order == 'desc' else 'ASC'

    rows = conn.execute(
        f"""SELECT id, parent_id, name, type, path, size, extension,
                   modify_time, is_hidden
            FROM nodes
            WHERE parent_id=?
            ORDER BY type ASC, {order_col} {order_dir}""",
        (parent_id,),
    ).fetchall()

    return [
        {
            'id': r[0], 'parent_id': r[1], 'name': r[2], 'type': r[3],
            'path': r[4], 'size': r[5], 'extension': r[6],
            'modify_time': r[7], 'is_hidden': bool(r[8]),
        }
        for r in rows
    ]


def get_media_page(conn, table, parent_id, limit, offset):
    """分页取媒体文件（images 或 videos 表）

    返回 (rows, total_count)
    rows 为 list[dict] — id/parent_id/name/path/modify_time
    """
    total = conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE parent_id=?", (parent_id,)
    ).fetchone()[0]

    rows = conn.execute(
        f"""SELECT id, parent_id, name, path, modify_time
            FROM {table}
            WHERE parent_id=?
            ORDER BY name ASC
            LIMIT ? OFFSET ?""",
        (parent_id, limit, offset),
    ).fetchall()

    return (
        [
            {
                'id': r[0], 'parent_id': r[1], 'name': r[2],
                'path': r[3], 'modify_time': r[4],
            }
            for r in rows
        ],
        total,
    )


def get_media_page_all(conn, table, limit, offset):
    """从整个媒体表分页取数据（按 path 排序实现文件夹分组）

    返回 (rows, total_count)
    rows 为 list[dict] — id/parent_id/name/path/modify_time
    """
    total = conn.execute(
        f"SELECT COUNT(*) FROM {table} m JOIN nodes n ON n.path = m.path WHERE n.type=2"
    ).fetchone()[0]

    rows = conn.execute(
        f"""SELECT m.id, m.parent_id, m.name, m.path, m.modify_time
            FROM {table} m
            JOIN nodes n ON n.path = m.path
            WHERE n.type=2
            ORDER BY m.path ASC
            LIMIT ? OFFSET ?""",
        (limit, offset),
    ).fetchall()

    return (
        [
            {
                'id': r[0], 'parent_id': r[1], 'name': r[2],
                'path': r[3], 'modify_time': r[4],
            }
            for r in rows
        ],
        total,
    )


def get_random_media(conn, table, limit, exclude_paths=None):
    """从媒体表随机取 N 条真实文件（不含目录），可排除指定路径

    返回 list[dict] — id/parent_id/name/path/modify_time
    """
    if exclude_paths:
        placeholders = ','.join('?' for _ in exclude_paths)
        rows = conn.execute(
            f"""SELECT m.id, m.parent_id, m.name, m.path, m.modify_time
                FROM {table} m
                JOIN nodes n ON n.path = m.path
                WHERE n.type=2 AND m.path NOT IN ({placeholders})
                ORDER BY RANDOM() LIMIT ?""",
            (*exclude_paths, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            f"""SELECT m.id, m.parent_id, m.name, m.path, m.modify_time
                FROM {table} m
                JOIN nodes n ON n.path = m.path
                WHERE n.type=2
                ORDER BY RANDOM() LIMIT ?""",
            (limit,),
        ).fetchall()

    return [
        {
            'id': r[0], 'parent_id': r[1], 'name': r[2],
            'path': r[3], 'modify_time': r[4],
        }
        for r in rows
    ]


def get_subfolder_nodes(conn, parent_id, sort_type='name', sort_order='asc'):
    """获取某个节点的直接子文件夹列表

    返回 list[dict] — id/name/path
    """
    order_col = 'modify_time' if sort_type == 'time' else 'name'
    order_dir = 'DESC' if sort_order == 'desc' else 'ASC'
    rows = conn.execute(
        f"""SELECT id, name, path
            FROM nodes
            WHERE parent_id=? AND type=1
            ORDER BY {order_col} {order_dir}""",
        (parent_id,),
    ).fetchall()
    return [{'id': r[0], 'name': r[1], 'path': r[2]} for r in rows]


def get_node_by_path(conn, path):
    """根据路径查找 nodes 表中的节点，返回 dict 或 None"""
    cursor = conn.execute(
        "SELECT id, parent_id, name, type, path FROM nodes WHERE path=?", (path,)
    )
    row = cursor.fetchone()
    if row:
        return {'id': row[0], 'parent_id': row[1], 'name': row[2],
                'type': row[3], 'path': row[4]}
    return None


def get_media_in_folder(conn, table, folder_path, limit, offset,
                        sort_type='name', sort_order='asc'):
    """获取文件夹（递归含子文件夹）中的媒体文件，分页

    通过 path 前缀匹配 + nodes 关联实现递归查询，只返回文件（type=2）。
    返回 (rows, total_count)
    rows 为 list[dict] — id/parent_id/name/path/modify_time
    """
    norm_path = os.path.normpath(folder_path)
    prefix = norm_path + os.sep
    order_col = 'modify_time' if sort_type == 'time' else 'name'
    order_dir = 'DESC' if sort_order == 'desc' else 'ASC'

    total = conn.execute(
        f"""SELECT COUNT(*) FROM {table} m
            JOIN nodes n ON n.path = m.path
            WHERE m.path LIKE ? AND n.type=2""",
        (prefix + '%',)
    ).fetchone()[0]

    rows = conn.execute(
        f"""SELECT m.id, m.parent_id, m.name, m.path, m.modify_time
            FROM {table} m
            JOIN nodes n ON n.path = m.path
            WHERE m.path LIKE ? AND n.type=2
            ORDER BY {order_col} {order_dir}
            LIMIT ? OFFSET ?""",
        (prefix + '%', limit, offset),
    ).fetchall()

    return (
        [
            {
                'id': r[0], 'parent_id': r[1], 'name': r[2],
                'path': r[3], 'modify_time': r[4],
            }
            for r in rows
        ],
        total,
    )


def get_random_media_in_folder(conn, table, folder_path, limit):
    """从文件夹（递归含子文件夹）中随机取媒体文件（仅文件）"""
    norm_path = os.path.normpath(folder_path)
    prefix = norm_path + os.sep
    rows = conn.execute(
        f"""SELECT m.id, m.parent_id, m.name, m.path, m.modify_time
            FROM {table} m
            JOIN nodes n ON n.path = m.path
            WHERE m.path LIKE ? AND n.type=2
            ORDER BY RANDOM() LIMIT ?""",
        (prefix + '%', limit),
    ).fetchall()
    return [
        {
            'id': r[0], 'parent_id': r[1], 'name': r[2],
            'path': r[3], 'modify_time': r[4],
        }
        for r in rows
    ]


# ── 封面读写 ─────────────────────────────────────────────


def get_cover(conn, table, path):
    """查询某个文件的 cover BLOB，返回 bytes 或 None"""
    cursor = conn.execute(
        f"SELECT cover FROM {table} WHERE path=?", (path,)
    )
    row = cursor.fetchone()
    return row[0] if row and row[0] else None


def set_cover(conn, table, path, cover_data):
    """写入 cover BLOB"""
    conn.execute(
        f"UPDATE {table} SET cover=? WHERE path=?", (cover_data, path)
    )
    conn.commit()


def generate_and_cache_cover(conn, table, filepath):
    """生成缩略图 → 写入 DB → 返回 JPEG bytes

    如果 DB 中已有 cover 则直接返回，不重复生成。
    table: 'images' | 'videos'
    返回 (jpeg_bytes, mime_type) 或 (None, None)
    """
    # 查缓存
    cover = get_cover(conn, table, filepath)
    if cover:
        return cover, 'image/jpeg'

    ext = os.path.splitext(filepath)[1].lower()
    is_image = ext in config.IMAGE_EXT
    is_video = ext in config.VIDEO_EXT

    if not is_image and not is_video:
        return None, None

    try:
        from PIL import Image as PilImage
    except ImportError:
        PilImage = None

    if PilImage is None:
        return None, None

    img = None
    try:
        if is_image:
            try:
                im = PilImage.open(filepath)
                im.thumbnail(config.THUMBNAIL_SIZE, PilImage.Resampling.LANCZOS)
                img = im
            except Exception:
                return None, None
        elif is_video:
            try:
                import cv2
                cap = cv2.VideoCapture(filepath)
                if not cap.isOpened():
                    return None, None
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                mid_frame = total_frames // 2 if total_frames > 0 else 0
                cap.set(cv2.CAP_PROP_POS_FRAMES, mid_frame)
                ret, frame = cap.read()
                cap.release()
                if not ret:
                    return None, None
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                im = PilImage.fromarray(frame_rgb)
                im.thumbnail(config.THUMBNAIL_SIZE, PilImage.Resampling.LANCZOS)
                img = im
            except Exception:
                return None, None

        if img is None:
            return None, None

        if img.mode in ('RGBA', 'P'):
            bg = PilImage.new('RGB', img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = bg

        buf = BytesIO()
        img.save(buf, format='JPEG', quality=70)
        jpeg_bytes = buf.getvalue()

        # 确保行存在并写入 cover
        conn.execute(
            f"""INSERT INTO {table} (parent_id, name, path, modify_time, cover)
                VALUES (0, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET cover=excluded.cover""",
            (os.path.basename(filepath), filepath, os.path.getmtime(filepath), jpeg_bytes),
        )
        conn.commit()
        return jpeg_bytes, 'image/jpeg'

    except Exception:
        return None, None


def sync_folder(conn, folder_path, run_mode='normal', recursive=False, _depth=0):
    """增量同步单个文件夹（仅 scandir 1 层），可选递归同步子文件夹

    当 recursive=True 时递归同步所有后代子文件夹，_depth 用于限制递归深度。
    """
    if _depth > 50:
        return
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

    # 递归同步子文件夹
    if recursive:
        cursor = conn.execute(
            "SELECT path FROM nodes WHERE parent_id=? AND type=1", (folder_id,)
        )
        for row in cursor.fetchall():
            sync_folder(conn, row[0], run_mode=run_mode, recursive=True, _depth=_depth + 1)

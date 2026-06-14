"""数据库连接、表创建、全量/增量同步、封面缓存与查询接口

Schema:
    nodes — 完整文件系统目录树
    media — 媒体文件（含 cover BLOB + media_type 区分 video/image）
"""
import os
import time
import sqlite3
from io import BytesIO

from config import config
from utils.logging_utils import logger

# ---------------------------------------------------------------------------
# 封面生成可选依赖
# ---------------------------------------------------------------------------
try:
    from PIL import Image as PilImage
    try:
        _LANCZOS = PilImage.Resampling.LANCZOS
    except AttributeError:
        _LANCZOS = PilImage.LANCZOS
    HAS_PIL = True
except ImportError:
    PilImage = None
    HAS_PIL = False

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    cv2 = None
    HAS_CV2 = False

# ---------------------------------------------------------------------------
# 连接工厂
# ---------------------------------------------------------------------------


def get_db(db_path=None):
    """创建数据库连接，启用 WAL + Row 工厂"""
    path = db_path or config.DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.isolation_level = None
    return conn


# ---------------------------------------------------------------------------
# 表初始化
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS nodes (
    id           INTEGER PRIMARY KEY,
    parent_id    INTEGER NOT NULL DEFAULT 0,
    name         TEXT    NOT NULL,
    type         INTEGER NOT NULL,          -- 1=目录 2=文件
    path         TEXT    NOT NULL UNIQUE,
    size         INTEGER NOT NULL DEFAULT 0,
    extension    TEXT    DEFAULT NULL,
    modify_time  REAL    NOT NULL,
    is_hidden    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS media (
    id           INTEGER PRIMARY KEY,
    parent_id    INTEGER NOT NULL DEFAULT 0,
    name         TEXT    NOT NULL,
    media_type   TEXT    NOT NULL,          -- 'video' | 'image'
    path         TEXT    NOT NULL UNIQUE,
    modify_time  REAL    NOT NULL,
    cover        BLOB    DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id);
CREATE INDEX IF NOT EXISTS idx_nodes_path  ON nodes(path);
CREATE INDEX IF NOT EXISTS idx_media_path  ON media(path);
CREATE INDEX IF NOT EXISTS idx_media_type  ON media(media_type);
"""


def init_tables(conn):
    """创建 nodes + media 表及索引（幂等）"""
    conn.executescript(_SCHEMA_SQL)
    conn.commit()


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

_FILE_ATTRIBUTE_HIDDEN = 2


def _get_hidden_flag(entry_name, stat_info):
    if entry_name.startswith('.'):
        return 1
    attrs = getattr(stat_info, 'st_file_attributes', 0)
    return 1 if (attrs & _FILE_ATTRIBUTE_HIDDEN) else 0


def _collect_fs_node(entry, parent_path):
    """从 DirEntry 收集文件/目录元信息，失败返回 None"""
    try:
        st = entry.stat()
        name = entry.name
        is_dir = entry.is_dir()
        ext = None
        if not is_dir:
            raw = os.path.splitext(name)[1].lower()
            if raw:
                ext = raw[1:]  # 去掉点号
        return {
            'name': name,
            'type': 1 if is_dir else 2,
            'path': entry.path,
            'size': 0 if is_dir else st.st_size,
            'extension': ext,
            'parent_path': parent_path,
            'modify_time': st.st_mtime,
            'is_hidden': _get_hidden_flag(name, st),
        }
    except OSError:
        return None


# -- 封面生成 ----------------------------------------------------------------


def _generate_image_cover(filepath):
    if not HAS_PIL:
        return None
    try:
        im = PilImage.open(filepath)
        im.thumbnail((300, 300), _LANCZOS)
        if im.mode in ('RGBA', 'P'):
            bg = PilImage.new('RGB', im.size, (255, 255, 255))
            mask = im.split()[-1] if im.mode == 'RGBA' else None
            bg.paste(im, mask=mask)
            im = bg
        elif im.mode != 'RGB':
            im = im.convert('RGB')
        buf = BytesIO()
        im.save(buf, format='JPEG', quality=60)
        return buf.getvalue()
    except Exception:
        return None


def _generate_video_cover(filepath):
    if not HAS_CV2:
        return None
    try:
        cap = cv2.VideoCapture(filepath)
        if not cap.isOpened():
            return None
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        mid = max(0, total // 2) if total > 0 else 0
        cap.set(cv2.CAP_PROP_POS_FRAMES, mid)
        ok, frame = cap.read()
        cap.release()
        if not ok or not HAS_PIL:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        im = PilImage.fromarray(rgb)
        im.thumbnail((300, 300), _LANCZOS)
        buf = BytesIO()
        im.save(buf, format='JPEG', quality=60)
        return buf.getvalue()
    except Exception:
        return None


def _media_type_from_ext(ext):
    """根据扩展名返回 'video' | 'image' | None"""
    if ext in config.VIDEO_EXT:
        return 'video'
    if ext in config.IMAGE_EXT:
        return 'image'
    return None


# ---------------------------------------------------------------------------
# 全量同步 — staging table + SQL diff
# ---------------------------------------------------------------------------

_STAGING_DDL = """
CREATE TEMP TABLE staging (
    path         TEXT PRIMARY KEY,
    parent_path  TEXT,
    name         TEXT,
    type         INTEGER,
    size         INTEGER,
    extension    TEXT,
    modify_time  REAL,
    is_hidden    INTEGER
)
"""


def sync_database(conn, root_path):
    """全量 scandir → staging → 3-way diff → 写入 nodes

    返回 (added, removed, updated) 计数，失败返回 None
    """
    root_path = os.path.abspath(str(root_path))
    if not os.path.isdir(root_path):
        logger.debug(f"sync_database: 目录不存在 {root_path}")
        return None

    init_tables(conn)
    cursor = conn.cursor()
    t0 = time.time()

    # -- Step 1: staging 表 --
    cursor.execute("DROP TABLE IF EXISTS staging")
    cursor.execute(_STAGING_DDL)

    # 根节点
    root_st = os.stat(root_path)
    root_name = os.path.basename(root_path) or root_path
    root_hidden = _get_hidden_flag(root_name, root_st)
    cursor.execute(
        "INSERT INTO staging (path, parent_path, name, type, size, extension, "
        "modify_time, is_hidden) VALUES (?, '', ?, 1, 0, NULL, ?, ?)",
        (root_path, root_name, root_st.st_mtime, root_hidden),
    )
    scanned = 1

    # DFS 遍历，分批提交 staging
    conn.execute("BEGIN")
    stack = [root_path]
    batch = 0
    while stack:
        dirpath = stack.pop()
        try:
            with os.scandir(dirpath) as it:
                for entry in it:
                    node = _collect_fs_node(entry, dirpath)
                    if node is None:
                        continue
                    cursor.execute(
                        "INSERT INTO staging (path, parent_path, name, type, "
                        "size, extension, modify_time, is_hidden) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (node['path'], node['parent_path'], node['name'],
                         node['type'], node['size'], node['extension'],
                         node['modify_time'], node['is_hidden']),
                    )
                    scanned += 1
                    if node['type'] == 1:
                        stack.append(entry.path)
                    batch += 1
                    if batch >= 50000:
                        conn.commit(); conn.execute("BEGIN")
                        batch = 0
        except (PermissionError, OSError):
            continue
    if batch > 0:
        conn.commit()

    logger.debug(f"sync_database: 扫描完成 {scanned} 节点 ({time.time() - t0:.1f}s)")

    # -- Step 2: 计算差异 --
    to_add = cursor.execute(
        "SELECT COUNT(*) FROM staging WHERE path NOT IN (SELECT path FROM nodes)"
    ).fetchone()[0]
    to_remove = cursor.execute(
        "SELECT COUNT(*) FROM nodes WHERE path NOT IN (SELECT path FROM staging)"
    ).fetchone()[0]
    to_update = cursor.execute(
        "SELECT COUNT(*) FROM staging JOIN nodes USING(path) "
        "WHERE staging.modify_time != nodes.modify_time"
    ).fetchone()[0]

    if to_add == 0 and to_remove == 0 and to_update == 0:
        cursor.execute("DROP TABLE IF EXISTS staging")
        logger.debug(f"sync_database: 无变化 ({time.time() - t0:.1f}s)")
        return 0, 0, 0

    logger.debug(f"sync_database: +{to_add}/-{to_remove}/~{to_update}")

    # -- Step 3: 执行同步 --
    conn.execute("BEGIN")
    try:
        # 删除 media 中对应行
        cursor.execute(
            "DELETE FROM media WHERE path IN ("
            "  SELECT path FROM nodes WHERE path NOT IN (SELECT path FROM staging)"
            ")"
        )
        # 删除节点（按路径深度降序，先删子节点）
        cursor.execute(
            "DELETE FROM nodes WHERE path IN ("
            "  SELECT path FROM nodes WHERE path NOT IN (SELECT path FROM staging)"
            "  ORDER BY (LENGTH(path) - LENGTH(REPLACE(path, '\\', ''))) DESC"
            ")"
        )
        # 新增节点
        cursor.execute(
            "INSERT INTO nodes (parent_id, name, type, path, size, extension, "
            "modify_time, is_hidden) "
            "SELECT 0, s.name, s.type, s.path, s.size, s.extension, "
            "s.modify_time, s.is_hidden "
            "FROM staging s WHERE s.path NOT IN (SELECT path FROM nodes)"
        )
        # 修正 parent_id
        cursor.execute(
            "UPDATE nodes SET parent_id = ("
            "  SELECT COALESCE(p.id, 0) FROM staging s "
            "  JOIN nodes p ON p.path = s.parent_path "
            "  WHERE s.path = nodes.path"
            ") WHERE path IN (SELECT path FROM staging WHERE parent_path != '')"
        )
        # 更新已变化的节点
        cursor.execute(
            "UPDATE nodes SET size = s.size, modify_time = s.modify_time, "
            "is_hidden = s.is_hidden "
            "FROM staging s "
            "WHERE nodes.path = s.path AND nodes.modify_time != s.modify_time"
        )
        conn.commit()
    except Exception:
        conn.rollback()
        cursor.execute("DROP TABLE IF EXISTS staging")
        raise
    finally:
        cursor.execute("DROP TABLE IF EXISTS staging")

    logger.debug(f"sync_database: 同步完成 ({time.time() - t0:.1f}s)")
    return to_add, to_remove, to_update


# ---------------------------------------------------------------------------
# 增量同步 — 单文件夹
# ---------------------------------------------------------------------------


def _cascade_delete_node(conn, node_id):
    """递归删除节点及其所有子节点（含 media 记录）"""
    children = conn.execute(
        "SELECT id, type, path FROM nodes WHERE parent_id=?", (node_id,)
    ).fetchall()
    for child in children:
        _cascade_delete_node(conn, child['id'])
    conn.execute("DELETE FROM media WHERE path = (SELECT path FROM nodes WHERE id=?)", (node_id,))
    conn.execute("DELETE FROM nodes WHERE id=?", (node_id,))


def _ensure_node(conn, folder_path):
    """确保 folder_path 在 nodes 中存在（惰性创建祖先链），返回其 id"""
    folder_path = os.path.abspath(folder_path)
    row = conn.execute(
        "SELECT id FROM nodes WHERE path=? AND type=1", (folder_path,)
    ).fetchone()
    if row:
        return row[0]

    parent_path = os.path.dirname(folder_path)
    parent_id = 0
    if parent_path and parent_path != folder_path:
        parent_id = _ensure_node(conn, parent_path)

    name = os.path.basename(folder_path) or folder_path
    try:
        st = os.stat(folder_path)
        mtime = st.st_mtime
        hidden = _get_hidden_flag(name, st)
    except OSError:
        mtime = time.time()
        hidden = 0

    cur = conn.execute(
        "INSERT INTO nodes (parent_id, name, type, path, size, extension, "
        "modify_time, is_hidden) VALUES (?, ?, 1, ?, 0, NULL, ?, ?)",
        (parent_id, name, folder_path, mtime, hidden),
    )
    return cur.lastrowid


def _upsert_media(conn, parent_id, entry, mtime, is_dir):
    """将一条文件系统条目写入 media 表（若为媒体文件）"""
    if is_dir:
        return
    ext = os.path.splitext(entry.name)[1].lower()
    media_type = _media_type_from_ext(ext)
    if media_type is None:
        return

    entry_path = entry.path
    existing = conn.execute(
        "SELECT id FROM media WHERE path=?", (entry_path,)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE media SET parent_id=?, name=?, modify_time=? WHERE id=?",
            (parent_id, entry.name, mtime, existing[0]),
        )
    else:
        conn.execute(
            "INSERT INTO media (parent_id, name, media_type, path, modify_time, cover) "
            "VALUES (?, ?, ?, ?, ?, NULL)",
            (parent_id, entry.name, media_type, entry_path, mtime),
        )


def sync_folder(conn, folder_path, run_mode=None, recursive=False, _depth=0):
    """增量同步单个文件夹（1 层 scandir），可选递归子文件夹

    自动维护 nodes + media 两张表。
    """
    if _depth > 50:
        return
    init_tables(conn)
    folder_path = os.path.abspath(folder_path)
    folder_id = _ensure_node(conn, folder_path)

    # 收集 DB 现有子项 {path: {col: value}}
    db_children = {}
    for row in conn.execute(
        "SELECT id, name, path, modify_time, type, extension, size, is_hidden "
        "FROM nodes WHERE parent_id=?", (folder_id,)
    ).fetchall():
        db_children[row['path']] = {
            'id': row['id'], 'name': row['name'],
            'modify_time': row['modify_time'], 'type': row['type'],
            'extension': row['extension'], 'size': row['size'],
            'is_hidden': row['is_hidden'],
        }

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
            st = entry.stat(follow_symlinks=False)
        except OSError:
            continue

        fs_type = 1 if is_dir else 2
        fs_size = st.st_size if is_file else 0
        fs_ext = os.path.splitext(entry.name)[1].lower() if is_file else None
        fs_mtime = st.st_mtime
        fs_hidden = _get_hidden_flag(entry.name, st)

        if entry_path in db_children:
            db_row = db_children.pop(entry_path)
            if (abs(db_row['modify_time'] - fs_mtime) > 0.001
                    or db_row['size'] != fs_size
                    or db_row['type'] != fs_type
                    or (db_row['extension'] or '') != (fs_ext or '')
                    or db_row['is_hidden'] != fs_hidden):
                conn.execute(
                    "UPDATE nodes SET size=?, extension=?, modify_time=?, "
                    "type=?, is_hidden=? WHERE id=?",
                    (fs_size, fs_ext, fs_mtime, fs_type, fs_hidden, db_row['id']),
                )
                _upsert_media(conn, folder_id, entry, fs_mtime, is_dir)
        else:
            existing = conn.execute(
                "SELECT id FROM nodes WHERE path=?", (entry_path,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE nodes SET parent_id=?, name=?, type=?, size=?, "
                    "extension=?, modify_time=?, is_hidden=? WHERE id=?",
                    (folder_id, entry.name, fs_type, fs_size, fs_ext,
                     fs_mtime, fs_hidden, existing[0]),
                )
            else:
                conn.execute(
                    "INSERT INTO nodes (parent_id, name, type, path, size, "
                    "extension, modify_time, is_hidden) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (folder_id, entry.name, fs_type, entry_path, fs_size,
                     fs_ext, fs_mtime, fs_hidden),
                )
            _upsert_media(conn, folder_id, entry, fs_mtime, is_dir)

    # 删除文件系统中不存在的条目（含级联删除子节点和媒体记录）
    for path in db_children:
        row_id = db_children[path]['id']
        _cascade_delete_node(conn, row_id)

    conn.commit()

    if recursive:
        for row in conn.execute(
            "SELECT path FROM nodes WHERE parent_id=? AND type=1", (folder_id,)
        ).fetchall():
            sync_folder(conn, row['path'], run_mode=run_mode, recursive=True,
                       _depth=_depth + 1)


# ---------------------------------------------------------------------------
# 批量封面同步
# ---------------------------------------------------------------------------


def sync_media_covers(conn, run_mode=None):
    """将 nodes 中媒体文件同步到 media 表并生成封面

    对新增/修改的文件生成 cover BLOB，删除已不存在的媒体行。
    返回 (generated_count, cover_total_bytes)
    """
    init_tables(conn)
    cursor = conn.cursor()

    # 收集 nodes 中的所有媒体文件
    all_exts = sorted(
        ext[1:] for ext in config.VIDEO_EXT | config.IMAGE_EXT
    )
    placeholders = ','.join('?' for _ in all_exts)
    node_rows = cursor.execute(
        f"SELECT id, parent_id, name, path, modify_time, extension "
        f"FROM nodes WHERE type=2 AND extension IN ({placeholders})",
        all_exts,
    ).fetchall()

    if not node_rows:
        cursor.execute("DELETE FROM media")
        conn.commit()
        return 0, 0

    fs_nodes = {}
    for r in node_rows:
        fs_nodes[r['path']] = {
            'node_id': r['id'], 'parent_id': r['parent_id'],
            'name': r['name'], 'extension': r['extension'],
            'modify_time': r['modify_time'],
        }

    existing = {
        r['path']: r['modify_time']
        for r in cursor.execute("SELECT path, modify_time FROM media").fetchall()
    }

    to_add = set(fs_nodes) - set(existing)
    to_remove = set(existing) - set(fs_nodes)
    to_update = [
        p for p in (set(fs_nodes) & set(existing))
        if fs_nodes[p]['modify_time'] != existing[p]
    ]

    for p in sorted(to_remove, key=lambda x: x.count(os.sep), reverse=True):
        cursor.execute("DELETE FROM media WHERE path=?", (p,))
    if to_remove:
        conn.commit()

    total_work = len(to_add) + len(to_update)
    if total_work == 0:
        return 0, 0

    generated = 0
    conn.execute("BEGIN")
    try:
        for fp in sorted(to_add):
            info = fs_nodes[fp]
            ext = '.' + info['extension'].lower()
            cover = None
            if ext in config.VIDEO_EXT:
                cover = _generate_video_cover(fp)
                generated += 1
            elif ext in config.IMAGE_EXT:
                cover = _generate_image_cover(fp)
                generated += 1

            media_type = _media_type_from_ext(ext)
            if media_type:
                cursor.execute(
                    "INSERT OR IGNORE INTO media "
                    "(parent_id, name, media_type, path, modify_time, cover) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (info['parent_id'], info['name'], media_type, fp,
                     info['modify_time'], cover),
                )

        for fp in to_update:
            info = fs_nodes[fp]
            ext = '.' + info['extension'].lower()
            cover = None
            if ext in config.VIDEO_EXT:
                cover = _generate_video_cover(fp)
                generated += 1
            elif ext in config.IMAGE_EXT:
                cover = _generate_image_cover(fp)
                generated += 1

            conn.execute(
                "UPDATE media SET parent_id=?, name=?, modify_time=?, cover=? "
                "WHERE path=?",
                (info['parent_id'], info['name'], info['modify_time'], cover, fp),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    cover_bytes = 0
    row = cursor.execute(
        "SELECT SUM(LENGTH(cover)) FROM media WHERE cover IS NOT NULL"
    ).fetchone()
    if row and row[0]:
        cover_bytes = row[0]

    return generated, cover_bytes


# ---------------------------------------------------------------------------
# 查询接口
# ---------------------------------------------------------------------------


def get_children(conn, parent_id, sort_type='name', sort_order='asc'):
    """获取某文件夹的直接子项，文件夹在前"""
    order_col = 'modify_time' if sort_type == 'time' else 'name'
    order_dir = 'DESC' if sort_order == 'desc' else 'ASC'
    rows = conn.execute(
        f"SELECT id, parent_id, name, type, path, size, extension, "
        f"modify_time, is_hidden FROM nodes WHERE parent_id=? "
        f"ORDER BY type ASC, {order_col} {order_dir}",
        (parent_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_media_page(conn, media_type, limit, offset,
                   sort_type='name', sort_order='asc', media_dir=None):
    """分页取媒体文件

    media_type: 'video' | 'image'
    返回 (rows, total_count)
    """
    where = "m.media_type = ? AND n.type = 2"
    params = [media_type]
    if media_dir:
        media_prefix = os.path.abspath(str(media_dir)) + os.sep
        where += " AND m.path LIKE ?"
        params.append(media_prefix + '%')

    total = conn.execute(
        f"SELECT COUNT(*) FROM media m JOIN nodes n ON n.path = m.path "
        f"WHERE {where}", params,
    ).fetchone()[0]

    order_col = 'm.modify_time' if sort_type == 'time' else 'm.name'
    order_dir = 'DESC' if sort_order == 'desc' else 'ASC'

    rows = conn.execute(
        f"SELECT m.id, m.parent_id, m.name, m.path, m.modify_time, m.media_type "
        f"FROM media m JOIN nodes n ON n.path = m.path "
        f"WHERE {where} ORDER BY {order_col} {order_dir} "
        f"LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()

    return [dict(r) for r in rows], total


def get_random_media(conn, media_type, limit, exclude_paths=None, media_dir=None):
    """随机取 N 条媒体文件，可排除指定路径

    返回 list[dict] — id/parent_id/name/path/modify_time/media_type
    """
    where = "m.media_type = ? AND n.type = 2"
    params = [media_type]
    if media_dir:
        media_prefix = os.path.abspath(str(media_dir)) + os.sep
        where += " AND m.path LIKE ?"
        params.append(media_prefix + '%')

    if exclude_paths:
        ph = ','.join('?' for _ in exclude_paths)
        where += f" AND m.path NOT IN ({ph})"
        params += exclude_paths

    rows = conn.execute(
        f"SELECT m.id, m.parent_id, m.name, m.path, m.modify_time, m.media_type "
        f"FROM media m JOIN nodes n ON n.path = m.path "
        f"WHERE {where} ORDER BY RANDOM() LIMIT ?",
        params + [limit],
    ).fetchall()
    return [dict(r) for r in rows]


def get_media_in_folder(conn, media_type, folder_path, limit, offset,
                         sort_type='name', sort_order='asc'):
    """获取文件夹（递归子文件夹）中的媒体文件，分页

    返回 (rows, total_count)
    """
    norm = os.path.normpath(folder_path)
    prefix = norm + os.sep
    order_col = 'm.modify_time' if sort_type == 'time' else 'm.name'
    order_dir = 'DESC' if sort_order == 'desc' else 'ASC'

    params = [media_type, prefix + '%']

    total = conn.execute(
        "SELECT COUNT(*) FROM media m JOIN nodes n ON n.path = m.path "
        "WHERE m.media_type = ? AND m.path LIKE ? AND n.type = 2",
        params,
    ).fetchone()[0]

    rows = conn.execute(
        f"SELECT m.id, m.parent_id, m.name, m.path, m.modify_time, m.media_type "
        f"FROM media m JOIN nodes n ON n.path = m.path "
        f"WHERE m.media_type = ? AND m.path LIKE ? AND n.type = 2 "
        f"ORDER BY {order_col} {order_dir} LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()

    return [dict(r) for r in rows], total


def get_random_media_in_folder(conn, media_type, folder_path, limit):
    """从文件夹（递归子文件夹）中随机取媒体文件"""
    norm = os.path.normpath(folder_path)
    prefix = norm + os.sep
    rows = conn.execute(
        "SELECT m.id, m.parent_id, m.name, m.path, m.modify_time, m.media_type "
        "FROM media m JOIN nodes n ON n.path = m.path "
        "WHERE m.media_type = ? AND m.path LIKE ? AND n.type = 2 "
        "ORDER BY RANDOM() LIMIT ?",
        (media_type, prefix + '%', limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_node_by_path(conn, path):
    """按路径查 nodes，返回 dict 或 None"""
    row = conn.execute(
        "SELECT id, parent_id, name, type, path FROM nodes WHERE path=?", (path,)
    ).fetchone()
    return dict(row) if row else None


def get_subfolder_nodes(conn, parent_id, sort_type='name', sort_order='asc'):
    """获取某个节点的直接子文件夹"""
    order_col = 'modify_time' if sort_type == 'time' else 'name'
    order_dir = 'DESC' if sort_order == 'desc' else 'ASC'
    rows = conn.execute(
        f"SELECT id, name, path FROM nodes "
        f"WHERE parent_id=? AND type=1 ORDER BY {order_col} {order_dir}",
        (parent_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_direct_media(conn, parent_id, media_type, sort_type='name',
                     sort_order='asc', limit=None, offset=0):
    """查询某个文件夹的直接子媒体文件（不递归子文件夹）

    用 m.parent_id = ? 精确匹配，仅返回直接子文件。
    返回 (rows, total_count)
    """
    order_col = 'm.modify_time' if sort_type == 'time' else 'm.name'
    order_dir = 'DESC' if sort_order == 'desc' else 'ASC'

    params = [media_type, parent_id]

    total = conn.execute(
        "SELECT COUNT(*) FROM media m JOIN nodes n ON n.path = m.path "
        "WHERE m.media_type = ? AND m.parent_id = ? AND n.type = 2",
        params,
    ).fetchone()[0]

    query = (
        f"SELECT m.id, m.parent_id, m.name, m.path, m.modify_time, m.media_type "
        f"FROM media m JOIN nodes n ON n.path = m.path "
        f"WHERE m.media_type = ? AND m.parent_id = ? AND n.type = 2 "
        f"ORDER BY {order_col} {order_dir}"
    )
    if limit is not None:
        query += f" LIMIT ? OFFSET ?"
        params += [limit, offset]
    rows = conn.execute(query, params).fetchall()

    return [dict(r) for r in rows], total


# ---------------------------------------------------------------------------
# 封面读写
# ---------------------------------------------------------------------------


def get_cover(conn, path):
    """读取 cover BLOB，返回 bytes 或 None"""
    row = conn.execute("SELECT cover FROM media WHERE path=?", (path,)).fetchone()
    return row[0] if row and row[0] else None


def set_cover(conn, path, cover_data):
    """写入 cover BLOB"""
    conn.execute("UPDATE media SET cover=? WHERE path=?", (cover_data, path))
    conn.commit()


def generate_and_cache_cover(conn, path):
    """生成缩略图 → 写入 media.cover → 返回 (jpeg_bytes, mime_type)

    若已有 cover 则直接返回。
    """
    cover = get_cover(conn, path)
    if cover:
        return cover, 'image/jpeg'

    ext = os.path.splitext(path)[1].lower()
    if ext in config.VIDEO_EXT:
        jpeg = _generate_video_cover(path)
    elif ext in config.IMAGE_EXT:
        jpeg = _generate_image_cover(path)
    else:
        return None, None

    if not jpeg:
        return None, None

    media_type = _media_type_from_ext(ext)
    if media_type:
        conn.execute(
            "INSERT INTO media (parent_id, name, media_type, path, modify_time, cover) "
            "VALUES (0, ?, ?, ?, ?, ?) "
            "ON CONFLICT(path) DO UPDATE SET cover=excluded.cover",
            (os.path.basename(path), media_type, path, os.path.getmtime(path), jpeg),
        )
        conn.commit()

    return jpeg, 'image/jpeg'

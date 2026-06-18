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
    conn.execute("PRAGMA busy_timeout=5000")
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

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY,
    password_hash   TEXT    NOT NULL,
    salt            TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id);
CREATE INDEX IF NOT EXISTS idx_nodes_path  ON nodes(path);
CREATE INDEX IF NOT EXISTS idx_media_path        ON media(path);
CREATE INDEX IF NOT EXISTS idx_media_type        ON media(media_type);
CREATE INDEX IF NOT EXISTS idx_media_parent_type ON media(parent_id, media_type);
"""


def _default_password_hash():
    """生成默认密码 '123456' 的哈希值（固定盐）"""
    import hashlib
    default_salt = 'laptopwatch_v1'
    return (
        hashlib.sha256(('123456' + default_salt).encode('utf-8')).hexdigest(),
        default_salt,
    )


def seed_default_user(conn):
    """如果 users 表为空，插入默认密码哈希"""
    existing = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
    if existing:
        return
    pwd_hash, salt = _default_password_hash()
    now = time.strftime('%Y-%m-%d %H:%M:%S')
    conn.execute(
        "INSERT INTO users (id, password_hash, salt, updated_at) VALUES (1, ?, ?, ?)",
        (pwd_hash, salt, now),
    )
    conn.commit()


def init_tables(conn):
    """创建 nodes + media + users 表及索引（幂等），种子默认用户"""
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    seed_default_user(conn)


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

_FILE_ATTRIBUTE_HIDDEN = 2


def _get_hidden_flag(entry_name, stat_info):
    if entry_name.startswith('.'):
        return 1
    attrs = getattr(stat_info, 'st_file_attributes', 0)
    return 1 if (attrs & _FILE_ATTRIBUTE_HIDDEN) else 0


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
    """将一条文件系统条目写入 media 表（若为媒体文件），返回是否写入

    扩展名不再属于媒体类型时，清理可能存在的过期 media 记录。
    """
    if is_dir:
        return False
    ext = os.path.splitext(entry.name)[1].lower()
    media_type = _media_type_from_ext(ext)
    if media_type is None:
        conn.execute("DELETE FROM media WHERE path=?", (entry.path,))
        return False

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
    return True


def sync_folder(conn, folder_path, run_mode=None, recursive=False, _depth=0):
    """增量同步单个文件夹（1 层 scandir），可选递归子文件夹

    自动维护 nodes + media 两张表。
    """
    if _depth > 50:
        return
    init_tables(conn)
    folder_path = os.path.abspath(folder_path)
    folder_id = _ensure_node(conn, folder_path)

    added = 0
    updated = 0
    deleted = 0
    media_count = 0

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
                updated += 1
                if _upsert_media(conn, folder_id, entry, fs_mtime, is_dir):
                    media_count += 1
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
                updated += 1
            else:
                conn.execute(
                    "INSERT INTO nodes (parent_id, name, type, path, size, "
                    "extension, modify_time, is_hidden) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (folder_id, entry.name, fs_type, entry_path, fs_size,
                     fs_ext, fs_mtime, fs_hidden),
                )
                added += 1
            if _upsert_media(conn, folder_id, entry, fs_mtime, is_dir):
                media_count += 1

    # 删除文件系统中不存在的条目（含级联删除子节点和媒体记录）
    for _path in db_children:
        row_id = db_children[_path]['id']
        _cascade_delete_node(conn, row_id)
        deleted += 1

    conn.commit()

    if added or updated or deleted:
        logger.debug(
            "sync_folder: %s → +%d ~%d -%d media:%d recursive:%s depth:%d",
            folder_path, added, updated, deleted, media_count,
            recursive, _depth,
        )

    if recursive:
        for row in conn.execute(
            "SELECT path FROM nodes WHERE parent_id=? AND type=1", (folder_id,)
        ).fetchall():
            sync_folder(conn, row['path'], run_mode=run_mode, recursive=True,
                       _depth=_depth + 1)


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
        media_prefix = os.path.abspath(str(media_dir)).rstrip(os.sep) + os.sep
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
        media_prefix = os.path.abspath(str(media_dir)).rstrip(os.sep) + os.sep
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
# 文件夹遍历器 — 按需核实 + 逐文件夹收集
# ---------------------------------------------------------------------------


def _format_media_row(row):
    """将 media 表行格式化为前端统一结构"""
    import os as _os
    media_dir_str = str(config.MEDIA_DIR).replace('\\', '/') + '/'
    path = row['path'].replace('\\', '/')
    rel_path = path.replace(media_dir_str, '', 1) if media_dir_str else row['name']
    ext = _os.path.splitext(row['name'])[1].lower()
    from datetime import datetime
    return {
        'name': row['name'],
        'path': row['path'],
        'relative_path': rel_path,
        'mtime': datetime.fromtimestamp(row['modify_time']).strftime('%Y-%m-%d %H:%M:%S'),
        'timestamp': row['modify_time'],
        'is_video': ext in config.VIDEO_EXT,
        'is_image': ext in config.IMAGE_EXT,
        'media_type': row['media_type'],
    }


def traverse_media(conn, root_path, media_type, offset=0, limit=36,
                   sort_type='name', sort_order='asc',
                   random_start=False, exclude_paths=None):
    """文件夹遍历器：用到才核实，动态队列，逐文件夹收集

    - 只 sync_folder(root) 一层以发现直接子文件夹
    - 遍历队列动态推进，处理到哪个文件夹才 sync 哪个
    - 处理中发现的子文件夹追加到队尾，深层嵌套自然处理
    - 返回 (items, next_offset, has_more)
    """
    init_tables(conn)
    root_path = os.path.abspath(root_path)
    root_id = _ensure_node(conn, root_path)

    # 同步根目录（1 层）以发现直接子文件夹
    sync_folder(conn, root_path)

    # 从 DB 取根目录的直接子文件夹，构建初始队列
    subdirs = get_subfolder_nodes(conn, root_id, sort_type, sort_order)
    if random_start and subdirs:
        import random as _random
        start_idx = _random.randint(0, len(subdirs) - 1)
        subdirs = subdirs[start_idx:] + subdirs[:start_idx]

    # 动态遍历队列
    queue = [(root_id, root_path)]
    queue.extend((f['id'], f['path']) for f in subdirs)

    logger.debug(
        "traverse_media: root=%s type=%s offset=%d limit=%d init_folders=%d exclude=%d",
        root_path, media_type, offset, limit, len(subdirs),
        len(exclude_paths) if exclude_paths else 0,
    )

    collected = []
    skipped = 0
    has_more = False
    exclude_set = set(exclude_paths) if exclude_paths else set()

    queue_idx = 0
    while queue_idx < len(queue) and len(collected) < limit:
        seg_id, seg_path = queue[queue_idx]
        queue_idx += 1

        # 用到才核实：根目录已在上方同步，子文件夹遍历到才 sync
        if queue_idx > 1:
            sync_folder(conn, seg_path)
            # 发现新的子文件夹，追加到队尾
            new_subs = get_subfolder_nodes(conn, seg_id, sort_type, sort_order)
            for ns in new_subs:
                queue.append((ns['id'], ns['path']))

        # 获取当前文件夹的直接媒体文件数
        seg_total = conn.execute(
            "SELECT COUNT(*) FROM media WHERE parent_id=? AND media_type=?",
            (seg_id, media_type),
        ).fetchone()[0]
        if seg_total == 0:
            continue

        if skipped + seg_total <= offset:
            skipped += seg_total
            continue

        # offset 落在当前段内 — 取文件（翻页处理 exclude 过滤）
        seg_offset = max(0, offset - skipped)

        while len(collected) < limit and seg_offset < seg_total:
            rows, _ = get_direct_media(
                conn, seg_id, media_type, sort_type, sort_order,
                limit=limit - len(collected), offset=seg_offset,
            )
            fetched_count = len(rows)
            if not rows:
                break
            if exclude_set:
                rows = [r for r in rows if r['path'] not in exclude_set]
            for r in rows:
                if len(collected) >= limit:
                    break
                collected.append(_format_media_row(r))
            seg_offset += fetched_count

        skipped += seg_total
        if len(collected) >= limit:
            has_more = (seg_offset < seg_total or queue_idx < len(queue))
            break

    next_offset = offset + len(collected)
    logger.debug(
        "traverse_media: 返回 %d 条 has_more=%s next_offset=%d scanned=%d",
        len(collected), has_more, next_offset, queue_idx,
    )
    return collected, next_offset, has_more


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

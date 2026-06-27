"""
媒体处理工具函数
"""
import os
import time
import threading
from pathlib import Path
from datetime import datetime
from config import config
from utils.logging_utils import logger


def get_files_in_folder(folder_path):
    """获取文件夹内的直接媒体文件列表（DB 查询，无缓存）"""
    if config.RUN_MODE not in ['video', 'image', 'douyin'] or not config.MEDIA_DIR:
        return []

    media_type = 'video' if config.RUN_MODE in ('video', 'douyin') else 'image'
    files = []
    try:
        from utils.db_utils import get_db, get_node_by_path, get_direct_media, sync_folder
        conn = get_db()
        sync_folder(conn, str(folder_path))
        media_dir_str = str(config.MEDIA_DIR)
        node = get_node_by_path(conn, str(folder_path))
        if node:
            rows, _ = get_direct_media(
                conn, node['id'], media_type,
                config.SORT_TYPE, config.SORT_ORDER)
            for r in rows:
                rel_path = os.path.relpath(r['path'], media_dir_str)
                files.append({
                    'name': r['name'],
                    'path': r['path'],
                    'rel_path': rel_path,
                    'mtime': r['modify_time'],
                    'size': 0,
                })
        conn.close()
    except Exception as e:
        logger.debug(f"get_files_in_folder DB 查询失败: {e}")
    return files


def _get_sorted_subfolders(folder_path, conn=None):
    """获取排序后的子文件夹列表（DB 查询）"""
    _own_conn = conn is None
    try:
        from utils.db_utils import get_db, get_node_by_path, get_subfolder_nodes
        if _own_conn:
            conn = get_db()
        node = get_node_by_path(conn, str(folder_path))
        if not node:
            return []
        rows = get_subfolder_nodes(conn, node['id'], config.SORT_TYPE, config.SORT_ORDER)
        return [{'path': r['path'], 'name': r['name'], 'mtime': 0} for r in rows]
    except Exception as e:
        logger.debug(f"_get_sorted_subfolders DB 查询失败: {e}")
        return []
    finally:
        if _own_conn and conn:
            conn.close()


def _format_file_item(f):
    """格式化单个文件项"""
    rel_path = f['rel_path']
    relative_path = rel_path.replace('\\', '/')
    if not relative_path or relative_path == '.':
        relative_path = f['name']

    item = {
        'name': f['name'],
        'relative_path': relative_path,
        'mtime': datetime.fromtimestamp(f['mtime']).strftime('%Y-%m-%d %H:%M:%S'),
        'timestamp': f['mtime']
    }

    ext = os.path.splitext(item['name'])[1].lower()
    item['is_video'] = ext in config.VIDEO_EXT
    item['is_image'] = ext in config.IMAGE_EXT

    return item


def _format_db_row(r):
    """将 DB media 行格式化为统一的前端数据格式"""
    media_dir_str = str(config.MEDIA_DIR)
    rel_path = os.path.relpath(r['path'], media_dir_str)
    relative_path = rel_path.replace('\\', '/')
    if not relative_path or relative_path == '.':
        relative_path = r['name']

    ext = os.path.splitext(r['name'])[1].lower()
    return {
        'name': r['name'],
        'relative_path': relative_path,
        'mtime': datetime.fromtimestamp(r['modify_time']).strftime('%Y-%m-%d %H:%M:%S'),
        'timestamp': r['modify_time'],
        'is_video': ext in config.VIDEO_EXT,
        'is_image': ext in config.IMAGE_EXT,
    }


# ==================== 目录浏览模式工具函数 ====================

_would_redirect_cache: dict[str, bool] = {}
_category_info_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()


def invalidate_cache(clear_key: str | None = None):
    """清除重定向和分类信息缓存，clear_key 为 None 时全清空"""
    with _cache_lock:
        if clear_key is None:
            _would_redirect_cache.clear()
            _category_info_cache.clear()
        else:
            key = str(clear_key)
            _would_redirect_cache.pop(key, None)
            # 清除以此路径为前缀的所有缓存（处理子目录变更影响父目录聚合）
            for k in list(_category_info_cache.keys()):
                if k == key or k.startswith(key + os.sep):
                    _category_info_cache.pop(k, None)


def _collect_files_recursive(folder_path, limit, run_mode, conn=None):
    """从文件夹递归收集媒体文件（纯 DB 查询，不 sync），返回最多 limit 个格式化项"""
    if limit <= 0:
        return []

    media_type = 'video' if run_mode in ('video', 'douyin') else 'image'
    _own_conn = conn is None
    try:
        from utils.db_utils import get_db, get_media_page
        if _own_conn:
            conn = get_db()
        rows, _ = get_media_page(
            conn, media_type, limit, 0,
            sort_type=config.SORT_TYPE, sort_order=config.SORT_ORDER,
            media_dir=str(folder_path),
        )
        return [_format_db_row(r) for r in rows]
    except Exception as e:
        logger.debug(f"_collect_files_recursive DB 失败: {e}")
        return []
    finally:
        if _own_conn and conn:
            conn.close()


def _collect_files_recursive_random(folder_path, limit, run_mode, conn=None):
    """随机模式：通过 get_random_media 纯 DB 查询收集文件"""
    if limit <= 0:
        return []

    media_type = 'video' if run_mode in ('video', 'douyin') else 'image'
    _own_conn = conn is None
    try:
        from utils.db_utils import get_db, get_random_media
        if _own_conn:
            conn = get_db()
        rows = get_random_media(conn, media_type, limit, media_dir=str(folder_path))
        return [_format_db_row(r) for r in rows]
    except Exception as e:
        logger.debug(f"_collect_files_recursive_random DB 失败: {e}")
        return []
    finally:
        if _own_conn and conn:
            conn.close()


def get_category_children_info(folder_path, run_mode, limit=None, random_mode=False,
                              already_synced=None, conn=None):
    """
    获取某文件夹的分类结构信息。

    Args:
        folder_path: 文件夹路径（绝对路径或 Path 对象）
        run_mode: 运行模式 ('video' 或 'image')
        limit: 每个分类区块的文件上限，默认 config.CATEGORY_PAGE_SIZE
        random_mode: 是否启用随机位置
        already_synced: 可选 set，已同步过的文件夹路径集合，用于跳过重复 sync

    Returns:
        dict: {
            'folder_name': 当前文件夹名,
            'folder_path': 相对路径,
            'is_leaf': 是否为叶子（无子文件夹）,
            'categories': [{ name, path, is_leaf, files, has_files }],
            'root_files': [当前目录下的直接文件],
            'total_categories': 有效分类数,
            'single_leaf_override': 是否触发兜底（仅一个分类有文件）
        }
    """
    if isinstance(folder_path, str):
        folder_path = Path(folder_path)

    if limit is None:
        limit = config.CATEGORY_PAGE_SIZE

    # 计算当前文件夹的相对路径
    rel_base = str(folder_path.resolve())
    media_dir_str = str(config.MEDIA_DIR.resolve())
    if rel_base == media_dir_str:
        folder_rel_path = ''
    else:
        folder_rel_path = os.path.relpath(rel_base, media_dir_str).replace('\\', '/')

    # 检查缓存（非 refresh 路径，already_synced 为 set 说明不会重新 sync）
    cache_key = f"{rel_base}:{run_mode}:{random_mode}:{limit}"
    if already_synced is not None:
        with _cache_lock:
            cached = _category_info_cache.get(cache_key)
        if cached is not None:
            return cached

    folder_name = folder_path.name if folder_rel_path else config.MEDIA_DIR.name

    # 收集根目录下的直接文件（仅当前文件夹，不递归子文件夹）
    media_type = 'video' if run_mode in ('video', 'douyin') else 'image'
    _own_shared_conn = conn is None
    try:
        from utils.db_utils import get_db, get_node_by_path, get_direct_media, sync_folder
        if _own_shared_conn:
            shared_conn = get_db()
        else:
            shared_conn = conn

        # 检查是否有子文件夹（复用共享连接）
        subfolders = _get_sorted_subfolders(folder_path, conn=shared_conn)
        is_leaf = len(subfolders) == 0

        result = {
            'folder_name': folder_name,
            'folder_path': folder_rel_path,
            'is_leaf': is_leaf,
            'categories': [],
            'root_files': [],
            'total_categories': 0,
            'single_leaf_override': False
        }
        node = get_node_by_path(shared_conn, str(folder_path))
        if node:
            rows, _ = get_direct_media(
                shared_conn, node['id'], media_type,
                config.SORT_TYPE, config.SORT_ORDER,
                limit=limit)
            result['root_files'] = [_format_db_row(r) for r in rows]
    except Exception:
        logger.debug(f"get_category_children_info: 根文件查询失败")
        result['root_files'] = []
        shared_conn = None

    # 处理每个子文件夹（分类）
    try:
        for sub in subfolders:
            sub_path = sub['path']
            sub_rel_path = os.path.relpath(sub_path, media_dir_str).replace('\\', '/')

            # 检查这个子文件夹是否有子文件夹（判断是否叶子）
            sub_subfolders = _get_sorted_subfolders(sub_path, conn=shared_conn)
            sub_is_leaf = len(sub_subfolders) == 0

            # 收集文件：先同步再查询，确保 DB 中有该子文件夹的数据
            if already_synced is None or sub_path not in already_synced:
                sync_folder(shared_conn, sub_path)
                if already_synced is not None:
                    already_synced.add(sub_path)
            if random_mode:
                files = _collect_files_recursive_random(sub_path, limit, run_mode, conn=shared_conn)
            else:
                files = _collect_files_recursive(sub_path, limit, run_mode, conn=shared_conn)

            has_files = len(files) > 0
            if has_files:
                result['categories'].append({
                    'name': sub['name'],
                    'path': sub_rel_path,
                    'is_leaf': sub_is_leaf,
                    'files': files,
                    'has_files': has_files
                })

    finally:
        if _own_shared_conn and shared_conn:
            shared_conn.close()

    result['total_categories'] = len(result['categories'])

    # 兜底规则：只有一个分类有文件，且无根文件
    if result['total_categories'] == 1 and len(result['root_files']) == 0:
        result['single_leaf_override'] = result['categories'][0]['is_leaf']

    # 缓存重定向判断结果，避免 from_override 链重复计算
    with _cache_lock:
        _would_redirect_cache[str(folder_path.resolve())] = (
            result['is_leaf']
            or result['total_categories'] == 0
            or (result['single_leaf_override'] and result['total_categories'] == 1)
        )
        # 缓存完整分类数据，仅当已有节流保护时（非首次加载 / 非 refresh）
        if already_synced is not None:
            _category_info_cache[cache_key] = result

    return result


def check_browse_would_redirect(folder_path, already_synced=None):
    """
    检查浏览该文件夹时是否会重定向到 grid 页面。
    返回 True 表示 /category/browse/ 会触发重定向（叶子或单分类兜底），
    用于 grid 页面判断返回按钮是否会导致循环。
    优先从缓存读取，避免 from_override 链重复计算。
    """
    cache_key = str(Path(folder_path).resolve())
    with _cache_lock:
        cached = _would_redirect_cache.get(cache_key)
    if cached is not None:
        return cached

    info = get_category_children_info(
        str(folder_path), config.RUN_MODE,
        random_mode=config.RANDOM_MODE,
        already_synced=already_synced,
    )

    # _would_redirect_cache 已在 get_category_children_info 中写入
    with _cache_lock:
        return _would_redirect_cache.get(cache_key, False)

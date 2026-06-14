"""
媒体处理工具函数
"""
import os
import time
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


def _get_sorted_subfolders(folder_path):
    """获取排序后的子文件夹列表（DB 查询）"""
    try:
        from utils.db_utils import get_db, get_node_by_path, get_subfolder_nodes
        conn = get_db()
        node = get_node_by_path(conn, str(folder_path))
        if not node:
            conn.close()
            return []
        rows = get_subfolder_nodes(conn, node['id'], config.SORT_TYPE, config.SORT_ORDER)
        conn.close()
        return [{'path': r['path'], 'name': r['name'], 'mtime': 0} for r in rows]
    except Exception as e:
        logger.debug(f"_get_sorted_subfolders DB 查询失败: {e}")
        return []


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


def _collect_files_recursive(folder_path, limit, run_mode):
    """从文件夹递归收集媒体文件（通过 traverse_media），返回最多 limit 个格式化项"""
    if limit <= 0:
        return []

    media_type = 'video' if run_mode in ('video', 'douyin') else 'image'
    try:
        from utils.db_utils import get_db, traverse_media
        conn = get_db()
        items, _, _ = traverse_media(
            conn, str(folder_path), media_type,
            offset=0, limit=limit,
            sort_type=config.SORT_TYPE,
            sort_order=config.SORT_ORDER,
        )
        conn.close()
        return items
    except Exception as e:
        logger.debug(f"_collect_files_recursive DB 失败: {e}")
        return []


def _collect_files_recursive_random(folder_path, limit, run_mode):
    """随机位置模式：通过 traverse_media(random_start=True) 收集文件"""
    if limit <= 0:
        return []

    media_type = 'video' if run_mode in ('video', 'douyin') else 'image'
    try:
        from utils.db_utils import get_db, traverse_media
        conn = get_db()
        items, _, _ = traverse_media(
            conn, str(folder_path), media_type,
            offset=0, limit=limit,
            sort_type=config.SORT_TYPE,
            sort_order=config.SORT_ORDER,
            random_start=True,
        )
        conn.close()
        return items
    except Exception as e:
        logger.debug(f"_collect_files_recursive_random DB 失败: {e}")
        return []


def get_category_children_info(folder_path, run_mode, limit=None, random_mode=False):
    """
    获取某文件夹的分类结构信息。

    Args:
        folder_path: 文件夹路径（绝对路径或 Path 对象）
        run_mode: 运行模式 ('video' 或 'image')
        limit: 每个分类区块的文件上限，默认 config.CATEGORY_PAGE_SIZE
        random_mode: 是否启用随机位置

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

    folder_name = folder_path.name if folder_rel_path else config.MEDIA_DIR.name

    # 检查是否有子文件夹
    subfolders = _get_sorted_subfolders(folder_path)
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

    # 收集根目录下的直接文件（仅当前文件夹，不递归子文件夹）
    media_type = 'video' if run_mode in ('video', 'douyin') else 'image'
    try:
        from utils.db_utils import get_db, get_node_by_path, get_direct_media
        conn = get_db()
        node = get_node_by_path(conn, str(folder_path))
        if node:
            rows, _ = get_direct_media(
                conn, node['id'], media_type,
                config.SORT_TYPE, config.SORT_ORDER)
            result['root_files'] = [_format_db_row(r) for r in rows]
        conn.close()
    except Exception:
        logger.debug(f"get_category_children_info: 根文件查询失败")
        result['root_files'] = []

    # 处理每个子文件夹（分类）
    for sub in subfolders:
        sub_path = sub['path']
        sub_rel_path = os.path.relpath(sub_path, media_dir_str).replace('\\', '/')

        # 检查这个子文件夹是否有子文件夹（判断是否叶子）
        sub_subfolders = _get_sorted_subfolders(sub_path)
        sub_is_leaf = len(sub_subfolders) == 0

        # 收集文件
        if random_mode:
            files = _collect_files_recursive_random(sub_path, limit, run_mode)
        else:
            files = _collect_files_recursive(sub_path, limit, run_mode)

        has_files = len(files) > 0
        if not has_files:
            continue  # 空文件夹跳过

        result['categories'].append({
            'name': sub['name'],
            'path': sub_rel_path,
            'is_leaf': sub_is_leaf,
            'files': files,
            'has_files': has_files
        })

    result['total_categories'] = len(result['categories'])

    # 兜底规则：只有一个分类有文件，且无根文件
    if result['total_categories'] == 1 and len(result['root_files']) == 0:
        result['single_leaf_override'] = result['categories'][0]['is_leaf']

    return result


def check_browse_would_redirect(folder_path):
    """
    检查浏览该文件夹时是否会重定向到 grid 页面。
    返回 True 表示 /category/browse/ 会触发重定向（叶子或单分类兜底），
    用于 grid 页面判断返回按钮是否会导致循环。
    """
    info = get_category_children_info(
        str(folder_path), config.RUN_MODE,
        random_mode=config.RANDOM_MODE
    )

    # 叶子节点（无子文件夹）→ grid
    if info['is_leaf']:
        return True

    # 所有子文件夹均为空 → 同叶子处理，重定向到 grid
    if info['total_categories'] == 0:
        return True

    # 仅有一个带文件的分类且无根文件 → 兜底重定向到 grid
    if info.get('single_leaf_override') and info['total_categories'] == 1:
        return True

    return False

"""
媒体处理工具函数
"""
import os
import time
import random
from pathlib import Path
from datetime import datetime
from config import config
from utils.logging_utils import logger
from models.cache_models import cache_manager

def get_sorted_folders():
    """获取排序后的文件夹列表（带缓存）"""
    if config.RUN_MODE not in ['video', 'image', 'douyin'] or not config.MEDIA_DIR or not config.MEDIA_DIR.exists():
        return []

    current_time = time.time()
    cached = cache_manager.get_folders_cache(config.SORT_TYPE, config.SORT_ORDER)
    if cached is not None:
        return cached

    folders = []
    try:
        root_stat = os.stat(str(config.MEDIA_DIR))
        root_mtime = root_stat.st_mtime
        root_folder = {
            'path': str(config.MEDIA_DIR),
            'rel_path': '',
            'name': config.MEDIA_DIR.name,
            'mtime': root_mtime
        }
        folders.append(root_folder)
    except Exception as e:
        from utils.logging_utils import logger
        logger.error(f"获取根目录状态失败: {e}", exc_info=True)

    try:
        for root, dirs, _ in os.walk(str(config.MEDIA_DIR)):
            for d in dirs:
                full_path = os.path.join(root, d)
                try:
                    stat = os.stat(full_path)
                    mtime = stat.st_mtime
                except Exception:
                    mtime = 0
                rel_path = os.path.relpath(full_path, config.MEDIA_DIR)
                folders.append({
                    'path': full_path,
                    'rel_path': rel_path,
                    'name': d,
                    'mtime': mtime
                })
    except Exception as e:
        from utils.logging_utils import logger
        logger.error(f"遍历文件夹失败: {e}", exc_info=True)

    reverse = (config.SORT_ORDER == 'desc')
    if config.SORT_TYPE == 'time':
        folders.sort(key=lambda x: x['mtime'], reverse=reverse)
    else:
        folders.sort(key=lambda x: x['name'].lower(), reverse=reverse)

    cache_manager.set_folders_cache(folders, config.SORT_TYPE, config.SORT_ORDER)

    return folders


def get_files_in_folder(folder_path):
    """获取文件夹中的媒体文件（带缓存）"""
    if config.RUN_MODE not in ['video', 'image', 'douyin'] or not config.MEDIA_DIR or not config.MEDIA_DIR.exists():
        return []

    current_time = time.time()
    cached = cache_manager.get_files_cache(folder_path, config.SORT_TYPE, config.SORT_ORDER)
    if cached is not None:
        return cached

    target_ext = config.VIDEO_EXT if config.RUN_MODE in ('video', 'douyin') else config.IMAGE_EXT
    files = []
    try:
        with os.scandir(folder_path) as entries:
            for entry in entries:
                if entry.is_file() and entry.name.lower().endswith(tuple(target_ext)):
                    try:
                        stat = entry.stat()
                        media_dir_str = str(config.MEDIA_DIR)
                        rel_path = os.path.relpath(entry.path, media_dir_str)
                        # 调试日志：检查rel_path是否为空
                        if not rel_path or rel_path == '.':
                            from utils.logging_utils import logger
                            logger.warning(f"get_files_in_folder: 异常相对路径 entry.path={entry.path}, MEDIA_DIR={media_dir_str}, rel_path={rel_path}")
                        file_info = {
                            'name': entry.name,
                            'path': entry.path,
                            'rel_path': rel_path,
                            'mtime': stat.st_mtime,
                            'size': stat.st_size
                        }
                        files.append(file_info)
                    except Exception:
                        continue
    except Exception as e:
        from utils.logging_utils import logger
        logger.error(f"扫描文件夹失败 {folder_path}: {e}", exc_info=True)

    reverse = (config.SORT_ORDER == 'desc')
    if config.SORT_TYPE == 'time':
        files.sort(key=lambda x: x['mtime'], reverse=reverse)
    else:
        files.sort(key=lambda x: x['name'].lower(), reverse=reverse)

    cache_manager.set_files_cache(folder_path, files, config.SORT_TYPE, config.SORT_ORDER)

    return files

def _get_sorted_subfolders(folder_path):
    """获取排序后的子文件夹列表"""
    subfolders = []
    try:
        with os.scandir(folder_path) as entries:
            for entry in entries:
                if entry.is_dir():
                    try:
                        stat = entry.stat()
                        subfolders.append({
                            'path': entry.path,
                            'name': entry.name,
                            'mtime': stat.st_mtime
                        })
                    except Exception:
                        pass
    except Exception as e:
        logger.warning(f"扫描子文件夹失败 {folder_path}: {e}")

    # 按 GUI 设置排序
    reverse = (config.SORT_ORDER == 'desc')
    if config.SORT_TYPE == 'time':
        subfolders.sort(key=lambda x: x['mtime'], reverse=reverse)
    else:
        subfolders.sort(key=lambda x: x['name'].lower(), reverse=reverse)

    return subfolders


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


def _build_video_info(f):
    """将文件信息转为视频信息"""
    return {
        'name': f['name'],
        'relative_path': f['rel_path'].replace(os.sep, '/'),
        'timestamp': f['mtime']
    }


def get_video_at_offset(cursor):
    """按偏移量获取单个视频文件，返回 (video_info, has_more)
    每次调用会扫描文件夹列表并计数，依赖已有的文件夹/文件缓存（60s），无额外存储"""
    folders = get_sorted_folders()
    count = 0
    for folder in folders:
        files = get_files_in_folder(folder['path'])
        for f in files:
            ext = os.path.splitext(f['name'])[1].lower()
            if ext not in config.VIDEO_EXT:
                continue
            if count == cursor:
                return _build_video_info(f), True
            count += 1
    return None, False


def pick_random_media_video(history):
    """随机媒体模式：随机树下降算法。

    每层将当前目录的（视频文件 + 子文件夹）混合随机选择，
    命中文件且未看过则返回，命中文件夹则下钻，
    无文件或全部已看过则回溯到父级继续。
    典型 IO 开销仅 3-5 次 scandir 而非全量 os.walk。
    """
    root_path = config.MEDIA_DIR
    target_ext = config.VIDEO_EXT
    history_set = {h.get('relative_path', '') for h in history} if history else set()

    def _descend(folder_path, depth=0):
        if depth > 200:
            return None

        files = get_files_in_folder(folder_path)
        subfolders = _get_sorted_subfolders(folder_path)

        # 当前目录未看过的文件
        unseen = []
        for f in files:
            ext = os.path.splitext(f['name'])[1].lower()
            if ext not in target_ext:
                continue
            if f['rel_path'].replace(os.sep, '/') not in history_set:
                unseen.append(f)

        if not subfolders:
            # 叶子文件夹：从本层文件随机选
            if unseen:
                return _build_video_info(random.choice(unseen))
            return None

        # 有子文件夹：文件 + 文件夹混合随机池
        pool = [('file', f) for f in unseen]
        pool.extend([('folder', s) for s in subfolders])
        random.shuffle(pool)

        for kind, item in pool:
            if kind == 'folder':
                result = _descend(item['path'], depth + 1)
                if result:
                    return result
            else:
                return _build_video_info(item)

        return None

    return _descend(str(root_path))


# ==================== 目录浏览模式工具函数 ====================


def _collect_files_recursive(folder_path, limit, run_mode):
    """
    递归收集文件夹及其后代中的所有媒体文件。
    深度优先遍历，按排序规则取文件。
    返回最多 limit 个格式化文件项。
    """
    if limit <= 0:
        return []

    target_ext = config.VIDEO_EXT if run_mode in ('video', 'douyin') else config.IMAGE_EXT
    collected = []

    # 收集当前文件夹的直接文件
    direct_files = []
    try:
        with os.scandir(folder_path) as entries:
            for entry in entries:
                if entry.is_file() and entry.name.lower().endswith(tuple(target_ext)):
                    try:
                        stat = entry.stat()
                        media_dir_str = str(config.MEDIA_DIR)
                        rel_path = os.path.relpath(entry.path, media_dir_str)
                        direct_files.append({
                            'name': entry.name,
                            'path': entry.path,
                            'rel_path': rel_path,
                            'mtime': stat.st_mtime,
                            'size': stat.st_size
                        })
                    except Exception:
                        continue
    except Exception as e:
        logger.warning(f"扫描文件失败 {folder_path}: {e}")

    # 排序直接文件
    reverse = (config.SORT_ORDER == 'desc')
    if config.SORT_TYPE == 'time':
        direct_files.sort(key=lambda x: x['mtime'], reverse=reverse)
    else:
        direct_files.sort(key=lambda x: x['name'].lower(), reverse=reverse)

    # 添加到结果
    for f in direct_files:
        if len(collected) >= limit:
            break
        collected.append(_format_file_item(f))

    if len(collected) >= limit:
        return collected[:limit]

    # 递归子文件夹
    subfolders = _get_sorted_subfolders(folder_path)
    for sub in subfolders:
        if len(collected) >= limit:
            break
        sub_files = _collect_files_recursive(sub['path'], limit - len(collected), run_mode)
        collected.extend(sub_files)

    return collected[:limit]


def _collect_files_recursive_random(folder_path, limit, run_mode):
    """
    随机位置模式：从 folder_path 的直接子文件夹中随机选一个，
    递归取文件。如果不够，按顺序从其他兄弟文件夹补。
    如果没有子文件夹，直接从当前文件夹取文件。
    """
    if limit <= 0:
        return []

    subfolders = _get_sorted_subfolders(folder_path)

    if not subfolders:
        # 没有子文件夹，直接从当前文件夹取文件
        return _collect_files_recursive(folder_path, limit, run_mode)

    # 随机选一个子文件夹作为起始
    start_idx = random.randint(0, len(subfolders) - 1)
    # 从随机起点开始重新排列（轮转）
    rotated = subfolders[start_idx:] + subfolders[:start_idx]

    collected = []
    for sub in rotated:
        if len(collected) >= limit:
            break
        sub_files = _collect_files_recursive(sub['path'], limit - len(collected), run_mode)
        collected.extend(sub_files)

    # 如果所有子文件夹都不够，再从当前文件夹自身取直接文件（不递归，避免重复）
    if len(collected) < limit:
        existing_paths = {f['relative_path'] for f in collected}
        target_ext = config.VIDEO_EXT if run_mode in ('video', 'douyin') else config.IMAGE_EXT
        direct_files = []
        try:
            with os.scandir(folder_path) as entries:
                for entry in entries:
                    if entry.is_file() and entry.name.lower().endswith(tuple(target_ext)):
                        try:
                            stat = entry.stat()
                            media_dir_str = str(config.MEDIA_DIR)
                            rel_path = os.path.relpath(entry.path, media_dir_str)
                            direct_files.append({
                                'name': entry.name,
                                'path': entry.path,
                                'rel_path': rel_path,
                                'mtime': stat.st_mtime,
                                'size': stat.st_size
                            })
                        except Exception:
                            continue
        except Exception:
            logger.debug(f"_collect_files_recursive_random: scandir 失败 {folder_path}")
        reverse = (config.SORT_ORDER == 'desc')
        if config.SORT_TYPE == 'time':
            direct_files.sort(key=lambda x: x['mtime'], reverse=reverse)
        else:
            direct_files.sort(key=lambda x: x['name'].lower(), reverse=reverse)
        for f in direct_files:
            if len(collected) >= limit:
                break
            formatted = _format_file_item(f)
            if formatted['relative_path'] not in existing_paths:
                collected.append(formatted)

    return collected[:limit]


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

    # 收集根目录下的直接文件
    target_ext = config.VIDEO_EXT if run_mode in ('video', 'douyin') else config.IMAGE_EXT
    root_files = []
    try:
        with os.scandir(str(folder_path)) as entries:
            for entry in entries:
                if entry.is_file() and entry.name.lower().endswith(tuple(target_ext)):
                    try:
                        stat = entry.stat()
                        rel_path = os.path.relpath(entry.path, media_dir_str)
                        root_files.append({
                            'name': entry.name,
                            'path': entry.path,
                            'rel_path': rel_path,
                            'mtime': stat.st_mtime,
                            'size': stat.st_size
                        })
                    except Exception:
                        continue
    except Exception:
        logger.debug(f"get_category_children_info: scandir 失败 {folder_path}")

    # 排序根文件
    reverse = (config.SORT_ORDER == 'desc')
    if config.SORT_TYPE == 'time':
        root_files.sort(key=lambda x: x['mtime'], reverse=reverse)
    else:
        root_files.sort(key=lambda x: x['name'].lower(), reverse=reverse)

    result['root_files'] = [_format_file_item(f) for f in root_files]

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


def get_grid_page_files(folder_path, offset, limit, run_mode):
    """
    获取叶子文件夹的分页文件（用于网格页面）。
    返回 (files_list, total_count, has_more)
    """
    if isinstance(folder_path, str):
        folder_path = Path(folder_path)

    target_ext = config.VIDEO_EXT if run_mode in ('video', 'douyin') else config.IMAGE_EXT

    # 获取所有文件
    all_files = []
    try:
        with os.scandir(str(folder_path)) as entries:
            for entry in entries:
                if entry.is_file() and entry.name.lower().endswith(tuple(target_ext)):
                    try:
                        stat = entry.stat()
                        media_dir_str = str(config.MEDIA_DIR)
                        rel_path = os.path.relpath(entry.path, media_dir_str)
                        all_files.append({
                            'name': entry.name,
                            'path': entry.path,
                            'rel_path': rel_path,
                            'mtime': stat.st_mtime,
                            'size': stat.st_size
                        })
                    except Exception:
                        continue
    except Exception as e:
        logger.warning(f"扫描文件夹失败 {folder_path}: {e}")

    # 排序
    reverse = (config.SORT_ORDER == 'desc')
    if config.SORT_TYPE == 'time':
        all_files.sort(key=lambda x: x['mtime'], reverse=reverse)
    else:
        all_files.sort(key=lambda x: x['name'].lower(), reverse=reverse)

    total = len(all_files)
    page_files = all_files[offset:offset + limit]

    formatted = [_format_file_item(f) for f in page_files]
    has_more = (offset + limit) < total

    return formatted, total, has_more


def check_browse_would_redirect(folder_path):
    """
    检查浏览该文件夹时是否会重定向到 grid 页面。
    返回 True 表示 /category/browse/ 会触发重定向（叶子或单分类兜底），
    用于 grid 页面判断返回按钮是否会导致循环。

    直接使用 get_category_children_info 的结果来判断，与 category_browse
    的实际跳转逻辑保持一致，避免因空子文件夹导致误判。
    """
    if isinstance(folder_path, str):
        folder_path = Path(folder_path)

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

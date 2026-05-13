"""
媒体处理工具函数
"""
import os
import time
import random
import threading
import uuid
from pathlib import Path
from datetime import datetime
from config import config
from utils.logging_utils import logger
from models.cache_models import cache_manager

# 服务端遍历状态存储（keyed by traversal_id）
_traversal_store = {}
_traversal_lock = threading.Lock()


def remove_traversal(traversal_id: str):
    """删除指定遍历状态"""
    with _traversal_lock:
        _traversal_store.pop(traversal_id, None)


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


def init_traversal(root_path, run_mode):
    """初始化遍历状态，返回 traversal_id"""
    logger.info(f"初始化遍历: root={root_path}, mode={run_mode}")
    # 确保是Path对象
    if isinstance(root_path, str):
        root_path = Path(root_path)
    print(f"[INFO] 初始化遍历: {root_path.name}, 模式={run_mode}", flush=True)

    # 清理超过 1 小时未活动的旧遍历
    stale_threshold = time.time() - 3600
    with _traversal_lock:
        stale_ids = [tid for tid, t in list(_traversal_store.items())
                     if t.get('last_activity_time', 0) < stale_threshold]
        for tid in stale_ids:
            del _traversal_store[tid]
    if stale_ids:
        logger.info(f"清理了 {len(stale_ids)} 个过期遍历状态")

    # 获取根目录下所有子文件夹，按排序
    root_subfolders = _get_sorted_subfolders(root_path)

    if not root_subfolders:
        logger.info("根目录没有子文件夹，直接播放根目录")
        print(f"[INFO] 根目录没有子文件夹，直接播放根目录", flush=True)
        traversal_id = str(uuid.uuid4())
        with _traversal_lock:
            _traversal_store[traversal_id] = {
                'current_folder': root_path,
                'current_file_idx': 0,
                'folder_stack': [],  # 文件夹遍历栈
                'finished': False,
                'root_path': root_path,
                'run_mode': run_mode,
                'last_activity_time': time.time()
            }
        return traversal_id

    # 有子文件夹，随机选一个根目录子文件夹作为起点
    start_root_idx = random.randint(0, len(root_subfolders) - 1)
    logger.info(f"随机选择第 {start_root_idx} 个根目录子文件夹: {root_subfolders[start_root_idx]['name']}")
    print(f"[INFO] 随机选择起点根文件夹: {root_subfolders[start_root_idx]['name']}", flush=True)

    # 构建初始的文件夹遍历栈，记录同级文件夹信息，用于随机选择起点子文件夹
    start_root_folder = root_subfolders[start_root_idx]['path']
    target_ext = config.VIDEO_EXT if run_mode == 'video' else config.IMAGE_EXT

    # 创建遍历栈，从根目录开始向下构建到起始子文件夹
    folder_stack = []

    # 先处理根目录这一层
    folder_stack.append({
        'folder_path': str(root_path),
        'sibling_folders': root_subfolders,  # 同级文件夹列表
        'current_sibling_idx': start_root_idx,  # 当前同级索引
        'start_sibling_idx': start_root_idx,  # 记录起始同级索引
        'visited_all_siblings': False  # 是否遍历完所有同级
    })

    # 现在从选中的根目录子文件夹开始，继续向下遍历并随机选择一个起点
    current_path = start_root_folder
    while True:
        subfolders = _get_sorted_subfolders(current_path)
        if not subfolders:
            break  # 到达叶子节点

        # 有子文件夹，随机选择一个
        start_sub_idx = random.randint(0, len(subfolders) - 1)
        folder_stack.append({
            'folder_path': current_path,
            'sibling_folders': subfolders,
            'current_sibling_idx': start_sub_idx,
            'start_sibling_idx': start_sub_idx,
            'visited_all_siblings': False
        })
        current_path = subfolders[start_sub_idx]['path']

    # 记录最终的起点文件夹
    start_leaf_folder = current_path
    logger.info(f"初始叶子文件夹: {start_leaf_folder}")
    print(f"[INFO] 初始播放文件夹: {Path(start_leaf_folder).name}", flush=True)

    traversal_id = str(uuid.uuid4())
    with _traversal_lock:
        _traversal_store[traversal_id] = {
            'current_folder': start_leaf_folder,
            'current_file_idx': 0,
            'folder_stack': folder_stack,  # 文件夹遍历栈
            'finished': False,
            'root_path': root_path,
            'run_mode': run_mode,
            'last_activity_time': time.time()
        }
    return traversal_id


def _get_next_folder(traversal):
    """获取下一个要播放的文件夹。返回 (folder_path, has_more)"""
    folder_stack = traversal.get('folder_stack', [])

    if not folder_stack:
        traversal['finished'] = True
        return None, False

    # 从栈顶开始向上查找下一个可用的文件夹
    while folder_stack:
        current_level = folder_stack[-1]
        sibling_folders = current_level['sibling_folders']
        current_idx = current_level['current_sibling_idx']
        start_idx = current_level['start_sibling_idx']
        visited_all = current_level.get('visited_all_siblings', False)

        # 计算下一个同级索引
        next_idx = current_idx + 1

        # 如果到达同级末尾
        if next_idx >= len(sibling_folders):
            next_idx = 0

        # 检查是否回绕到起点了（说明这一层的同级都遍历完了）
        if next_idx == start_idx and not visited_all:
            # 第一次回绕，标记这一层已遍历完所有同级
            current_level['visited_all_siblings'] = True
        elif next_idx == start_idx and visited_all:
            # 已经是第二圈了，这一层没有更多同级了，向上一层
            folder_stack.pop()
            continue

        # 更新当前层的索引
        current_level['current_sibling_idx'] = next_idx

        # 选中下一个同级文件夹
        next_sibling_folder = sibling_folders[next_idx]['path']

        # 现在需要进入这个文件夹，找到第一个叶子（如果有子文件夹的话）
        # 但是根据逻辑，我们应该按照顺序遍历这个同级文件夹下面的所有子文件夹
        # 首先检查这个同级文件夹是否有子文件夹
        subfolders = _get_sorted_subfolders(next_sibling_folder)

        if subfolders:
            # 有子文件夹，需要向下遍历，找到第一个子文件夹（按排序）
            # 构建新的层级
            current_path = next_sibling_folder
            while True:
                children = _get_sorted_subfolders(current_path)
                if not children:
                    break  # 到达叶子节点
                # 加入新层级，从第一个子文件夹开始
                folder_stack.append({
                    'folder_path': current_path,
                    'sibling_folders': children,
                    'current_sibling_idx': 0,
                    'start_sibling_idx': 0,
                    'visited_all_siblings': False
                })
                current_path = children[0]['path']

            # 找到最终的叶子文件夹
            next_folder = current_path
        else:
            # 没有子文件夹，这个同级文件夹就是叶子
            next_folder = next_sibling_folder

        logger.debug(f"下一个文件夹: {next_folder}")
        return next_folder, True

    # 没有更多文件夹了
    traversal['finished'] = True
    return None, False


def _format_file_item(f):
    """格式化单个文件项"""
    rel_path = f['rel_path']
    relative_path = rel_path.replace('\\', '/')
    if not relative_path or relative_path == '.':
        logger.warning(f"get_next_media_files: 异常相对路径 f['name']={f['name']}, f['path']={f['path']}, rel_path={rel_path}")
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


def get_next_media_files(traversal_id, limit):
    """获取下一批媒体文件，返回 (files_list, has_more)"""
    with _traversal_lock:
        traversal = _traversal_store.get(traversal_id)

    if not traversal:
        logger.error(f"get_next_media_files: traversal_id 未找到: {traversal_id}")
        return [], False

    if traversal.get('finished'):
        with _traversal_lock:
            _traversal_store.pop(traversal_id, None)
        return [], False

    result = []
    traversal['last_activity_time'] = time.time()

    current_folder = traversal['current_folder']
    current_idx = traversal.get('current_file_idx', 0)

    # 持续获取文件，直到达到limit或没有更多文件
    while len(result) < limit:
        if time.time() - traversal['last_activity_time'] > 20:
            traversal['finished'] = True
            break

        current_files = get_files_in_folder(current_folder)

        # 如果当前文件夹还有文件，添加到结果中
        if current_idx < len(current_files):
            f = current_files[current_idx]
            result.append(_format_file_item(f))
            current_idx += 1
        else:
            # 当前文件夹没有更多文件了，需要找到下一个有文件的文件夹
            next_folder_found = False
            while not next_folder_found:
                next_folder, has_more = _get_next_folder(traversal)

                if not has_more or not next_folder:
                    # 没有更多文件夹了，退出循环
                    break

                # 检查这个新文件夹是否有文件
                next_files = get_files_in_folder(next_folder)
                if len(next_files) > 0:
                    # 找到了有文件的文件夹
                    current_folder = next_folder
                    traversal['current_folder'] = current_folder
                    current_idx = 0
                    next_folder_found = True
                # 如果这个文件夹也没文件，继续循环寻找下一个

            if not next_folder_found:
                # 没有更多文件夹了，退出主循环
                break

    traversal['current_file_idx'] = current_idx

    # 检查是否还有更多文件可以获取
    has_more = False

    # 检查是否已标记为完成
    if traversal.get('finished', False):
        has_more = False
        with _traversal_lock:
            _traversal_store.pop(traversal_id, None)
    else:
        # 首先检查当前文件夹是否还有剩余文件
        current_files = get_files_in_folder(traversal['current_folder'])
        if current_idx < len(current_files):
            has_more = True
        else:
            # 当前文件夹没有文件了，尝试查找下一个文件夹看看是否有文件
            # 我们暂时不修改traversal状态
            folder_stack = traversal.get('folder_stack', [])
            if folder_stack:
                # 假设还有更多（除非遍历真的结束了）
                has_more = True

    logger.info(f"get_next_media_files: 返回 {len(result)} 个文件, has_more={has_more}")
    return result, has_more


# ==================== 顺序遍历（非随机模式） ====================

def _get_sorted_media_files(folder_path, target_ext):
    """获取单个文件夹中排序后的媒体文件（不递归），供顺序遍历栈帧使用"""
    files = []
    try:
        with os.scandir(folder_path) as entries:
            for entry in entries:
                if entry.is_file() and entry.name.lower().endswith(tuple(target_ext)):
                    try:
                        stat = entry.stat()
                        media_dir_str = str(config.MEDIA_DIR)
                        rel_path = os.path.relpath(entry.path, media_dir_str)
                        files.append({
                            'name': entry.name,
                            'path': entry.path,
                            'rel_path': rel_path,
                            'mtime': stat.st_mtime,
                            'size': stat.st_size
                        })
                    except Exception:
                        continue
    except Exception as e:
        logger.warning(f"扫描媒体文件失败 {folder_path}: {e}")

    reverse = (config.SORT_ORDER == 'desc')
    if config.SORT_TYPE == 'time':
        files.sort(key=lambda x: x['mtime'], reverse=reverse)
    else:
        files.sort(key=lambda x: x['name'].lower(), reverse=reverse)

    return files


def init_sequential_traversal(root_path, run_mode):
    """初始化顺序遍历状态。
    从根目录开始，沿第一个子文件夹一路下钻到叶子，
    每层栈帧存储排序后的子文件夹列表和媒体文件列表。
    """
    if isinstance(root_path, str):
        root_path = Path(root_path)

    target_ext = config.VIDEO_EXT if run_mode in ('video', 'douyin') else config.IMAGE_EXT

    logger.info(f"初始化顺序遍历: root={root_path}, mode={run_mode}")
    print(f"[INFO] 初始化顺序遍历: {root_path.name}, 模式={run_mode}", flush=True)

    # 清理超过 1 小时未活动的旧遍历
    stale_threshold = time.time() - 3600
    with _traversal_lock:
        stale_ids = [tid for tid, t in list(_traversal_store.items())
                     if t.get('last_activity_time', 0) < stale_threshold]
        for tid in stale_ids:
            del _traversal_store[tid]

    folder_stack = []
    current_path = root_path

    while True:
        subfolders = _get_sorted_subfolders(current_path)
        media_files = _get_sorted_media_files(current_path, target_ext)

        frame = {
            'folder_path': str(current_path),
            'subfolders': subfolders,
            'current_subfolder_idx': 0,
            'media_files': media_files,
            'media_file_idx': 0,
        }
        folder_stack.append(frame)

        if subfolders:
            frame['current_subfolder_idx'] = 1
            current_path = subfolders[0]['path']
        else:
            break

    traversal_id = str(uuid.uuid4())
    with _traversal_lock:
        _traversal_store[traversal_id] = {
            'folder_stack': folder_stack,
            'finished': False,
            'root_path': root_path,
            'run_mode': run_mode,
            'last_activity_time': time.time()
        }
    return traversal_id


def get_next_sequential_files(traversal_id, limit):
    """获取下一批文件（顺序遍历，深度优先）。
    每进入一个文件夹：先逐个深入子文件夹，子文件夹全部走完后消费当前层媒体文件。
    当前层耗尽后弹出栈帧回到父级继续。
    """
    with _traversal_lock:
        traversal = _traversal_store.get(traversal_id)
    if not traversal:
        logger.error(f"get_next_sequential_files: traversal_id 未找到: {traversal_id}")
        return [], False

    if traversal.get('finished'):
        with _traversal_lock:
            _traversal_store.pop(traversal_id, None)
        return [], False

    traversal['last_activity_time'] = time.time()
    result = []
    target_ext = config.VIDEO_EXT if traversal.get('run_mode') in ('video', 'douyin') else config.IMAGE_EXT
    stack = traversal['folder_stack']

    while len(result) < limit:
        if not stack:
            traversal['finished'] = True
            break

        frame = stack[-1]

        # 阶段1：还有子文件夹未探索 → 进入下一个子文件夹并下钻到叶子
        if frame['current_subfolder_idx'] < len(frame['subfolders']):
            next_sub = frame['subfolders'][frame['current_subfolder_idx']]
            frame['current_subfolder_idx'] += 1

            current_path = next_sub['path']
            while True:
                subfolders = _get_sorted_subfolders(current_path)
                media_files = _get_sorted_media_files(current_path, target_ext)
                new_frame = {
                    'folder_path': str(current_path),
                    'subfolders': subfolders,
                    'current_subfolder_idx': 0,
                    'media_files': media_files,
                    'media_file_idx': 0,
                }
                stack.append(new_frame)
                if subfolders:
                    new_frame['current_subfolder_idx'] = 1
                    current_path = subfolders[0]['path']
                else:
                    break
            continue

        # 阶段2：没有子文件夹了 → 消费当前层自身的媒体文件
        frame_media = frame['media_files']
        idx = frame['media_file_idx']

        while idx < len(frame_media) and len(result) < limit:
            result.append(_format_file_item(frame_media[idx]))
            idx += 1

        frame['media_file_idx'] = idx

        if idx >= len(frame_media):
            # 当前文件夹耗尽，弹出回到父级
            stack.pop()
        else:
            break

    has_more = not traversal.get('finished', False) and len(stack) > 0

    if traversal.get('finished'):
        with _traversal_lock:
            _traversal_store.pop(traversal_id, None)

    logger.info(f"get_next_sequential_files: 返回 {len(result)} 个文件, has_more={has_more}")
    return result, has_more


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
    返回 True 表示 /category/browse/ 会触发重定向（叶子或兜底），
    用于 grid 页面判断返回按钮是否会导致循环。
    """
    if isinstance(folder_path, str):
        folder_path = Path(folder_path)

    # 检查是否有子文件夹
    try:
        has_subfolders = any(e.is_dir() for e in os.scandir(str(folder_path)))
    except Exception:
        return True  # 无法访问，保守处理

    if not has_subfolders:
        return True  # 叶子文件夹 → redirect to grid

    # 有子文件夹 → 检查是否满足兜底条件
    info = get_category_children_info(
        str(folder_path), config.RUN_MODE,
        random_mode=config.RANDOM_MODE
    )
    return info.get('single_leaf_override', False) and info['total_categories'] == 1

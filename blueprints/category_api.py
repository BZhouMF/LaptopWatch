"""
目录浏览模式API蓝图
提供分类区块展示接口
"""
import os
import time
import threading
import urllib.parse
from pathlib import Path
from flask import Blueprint, request, jsonify, send_file, redirect
from config import config
from utils.logging_utils import log_access, log_exception, logger
from utils.media_utils import get_category_children_info, invalidate_cache
from blueprints.auth import login_required, require_mode

category_bp = Blueprint('category', __name__, url_prefix='/category')


_scanned_folders = set()  # 已同步过的文件夹，点击刷新可清除
_scanned_folders_lock = threading.Lock()
_last_config_version = config.CONFIG_VERSION


def _sync_db(folder_path, conn=None):
    """同步当前文件夹到 DB，同目录只扫描一次。可传入共享连接避免重复开/关。"""
    global _last_config_version
    # 配置变更（模式切换、媒体目录变更等）→ 清除节流阀，强制重新扫描
    if config.CONFIG_VERSION != _last_config_version:
        with _scanned_folders_lock:
            _scanned_folders.clear()
        invalidate_cache()
        _last_config_version = config.CONFIG_VERSION

    # 在锁内同时完成检查与标记，避免并发线程同时通过检查
    with _scanned_folders_lock:
        if folder_path in _scanned_folders:
            return
        _scanned_folders.add(folder_path)

    try:
        if config.DB_PATH and config.MEDIA_DIR:
            from utils.db_utils import get_db, sync_folder
            if conn is None:
                conn = get_db()
            sync_folder(conn, folder_path)
    except Exception:
        # 同步失败时移除标记，允许下次请求重试
        with _scanned_folders_lock:
            _scanned_folders.discard(folder_path)


def _get_lazy_page_files(folder_path, offset, limit, run_mode):
    """惰性分页 — 通过 traverse_media 从 DB 遍历取文件，不统计总数"""
    try:
        if config.DB_PATH and config.MEDIA_DIR:
            from utils.db_utils import get_db, traverse_media
            media_type = 'video' if run_mode in ('video', 'douyin') else 'image'
            conn = get_db()
            files, next_offset, has_more = traverse_media(
                conn, str(folder_path), media_type,
                offset=offset, limit=limit,
                sort_type=config.SORT_TYPE,
                sort_order=config.SORT_ORDER,
                skip_sync=(offset > 0),
            )
            return files, has_more
        return [], False
    except Exception:
        logger.debug("_get_lazy_page_files DB 失败")
        return [], False


@category_bp.route('/data', methods=['GET'])
@login_required
@require_mode('video', 'image')
def category_data():
    """
    JSON API: 获取某路径下的分类结构数据。
    Query params: path=相对路径（空=根目录）, refresh=1 清除缓存
    """
    global _last_config_version
    # 配置变更（模式切换、媒体目录变更等）→ 清除节流阀与缓存
    if config.CONFIG_VERSION != _last_config_version:
        with _scanned_folders_lock:
            _scanned_folders.clear()
        invalidate_cache()
        _last_config_version = config.CONFIG_VERSION

    start_time = time.time()
    try:
        folder_rel_path = request.args.get('path', '')
        if folder_rel_path:
            folder_rel_path = urllib.parse.unquote(folder_rel_path)
            full_path = (config.MEDIA_DIR / folder_rel_path).resolve()
            if not str(full_path).startswith(str(config.MEDIA_DIR.resolve())):
                return jsonify({'code': 1, 'msg': '非法访问'}), 403
        else:
            full_path = config.MEDIA_DIR

        if not full_path or not full_path.exists() or not full_path.is_dir():
            return jsonify({'code': 1, 'msg': '目录不存在'}), 404

        # 手动刷新 → 清除节流阀 + 缓存，强制重新扫描
        if request.args.get('refresh') == '1':
            with _scanned_folders_lock:
                _scanned_folders.discard(str(full_path))
            invalidate_cache(str(full_path))

        # 同步 DB 确保 per-disk 表已更新
        _sync_db(str(full_path))

        info = get_category_children_info(
            str(full_path), config.RUN_MODE,
            random_mode=config.RANDOM_MODE,
            already_synced=_scanned_folders,
        )

        return jsonify({'code': 0, 'data': info})
    except Exception as e:
        logger.error(f"category_data 错误: {e}", exc_info=True)
        return jsonify({'code': 1, 'msg': str(e)}), 500
    finally:
        log_access(request, 'CATEGORY_DATA', request.args.get('path', ''),
                   duration=time.time() - start_time)


@category_bp.route('/grid_more', methods=['GET'])
@login_required
@require_mode('video', 'image')
def category_grid_more():
    """叶子文件夹加载更多（JSON API，惰性分页，不统计总数）"""
    start_time = time.time()
    try:
        folder_path = request.args.get('path', '')
        offset = int(request.args.get('offset', 0))
        limit = int(request.args.get('limit', config.PAGE_LOAD))

        decoded_path = urllib.parse.unquote(folder_path)
        full_path = (config.MEDIA_DIR / decoded_path).resolve()

        if not str(full_path).startswith(str(config.MEDIA_DIR.resolve())):
            return jsonify({'code': 1, 'msg': '非法访问'}), 403

        # 手动刷新 → 清除节流阀 + 缓存，强制重新扫描
        if request.args.get('refresh') == '1':
            with _scanned_folders_lock:
                _scanned_folders.discard(str(full_path))
            invalidate_cache(str(full_path))

        _sync_db(str(full_path))

        files, has_more = _get_lazy_page_files(
            str(full_path), offset, limit, config.RUN_MODE
        )

        return jsonify({
            'code': 0,
            'data': files,
            'has_more': has_more,
            'next_offset': offset + len(files)
        })
    except Exception as e:
        logger.error(f"category_grid_more 错误: {e}", exc_info=True)
        return jsonify({'code': 1, 'msg': str(e)}), 500
    finally:
        log_access(request, 'CATEGORY_GRID_MORE', request.args.get('path', ''),
                   duration=time.time() - start_time)


@category_bp.route('/browse/<path:folder_path>', methods=['GET'])
@login_required
@require_mode('video', 'image')
def category_browse(folder_path):
    """SSR 入口：处理 refresh 后返回 React SPA"""
    start_time = time.time()
    try:
        decoded_path = urllib.parse.unquote(folder_path)
        full_path = (config.MEDIA_DIR / decoded_path).resolve()

        if not str(full_path).startswith(str(config.MEDIA_DIR.resolve())):
            return '非法访问', 403

        # 手动刷新 → 清除节流阀 + 缓存
        if request.args.get('refresh') == '1':
            with _scanned_folders_lock:
                _scanned_folders.discard(str(full_path))
            invalidate_cache(str(full_path))

        # 返回 React SPA 入口（前端路由会接管 /category/*）
        react_index = config.REACT_DIST_DIR / 'index.html'
        if react_index.is_file():
            return send_file(str(react_index))
        return 'React 前端未构建', 500
    except Exception as e:
        logger.error(f"category_browse 错误: {e}", exc_info=True)
        return '加载失败', 500
    finally:
        log_access(request, 'CATEGORY_BROWSE', folder_path,
                   duration=time.time() - start_time)


@category_bp.route('/grid/<path:folder_path>', methods=['GET'])
@login_required
@require_mode('video', 'image')
def category_grid(folder_path):
    """SSR 入口：处理 refresh 后返回 React SPA"""
    start_time = time.time()
    try:
        decoded_path = urllib.parse.unquote(folder_path)
        full_path = (config.MEDIA_DIR / decoded_path).resolve()

        if not str(full_path).startswith(str(config.MEDIA_DIR.resolve())):
            return '非法访问', 403

        # 手动刷新 → 清除节流阀 + 缓存
        if request.args.get('refresh') == '1':
            with _scanned_folders_lock:
                _scanned_folders.discard(str(full_path))
            invalidate_cache(str(full_path))

        # 返回 React SPA 入口（前端路由会接管 /category/*）
        react_index = config.REACT_DIST_DIR / 'index.html'
        if react_index.is_file():
            return send_file(str(react_index))
        return 'React 前端未构建', 500
    except Exception as e:
        logger.error(f"category_grid 错误: {e}", exc_info=True)
        return '加载失败', 500
    finally:
        log_access(request, 'CATEGORY_GRID', folder_path,
                   duration=time.time() - start_time)

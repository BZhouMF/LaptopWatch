"""
目录浏览模式API蓝图
提供分类区块展示接口
"""
import os
import time
import urllib.parse
from pathlib import Path
from flask import Blueprint, request, jsonify, render_template, redirect
from config import config
from utils.logging_utils import log_access, log_exception, logger
from utils.media_utils import get_category_children_info, check_browse_would_redirect
from blueprints.auth import login_required, require_mode

category_bp = Blueprint('category', __name__, url_prefix='/category')


_scanned_folders = set()  # 已同步过的文件夹，点击刷新可清除


def _sync_db(folder_path):
    """同步当前文件夹到 DB，同目录只扫描一次"""
    if folder_path in _scanned_folders:
        return
    try:
        if config.DB_PATH and config.MEDIA_DIR:
            from utils.db_utils import get_db, sync_folder
            conn = get_db()
            sync_folder(conn, folder_path)
            conn.close()
            _scanned_folders.add(folder_path)
    except Exception:
        pass


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
                skip_sync=True,
            )
            conn.close()
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
    Query params: path=相对路径（空=根目录）
    """
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


@category_bp.route('/browse/<path:folder_path>', methods=['GET'])
@login_required
@require_mode('video', 'image')
def category_browse(folder_path):
    """
    进入子文件夹。
    如果有子文件夹 → 渲染分类页面
    如果是叶子 → 跳转到网格页面
    """
    start_time = time.time()
    try:
        decoded_path = urllib.parse.unquote(folder_path)
        full_path = (config.MEDIA_DIR / decoded_path).resolve()

        if not str(full_path).startswith(str(config.MEDIA_DIR.resolve())):
            return '非法访问', 403
        if not full_path.exists() or not full_path.is_dir():
            return '目录不存在', 404

        # 计算父路径用于返回按钮
        parent_rel = os.path.relpath(str(full_path.parent), str(config.MEDIA_DIR))
        parent_path = parent_rel.replace('\\', '/')
        if parent_path == '.':
            parent_path = ''

        folder_rel = decoded_path.replace('\\', '/')

        # 手动刷新 → 清除节流阀，强制重新扫描
        if request.args.get('refresh') == '1':
            _scanned_folders.discard(str(full_path))

        # 同步 DB 确保 per-disk 表已更新
        _sync_db(str(full_path))

        # 获取分类信息（内部已过滤空文件夹）
        info = get_category_children_info(
            str(full_path), config.RUN_MODE,
            random_mode=config.RANDOM_MODE,
            already_synced=_scanned_folders,
        )

        # 兜底规则：只有一个分类有文件且无根文件 → 直接跳转到网格页面
        if info.get('single_leaf_override') and info['total_categories'] == 1:
            only_cat = info['categories'][0]
            return redirect(f'/category/grid/{only_cat["path"]}?from_override=1')

        # 有非空子文件夹 → 分类页面
        if info['total_categories'] > 0:
            return render_template('category_index.html',
                                   category_info=info,
                                   parent_path=parent_path,
                                   current_path=folder_rel,
                                   is_homepage=False)

        # 叶子或所有子文件夹均无媒体文件 → 网格页面
        return redirect(f'/category/grid/{folder_rel}?from_override=1')

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
    """叶子文件夹的网格页面（36 个/页）"""
    start_time = time.time()
    try:
        decoded_path = urllib.parse.unquote(folder_path)
        full_path = (config.MEDIA_DIR / decoded_path).resolve()

        if not str(full_path).startswith(str(config.MEDIA_DIR.resolve())):
            return '非法访问', 403
        if not full_path.exists() or not full_path.is_dir():
            return '目录不存在', 404

        # 手动刷新 → 清除节流阀，强制重新扫描
        if request.args.get('refresh') == '1':
            _scanned_folders.discard(str(full_path))

        # 同步 DB 确保 per-disk 表已更新
        _sync_db(str(full_path))

        page_size = config.CATEGORY_DETAIL_PAGE_SIZE
        files, has_more = _get_lazy_page_files(
            str(full_path), 0, page_size, config.RUN_MODE
        )

        # 计算父路径
        parent_rel = os.path.relpath(str(full_path.parent), str(config.MEDIA_DIR))
        parent_path = parent_rel.replace('\\', '/')
        if parent_path == '.':
            parent_path = ''

        # 来自兜底/叶子重定向时，向上查找第一个不会触发循环的父级
        hide_back = False
        if request.args.get('from_override', '0') == '1':
            check_path = full_path.parent
            while True:
                if str(check_path.resolve()) == str(config.MEDIA_DIR.resolve()):
                    parent_path = ''
                    if check_browse_would_redirect(config.MEDIA_DIR, already_synced=_scanned_folders):
                        hide_back = True
                    break

                if check_browse_would_redirect(check_path, already_synced=_scanned_folders):
                    check_path = check_path.parent
                else:
                    parent_rel = os.path.relpath(str(check_path), str(config.MEDIA_DIR))
                    parent_path = parent_rel.replace('\\', '/')
                    if parent_path == '.':
                        parent_path = ''
                    break

        return render_template('category_grid.html',
                               files=files,
                               folder_name=full_path.name,
                               folder_path=decoded_path.replace('\\', '/'),
                               parent_path=parent_path,
                               hide_back=hide_back,
                               page_size=page_size,
                               has_more=has_more)
    except Exception as e:
        logger.error(f"category_grid 错误: {e}", exc_info=True)
        return '加载失败', 500
    finally:
        log_access(request, 'CATEGORY_GRID', folder_path,
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

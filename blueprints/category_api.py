"""
目录浏览模式API蓝图
提供分类区块展示接口
"""
import os
import time
import urllib.parse
from pathlib import Path
from datetime import datetime
from flask import Blueprint, request, jsonify, render_template, redirect
from config import config
from utils.logging_utils import log_access, log_exception, logger
from utils.media_utils import get_category_children_info, get_files_in_folder, check_browse_would_redirect
from blueprints.auth import login_required, require_mode

category_bp = Blueprint('category', __name__, url_prefix='/category')


def _media_table(run_mode):
    return 'videos' if run_mode in ('video', 'douyin') else 'images'


# ── DB-first 实现 ─────────────────────────────────────────


def _db_get_conn(run_mode, folder_path):
    """获取 DB 连接并确保当前文件夹已同步，失败返回 None"""
    try:
        db_path = config.DB_PATH
        if not db_path:
            return None
        from utils.db_utils import get_db, ensure_tables, sync_folder
        conn = get_db(db_path)
        ensure_tables(conn)
        if config.MEDIA_DIR:
            sync_folder(conn, str(folder_path), run_mode=run_mode, recursive=True)
        return conn
    except Exception:
        return None


def _format_media_item(name, file_path, media_dir_str):
    """格式化单个媒体项（category 用，不包含 mtime/timestamp）"""
    rel_path = file_path.replace('\\', '/')
    if media_dir_str:
        rel_path = rel_path.replace(media_dir_str.replace('\\', '/') + '/', '', 1)
    return {
        'name': name,
        'relative_path': rel_path,
        'is_video': name.lower().endswith(tuple(config.VIDEO_EXT)),
        'is_image': name.lower().endswith(tuple(config.IMAGE_EXT)),
    }


def _db_category_data(folder_path, run_mode, random_mode=False):
    """从 DB 获取分类结构数据，替代 get_category_children_info

    返回 (success, info_dict) — info_dict 结构与 get_category_children_info 一致
    """
    conn = _db_get_conn(run_mode, folder_path)
    if not conn:
        return False, None

    try:
        from utils.db_utils import get_node_by_path, get_subfolder_nodes, \
            get_media_in_folder, get_random_media_in_folder

        table = _media_table(run_mode)
        folder_path_str = str(folder_path)
        media_dir_str = str(config.MEDIA_DIR.resolve())
        limit_preview = config.CATEGORY_PAGE_SIZE

        # 相对路径
        if folder_path_str == media_dir_str:
            folder_rel_path = ''
        else:
            folder_rel_path = os.path.relpath(folder_path_str, media_dir_str).replace('\\', '/')
        folder_name = os.path.basename(folder_path_str) if folder_rel_path else config.MEDIA_DIR.name

        # 当前文件夹的 node
        node = get_node_by_path(conn, folder_path_str)

        # 子文件夹
        subfolders = []
        if node:
            subfolders = get_subfolder_nodes(conn, node['id'], config.SORT_TYPE, config.SORT_ORDER)
        is_leaf = len(subfolders) == 0

        # 根目录下的直接媒体文件（通过 nodes.parent_id 关联，仅获取直接子文件）
        root_files = []
        if node:
            direct_rows = conn.execute(
                f"""SELECT m.name, m.path
                    FROM {table} m
                    JOIN nodes n ON n.path = m.path
                    WHERE n.parent_id=? AND n.type=2""",
                (node['id'],)
            ).fetchall()
            root_files = [_format_media_item(r[0], r[1], media_dir_str) for r in direct_rows]
            # 排序
            rev = config.SORT_ORDER == 'desc'
            root_files.sort(key=lambda x: x['name'].lower(), reverse=rev)

        # 处理每个子文件夹（分类）
        categories = []
        for sub in subfolders:
            sub_rel_path = os.path.relpath(sub['path'], media_dir_str).replace('\\', '/')

            # 检查子文件夹是否有子文件夹
            sub_subs = get_subfolder_nodes(conn, sub['id'], config.SORT_TYPE, config.SORT_ORDER)
            sub_is_leaf = len(sub_subs) == 0

            # 取预览文件
            if random_mode:
                preview_rows = get_random_media_in_folder(conn, table, sub['path'], limit_preview)
            else:
                preview_rows, _ = get_media_in_folder(
                    conn, table, sub['path'], limit_preview, 0,
                    config.SORT_TYPE, config.SORT_ORDER
                )

            files = [_format_media_item(r['name'], r['path'], media_dir_str) for r in preview_rows]

            has_files = len(files) > 0
            if not has_files and sub_is_leaf:
                continue

            categories.append({
                'name': sub['name'],
                'path': sub_rel_path,
                'is_leaf': sub_is_leaf,
                'files': files,
                'has_files': has_files,
            })

        # 归类到响应结构
        info = {
            'folder_name': folder_name,
            'folder_path': folder_rel_path,
            'is_leaf': is_leaf,
            'categories': categories,
            'root_files': root_files,
            'total_categories': len(categories),
            'single_leaf_override': False,
        }

        if info['total_categories'] == 1 and len(info['root_files']) == 0:
            info['single_leaf_override'] = info['categories'][0]['is_leaf']

        conn.close()
        return True, info

    except Exception:
        conn.close()
        return False, None


def _db_grid_files(folder_path, offset, limit, run_mode):
    """从 DB 分页取网格文件，替代 _get_lazy_page_files

    返回 (success, formatted_files, has_more, next_offset)
    """
    conn = _db_get_conn(run_mode, folder_path)
    if not conn:
        return False, None, False, 0

    try:
        from utils.db_utils import get_media_in_folder, get_random_media_in_folder

        table = _media_table(run_mode)
        folder_path_str = str(folder_path)
        media_dir_str = str(config.MEDIA_DIR.resolve())
        is_random = config.RANDOM_MODE

        if is_random:
            rows = get_random_media_in_folder(conn, table, folder_path_str, limit)
            total = len(rows)
            has_more = len(rows) == limit
        else:
            rows, total = get_media_in_folder(
                conn, table, folder_path_str, limit, offset,
                config.SORT_TYPE, config.SORT_ORDER
            )
            has_more = (offset + len(rows)) < total

        conn.close()

        files = [_format_media_item(r['name'], r['path'], media_dir_str) for r in rows]
        return True, files, has_more, offset + len(files)

    except Exception:
        conn.close()
        return False, None, False, 0


def _db_check_browse_would_redirect(folder_path):
    """从 DB 检查浏览该文件夹时是否会重定向到 grid 页面

    返回 (success, would_redirect)
    """
    ok, info = _db_category_data(str(folder_path), config.RUN_MODE, config.RANDOM_MODE)
    if not ok:
        return False, False

    if info['is_leaf'] or info['total_categories'] == 0:
        return True, True
    if info.get('single_leaf_override') and info['total_categories'] == 1:
        return True, True
    return True, False


# ── Filesystem fallback ────────────────────────────────────


def _get_lazy_page_files(folder_path, offset, limit, run_mode):
    """惰性获取分页文件，不统计总数。
    使用 get_files_in_folder（带缓存）避免重复扫描磁盘。
    返回 (formatted_files, has_more)
    """
    all_files = get_files_in_folder(folder_path)
    page_raw = all_files[offset:offset + limit]
    has_more = (offset + limit) < len(all_files)

    target_ext_video = config.VIDEO_EXT
    target_ext_image = config.IMAGE_EXT

    formatted = []
    for f in page_raw:
        rel_path = f['rel_path'].replace('\\', '/')
        if not rel_path or rel_path == '.':
            rel_path = f['name']
        formatted.append({
            'name': f['name'],
            'relative_path': rel_path,
            'is_video': f['name'].lower().endswith(tuple(target_ext_video)),
            'is_image': f['name'].lower().endswith(tuple(target_ext_image)),
        })

    return formatted, has_more


@category_bp.route('/data')
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

        # DB 优先
        db_ok, db_info = _db_category_data(str(full_path), config.RUN_MODE, config.RANDOM_MODE)
        if db_ok and db_info:
            return jsonify({'code': 0, 'data': db_info})

        # 回退到 filesystem
        info = get_category_children_info(
            str(full_path), config.RUN_MODE,
            random_mode=config.RANDOM_MODE
        )

        return jsonify({'code': 0, 'data': info})
    except Exception as e:
        logger.error(f"category_data 错误: {e}", exc_info=True)
        return jsonify({'code': 1, 'msg': str(e)}), 500
    finally:
        log_access(request, 'CATEGORY_DATA', request.args.get('path', ''),
                   duration=time.time() - start_time)


@category_bp.route('/browse/<path:folder_path>')
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

        # 获取分类信息（内部已过滤空文件夹）
        # DB 优先
        db_ok, db_info = _db_category_data(str(full_path), config.RUN_MODE, config.RANDOM_MODE)
        info = db_info if db_ok and db_info else get_category_children_info(
            str(full_path), config.RUN_MODE,
            random_mode=config.RANDOM_MODE
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


@category_bp.route('/grid/<path:folder_path>')
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

        page_size = config.CATEGORY_DETAIL_PAGE_SIZE

        # DB 优先
        db_ok, files, has_more, _ = _db_grid_files(
            str(full_path), 0, page_size, config.RUN_MODE
        )
        if not db_ok:
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
                    db_ok2, would = _db_check_browse_would_redirect(config.MEDIA_DIR)
                    if not db_ok2:
                        would = check_browse_would_redirect(config.MEDIA_DIR)
                    if would:
                        hide_back = True
                    break

                db_ok2, would = _db_check_browse_would_redirect(check_path)
                if not db_ok2:
                    would = check_browse_would_redirect(check_path)

                if would:
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


@category_bp.route('/grid_more')
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

        # DB 优先
        db_ok, files, has_more, next_offset = _db_grid_files(
            str(full_path), offset, limit, config.RUN_MODE
        )
        if not db_ok:
            files, has_more = _get_lazy_page_files(
                str(full_path), offset, limit, config.RUN_MODE
            )
            next_offset = offset + len(files)

        return jsonify({
            'code': 0,
            'data': files,
            'has_more': has_more,
            'next_offset': next_offset
        })
    except Exception as e:
        logger.error(f"category_grid_more 错误: {e}", exc_info=True)
        return jsonify({'code': 1, 'msg': str(e)}), 500
    finally:
        log_access(request, 'CATEGORY_GRID_MORE', request.args.get('path', ''),
                   duration=time.time() - start_time)

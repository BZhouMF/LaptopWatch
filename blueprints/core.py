"""核心蓝图模块
包含首页、目录浏览等核心路由
"""
import os
import time
from datetime import datetime
from flask import Blueprint, render_template, session, request
from config import config
from utils.file_utils import get_drives
from utils.logging_utils import log_access, log_exception, logger
from utils.media_utils import (
    get_category_children_info,
)
from blueprints.auth import login_required, require_mode

core_bp = Blueprint('core', __name__)

@core_bp.route('/')
@login_required
def index():
    """首页，根据运行模式返回不同内容"""
    start_time = time.time()
    try:
        if config.RUN_MODE == 'normal':
            drives = get_drives()
            return render_template('index.html', drives=drives, MAX_HISTORY_LENGTH=config.MAX_HISTORY_LENGTH)
        elif config.RUN_MODE == 'douyin':
            return render_template('douyin.html',
                                   auto_play=config.DOUYIN_AUTO_PLAY,
                                   muted=config.DOUYIN_MUTED)
        elif config.CATEGORY_BROWSE:
            # 目录浏览模式：按文件夹分区块展示
            info = get_category_children_info(
                str(config.MEDIA_DIR), config.RUN_MODE,
                random_mode=config.RANDOM_MODE
            )

            # 兜底规则：只有一个分类有文件且为叶子 → 直接跳转到网格页面
            if info.get('single_leaf_override') and info['total_categories'] == 1:
                only_cat = info['categories'][0]
                from flask import redirect
                return redirect(f'/category/grid/{only_cat["path"]}?from_override=1')

            return render_template('category_index.html',
                                   category_info=info,
                                   parent_path='',
                                   current_path='',
                                   is_homepage=True)
        else:
            # 媒体模式：DB 优先读取首页数据
            first_page = []
            has_more = False
            try:
                db_path = config.DB_PATH
                if db_path:
                    from utils.db_utils import get_db, ensure_tables, sync_folder, \
                        get_random_media, get_media_page_all
                    conn = get_db(db_path)
                    ensure_tables(conn)
                    if config.MEDIA_DIR:
                        sync_folder(conn, str(config.MEDIA_DIR), run_mode=config.RUN_MODE)

                    table = 'videos' if config.RUN_MODE in ('video', 'douyin') else 'images'
                    if config.RANDOM_MODE:
                        rows = get_random_media(conn, table, config.PAGE_FIRST)
                        has_more = len(rows) == config.PAGE_FIRST
                    else:
                        rows, total = get_media_page_all(conn, table, config.PAGE_FIRST, 0)
                        has_more = len(rows) < total

                    media_dir_str = str(config.MEDIA_DIR).replace('\\', '/') + '/'
                    for r in rows:
                        path = r['path'].replace('\\', '/')
                        rel_path = path.replace(media_dir_str, '', 1) if media_dir_str else path
                        ext = os.path.splitext(r['name'])[1].lower()
                        first_page.append({
                            'name': r['name'],
                            'relative_path': rel_path,
                            'mtime': datetime.fromtimestamp(r['modify_time']).strftime('%Y-%m-%d %H:%M:%S'),
                            'timestamp': r['modify_time'],
                            'is_video': ext in config.VIDEO_EXT,
                            'is_image': ext in config.IMAGE_EXT,
                        })
                    conn.close()
            except Exception:
                logger.debug("首页 DB 读取失败，返回空列表")

            template = 'media_index.html'
            return render_template(template,
                                   media_list=first_page,
                                   page_first=config.PAGE_FIRST,
                                   page_load=config.PAGE_LOAD,
                                   total=0,
                                   total_pages=1,
                                   current_page=1,
                                   has_more=has_more,
                                   config=config)
    except Exception as e:
        import traceback
        logger.error(f"INDEX 路由发生错误: {e}\n{traceback.format_exc()}")
        log_exception(request, 'INDEX', '', e)
        return "首页加载失败", 500
    finally:
        log_access(request, 'INDEX', '', duration=time.time() - start_time)

@core_bp.route('/browse/<path:dirpath>')
@login_required
@require_mode('normal')
def browse(dirpath):
    """目录浏览（普通模式）"""
    start_time = time.time()
    try:
        import os
        abs_path = os.path.abspath(dirpath)
        if not os.path.exists(abs_path):
            return render_template('unpage.html'), 404
        if os.path.isfile(abs_path):
            from utils.file_utils import safe_send_file
            return safe_send_file(abs_path, as_attachment=True)

        # 实时增量同步：用户点击时仅核对当前文件夹
        if config.MEDIA_DIR and config.DB_PATH:
            try:
                from utils.db_utils import get_db, sync_folder
                db_conn = get_db(config.DB_PATH)
                sync_folder(db_conn, abs_path, run_mode='normal')
                db_conn.close()
            except Exception:
                pass  # 同步失败不影响浏览

        parent_path = os.path.dirname(abs_path)
        parent_link = '/' if os.path.ismount(abs_path) else f'/browse/{parent_path.replace(os.sep, "/")}'
        return render_template('browse.html',
                               abs_path=abs_path,
                               parent_link=parent_link,
                               btn_text='返回上一级',
                               MAX_HISTORY_LENGTH=config.MAX_HISTORY_LENGTH)
    except Exception as e:
        log_exception(request, 'BROWSE', dirpath, e)
        return "浏览失败", 500
    finally:
        log_access(request, 'BROWSE', dirpath, duration=time.time() - start_time)

@core_bp.route('/favicon.ico')
def favicon():
    """空favicon响应"""
    return '', 204

# ==================== 旧版路由兼容重定向 ====================
# 以下路由为历史遗留的兼容性重定向，将旧版URL映射到新的蓝图前缀

@core_bp.route('/serve_media/<path:relative_path>')
@login_required
def redirect_serve_media(relative_path):
    """兼容重定向：旧版 /serve_media/ -> 新版 /media/serve_media/"""
    from flask import redirect
    return redirect(f'/media/serve_media/{relative_path}')

@core_bp.route('/load_more')
@login_required
def redirect_load_more():
    """兼容重定向：旧版 /load_more -> 新版 /media/load_more"""
    from flask import redirect, request
    query_string = request.query_string.decode('utf-8') if request.query_string else ''
    url = f'/media/load_more'
    if query_string:
        url += f'?{query_string}'
    return redirect(url)

@core_bp.route('/raw/<path:filepath>')
@login_required
def redirect_raw(filepath):
    """兼容重定向：旧版 /raw/ -> 新版 /file/raw/"""
    from flask import redirect, request
    query_string = request.query_string.decode('utf-8') if request.query_string else ''
    url = f'/file/raw/{filepath}'
    if query_string:
        url += f'?{query_string}'
    return redirect(url)

@core_bp.route('/view/<path:filepath>')
@login_required
def redirect_view(filepath):
    """兼容重定向：旧版 /view/ -> 新版 /file/view/"""
    from flask import redirect, request
    query_string = request.query_string.decode('utf-8') if request.query_string else ''
    url = f'/file/view/{filepath}'
    if query_string:
        url += f'?{query_string}'
    return redirect(url)

@core_bp.route('/text/<path:filepath>')
@login_required
def redirect_text(filepath):
    """兼容重定向：旧版 /text/ -> 新版 /file/text/"""
    from flask import redirect, request
    query_string = request.query_string.decode('utf-8') if request.query_string else ''
    url = f'/file/text/{filepath}'
    if query_string:
        url += f'?{query_string}'
    return redirect(url)

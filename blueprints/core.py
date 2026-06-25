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


@core_bp.route('/setup', methods=['GET'])
def setup_page():
    """启动配置页面（桌面 App 入口，替代 tkinter GUI）"""
    import socket
    from utils.process_utils import get_local_ip
    lan_ip = get_local_ip()
    local_url = 'http://127.0.0.1:5000'
    lan_url = f'http://{lan_ip}:5000' if lan_ip else ''
    return render_template('setup.html',
                          local_url=local_url,
                          lan_url=lan_url,
                          current_mode=config.RUN_MODE,
                          media_dir=str(config.MEDIA_DIR) if config.MEDIA_DIR else '')


@core_bp.route('/', methods=['GET'])
@login_required
def index():
    """首页，根据运行模式返回不同内容"""
    start_time = time.time()
    try:
        if config.RUN_MODE == 'normal':
            drives = get_drives()
            return render_template('index.html', drives=drives, MAX_HISTORY_LENGTH=config.MAX_HISTORY_LENGTH)
        elif config.RUN_MODE == 'douyin':
            # 同步 DB 确保所有表已更新
            try:
                if config.DB_PATH and config.MEDIA_DIR:
                    from utils.db_utils import get_db, sync_folder
                    conn = get_db()
                    sync_folder(conn, str(config.MEDIA_DIR))
                    conn.close()
            except Exception:
                logger.debug("抖音模式首页 DB 同步失败")

            return render_template('douyin.html',
                                   auto_play=config.DOUYIN_AUTO_PLAY,
                                   muted=config.DOUYIN_MUTED,
                                   native_fullscreen=config.NATIVE_FULLSCREEN)
        elif config.CATEGORY_BROWSE:
            # 先同步所有文件到 DB
            try:
                if config.DB_PATH and config.MEDIA_DIR:
                    from utils.db_utils import get_db, sync_folder
                    conn = get_db()
                    sync_folder(conn, str(config.MEDIA_DIR))
                    conn.close()
            except Exception:
                logger.debug("目录浏览模式 DB 同步失败，回退到文件系统")

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
                                   view_type='category',
                                   category_info=info,
                                   parent_path='',
                                   current_path='',
                                   is_homepage=True)
        else:
            # 媒体模式：文件夹遍历器，按需核实
            first_page = []
            has_more = False
            total_count = 0
            try:
                if config.DB_PATH and config.MEDIA_DIR:
                    from utils.db_utils import get_db, traverse_media, init_tables, sync_folder, _format_media_row
                    import os as _os
                    import random as _random
                    conn = get_db()
                    media_type = 'video' if config.RUN_MODE == 'video' else 'image'

                    if config.RANDOM_MODE:
                        init_tables(conn)
                        sync_folder(conn, str(config.MEDIA_DIR))

                        seed_key = '_random_seed_' + config.RUN_MODE
                        if seed_key not in session:
                            session[seed_key] = _random.randint(0, 2 ** 31 - 1)
                        seed = session[seed_key]

                        media_prefix = _os.path.abspath(str(config.MEDIA_DIR)).rstrip(_os.sep) + _os.sep
                        all_ids = [
                            row[0] for row in conn.execute(
                                "SELECT m.id FROM media m JOIN nodes n ON n.path = m.path "
                                "WHERE m.media_type = ? AND n.type = 2 AND m.path LIKE ?",
                                (media_type, media_prefix + '%'),
                            ).fetchall()
                        ]

                        rng = _random.Random(seed)
                        rng.shuffle(all_ids)

                        total_count = len(all_ids)
                        page_ids = all_ids[0:config.PAGE_FIRST]

                        if page_ids:
                            ph = ','.join('?' for _ in page_ids)
                            rows = conn.execute(
                                f"SELECT id, parent_id, name, path, modify_time, media_type "
                                f"FROM media WHERE id IN ({ph})",
                                page_ids,
                            ).fetchall()
                            row_map = {r['id']: r for r in rows}
                            rows = [row_map[mid] for mid in page_ids if mid in row_map]
                        else:
                            rows = []

                        for r in rows:
                            first_page.append(_format_media_row(r))
                        has_more = (config.PAGE_FIRST < total_count)
                    else:
                        first_page, _, has_more = traverse_media(
                            conn, str(config.MEDIA_DIR), media_type,
                            offset=0, limit=config.PAGE_FIRST,
                            sort_type=config.SORT_TYPE,
                            sort_order=config.SORT_ORDER,
                            random_start=False,
                        )
                    conn.close()
            except Exception:
                logger.debug("首页 DB 读取失败，返回空列表")

            template = 'media_index.html'
            total_pages = 2 if has_more else 1
            return render_template(template,
                                   media_list=first_page,
                                   page_first=config.PAGE_FIRST,
                                   page_load=config.PAGE_LOAD,
                                   total=total_count,
                                   total_pages=total_pages,
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

@core_bp.route('/browse/<path:dirpath>', methods=['GET'])
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

@core_bp.route('/api/drives', methods=['GET'])
@login_required
def api_drives():
    """返回可用驱动器列表"""
    return {'drives': get_drives()}


@core_bp.route('/favicon.ico', methods=['GET'])
def favicon():
    """空favicon响应"""
    return '', 204

# ==================== 旧版路由兼容重定向 ====================
# 以下路由为历史遗留的兼容性重定向，将旧版URL映射到新的蓝图前缀

@core_bp.route('/serve_media/<path:relative_path>', methods=['GET'])
@login_required
def redirect_serve_media(relative_path):
    """兼容重定向：旧版 /serve_media/ -> 新版 /media/serve_media/"""
    from flask import redirect
    return redirect(f'/media/serve_media/{relative_path}')

@core_bp.route('/load_more', methods=['GET'])
@login_required
def redirect_load_more():
    """兼容重定向：旧版 /load_more -> 新版 /media/load_more"""
    from flask import redirect, request
    query_string = request.query_string.decode('utf-8') if request.query_string else ''
    url = f'/media/load_more'
    if query_string:
        url += f'?{query_string}'
    return redirect(url)

@core_bp.route('/raw/<path:filepath>', methods=['GET'])
@login_required
def redirect_raw(filepath):
    """兼容重定向：旧版 /raw/ -> 新版 /file/raw/"""
    from flask import redirect, request
    query_string = request.query_string.decode('utf-8') if request.query_string else ''
    url = f'/file/raw/{filepath}'
    if query_string:
        url += f'?{query_string}'
    return redirect(url)

@core_bp.route('/view/<path:filepath>', methods=['GET'])
@login_required
def redirect_view(filepath):
    """兼容重定向：旧版 /view/ -> 新版 /file/view/"""
    from flask import redirect, request
    query_string = request.query_string.decode('utf-8') if request.query_string else ''
    url = f'/file/view/{filepath}'
    if query_string:
        url += f'?{query_string}'
    return redirect(url)

@core_bp.route('/text/<path:filepath>', methods=['GET'])
@login_required
def redirect_text(filepath):
    """兼容重定向：旧版 /text/ -> 新版 /file/text/"""
    from flask import redirect, request
    query_string = request.query_string.decode('utf-8') if request.query_string else ''
    url = f'/file/text/{filepath}'
    if query_string:
        url += f'?{query_string}'
    return redirect(url)


# ── Setup 页面 API ──

@core_bp.route('/api/start_service', methods=['POST'])
def api_start_service():
    """应用配置并更新运行时参数，生成二维码"""
    settings = request.get_json(silent=True) or {}

    mode = settings.get('mode')
    if mode:
        config.RUN_MODE = mode

    media_dir = settings.get('media_dir')
    if media_dir:
        from pathlib import Path
        config.MEDIA_DIR = Path(media_dir).resolve()

    sort_type = settings.get('sort_type')
    if sort_type:
        config.SORT_TYPE = sort_type

    sort_order = settings.get('sort_order')
    if sort_order:
        config.SORT_ORDER = sort_order

    config.RANDOM_MODE = settings.get('random', False)
    config.DOUYIN_RANDOM_MEDIA = settings.get('douyin_random', False)
    config.CATEGORY_BROWSE = settings.get('category_browse', False)

    from utils.process_utils import get_local_ip
    lan_ip = get_local_ip()
    lan_url = f'http://{lan_ip}:5000' if lan_ip else ''
    local_url = 'http://127.0.0.1:5000'

    # 生成二维码
    qr_base64 = ''
    try:
        import qrcode
        from PIL import Image
        import base64
        from io import BytesIO
        qr = qrcode.QRCode(box_size=4, border=1)
        qr.add_data(lan_url or local_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white').convert('RGB')
        img = img.resize((150, 150))
        buf = BytesIO()
        img.save(buf, format='PNG')
        qr_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    except Exception:
        pass

    return {
        'code': 0,
        'msg': '配置已应用',
        'local_url': local_url,
        'lan_url': lan_url,
        'qr_base64': qr_base64,
        'settings': settings,
    }


@core_bp.route('/api/stop_service', methods=['POST'])
def api_stop_service():
    """停止服务，重置为 normal 模式"""
    config.RUN_MODE = 'normal'
    config.MEDIA_DIR = None
    config.RANDOM_MODE = False
    config.DOUYIN_RANDOM_MEDIA = False
    config.CATEGORY_BROWSE = False
    return {'code': 0, 'msg': '服务已停止'}

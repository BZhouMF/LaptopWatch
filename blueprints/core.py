"""核心蓝图模块
包含 API 路由、旧版兼容重定向和 Setup 配置接口
"""
from flask import Blueprint, request, session
from config import config
from utils.file_utils import get_drives
from utils.logging_utils import logger
from blueprints.auth import login_required

core_bp = Blueprint('core', __name__)


@core_bp.route('/api/drives', methods=['GET'])
@login_required
def api_drives():
    """返回可用驱动器列表"""
    return {'drives': get_drives()}


@core_bp.route('/api/mode', methods=['GET'])
def api_mode():
    """返回当前运行模式及配置"""
    return {
        'run_mode': config.RUN_MODE,
        'category_browse': config.CATEGORY_BROWSE,
        'random_mode': config.RANDOM_MODE,
        'douyin_random_media': config.DOUYIN_RANDOM_MEDIA,
        'page_first': config.PAGE_FIRST,
        'page_load': config.PAGE_LOAD,
        'video_port': config.VIDEO_SERVE_PORT,
    }


@core_bp.route('/favicon.ico', methods=['GET'])
def favicon():
    """空favicon响应"""
    return '', 204

@core_bp.route('/api/config-version', methods=['GET'])
def api_config_version():
    """返回当前配置版本号 — 供 React 前端轮询检测配置变更"""
    return {
        'version': config.CONFIG_VERSION,
        'service_active': config.SERVICE_ACTIVE,
    }

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
    config.DOUYIN_RANDOM_MEDIA = settings.get('douyin_random', True)
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


@core_bp.route('/api/admin/config', methods=['POST'])
def api_admin_config():
    """运行时更新配置 — 支持 session 登录或 X-Auth-Password 头部认证"""
    # ── 认证：优先 session，其次密码头部 ──
    if not session.get('logged_in'):
        password = request.headers.get('X-Auth-Password', '')
        if password != config.DEFAULT_PASSWORD:
            return {'code': 1, 'msg': '未授权'}, 401

    body = request.get_json(silent=True) or {}

    mode = body.get('mode')
    category_browse = body.get('category_browse')
    random_mode = body.get('random_mode')
    douyin_random_media = body.get('douyin_random_media')
    service_active = body.get('service_active')
    media_dir = body.get('media_dir')

    if mode is not None and mode not in ('normal', 'video', 'image', 'douyin'):
        return {'code': 1, 'msg': f'无效的运行模式: {mode}'}, 400

    ok, result = config.update_runtime(
        mode=mode,
        category_browse=category_browse,
        random_mode=random_mode,
        douyin_random_media=douyin_random_media,
        service_active=service_active,
        media_dir=media_dir,
    )
    if not ok:
        return result, 400

    logger.info(f'[ADMIN] 运行时配置已更新: {result}')
    return {'code': 0, 'msg': '配置已更新', 'config': result}

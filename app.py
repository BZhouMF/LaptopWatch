"""
LaptopWatch - 主应用程序入口
模块化重构版本
"""
import os
import sys
import time
from datetime import timedelta
from pathlib import Path
# from config import IS_DEBUG

# ==================== 打包exe资源路径适配 ====================
if getattr(sys, 'frozen', False):
    base_path = Path(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))))
else:
    base_path = Path(__file__).parent
# ==================== 适配代码结束 ====================

# 导入配置
from config import config

# 导入日志工具并初始化
from utils.logging_utils import setup_logging, logger

# 初始化日志
setup_logging()

# 导入蓝图
from blueprints.auth import auth_bp
from blueprints.core import core_bp
from blueprints.normal_api import normal_bp
from blueprints.media_api import media_bp
from blueprints.file_api import file_bp
from blueprints.douyin_api import douyin_bp
from blueprints.category_api import category_bp

# 导入缩略图工具以初始化后端状态
from utils.thumbnail_utils import log_thumbnail_backend_status

# 创建Flask应用
from flask import Flask, jsonify

app = Flask(
    __name__,
    template_folder=config.TEMPLATE_FOLDER,
    static_folder=config.STATIC_FOLDER,
    static_url_path=config.STATIC_URL_PATH
)

# 应用配置
app.secret_key = config.SECRET_KEY
app.permanent_session_lifetime = timedelta(hours=config.SESSION_LIFETIME_HOURS)

# 注册蓝图
app.register_blueprint(auth_bp)
app.register_blueprint(core_bp)
app.register_blueprint(normal_bp)
app.register_blueprint(media_bp)
app.register_blueprint(file_bp)
app.register_blueprint(douyin_bp)
app.register_blueprint(category_bp)

# ==================== 请求日志中间件 ====================
# 不需要记录到 stdout 的请求路径前缀
_SILENT_PREFIXES = ('/static/', '/favicon.ico', '/media/thumbnail/', '/media/navigate', '/media/serve_media/')


@app.before_request
def log_incoming_request():
    """记录到达的请求，静默跳过无分析价值的请求"""
    from flask import request
    from utils.logging_utils import _safe_print
    if 'Range' in request.headers:
        return
    if request.path.startswith(_SILENT_PREFIXES):
        return
    _safe_print(f"[REQUEST] {request.remote_addr} -> {request.method} {request.path}", flush=True)

# 注入前端路由常量到所有模板
from routes_config import FRONTEND_ROUTES


@app.context_processor
def inject_routes():
    """注入前端路由常量，mediaServe 动态拼接（支持 LAN 访问不同主机 IP）"""
    from flask import request
    host = request.host.split(':')[0]
    routes = dict(FRONTEND_ROUTES)
    routes['mediaServe'] = f'http://{host}:{config.VIDEO_SERVE_PORT}/media/serve_media/'
    return {'ROUTES': routes, 'config': config}


@app.template_filter('path_quote')
def path_quote_filter(path):
    """URL 编码路径中除斜杠以外的特殊字符"""
    from urllib.parse import quote
    return quote(path, safe='/')


# 记录视频缩略图后端状态
log_thumbnail_backend_status()

# 记录启动信息
logger.info(f"启动模式: {config.RUN_MODE}")
if config.RUN_MODE != 'normal' and config.MEDIA_DIR:
    logger.info(f"媒体目录: {config.MEDIA_DIR}")
if config.RUN_MODE == 'douyin':
    logger.info(f"抖音自动播放: {config.DOUYIN_AUTO_PLAY}")
    logger.info(f"抖音默认静音: {config.DOUYIN_MUTED}")
logger.info(f"分页配置: PAGE_FIRST={config.PAGE_FIRST}, PAGE_LOAD={config.PAGE_LOAD}")

# ── 祖先链由各 API 内部的 traverse_media / sync_folder 按需确认，启动时不执行全量同步 ──

# ==================== 全局异常处理器 ====================
from werkzeug.exceptions import HTTPException

@app.errorhandler(Exception)
def handle_unhandled_exception(e):
    """捕获所有未处理的异常，记录到日志并返回500错误"""
    # 跳过HTTP异常（404等），让Flask默认处理
    if isinstance(e, HTTPException):
        return e

    from flask import request
    import traceback
    from utils.logging_utils import _safe_print

    # 用 _safe_print 避免 Windows GBK 编码问题
    error_msg = f"服务器内部错误: {str(e)}"
    try:
        path_info = f" - 路径: {request.path} - IP: {request.remote_addr}"
        error_msg += path_info
    except Exception:
        pass

    logger.error(error_msg, exc_info=True)
    tb = traceback.format_exc()
    _safe_print(f"[ERROR] {error_msg}", flush=True)
    _safe_print(tb, flush=True)

    # 同时写入日志文件确保不丢失
    try:
        error_log_path = config.LOG_DIR / 'error_traceback.txt'
        error_log_path.parent.mkdir(exist_ok=True, parents=True)
        with open(error_log_path, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{error_msg}\n")
            f.write(tb)
    except Exception:
        pass

    return "服务器内部错误", 500

# ==================== React SPA 静态资源 ====================
@app.route('/assets/<path:filename>')
def serve_react_assets(filename):
    """Serve React built static assets (JS/CSS)"""
    from flask import send_from_directory
    assets_dir = config.REACT_DIST_DIR / 'assets'
    if assets_dir.is_dir():
        return send_from_directory(str(assets_dir), filename)
    return '', 404


# ==================== 404错误处理器 ====================
@app.errorhandler(404)
def handle_not_found(e):
    """处理404错误：API返回JSON，页面请求返回React SPA入口"""
    from flask import request, send_file
    api_prefixes = ('/api/', '/media/', '/file/', '/category/', '/login', '/logout', '/register')
    if any(request.path.startswith(p) for p in api_prefixes):
        logger.debug(f"404 Not Found (API): {request.path}")
        return jsonify({'code': 1, 'msg': '请求的资源不存在'}), 404
    react_index = config.REACT_DIST_DIR / 'index.html'
    if react_index.is_file():
        return send_file(str(react_index))
    logger.debug(f"404 Not Found: {request.path}")
    return jsonify({'code': 1, 'msg': '请求的资源不存在'}), 404

# ==================== 启动 ====================
if __name__ == '__main__':
    import threading
    import uvicorn
    from waitress import serve
    from video_server import video_app

    # 1. FastAPI 视频服务（异步线程，专用于大文件流式传输）
    fastapi_ready = threading.Event()

    def _run_fastapi():
        uvicorn_config = uvicorn.Config(
            video_app, host='0.0.0.0', port=config.VIDEO_SERVE_PORT,
            log_level='warning',
        )
        server = uvicorn.Server(uvicorn_config)
        fastapi_ready.set()
        server.run()

    threading.Thread(target=_run_fastapi, daemon=True).start()
    fastapi_ready.wait(timeout=5)

    # 2. Flask 主应用（页面渲染 + API + 鉴权）
    port = int(os.getenv('LAPTOPWATCH_PORT', 5002))
    print(f"LaptopWatch 启动中... 模式: {config.RUN_MODE}")
    print(f"  Flask  (页面/API): http://0.0.0.0:{port}")
    print(f"  FastAPI (视频流):  http://0.0.0.0:{config.VIDEO_SERVE_PORT}")
    serve(app, host='0.0.0.0', port=port, threads=16)
"""
日志工具函数
"""
import os
import json
import time
import uuid
import logging
from pathlib import Path
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from flask import session, request

from config import config
from utils.cache_utils import cache_manager

def _safe_print(*args, **kwargs):
    """安全打印，处理 Windows 控制台输出异常"""
    try:
        print(*args, **kwargs)
    except (UnicodeEncodeError, OSError):
        import sys
        encoding = sys.stdout.encoding or 'utf-8'
        try:
            safe_args = []
            for arg in args:
                if isinstance(arg, str):
                    safe_args.append(arg.encode(encoding, errors='replace').decode(encoding))
                else:
                    safe_args.append(arg)
            print(*safe_args, **kwargs)
        except OSError:
            pass

# 自定义结构化日志格式化器
class StructuredFormatter(logging.Formatter):
    def format(self, record):
        if not config.LOG_STRUCTURED:
            return super().format(record)

        # 基础日志字段（精简版）
        log_data = {
            'time': datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S'),
            'level': record.levelname,
            'ip': record.context.get('client_ip', 'unknown') if hasattr(record, 'context') else 'unknown',
            'action': record.context.get('action', 'unknown') if hasattr(record, 'context') else 'unknown',
            'path': record.context.get('target_path', '') if hasattr(record, 'context') else '',
            'duration': record.context.get('duration', 0) if hasattr(record, 'context') else 0,
            'msg': record.getMessage()
        }

        return json.dumps(log_data, ensure_ascii=False)

# 配置日志系统
def setup_logging():
    """初始化日志配置"""
    root_logger = logging.getLogger()
    root_logger.setLevel(config.LOG_LEVEL)

    # 清除默认处理器
    root_logger.handlers.clear()

    # 检查是否通过 GUI 启动（通过环境变量判断）
    is_gui_launch = os.environ.get('LAPTOPWATCH_GUI_LAUNCH') == '1'

    # 控制台处理器（GUI模式只输出WARNING及以上级别，非GUI模式输出全部）
    console_handler = logging.StreamHandler()
    if is_gui_launch:
        # GUI模式：只输出警告和错误，避免过多日志阻塞GUI
        console_handler.setLevel(logging.WARNING)
    else:
        console_handler.setLevel(config.LOG_LEVEL)

    if config.LOG_STRUCTURED:
        console_formatter = StructuredFormatter()
    else:
        # 精简文本日志格式，只保留核心信息
        console_formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 文件轮转处理器（始终开启，确保日志总是写入文件）
    # 创建日志目录
    config.LOG_DIR.mkdir(exist_ok=True, parents=True)
    log_file = config.LOG_DIR / 'laptopwatch.log'
    file_handler = TimedRotatingFileHandler(
        str(log_file),
        when='midnight',
        interval=1,
        backupCount=config.LOG_RETENTION,
        encoding='utf-8'
    )
    file_handler.setLevel(config.LOG_LEVEL)
    if config.LOG_STRUCTURED:
        file_formatter = StructuredFormatter()
    else:
        file_formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # 关闭werkzeug默认访问日志（仅保留ERROR）
    logging.getLogger('werkzeug').setLevel(logging.ERROR)

def get_session_id():
    """获取或生成会话唯一ID（优化：确保session可用）"""
    try:
        if 'session_id' not in session:
            session['session_id'] = str(uuid.uuid4())
        return session['session_id']
    except Exception:
        return 'unknown'

def log_access(request_obj, action, path, details='', duration=0):
    """
    统一记录访问日志（优化版：精简日志内容）
    :param request_obj: Flask请求对象
    :param action: 操作类型（大写英文）
    :param path: 操作路径
    :param details: 额外信息
    :param duration: 操作耗时（秒）
    """
    # 清理过期缓存
    cache_manager.clean_preview_cache()

    # 标准化路径分隔符为正斜杠，确保日志一致性
    normalized_path = path.replace('\\', '/') if path else ''

    # 生成日志上下文（精简字段）
    context = {
        'session_id': get_session_id(),
        'client_ip': request_obj.remote_addr or 'unknown',
        'action': action,
        'target_path': normalized_path,
        'duration': round(duration, 3),
    }

    # 预览去重：同一会话同一文件仅记录一次
    if action in ('PREVIEW', 'RAW_PREVIEW'):
        cache_key = (context['session_id'], normalized_path)
        if cache_manager.check_and_set_preview_cache(cache_key):
            return

    # 精简日志消息格式，只保留核心信息
    log_msg = f"{context['client_ip']} | {action} | {normalized_path}"
    if details:
        log_msg += f" | {details}"
    if duration > 0:
        log_msg += f" | 耗时: {duration:.3f}s"

    # 记录日志
    logger = logging.getLogger(__name__)
    logger.info(log_msg, extra={'context': context})

    # 仅对用户主动操作输出到 stdout（GUI 用此信息显示实时活动）
    if action in ('INDEX', 'BROWSE', 'LOGIN', 'LOGOUT',
                  'DOWNLOAD', 'DOWNLOAD_MEDIA', 'DOWNLOAD_FOLDER', 'DOWNLOAD_SELECTED',
                  'LOAD_MORE', 'MEDIA_NAV', 'MEDIA_PLAY', 'MEDIA_VIEW',
                  'DOUYIN_INIT', 'DOUYIN_NEXT'):
        _safe_print(f"[ACCESS][{action}] {log_msg}", flush=True)


def log_exception(request_obj, action, path, exc: Exception):
    """统一记录异常日志（精简版）"""
    # 标准化路径分隔符为正斜杠，确保日志一致性
    normalized_path = path.replace('\\', '/') if path else ''

    context = {
        'session_id': get_session_id(),
        'client_ip': request_obj.remote_addr or 'unknown',
        'action': action,
        'target_path': normalized_path,
    }
    logger = logging.getLogger(__name__)
    error_msg = f"{context['client_ip']} | {action} | {normalized_path} | 异常: {str(exc)[:100]}"
    logger.error(
        error_msg,
        extra={'context': context},
        exc_info=True
    )
    # 同时输出到标准输出，确保GUI能捕获到错误信息
    _safe_print(f"[ERROR] {error_msg}", flush=True)

# 创建模块级logger
logger = logging.getLogger(__name__)
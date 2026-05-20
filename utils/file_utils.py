"""
文件操作工具函数
"""
import os
import mimetypes
from flask import send_from_directory
from config import config

# mimetypes 标准库未覆盖的视频/图片格式补充映射
_MIME_SUPPLEMENT = {
    '.m4v': 'video/mp4',
    '.mp4v': 'video/mp4',
    '.ogv': 'video/ogg',
    '.divx': 'video/x-msvideo',
    '.f4v': 'video/x-flv',
    '.flv': 'video/x-flv',
    '.m2t': 'video/mp2t',
    '.m2ts': 'video/mp2t',
    '.mts': 'video/mp2t',
    '.ts': 'video/mp2t',
    '.m2v': 'video/mpeg',
    '.mpv': 'video/mpeg',
    '.rmvb': 'application/vnd.rn-realmedia-vbr',
    '.vob': 'video/dvd',
    '.h264': 'video/h264',
    '.hevc': 'video/hevc',
    '.264': 'video/h264',
    '.265': 'video/hevc',
    '.mqv': 'video/quicktime',
    '.xvid': 'video/x-msvideo',
}


def get_mime_type(filepath):
    """获取文件的MIME类型，先尝试标准库，再使用补充映射"""
    mime_type, _ = mimetypes.guess_type(filepath)
    if mime_type is None:
        ext = os.path.splitext(filepath)[1].lower()
        mime_type = _MIME_SUPPLEMENT.get(ext, 'application/octet-stream')
    return mime_type


def get_drives():
    """获取Windows驱动器列表"""
    drives = []
    for drive in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        drive_path = f'{drive}:\\'
        if os.path.exists(drive_path):
            drives.append(drive)
    return drives

def get_icon(filename):
    """获取文件 emoji 图标"""
    ext = os.path.splitext(filename)[1].lower()
    if ext in config.IMAGE_EXT:
        return '🖼️'
    elif ext in config.VIDEO_EXT:
        return '🎬'
    elif ext in ['.txt', '.md']:
        return '📝'
    elif ext == '.py':
        return '🐍'
    elif ext in ['.html', '.css', '.js']:
        return '🌐'
    elif ext in ['.json', '.xml']:
        return '📋'
    elif ext in ['.zip', '.rar', '.7z']:
        return '📦'
    else:
        return '📄'

def sizeof_fmt(num, suffix='B'):
    """格式化文件大小"""
    for unit in ['', 'K', 'M', 'G', 'T']:
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Y{suffix}"

def safe_send_file(abs_path, as_attachment):
    """安全发送文件，处理权限异常"""
    try:
        directory = os.path.dirname(abs_path)
        filename = os.path.basename(abs_path)
        return send_from_directory(directory, filename, as_attachment=as_attachment)
    except PermissionError as e:
        from utils.logging_utils import logger
        logger.error(f"无权访问文件 {abs_path}: {e}", exc_info=True)
        return "[ERROR] 无权访问此文件", 403
    except Exception as e:
        from utils.logging_utils import logger
        logger.error(f"打开文件出错 {abs_path}: {e}", exc_info=True)
        return f"[ERROR] 打开文件出错: {str(e)}", 500
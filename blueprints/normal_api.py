"""
普通模式API蓝图
包含普通模式下的API接口
"""
import os
import time
import urllib.parse
from flask import Blueprint, request, jsonify
from config import config
from utils.logging_utils import log_access, log_exception, logger
from utils.file_utils import get_icon, sizeof_fmt
from blueprints.auth import login_required, require_mode

normal_bp = Blueprint('normal_api', __name__, url_prefix='/api')

@normal_bp.route('/check_path')
@login_required
@require_mode('normal')
def api_check_path():
    """检查路径是否存在"""
    start_time = time.time()
    try:
        path = request.args.get('path', '')
        if not path or path == '/':
            return jsonify({'exists': True, 'is_dir': True})
        try:
            # 解码URL路径
            decoded_path = urllib.parse.unquote(path)
            exists = os.path.exists(decoded_path)
            is_dir = os.path.isdir(decoded_path) if exists else False
            return jsonify({'exists': exists, 'is_dir': is_dir})
        except Exception as e:
            logger.error(f"检查路径异常 {path}: {e}")
            return jsonify({'exists': False, 'is_dir': False})
    except Exception as e:
        log_exception(request, 'CHECK_PATH', path, e)
        return jsonify({'error': '检查失败'}), 500
    finally:
        log_access(request, 'CHECK_PATH', locals().get('path', ''), duration=time.time() - start_time)

@normal_bp.route('/list')
@login_required
@require_mode('normal')
def api_list():
    """获取文件列表（支持分页、排序）"""
    start_time = time.time()
    try:
        path = request.args.get('path')
        typ = request.args.get('type', 'files')
        sort = request.args.get('sort', 'name')
        order = request.args.get('order', 'asc')
        offset = int(request.args.get('offset', 0))
        limit = int(request.args.get('limit', 20))
        # 解码URL路径
        if path:
            path = urllib.parse.unquote(path)
        if not path or not os.path.exists(path):
            return jsonify({'error': '路径无效'}), 400
        folders, files = [], []
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            try:
                                stat = entry.stat(follow_symlinks=False)
                                mtime = stat.st_mtime
                            except Exception as e:
                                logger.warning(f"获取文件状态失败 {entry.path}: {e}")
                                mtime = 0
                            folders.append({
                                'name': entry.name,
                                'path': entry.path,
                                'mtime': mtime,
                                'size': 0,
                                'date': time.strftime('%Y-%m-%d %H:%M', time.localtime(mtime)) if mtime else '未知',
                                'icon': '📁'
                            })
                        else:
                            try:
                                stat = entry.stat(follow_symlinks=False)
                                mtime = stat.st_mtime
                                size = stat.st_size
                            except Exception as e:
                                logger.warning(f"获取文件状态失败 {entry.path}: {e}")
                                continue
                            files.append({
                                'name': entry.name,
                                'path': entry.path,
                                'mtime': mtime,
                                'size': size,
                                'date': time.strftime('%Y-%m-%d %H:%M', time.localtime(mtime))
                            })
                    except Exception as e:
                        logger.warning(f"处理文件条目失败 {entry.path if 'entry' in locals() else 'unknown'}: {e}")
                        continue
        except Exception as e:
            return jsonify({'error': f'无法读取目录: {str(e)}'}), 500
        reverse = (order == 'desc')
        if sort == 'date':
            folders.sort(key=lambda x: x['mtime'], reverse=reverse)
            files.sort(key=lambda x: x['mtime'], reverse=reverse)
        elif sort == 'size':
            folders.sort(key=lambda x: x['size'], reverse=reverse)
            files.sort(key=lambda x: x['size'], reverse=reverse)
        else:
            folders.sort(key=lambda x: x['name'].lower(), reverse=reverse)
            files.sort(key=lambda x: x['name'].lower(), reverse=reverse)
        if typ == 'folders':
            return jsonify(folders)
        total = len(files)
        paged = files[offset:offset + limit]
        items = []
        for f in paged:
            try:
                ext = os.path.splitext(f['name'])[1].lower()
                is_video = ext in config.VIDEO_EXT
                is_image = ext in config.IMAGE_EXT
                is_text = ext in ['.txt', '.py', '.html', '.css', '.js', '.json', '.xml', '.md']
                items.append({
                    'name': f['name'],
                    'path': f['path'],
                    'thumb': None,
                    'icon': get_icon(f['name']),
                    'is_video': is_video,
                    'is_image': is_image,
                    'is_previewable': (is_image or is_video) and (not is_image or f['size'] <= config.MAX_IMAGE_SIZE),
                    'is_text_readable': is_text and f['size'] < 1024 * 1024,
                    'raw_url': f"/file/raw/{f['path'].replace(os.sep, '/')}",
                    'date': f['date'],
                    'size': sizeof_fmt(f['size'])
                })
            except Exception as e:
                logger.warning(f"处理文件项失败 {f['path'] if 'f' in locals() else 'unknown'}: {e}")
                continue
        return jsonify({'items': items, 'has_more': offset + limit < total})
    except Exception as e:
        log_exception(request, 'API_LIST', path, e)
        return jsonify({'error': '列表获取失败'}), 500
    finally:
        log_access(request, 'API_LIST', locals().get('path', ''), f'type={locals().get("typ", "")} offset={locals().get("offset", 0)}', duration=time.time() - start_time)

@normal_bp.route('/list_all')
@login_required
@require_mode('normal')
def api_list_all():
    """获取所有文件列表（无分页）"""
    start_time = time.time()
    try:
        path = request.args.get('path')
        # 解码URL路径
        if path:
            path = urllib.parse.unquote(path)
        if not path or not os.path.exists(path) or not os.path.isdir(path):
            return jsonify({'error': '无效路径'}), 400
        items = []
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    try:
                        items.append({
                            'path': entry.path,
                            'name': entry.name,
                            'is_dir': entry.is_dir(follow_symlinks=False)
                        })
                    except Exception as e:
                        logger.warning(f"扫描目录条目失败 {entry.path if 'entry' in locals() else 'unknown'}: {e}")
                        continue
        except Exception as e:
            return jsonify({'error': f'无法读取目录: {str(e)}'}), 500
        return jsonify(items)
    except Exception as e:
        log_exception(request, 'LIST_ALL', path, e)
        return jsonify({'error': '列表获取失败'}), 500
    finally:
        log_access(request, 'LIST_ALL', locals().get('path', ''), duration=time.time() - start_time)
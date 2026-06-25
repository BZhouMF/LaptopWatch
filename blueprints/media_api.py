"""
媒体模式API蓝图
包含媒体模式下的API接口
"""
import os
import re
import time
import socket
import urllib.parse
from flask import Blueprint, request, jsonify, send_from_directory, session, Response
from config import config
from utils.logging_utils import log_access, log_exception, logger
from utils.media_utils import get_files_in_folder
from utils.file_utils import get_mime_type
from blueprints.auth import login_required, require_mode

media_bp = Blueprint('media_api', __name__, url_prefix='/media')

# ── 全局 patch：Werkzeug FileWrapper 默认 8KB → 2MB，减少大视频的 chunk 数和 Range 请求频率 ──
from werkzeug.wsgi import FileWrapper as _OrigFileWrapper

class _BigFileWrapper(_OrigFileWrapper):
    def __init__(self, file, buffer_size=2 * 1024 * 1024):
        super().__init__(file, buffer_size)

import werkzeug.wsgi
werkzeug.wsgi.FileWrapper = _BigFileWrapper

# ── 视频流传输参数 ──
VIDEO_CHUNK = int(os.getenv('LAPTOPWATCH_VIDEO_CHUNK', 0.5 * 1024 * 1024))  # 512KB
SEND_TIMEOUT = 5  # socket 发送超时秒数，超时即客户端停止接收


# 随机模式 ID 缓存：{ (seed, media_type): (shuffled_ids, count) }
_random_id_cache = {}


def _media_type(run_mode=None):
    """根据运行模式返回 media_type 字符串"""
    mode = run_mode or config.RUN_MODE
    return 'video' if mode in ('video', 'douyin') else 'image'


def _db_load_more(offset, limit, is_random):
    """从 DB 遍历文件夹加载媒体文件，返回 (success, response_dict)"""
    try:
        if not config.DB_PATH or not config.MEDIA_DIR:
            return False, None

        from utils.db_utils import get_db, traverse_media, init_tables, sync_folder, _format_media_row
        import os as _os
        import random as _random

        conn = get_db()
        media_type = _media_type()

        if is_random:
            init_tables(conn)
            # sync_folder 已在 index 页调用，这里只做轻量刷新（1-level scandir）
            sync_folder(conn, str(config.MEDIA_DIR))

            seed_key = '_random_seed_' + config.RUN_MODE
            from flask import session
            if seed_key not in session:
                session[seed_key] = _random.randint(0, 2 ** 31 - 1)
            seed = session[seed_key]

            cache_key = (seed, media_type)
            if cache_key in _random_id_cache:
                all_ids, total = _random_id_cache[cache_key]
            else:
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
                total = len(all_ids)
                _random_id_cache[cache_key] = (all_ids, total)
            page_ids = all_ids[offset:offset + limit]

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

            data = [_format_media_row(r) for r in rows]
            next_offset = offset + len(data)
            has_more = (next_offset < total)
        else:
            data, next_offset, has_more = traverse_media(
                conn, str(config.MEDIA_DIR), media_type,
                offset=offset, limit=limit,
                sort_type=config.SORT_TYPE,
                sort_order=config.SORT_ORDER,
                random_start=False,
            )
        conn.close()

        return True, {
            'code': 0,
            'data': data,
            'has_more': has_more,
            'next_offset': next_offset,
            'is_random': is_random,
            'total': total if is_random else 0,
        }
    except Exception as e:
        logger.error(f"DB load_more 失败: {e}")
        return False, None


def _db_thumbnail(target_path):
    """从 DB 读取或生成 cover，返回 (success, jpeg_bytes, mime_type)"""
    try:
        if not config.DB_PATH:
            return False, None, None

        from utils.db_utils import get_db, generate_and_cache_cover
        conn = get_db()
        jpeg_bytes, mime = generate_and_cache_cover(conn, target_path)
        conn.close()

        if jpeg_bytes:
            return True, jpeg_bytes, mime
        return False, None, None
    except Exception as e:
        logger.error(f"DB thumbnail 失败: {e}")
        return False, None, None

@media_bp.route('/load_more', methods=['GET'])
@login_required
@require_mode('video', 'image', 'douyin')
def load_more():
    """加载更多媒体文件（DB 优先，回退到遍历）"""
    start_time = time.time()
    try:
        offset = int(request.args.get('offset', config.PAGE_FIRST))
        limit = int(request.args.get('limit', config.PAGE_LOAD))
        is_random = config.RANDOM_MODE

        # DB 优先
        db_ok, db_result = _db_load_more(offset, limit, is_random)
        if db_ok:
            return jsonify(db_result)

        # DB 不可用，返回空
        logger.debug("load_more: DB 不可用，无法加载数据")
        return jsonify({'code': 1, 'msg': '数据库不可用'}), 503
    except Exception as e:
        log_exception(request, 'LOAD_MORE', '', e)
        return jsonify({'code': 1, 'msg': '加载失败'}), 500
    finally:
        log_access(request, 'LOAD_MORE', f'offset={locals().get("offset", 0)}', duration=time.time() - start_time)

@media_bp.route('/thumbnail/<path:relative_path>', methods=['GET'])
@login_required
@require_mode('video', 'image', 'douyin', 'normal')
def api_thumbnail(relative_path):
    """生成并返回媒体文件缩略图（DB cover 优先，回退到实时生成）"""
    from utils.thumbnail_utils import generate_thumbnail
    from pathlib import Path
    import base64

    # 优先使用 query 参数中的绝对路径（普通模式）
    abs_path = request.args.get('path', '')
    if abs_path:
        target = Path(abs_path).resolve()
        if not target.is_file():
            return '', 404
    else:
        decoded_relative_path = urllib.parse.unquote(relative_path)
        if decoded_relative_path.startswith('/'):
            decoded_relative_path = decoded_relative_path[1:]

        if not config.MEDIA_DIR or not config.MEDIA_DIR.exists():
            return '', 404

        requested_path = config.MEDIA_DIR / decoded_relative_path
        target = requested_path.resolve()

        # 路径穿越保护
        if not str(target).startswith(str(config.MEDIA_DIR.resolve())):
            logger.warning(f"缩略图非法访问: {target} | IP: {request.remote_addr}")
            return '', 403

        if not target.is_file():
            return '', 404

    target_str = str(target)

    # DB cover 优先
    db_ok, jpeg_bytes, mime = _db_thumbnail(target_str)
    if db_ok and jpeg_bytes:
        return jpeg_bytes, 200, {
            'Content-Type': mime or 'image/jpeg',
            'Cache-Control': 'public, max-age=3600'
        }

    # 回退到实时生成
    thumb = generate_thumbnail(target_str)
    if thumb:
        mime_type, thumb_data = thumb
        return base64.b64decode(thumb_data), 200, {
            'Content-Type': mime_type,
            'Cache-Control': 'public, max-age=3600'
        }
    return '', 404

@media_bp.route('/serve_media/', methods=['GET'])
@login_required
@require_mode('video', 'image', 'douyin')
def serve_media_empty():
    """处理空的媒体文件请求"""
    from flask import jsonify
    return jsonify({'code': 1, 'msg': '未指定文件路径'}), 400


def _parse_range(range_header, file_size):
    """解析 HTTP Range 头，返回 (start, end) 或 None 表示非法范围"""
    if not range_header:
        return 0, file_size - 1
    match = re.match(r'bytes=(\d+)-(\d*)$', range_header)
    if not match:
        return 0, file_size - 1
    start = int(match.group(1))
    end_str = match.group(2)
    end = int(end_str) if end_str else file_size - 1
    if start >= file_size:
        return None
    if end >= file_size:
        end = file_size - 1
    return start, end


def _stream_video_file(filepath, range_header, mimetype, environ):
    """视频流式传输 — 512KB 匀速分块 + socket 超时保护"""
    file_size = os.path.getsize(filepath)

    parsed = _parse_range(range_header, file_size)
    if parsed is None:
        return Response('', status=416,
                        headers={'Content-Range': f'bytes */{file_size}'})
    start, end = parsed

    content_length = end - start + 1
    has_range = bool(range_header and range_header.startswith('bytes='))
    wsock = environ.get('werkzeug.socket') if environ else None

    if wsock:
        wsock.settimeout(SEND_TIMEOUT)

    def generate():
        remaining = content_length
        with open(filepath, 'rb') as fh:
            fh.seek(start)
            while remaining > 0:
                chunk_size = min(VIDEO_CHUNK, remaining)
                data = fh.read(chunk_size)
                if not data:
                    break
                remaining -= len(data)
                try:
                    yield data
                except (socket.timeout, TimeoutError, OSError):
                    break

    headers = {
        'Accept-Ranges': 'bytes',
        'Content-Length': str(content_length),
        'Content-Type': mimetype,
    }
    if has_range:
        headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'

    return Response(generate(), status=206 if has_range else 200,
                    headers=headers, direct_passthrough=True)


@media_bp.route('/serve_media/<path:relative_path>', methods=['GET'])
@login_required
@require_mode('video', 'image', 'douyin')
def serve_media(relative_path):
    """提供媒体文件流"""
    start_time = time.time()
    try:
        from utils.logging_utils import logger
        # 解码URL路径以处理特殊字符
        decoded_relative_path = urllib.parse.unquote(relative_path)

        # 去除前导斜杠，防止路径解析问题
        if decoded_relative_path.startswith('/'):
            decoded_relative_path = decoded_relative_path[1:]
            logger.debug(f"去除前导斜杠后的路径: {decoded_relative_path}")

        if not config.MEDIA_DIR or not config.MEDIA_DIR.exists():
            logger.warning(f"媒体目录不存在: {config.MEDIA_DIR}")
            return '媒体目录不存在', 404
        requested_path = config.MEDIA_DIR / decoded_relative_path
        target = requested_path.resolve()
        if not str(target).startswith(str(config.MEDIA_DIR.resolve())):
            from utils.logging_utils import logger
            logger.warning(f"非法访问尝试: {target} | IP: {request.remote_addr}")
            return '非法访问', 403
        if not target.is_file():
            from utils.logging_utils import logger
            logger.warning(f"文件不存在: {target} | IP: {request.remote_addr}")
            return '文件不存在', 404

        # 首次访问时记录到日志（相对路径，精简格式）
        ext = os.path.splitext(target.name)[1].lower()
        is_video = ext in config.VIDEO_EXT
        if 'Range' not in request.headers:
            action = 'MEDIA_PLAY' if is_video else 'MEDIA_VIEW'
            log_access(request, action, decoded_relative_path.replace('\\', '/'))

        mime_type = get_mime_type(str(target))

        if is_video:
            # 视频：自定义 burst-first Range 处理器，优化拖拽体验
            range_header = request.headers.get('Range', '')
            return _stream_video_file(str(target), range_header, mime_type, request.environ)
        else:
            # 图片：标准 send_file，文件小无需特殊优化
            directory = target.parent
            filename = target.name
            return send_from_directory(directory, filename, as_attachment=False, conditional=True, mimetype=mime_type)
    except Exception as e:
        from utils.logging_utils import logger
        # 详细错误日志
        logger.error(f"serve_media失败: 路径={relative_path}, 目标文件={target if 'target' in locals() else '未知'}, MIME类型={mime_type if 'mime_type' in locals() else '未知'}, 错误={str(e)}", exc_info=True)
        log_exception(request, 'MEDIA_ACCESS_ERROR', relative_path, e)
        return f'访问错误: {str(e)}', 500

@media_bp.route('/download_media/<path:relative_path>', methods=['GET'])
@login_required
@require_mode('video', 'image', 'douyin')
def download_media(relative_path):
    """下载媒体文件"""
    start_time = time.time()
    try:
        # 解码URL路径以处理特殊字符
        decoded_relative_path = urllib.parse.unquote(relative_path)

        if not config.MEDIA_DIR:
            return '接口不可用', 404
        try:
            requested_path = config.MEDIA_DIR / decoded_relative_path
            target = requested_path.resolve()
            if not str(target).startswith(str(config.MEDIA_DIR.resolve())):
                return '非法访问', 403
            if not target.is_file():
                return '文件不存在', 404

            log_access(request, 'DOWNLOAD_MEDIA', decoded_relative_path.replace('\\', '/'))

            directory = target.parent
            filename = target.name
            return send_from_directory(directory, filename, as_attachment=True)
        except Exception as e:
            from utils.logging_utils import logger
            logger.exception("download_media 异常")
            return f'下载错误: {str(e)}', 500
    except Exception as e:
        log_exception(request, 'DOWNLOAD_MEDIA', relative_path, e)
        return "下载失败", 500
    finally:
        log_access(request, 'DOWNLOAD_MEDIA',
                   locals().get('decoded_relative_path', relative_path).replace('\\', '/'),
                   duration=time.time() - start_time)

@media_bp.route('/navigate', methods=['GET'])
@login_required
@require_mode('video', 'image', 'douyin')
def api_media_navigate():
    """媒体文件导航（上一张/下一张）"""
    start_time = time.time()
    try:
        current_path = request.args.get('current_path')
        direction = request.args.get('direction')
        logger.debug(f"导航请求: current_path={current_path}, direction={direction}")
        if not current_path or direction not in ('prev', 'next'):
            return jsonify({'code': 1, 'msg': '参数错误'}), 400

        # 解码当前路径
        decoded_current_path = urllib.parse.unquote(current_path)

        current_full = config.MEDIA_DIR / decoded_current_path
        if not current_full.exists() or not current_full.is_file():
            return jsonify({'code': 1, 'msg': '文件不存在'}), 404
        folder = current_full.parent
        files = get_files_in_folder(str(folder))
        if not files:
            return jsonify({'code': 1, 'msg': '文件夹内无媒体文件'}), 404
        current_path_normalized = decoded_current_path.replace('\\', '/')
        index = None
        for i, f in enumerate(files):
            f_rel = f['rel_path'].replace(os.sep, '/')
            if f_rel == current_path_normalized:
                index = i
                break
        if index is None:
            return jsonify({'code': 1, 'msg': '当前文件不在列表中'}), 404
        new_index = index - 1 if direction == 'prev' else index + 1
        if new_index < 0 or new_index >= len(files):
            return jsonify({'code': 2, 'msg': '已到边界', 'data': None})
        new_file = files[new_index]
        ext = os.path.splitext(new_file['name'])[1].lower()
        is_video = ext in config.VIDEO_EXT
        logger.debug(f"导航成功: 新文件={new_file['rel_path']}, is_video={is_video}")
        return jsonify({
            'code': 0,
            'data': {
                'relative_path': new_file['rel_path'].replace(os.sep, '/'),
                'name': new_file['name'],
                'is_video': is_video
            }
        })
    except Exception as e:
        log_exception(request, 'MEDIA_NAV', current_path, e)
        return jsonify({'code': 1, 'msg': '导航失败'}), 500
    finally:
        log_access(request, 'MEDIA_NAV', locals().get('current_path', ''), locals().get('direction', ''), duration=time.time() - start_time)



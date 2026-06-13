"""
媒体模式API蓝图
包含媒体模式下的API接口
"""
import os
import time
import urllib.parse
from flask import Blueprint, request, jsonify, send_from_directory, session, render_template
from config import config
from utils.logging_utils import log_access, log_exception, logger
from utils.media_utils import get_next_media_files, get_next_sequential_files, get_files_in_folder
from utils.file_utils import get_mime_type
from blueprints.auth import login_required, require_mode

media_bp = Blueprint('media_api', __name__, url_prefix='/media')


def _media_table(run_mode):
    """根据运行模式返回媒体表名"""
    return 'videos' if run_mode in ('video', 'douyin') else 'images'


def _db_load_more(offset, limit, is_random):
    """从 DB 加载媒体文件，返回 (success, response_dict)"""
    try:
        db_path = config.DB_PATH
        if not db_path:
            return False, None

        from utils.db_utils import get_db, ensure_tables, sync_folder, \
            get_random_media, get_media_page_all

        conn = get_db(db_path)
        ensure_tables(conn)
        # 确保 MEDIA_DIR 根目录已同步
        if config.MEDIA_DIR:
            sync_folder(conn, str(config.MEDIA_DIR), run_mode=config.RUN_MODE)

        table = _media_table(config.RUN_MODE)

        if is_random:
            rows = get_random_media(conn, table, limit)
            total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            has_more = len(rows) == limit
        else:
            rows, total = get_media_page_all(conn, table, limit, offset)
            has_more = (offset + len(rows)) < total

        conn.close()

        media_dir_str = str(config.MEDIA_DIR).replace('\\', '/') + '/'
        data = []
        for r in rows:
            path = r['path'].replace('\\', '/')
            rel_path = path.replace(media_dir_str, '', 1) if media_dir_str else path
            ext = os.path.splitext(r['name'])[1].lower()
            from datetime import datetime
            data.append({
                'name': r['name'],
                'relative_path': rel_path,
                'mtime': datetime.fromtimestamp(r['modify_time']).strftime('%Y-%m-%d %H:%M:%S'),
                'timestamp': r['modify_time'],
                'is_video': ext in config.VIDEO_EXT,
                'is_image': ext in config.IMAGE_EXT,
            })

        return True, {
            'code': 0,
            'data': data,
            'has_more': has_more,
            'next_offset': offset + len(data),
            'is_random': is_random,
        }
    except Exception as e:
        logger.debug(f"DB load_more 失败，回退到遍历: {e}")
        return False, None


def _db_thumbnail(target_path):
    """从 DB 读取或生成 cover，返回 (success, jpeg_bytes, mime_type)"""
    try:
        db_path = config.DB_PATH
        if not db_path:
            return False, None, None

        from utils.db_utils import get_db, ensure_tables, generate_and_cache_cover
        conn = get_db(db_path)
        ensure_tables(conn)
        table = _media_table(config.RUN_MODE)
        jpeg_bytes, mime = generate_and_cache_cover(conn, table, target_path)
        conn.close()

        if jpeg_bytes:
            return True, jpeg_bytes, mime
        return False, None, None
    except Exception as e:
        logger.debug(f"DB thumbnail 失败: {e}")
        return False, None, None

@media_bp.route('/load_more')
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

        # 回退到遍历
        if is_random:
            if 'traversal_id' not in session:
                logger.error("load_more 随机模式：遍历状态不存在")
                return jsonify({'code': 1, 'msg': '遍历状态不存在，请刷新页面'})

            try:
                more, has_more = get_next_media_files(session['traversal_id'], limit)
                session.modified = True
                return jsonify({
                    'code': 0,
                    'data': more,
                    'has_more': has_more,
                    'next_offset': offset + len(more),
                    'is_random': True
                })
            except Exception as e:
                import traceback
                logger.error(f"load_more 随机模式发生错误: {e}\n{traceback.format_exc()}")
                return jsonify({'code': 1, 'msg': f'服务器内部错误: {str(e)}'}), 500
        else:
            if 'traversal_id' not in session:
                logger.error("load_more 顺序模式：遍历状态不存在")
                return jsonify({'code': 1, 'msg': '遍历状态不存在，请刷新页面'})

            try:
                more, has_more = get_next_sequential_files(session['traversal_id'], limit)
                session.modified = True
                return jsonify({
                    'code': 0,
                    'data': more,
                    'has_more': has_more,
                    'next_offset': offset + len(more),
                    'is_random': False
                })
            except Exception as e:
                import traceback
                logger.error(f"load_more 顺序模式发生错误: {e}\n{traceback.format_exc()}")
                return jsonify({'code': 1, 'msg': f'服务器内部错误: {str(e)}'}), 500
    except Exception as e:
        log_exception(request, 'LOAD_MORE', '', e)
        return jsonify({'code': 1, 'msg': '加载失败'}), 500
    finally:
        log_access(request, 'LOAD_MORE', f'offset={locals().get("offset", 0)}', duration=time.time() - start_time)

@media_bp.route('/thumbnail/<path:relative_path>')
@login_required
@require_mode('video', 'image', 'douyin')
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

@media_bp.route('/serve_media/')
@login_required
@require_mode('video', 'image', 'douyin')
def serve_media_empty():
    """处理空的媒体文件请求"""
    from flask import jsonify
    return jsonify({'code': 1, 'msg': '未指定文件路径'}), 400

@media_bp.route('/serve_media/<path:relative_path>')
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
        import os
        ext = os.path.splitext(target.name)[1].lower()
        is_video = ext in config.VIDEO_EXT
        if 'Range' not in request.headers:
            action = 'MEDIA_PLAY' if is_video else 'MEDIA_VIEW'
            log_access(request, action, decoded_relative_path.replace('\\', '/'))
        # 注意：这里不再为Range请求记录日志，避免频繁的日志输出

        # 调试日志：仅在非Range请求时记录文件信息
        if 'Range' not in request.headers:
            logger.debug(f"serve_media: 请求路径={relative_path}, 扩展名={target.suffix.lower()}")

        mime_type = get_mime_type(str(target))

        logger.debug(f"serve_media: MIME类型={mime_type}")
        directory = target.parent
        filename = target.name
        return send_from_directory(directory, filename, as_attachment=False, conditional=True, mimetype=mime_type)
    except Exception as e:
        from utils.logging_utils import logger
        # 详细错误日志
        logger.error(f"serve_media失败: 路径={relative_path}, 目标文件={target if 'target' in locals() else '未知'}, MIME类型={mime_type if 'mime_type' in locals() else '未知'}, 错误={str(e)}", exc_info=True)
        log_exception(request, 'MEDIA_ACCESS_ERROR', relative_path, e)
        return f'访问错误: {str(e)}', 500

@media_bp.route('/download_media/<path:relative_path>')
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

@media_bp.route('/navigate')
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


@media_bp.route('/player')
@login_required
@require_mode('video', 'image')
def media_player():
    """
    全屏媒体播放器页面（目录浏览模式专用）
    使用与抖音模式同款的播放器 UI 和交互。
    """
    start_time = time.time()
    try:
        media_path = request.args.get('path', '')
        if not media_path:
            return '缺少参数', 400

        decoded_path = urllib.parse.unquote(media_path)
        if decoded_path.startswith('/'):
            decoded_path = decoded_path[1:]

        full_path = (config.MEDIA_DIR / decoded_path).resolve()
        if not str(full_path).startswith(str(config.MEDIA_DIR.resolve())):
            return '非法访问', 403
        if not full_path.is_file():
            return '文件不存在', 404

        ext = full_path.suffix.lower()
        is_video = ext in config.VIDEO_EXT

        return render_template('player.html',
                               media_path=decoded_path.replace('\\', '/'),
                               media_name=full_path.name,
                               is_video=is_video)
    except Exception as e:
        logger.error(f"player 错误: {e}", exc_info=True)
        return '加载失败', 500
    finally:
        log_access(request, 'PLAYER', request.args.get('path', ''), duration=time.time() - start_time)

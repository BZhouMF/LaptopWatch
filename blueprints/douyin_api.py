"""
抖音模式API蓝图
提供竖屏滑动视频播放接口 — 从 DB 随机取视频
"""
import time
from flask import Blueprint, request, jsonify, session
from config import config
from utils.logging_utils import log_access, log_exception, logger
from blueprints.auth import login_required, require_mode

douyin_bp = Blueprint('douyin_api', __name__, url_prefix='/api/douyin')


def _get_history():
    """从 session 获取已播放视频路径列表"""
    return session.get('douyin_history', [])


def _save_history(history):
    """保存历史到 session，裁剪超限"""
    max_len = config.DOUYIN_HISTORY_MAX
    while len(history) > max_len:
        history.pop(0)
    session['douyin_history'] = history
    session.modified = True


def _format_video(row):
    """将遍历结果格式化为前端视频数据"""
    return {
        'name': row['name'],
        'relative_path': row['relative_path'],
        'is_video': True,
    }


def _pick_random_video(exclude_paths):
    """从 DB 遍历文件夹取一条视频，排除已播放路径

    返回 dict 或 None
    """
    try:
        if not config.DB_PATH or not config.MEDIA_DIR:
            return None

        from utils.db_utils import get_db, traverse_media

        conn = get_db()
        is_random = config.DOUYIN_RANDOM_MEDIA

        rows, _, _ = traverse_media(
            conn, str(config.MEDIA_DIR), 'video',
            offset=0, limit=1,
            sort_type=config.SORT_TYPE,
            sort_order=config.SORT_ORDER,
            random_start=is_random,
            exclude_paths=exclude_paths,
        )
        conn.close()
        return rows[0] if rows else None
    except Exception as e:
        logger.debug(f"DB 随机取视频失败: {e}")
        return None


@douyin_bp.route('/init')
@login_required
@require_mode('douyin')
def douyin_init():
    """初始化抖音会话，从 DB 随机取第一个视频"""
    start_time = time.time()
    try:
        video = _pick_random_video([])
        if not video:
            return jsonify({'code': 1, 'msg': '没有找到视频文件'})

        _save_history([video['path']])
        return jsonify({'code': 0, 'data': _format_video(video)})

    except Exception as e:
        log_exception(request, 'DOUYIN_INIT', '', e)
        return jsonify({'code': 1, 'msg': '初始化失败'}), 500
    finally:
        log_access(request, 'DOUYIN_INIT', '', duration=time.time() - start_time)


@douyin_bp.route('/next')
@login_required
@require_mode('douyin')
def douyin_next():
    """获取下一个随机视频，排除已播放的"""
    start_time = time.time()
    try:
        history = _get_history()

        video = _pick_random_video(history)
        if not video:
            return jsonify({'code': 2, 'msg': '没有更多了'})

        history.append(video['path'])
        _save_history(history)
        return jsonify({'code': 0, 'data': _format_video(video)})

    except Exception as e:
        log_exception(request, 'DOUYIN_NEXT', '', e)
        return jsonify({'code': 1, 'msg': '获取失败'}), 500
    finally:
        log_access(request, 'DOUYIN_NEXT', '', duration=time.time() - start_time)

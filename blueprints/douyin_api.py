"""
抖音模式API蓝图
提供竖屏滑动视频播放接口
"""
import time
import threading
import uuid
from flask import Blueprint, request, jsonify, session
from config import config
from utils.logging_utils import log_access, log_exception, logger
from utils.media_utils import (
    get_video_at_offset, pick_random_media_video,
    init_traversal, get_next_media_files
)
from blueprints.auth import login_required, require_mode

douyin_bp = Blueprint('douyin_api', __name__, url_prefix='/api/douyin')

# 服务端内存存储，避免超大 session cookie（Flask cookie 限制 ~4KB）
_douyin_store = {}
_douyin_lock = threading.Lock()


def _get_or_create_sid():
    """获取或创建 douyin 服务端会话 ID"""
    sid = session.get('douyin_sid')
    if not sid:
        sid = str(uuid.uuid4())
        session['douyin_sid'] = sid
        session.modified = True
        logger.info(f"[DOUYIN_DEBUG] Created new sid={sid} for session")
    else:
        logger.info(f"[DOUYIN_DEBUG] Found existing sid={sid} in session")
    return sid


def _get_state():
    """获取当前 douyin 会话状态"""
    sid = _get_or_create_sid()
    with _douyin_lock:
        if sid not in _douyin_store:
            logger.info(f"[DOUYIN_DEBUG] sid={sid} NOT in _douyin_store (store has {len(_douyin_store)} entries)")
            return None
        _douyin_store[sid]['last_activity_time'] = time.time()
        return _douyin_store[sid]


def _save_state(state):
    """保存 douyin 会话状态"""
    sid = _get_or_create_sid()
    state['last_activity_time'] = time.time()
    with _douyin_lock:
        _douyin_store[sid] = state
    session.modified = True
    logger.info(f"[DOUYIN_DEBUG] _save_state: sid={sid[:8]}... store now has {len(_douyin_store)} entries")


def _cleanup_stale():
    """清理超过 1 小时未活动的 douyin 会话"""
    stale_threshold = time.time() - 3600
    with _douyin_lock:
        stale_ids = [sid for sid, s in list(_douyin_store.items())
                     if s.get('last_activity_time', 0) < stale_threshold]
        for sid in stale_ids:
            del _douyin_store[sid]


def _trim_history(history):
    """裁剪历史记录到最大长度"""
    max_len = config.DOUYIN_HISTORY_MAX
    while len(history) > max_len:
        history.pop(0)


def _format_video(video):
    """格式化视频数据返回前端"""
    return {
        'name': video.get('name', ''),
        'relative_path': video.get('relative_path', ''),
        'is_video': True
    }


def _get_douyin_mode():
    """返回当前抖音子模式"""
    if config.DOUYIN_RANDOM_MEDIA:
        return 'random_media'
    if config.RANDOM_MODE:
        return 'random_walk'
    return 'sequential'


def _init_state():
    """初始化抖音状态，返回 (state_dict, first_video)，无视频时返回 (None, None)"""
    mode = _get_douyin_mode()

    if mode in ('random_walk', 'random_media'):
        if mode == 'random_walk':
            traversal_id = init_traversal(str(config.MEDIA_DIR), 'video')
            files, has_more = get_next_media_files(traversal_id, 1)
            videos = [f for f in files if f.get('is_video')]
            if videos:
                video = videos[0]
                state = {
                    'mode': mode,
                    'traversal_id': traversal_id,
                    'buffer': [],
                    'has_more': True,
                    'history': [_format_video(video)]
                }
                return state, video
        elif mode == 'random_media':
            video = pick_random_media_video([])
            if video:
                state = {
                    'mode': mode,
                    'history': [_format_video(video)]
                }
                return state, video
        # 随机模式没找到视频，降级到顺序扫描
        logger.warning(f"[DOUYIN_DEBUG] {mode} 未找到视频，降级到 sequential")

    # sequential 模式（或降级后）
    video, has_more = get_video_at_offset(0)
    if not video:
        return None, None
    state = {
        'mode': 'sequential',
        'cursor': 0,
        'has_more': has_more,
        'history': [_format_video(video)]
    }
    return state, video


def _refill_buffer(state):
    """为 random_walk 模式补充视频缓冲"""
    tid = state.get('traversal_id')
    if not tid:
        return
    files, has_more = get_next_media_files(tid, config.PAGE_LOAD)
    videos = [f for f in files if f.get('is_video')]
    if not videos and has_more:
        _refill_buffer(state)
        return
    state['buffer'] = videos
    state['has_more'] = has_more


@douyin_bp.route('/init')
@login_required
@require_mode('douyin')
def douyin_init():
    """初始化抖音会话，返回第一个视频"""
    start_time = time.time()
    try:
        _cleanup_stale()
        state, video = _init_state()
        if not state:
            return jsonify({'code': 1, 'msg': '没有找到视频文件'})
        _save_state(state)
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
    """获取下一个视频"""
    start_time = time.time()
    try:
        state = _get_state()
        if not state:
            logger.warning(f"[DOUYIN_DEBUG] session expired — auto-init new state")
            state, video = _init_state()
            if not state:
                return jsonify({'code': 2, 'msg': '没有更多了'})
            _save_state(state)
            history = state.get('history', [])
            return jsonify({'code': 0, 'data': _format_video(video)})

        mode = state['mode']
        history = state.get('history', [])

        if mode == 'sequential':
            cursor = state['cursor'] + 1
            video, has_more = get_video_at_offset(cursor)
            if not video:
                return jsonify({'code': 2, 'msg': '没有更多了'})
            state['cursor'] = cursor
            state['has_more'] = has_more
            history.append(_format_video(video))
            _trim_history(history)
            state['history'] = history
            _save_state(state)
            return jsonify({'code': 0, 'data': _format_video(video)})

        elif mode == 'random_walk':
            buffer = state.get('buffer', [])
            has_more = state.get('has_more', True)

            while not buffer and has_more:
                _refill_buffer(state)
                buffer = state.get('buffer', [])
                has_more = state.get('has_more', False)
                if not buffer and not has_more:
                    break

            if not buffer:
                return jsonify({'code': 2, 'msg': '没有更多了'})

            video = buffer.pop(0)
            state['buffer'] = buffer
            history.append(_format_video(video))
            _trim_history(history)
            state['history'] = history
            _save_state(state)
            return jsonify({'code': 0, 'data': _format_video(video)})

        elif mode == 'random_media':
            video = pick_random_media_video(history)
            if not video:
                return jsonify({'code': 2, 'msg': '没有更多了'})
            history.append(_format_video(video))
            _trim_history(history)
            state['history'] = history
            _save_state(state)
            return jsonify({'code': 0, 'data': _format_video(video)})

        else:
            return jsonify({'code': 1, 'msg': f'未知播放方式: {mode}'}), 400

    except Exception as e:
        log_exception(request, 'DOUYIN_NEXT', '', e)
        return jsonify({'code': 1, 'msg': '获取失败'}), 500
    finally:
        log_access(request, 'DOUYIN_NEXT', '', duration=time.time() - start_time)

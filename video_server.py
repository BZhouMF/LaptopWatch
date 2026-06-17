"""
FastAPI 视频流服务
异步非阻塞 + 令牌桶调速 + 断连保护，专用于大文件视频流式传输
"""
import os
import re
import time
import asyncio
import logging
from urllib.parse import unquote

from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from itsdangerous import URLSafeTimedSerializer
from flask.sessions import TaggedJSONSerializer

from config import config
from utils.file_utils import get_mime_type

# ── 日志：只记异常，不记正常传输 ──
_stream_logger = logging.getLogger('video_server')
_stream_logger.setLevel(logging.WARNING)

_flask_logger = logging.getLogger('utils.logging_utils')
for _handler in _flask_logger.handlers if _flask_logger.handlers else logging.getLogger().handlers:
    if isinstance(_handler, logging.Handler):
        _stream_logger.addHandler(_handler)
if not _stream_logger.handlers:
    _stream_logger.addHandler(logging.StreamHandler())
    _stream_logger.handlers[0].setFormatter(logging.Formatter(
        '[%(asctime)s] [VIDEO] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
    ))

video_app = FastAPI()

MEDIA_DIR = config.MEDIA_DIR.resolve() if config.MEDIA_DIR else None

# ── 可调参数（env 覆盖） ──
VIDEO_CHUNK = int(os.getenv('LAPTOPWATCH_VIDEO_CHUNK', 2 * 1024 * 1024))  # 2MB
# 目标发送速率（MB/s），默认 20 MB/s = 160 Mbps，足以支撑 4K 原盘
TARGET_SPEED_MB = float(os.getenv('LAPTOPWATCH_VIDEO_SPEED_MB', 20))
# 突发缓冲（MB），允许浏览器初始加载时短时间超速
BURST_MB = float(os.getenv('LAPTOPWATCH_VIDEO_BURST_MB', 16))

# —— Flask session cookie 验证 ——
_session_serializer = URLSafeTimedSerializer(
    config.SECRET_KEY,
    salt='cookie-session',
    serializer=TaggedJSONSerializer(),
    signer_kwargs={'key_derivation': 'hmac'}
)


def _check_login(request: Request) -> bool:
    session_cookie = request.cookies.get('session')
    if not session_cookie:
        return False
    try:
        data = _session_serializer.loads(session_cookie)
        return data.get('logged_in', False)
    except Exception:
        return False


def _parse_range(range_header: str, file_size: int):
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


def _is_video(filepath: str) -> bool:
    return os.path.splitext(filepath)[1].lower() in config.VIDEO_EXT


def _client_label(request: Request) -> str:
    ua = request.headers.get('user-agent', '').lower()
    if not ua:
        return '?'
    if 'android' in ua:
        return 'Android'
    if 'iphone' in ua or 'ipad' in ua:
        return 'iOS'
    if 'windows' in ua:
        return 'Win'
    if 'mac os' in ua or 'macintosh' in ua:
        return 'Mac'
    if 'linux' in ua:
        return 'Linux'
    return '?'


async def _video_chunk_generator(filepath: str, start: int, end: int,
                                 request: Request, logger: logging.Logger):
    """
    令牌桶调速的异步视频块生成器。

    用令牌桶将发送速率平滑控制在 TARGET_SPEED_MB 附近，
    同时允许 BURST_MB 的突发（浏览器初始缓冲阶段全速发送）。
    检测客户端断开即停。
    """
    remaining = end - start + 1
    total_bytes = remaining
    chunk_count = 0
    t_start = time.monotonic()

    # 令牌桶状态
    token_rate = TARGET_SPEED_MB * 1024 * 1024  # bytes/s
    max_tokens = BURST_MB * 1024 * 1024  # burst budget in bytes
    tokens = max_tokens  # 初始满桶，允许浏览器快速填满播放缓冲
    last_refill = t_start

    with open(filepath, 'rb') as fh:
        fh.seek(start)
        while remaining > 0:
            if await request.is_disconnected():
                elapsed = time.monotonic() - t_start
                sent_bytes = total_bytes - remaining
                speed = (sent_bytes / 1024 / 1024 / elapsed) if elapsed > 0 else 0
                logger.warning(
                    f"[断连] {_client_label(request)} | {os.path.basename(filepath)} | "
                    f"已发 {sent_bytes/1024/1024:.0f}/{total_bytes/1024/1024:.0f}MB | "
                    f"均速 {speed:.1f}MB/s"
                )
                return

            # ── 令牌桶：等待足够 token 再发送 ──
            chunk_size = min(VIDEO_CHUNK, remaining)
            while tokens < chunk_size:
                await asyncio.sleep(0.02)
                now = time.monotonic()
                tokens = min(max_tokens, tokens + (now - last_refill) * token_rate)
                last_refill = now
                if await request.is_disconnected():
                    return

            # 补充 token（基于实际经过的时间）
            now = time.monotonic()
            tokens = min(max_tokens, tokens + (now - last_refill) * token_rate)
            last_refill = now

            data = fh.read(chunk_size)
            if not data:
                break
            tokens -= len(data)
            remaining -= len(data)
            chunk_count += 1
            yield data

    # 正常完成：只在超过 50MB 的大传输时记一条 INFO
    elapsed = time.monotonic() - t_start
    if total_bytes > 50 * 1024 * 1024:
        speed = (total_bytes / 1024 / 1024 / elapsed) if elapsed > 0 else 0
        logger.info(
            f"[完成] {os.path.basename(filepath)} | "
            f"{total_bytes/1024/1024:.0f}MB | {chunk_count}块 | "
            f"{elapsed:.1f}s | {speed:.1f}MB/s"
        )


@video_app.get("/media/serve_media/{file_path:path}")
async def serve_video(file_path: str, request: Request):
    """视频流式传输 — 令牌桶调速 + Range 支持 + 断连保护"""
    if not _check_login(request):
        return Response(status_code=403)

    decoded = unquote(file_path)
    if decoded.startswith('/'):
        decoded = decoded[1:]

    if not MEDIA_DIR or not MEDIA_DIR.exists():
        return Response(status_code=404)

    target = (MEDIA_DIR / decoded).resolve()
    if not str(target).startswith(str(MEDIA_DIR)):
        return Response(status_code=403)
    if not target.is_file():
        return Response(status_code=404)

    file_size = os.path.getsize(str(target))
    mimetype = get_mime_type(str(target))
    range_header = request.headers.get('range', '')

    if _is_video(str(target)):
        parsed = _parse_range(range_header, file_size)
        if parsed is None:
            return Response(status_code=416, headers={'Content-Range': f'bytes */{file_size}'})
        start, end = parsed
        content_length = end - start + 1
        has_range = bool(range_header and range_header.startswith('bytes='))

        headers = {
            'Accept-Ranges': 'bytes',
            'Content-Length': str(content_length),
            'Content-Type': mimetype,
        }
        if has_range:
            headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'

        return StreamingResponse(
            _video_chunk_generator(str(target), start, end, request, _stream_logger),
            status_code=206 if has_range else 200,
            headers=headers,
            media_type=mimetype,
        )
    else:
        from fastapi.responses import FileResponse
        return FileResponse(
            str(target),
            media_type=mimetype,
            headers={'Accept-Ranges': 'bytes'},
            filename=target.name,
        )


@video_app.get("/media/serve_media/")
async def serve_media_empty(request: Request):
    if not _check_login(request):
        return Response(status_code=403)
    return Response(status_code=400)

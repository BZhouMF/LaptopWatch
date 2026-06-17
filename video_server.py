"""
FastAPI 视频流服务
小块匀速传输，降低移动端网络栈压力，专用于大文件视频流式传输
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

# ── 小块匀速参数（env 可覆盖） ──
VIDEO_CHUNK = int(os.getenv('LAPTOPWATCH_VIDEO_CHUNK', 512 * 1024))       # 512KB
TARGET_SPEED_MB = float(os.getenv('LAPTOPWATCH_VIDEO_SPEED_MB', 20))       # 20 MB/s

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


def _device_label(request: Request) -> str:
    """从 User-Agent 提取设备标识（临时诊断用）"""
    ua = request.headers.get('user-agent', '')
    if not ua:
        return 'unknown'
    ua_lower = ua.lower()
    if 'android' in ua_lower:
        # 尝试提取 Android 版本和手机型号
        import re as _re
        model = ''
        android_ver = ''
        m = _re.search(r'android\s+(\d+[.\d]*)', ua_lower)
        if m:
            android_ver = m.group(1)
        # 常见手机型号标识
        for pattern in ['huawei', 'xiaomi', 'samsung', 'oppo', 'vivo', 'oneplus', 'pixel']:
            idx = ua_lower.find(pattern)
            if idx != -1:
                model = ua[idx:idx+30].split(';')[0].strip()
                break
        if model:
            return f'Android{android_ver}({model})'
        return f'Android{android_ver}'
    if 'iphone' in ua_lower or 'ipad' in ua_lower:
        return 'iOS'
    if 'windows' in ua_lower:
        return 'Windows'
    return 'other'


async def _video_chunk_generator(filepath: str, start: int, end: int):
    """
    小块匀速生成器 — 每块发送后按目标速率补齐等待时间。
    """
    total_bytes = end - start + 1
    remaining = total_bytes
    chunk_time = VIDEO_CHUNK / (TARGET_SPEED_MB * 1024 * 1024)
    chunk_count = 0
    t_start = time.monotonic()

    with open(filepath, 'rb') as fh:
        fh.seek(start)
        while remaining > 0:
            t0 = time.monotonic()

            chunk_size = min(VIDEO_CHUNK, remaining)
            data = fh.read(chunk_size)
            if not data:
                break
            remaining -= len(data)
            chunk_count += 1
            yield data

            # 匀速：实际耗时短于目标则补齐
            elapsed = time.monotonic() - t0
            wait = chunk_time - elapsed
            if wait > 0:
                await asyncio.sleep(wait)

    # 传输结束（正常完成或被 Starlette 捕获断连后自然结束）
    elapsed = time.monotonic() - t_start
    sent_bytes = total_bytes - remaining
    speed = (sent_bytes / 1024 / 1024 / elapsed) if elapsed > 0 else 0
    _stream_logger.warning(
        f"[传输] {os.path.basename(filepath)} | "
        f"已发 {sent_bytes/1024/1024:.1f}/{total_bytes/1024/1024:.1f}MB | "
        f"{chunk_count}块 | {elapsed:.1f}s | 均速 {speed:.1f}MB/s"
    )


@video_app.get("/media/serve_media/{file_path:path}")
async def serve_video(file_path: str, request: Request):
    """视频流式传输 — 小块匀速 + Range 支持"""
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

        client_ip = request.client.host if request.client else '?'
        device = _device_label(request)
        range_label = f'{start/1024/1024:.0f}-{end/1024/1024:.0f}MB' if has_range else '全文件'
        _stream_logger.warning(
            f"[请求] {client_ip} | {device} | {target.name} "
            f"({file_size/1024/1024:.0f}MB) | Range: {range_label} | "
            f"返回段 {content_length/1024/1024:.1f}MB"
        )

        headers = {
            'Accept-Ranges': 'bytes',
            'Content-Length': str(content_length),
            'Content-Type': mimetype,
        }
        if has_range:
            headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'

        return StreamingResponse(
            _video_chunk_generator(str(target), start, end),
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

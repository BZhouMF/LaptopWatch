"""
FastAPI 视频流服务
异步非阻塞 + 大块传输 + 速率平滑，专用于大文件视频流式传输
"""
import os
import re
import asyncio
from urllib.parse import unquote

from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from itsdangerous import URLSafeTimedSerializer
from flask.sessions import TaggedJSONSerializer

from config import config
from utils.file_utils import get_mime_type

video_app = FastAPI()

MEDIA_DIR = config.MEDIA_DIR.resolve() if config.MEDIA_DIR else None

# 视频流分块：512KB 大块减少系统调用，同时控制突发速率
VIDEO_CHUNK = 512 * 1024
# 每块之间的微延迟（秒）：平滑输出避免 TCP 缓冲溢出
CHUNK_DELAY = 0.05

# —— Flask session cookie 验证（与 Flask 共享 SECRET_KEY） ——
_session_serializer = URLSafeTimedSerializer(
    config.SECRET_KEY,
    salt='cookie-session',
    serializer=TaggedJSONSerializer(),
    signer_kwargs={'key_derivation': 'hmac'}
)


def _check_login(request: Request) -> bool:
    """验证 Flask session cookie，确认用户已登录"""
    session_cookie = request.cookies.get('session')
    if not session_cookie:
        return False
    try:
        data = _session_serializer.loads(session_cookie)
        return data.get('logged_in', False)
    except Exception:
        return False


def _parse_range(range_header: str, file_size: int):
    """解析 HTTP Range 头，返回 (start, end) 或 None"""
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
    ext = os.path.splitext(filepath)[1].lower()
    return ext in config.VIDEO_EXT


async def _video_chunk_generator(filepath: str, start: int, end: int):
    """异步生成器：大块读取视频文件，检测断连即停，微延迟平滑流量"""
    remaining = end - start + 1
    with open(filepath, 'rb') as fh:
        fh.seek(start)
        while remaining > 0:
            chunk_size = min(VIDEO_CHUNK, remaining)
            data = fh.read(chunk_size)
            if not data:
                break
            remaining -= len(data)
            yield data
            if remaining > 0:
                await asyncio.sleep(CHUNK_DELAY)


@video_app.get("/media/serve_media/{file_path:path}")
async def serve_video(file_path: str, request: Request):
    """视频流式传输 — 大块读取 + Range 支持 + 断连保护"""
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
            _video_chunk_generator(str(target), start, end),
            status_code=206 if has_range else 200,
            headers=headers,
            media_type=mimetype,
        )
    else:
        # 图片等小文件：直接使用 FileResponse（自带 Range + etag 支持）
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

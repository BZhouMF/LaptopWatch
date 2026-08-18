"""
FastAPI 视频流服务
"""
import os
import re
from urllib.parse import unquote

from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from itsdangerous import URLSafeTimedSerializer
from flask.sessions import TaggedJSONSerializer

from config import config
from utils.file_utils import get_mime_type

video_app = FastAPI()

MEDIA_DIR = config.MEDIA_DIR.resolve() if config.MEDIA_DIR else None

VIDEO_CHUNK = int(os.getenv('LAPTOPWATCH_VIDEO_CHUNK', 2 * 1024 * 1024))  # 2MB

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


async def _video_generator(filepath: str, start: int, end: int, request: Request):
    remaining = end - start + 1
    with open(filepath, 'rb') as fh:
        fh.seek(start)
        while remaining > 0:
            if await request.is_disconnected():
                break
            chunk_size = min(VIDEO_CHUNK, remaining)
            data = fh.read(chunk_size)
            if not data:
                break
            remaining -= len(data)
            yield data


@video_app.get("/media/serve_media/{file_path:path}")
async def serve_video(file_path: str, request: Request):
    if not _check_login(request):
        return Response(status_code=403)

    decoded = unquote(file_path)
    if decoded.startswith('/'):
        decoded = decoded[1:]

    if MEDIA_DIR and MEDIA_DIR.exists():
        target = (MEDIA_DIR / decoded).resolve()
        if not str(target).startswith(str(MEDIA_DIR)):
            return Response(status_code=403)
    else:
        from pathlib import Path
        target = Path(decoded).resolve()

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
            'Cache-Control': 'public, max-age=600',
        }
        if has_range:
            headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'

        return StreamingResponse(
            _video_generator(str(target), start, end, request),
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

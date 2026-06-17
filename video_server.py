"""
FastAPI 视频流服务
异步非阻塞 + Range 请求原生支持，专用于大文件视频流式传输
"""
import os
from urllib.parse import unquote

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from itsdangerous import URLSafeTimedSerializer
from flask.sessions import TaggedJSONSerializer

from config import config
from utils.file_utils import get_mime_type

video_app = FastAPI()

MEDIA_DIR = config.MEDIA_DIR.resolve() if config.MEDIA_DIR else None

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


@video_app.get("/media/serve_media/{file_path:path}")
async def serve_video(file_path: str, request: Request):
    """异步视频文件流式传输，完整支持浏览器 Range 请求 + 拖拽即播"""
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

    mimetype = get_mime_type(str(target))
    return FileResponse(
        str(target),
        media_type=mimetype,
        headers={"Accept-Ranges": "bytes"},
        filename=target.name,
    )


@video_app.get("/media/serve_media/")
async def serve_media_empty(request: Request):
    if not _check_login(request):
        return Response(status_code=403)
    return Response(status_code=400)

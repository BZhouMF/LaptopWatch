"""
FastAPI 视频流服务
异步非阻塞 + 大块传输 + 速率平滑，专用于大文件视频流式传输
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

# ── 日志 ──
_stream_logger = logging.getLogger('video_server')
_stream_logger.setLevel(logging.DEBUG)

# 确保 video_server 日志写入文件（复用 Flask 已有的文件 handler）
_flask_logger = logging.getLogger('utils.logging_utils')
for _handler in _flask_logger.handlers if _flask_logger.handlers else logging.getLogger().handlers:
    if isinstance(_handler, logging.Handler):
        _stream_logger.addHandler(_handler)

# 如果没拿到任何 handler，fallback 到 root logger 的
if not _stream_logger.handlers:
    _stream_logger.addHandler(logging.StreamHandler())
    _stream_logger.handlers[0].setFormatter(logging.Formatter(
        '[%(asctime)s] [VIDEO] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
    ))

video_app = FastAPI()

MEDIA_DIR = config.MEDIA_DIR.resolve() if config.MEDIA_DIR else None

# 视频流分块：1MB 大块减少系统调用；env 可覆盖
VIDEO_CHUNK = int(os.getenv('LAPTOPWATCH_VIDEO_CHUNK', 1024 * 1024))

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


async def _video_chunk_generator(filepath: str, start: int, end: int,
                                 request: Request, logger: logging.Logger):
    """
    异步生成器：大块读取视频文件，检测断连即停。
    依赖 async send() 提供 TCP 背压，不再使用人为延迟。
    """
    remaining = end - start + 1
    total_bytes = remaining
    chunk_count = 0
    t_start = time.monotonic()

    with open(filepath, 'rb') as fh:
        fh.seek(start)
        while remaining > 0:
            # 检查客户端是否断开（浏览器关闭 / 网络中断）
            if await request.is_disconnected():
                elapsed = time.monotonic() - t_start
                sent = total_bytes - remaining
                speed = (sent / 1024 / 1024 / elapsed) if elapsed > 0 else 0
                logger.warning(
                    f"客户端断开 | 已发送 {sent}/{total_bytes} bytes "
                    f"({sent*100//total_bytes}%) | {chunk_count} chunks | "
                    f"耗时 {elapsed:.1f}s | 均速 {speed:.1f} MB/s",
                )
                return

            chunk_size = min(VIDEO_CHUNK, remaining)
            data = fh.read(chunk_size)
            if not data:
                break
            remaining -= len(data)
            chunk_count += 1
            yield data

            # 每个 chunk 后让出事件循环，确保其他请求不被饿死，同时给 TCP 背压留出空间
            await asyncio.sleep(0)

    # 完整传输完成
    elapsed = time.monotonic() - t_start
    speed = (total_bytes / 1024 / 1024 / elapsed) if elapsed > 0 else 0
    logger.info(
        f"传输完成 | {total_bytes} bytes | {chunk_count} chunks | "
        f"耗时 {elapsed:.1f}s | 均速 {speed:.1f} MB/s",
    )


def _client_label(request: Request) -> str:
    """从 User-Agent 提取简要设备标识"""
    ua = request.headers.get('user-agent', '')
    if not ua:
        return 'unknown'
    ua_lower = ua.lower()
    if 'android' in ua_lower:
        return 'Android'
    if 'iphone' in ua_lower or 'ipad' in ua_lower:
        return 'iOS'
    if 'windows' in ua_lower:
        return 'Windows'
    if 'mac os' in ua_lower or 'macintosh' in ua_lower:
        return 'macOS'
    if 'linux' in ua_lower:
        return 'Linux'
    return 'other'


@video_app.get("/media/serve_media/{file_path:path}")
async def serve_video(file_path: str, request: Request):
    """视频流式传输 — 异步大块读取 + Range 支持 + 断连保护 + 详细日志"""
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
    client_ip = request.client.host if request.client else 'unknown'
    device = _client_label(request)

    if _is_video(str(target)):
        parsed = _parse_range(range_header, file_size)
        if parsed is None:
            return Response(status_code=416, headers={'Content-Range': f'bytes */{file_size}'})
        start, end = parsed
        content_length = end - start + 1
        has_range = bool(range_header and range_header.startswith('bytes='))

        _stream_logger.info(
            f"[请求] {client_ip} ({device}) | {target.name} | "
            f"文件 {file_size/1024/1024:.0f}MB | "
            f"Range: {'bytes=' + str(start) + '-' + str(end) if has_range else '全文件'} | "
            f"请求段 {content_length/1024/1024:.1f}MB"
        )

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

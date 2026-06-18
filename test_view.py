import os
import re
import time
import socket
import logging
import itertools
from pathlib import Path
from flask import Flask, request, Response

app = Flask(__name__)

VIDEO_PATH = r"F:/大合集/爱爱/1080.mp4"

VIDEO_CHUNK = int(os.getenv('LAPTOPWATCH_VIDEO_CHUNK', 0.5 * 1024 * 1024))

_stream_logger = logging.getLogger('test_video')
_stream_logger.setLevel(logging.INFO)
_stream_logger.propagate = False
if not _stream_logger.handlers:
    _log_dir = Path('logs')
    _log_dir.mkdir(exist_ok=True)
    _stream_logger.addHandler(logging.FileHandler(_log_dir / 'test_video.log', encoding='utf-8'))
    _stream_logger.handlers[0].setFormatter(logging.Formatter(
        '[%(asctime)s.%(msecs)03d] [TEST_VIDEO] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
    ))

_req_counter = itertools.count(1)


def _parse_range(range_header, file_size):
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


SEND_TIMEOUT = 5  # socket 发送超时秒数，超时即客户端停止接收


def _stream_video_file(filepath, range_header, environ):
    file_size = os.path.getsize(filepath)

    parsed = _parse_range(range_header, file_size)
    if parsed is None:
        return Response('', status=416, headers={'Content-Range': f'bytes */{file_size}'})
    start, end = parsed
    content_length = end - start + 1
    has_range = bool(range_header and range_header.startswith('bytes='))
    wsock = environ.get('werkzeug.socket') if environ else None

    req_id = next(_req_counter)
    _stream_logger.info(
        f"#{req_id} [REQ] | {os.path.basename(filepath)} | "
        f"{start}-{end} | {content_length/1024/1024:.1f}MB"
    )

    if wsock:
        wsock.settimeout(SEND_TIMEOUT)

    def generate():
        t0 = time.monotonic()
        sent = 0
        reason = 'done'
        try:
            remaining = content_length
            with open(filepath, 'rb') as fh:
                fh.seek(start)
                while remaining > 0:
                    chunk_size = min(VIDEO_CHUNK, remaining)
                    data = fh.read(chunk_size)
                    if not data:
                        reason = 'eof'
                        break
                    remaining -= len(data)
                    sent += len(data)
                    try:
                        yield data
                    except (socket.timeout, TimeoutError, OSError):
                        reason = 'timeout'
                        break
        finally:
            elapsed = time.monotonic() - t0
            speed = (sent / 1024 / 1024 / elapsed) if elapsed > 0 else 0
            _stream_logger.info(
                f"#{req_id} [END:{reason}] [{sent/1024/1024:.1f}MB] "
                f"{os.path.basename(filepath)} | {elapsed:.1f}s | {speed:.1f}MB/s"
            )

    headers = {
        'Accept-Ranges': 'bytes',
        'Content-Length': str(content_length),
        'Content-Type': 'video/mp4',
    }
    if has_range:
        headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'

    return Response(generate(), status=206 if has_range else 200, headers=headers, direct_passthrough=True)


@app.route("/")
def index():
    return """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>视频测试</title>
<style>body{margin:0;background:#000}video{width:100%;height:100vh}</style>
</head>
<body>
<video id="v" controls muted playsinline>
  <source src="/video" type="video/mp4">
</video>
<script>
const v = document.getElementById('v'),
      log = (e, t) => console.log(e, t || performance.now());
v.addEventListener('seeking', () => log('▶ seeking',  performance.now()));
v.addEventListener('seeked',  () => log('✓ seeked',  performance.now()));
v.addEventListener('waiting', () => log('⏳ waiting', performance.now()));
v.addEventListener('canplay', () => log('▷ canplay',  performance.now()));
</script>
</body>
</html>"""


@app.route("/video")
def video():
    range_header = request.headers.get('Range', '')
    return _stream_video_file(VIDEO_PATH, range_header, request.environ)


if __name__ == "__main__":
    size_gb = os.path.getsize(VIDEO_PATH) / (1024 ** 3)
    print(f'测试服务启动')
    print(f'  视频: {VIDEO_PATH} ({size_gb:.1f}GB)')
    print(f'  分块: {VIDEO_CHUNK / 1024:.0f}KB')
    print(f'  地址: http://0.0.0.0:5000')
    app.run(host="0.0.0.0", port=5000, threaded=True, debug=False)

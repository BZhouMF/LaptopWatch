"""
PyWebView 桌面 App 演示 — 内嵌 Flask 服务的桌面窗口

用法:
    python test_gui.py                          # 默认 video 模式
    python test_gui.py --mode douyin            # 抖音模式
    python test_gui.py --mode video --dir "F:/视频"
"""
import argparse
import os
import threading
import webview


def parse_args():
    parser = argparse.ArgumentParser(description='LaptopWatch 桌面 App')
    parser.add_argument('--mode', default='video', choices=['normal', 'video', 'image', 'douyin'],
                        help='运行模式')
    parser.add_argument('--dir', dest='media_dir', default=None,
                        help='媒体目录路径')
    parser.add_argument('--port', type=int, default=5000,
                        help='服务端口')
    return parser.parse_args()


def main():
    args = parse_args()

    # 在导入 app 之前设置环境变量，config.py 在 import 时读取
    os.environ['LAPTOPWATCH_MODE'] = args.mode
    if args.media_dir:
        os.environ['LAPTOPWATCH_MEDIA_DIR'] = args.media_dir
    if args.mode == 'douyin':
        os.environ['LAPTOPWATCH_CATEGORY_BROWSE'] = 'true'

    # env vars 就绪后才导入 app（config 模块在导入时读取 env）
    from app import app as flask_app

    def run_flask():
        from waitress import serve
        serve(flask_app, host='127.0.0.1', port=args.port, threads=16)

    threading.Thread(target=run_flask, daemon=True).start()

    webview.create_window(
        title=f'LaptopWatch - {args.mode}',
        url=f'http://127.0.0.1:{args.port}/setup',
        width=900,
        height=700,
        resizable=True,
        min_size=(700, 600),
    )
    webview.start(debug=False)


if __name__ == '__main__':
    main()

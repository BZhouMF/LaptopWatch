"""测试 video_server.py — 视频流生成器（_video_generator）

覆盖：Range 分段流式读取、客户端断开提前停止。
读取已改为 asyncio.to_thread（线程池），此测试确保行为不变。
"""
import asyncio
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _FakeRequest:
    """模拟 FastAPI Request，仅提供 is_disconnected"""

    def __init__(self, disconnected=False):
        self._disc = disconnected

    async def is_disconnected(self):
        return self._disc


async def _collect(agen):
    """收集异步生成器的全部块"""
    return [chunk async for chunk in agen]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestVideoGenerator:

    def test_streams_full_file(self):
        """完整范围（0..size-1）分块读取，内容正确"""
        from video_server import _video_generator
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b'0123456789' * 100)  # 1000 bytes
            path = f.name
        try:
            size = os.path.getsize(path)
            chunks = _run(_collect(_video_generator(path, 0, size - 1, _FakeRequest())))
            data = b''.join(chunks)
            assert len(data) == size
            assert data[:10] == b'0123456789'
            assert data[-10:] == b'0123456789'
        finally:
            os.unlink(path)

    def test_streams_partial_range(self):
        """部分 Range（100..199）只读取该段"""
        from video_server import _video_generator
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b'0123456789' * 100)  # 1000 bytes
            path = f.name
        try:
            chunks = _run(_collect(_video_generator(path, 100, 199, _FakeRequest())))
            data = b''.join(chunks)
            assert len(data) == 100
            assert data[:3] == b'012'  # 第 100 字节起
            assert data == b'0123456789' * 10
        finally:
            os.unlink(path)

    def test_stops_when_client_disconnects(self):
        """客户端断开后生成器立即停止（不继续读盘）"""
        from video_server import _video_generator
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b'x' * 10000)
            path = f.name
        try:
            size = os.path.getsize(path)
            # 第一次迭代后断开
            disc = _FakeRequest()

            async def run():
                agen = _video_generator(path, 0, size - 1, disc)
                first = await agen.__anext__()
                disc._disc = True  # 标记断开
                rest = []
                try:
                    async for chunk in agen:
                        rest.append(chunk)
                except StopAsyncIteration:
                    pass
                return first, rest

            first, rest = _run(run())
            assert len(first) > 0
            assert len(rest) == 0  # 断开后不再产出
        finally:
            os.unlink(path)

    def test_empty_requested_range_returns_nothing(self):
        """0 字节范围不产出任何块"""
        from video_server import _video_generator
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b'abc')
            path = f.name
        try:
            # start > end 的异常范围：调用方（_parse_range）不会产生，
            # 这里验证生成器本身对空范围行为稳定（不抛错）
            chunks = _run(_collect(_video_generator(path, 5, 3, _FakeRequest())))
            assert b''.join(chunks) == b''
        finally:
            os.unlink(path)

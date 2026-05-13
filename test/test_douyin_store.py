"""抖音会话存储线程安全测试"""
import time
import threading
import uuid


class TestDouyinStoreThreadSafety:
    """_douyin_store 线程安全测试（无需 Flask 上下文）"""

    def test_lock_exists(self):
        """验证 _douyin_lock 存在且是 threading.Lock"""
        from blueprints.douyin_api import _douyin_lock
        assert isinstance(_douyin_lock, type(threading.Lock()))

    def test_concurrent_write_no_crash(self):
        """多个线程并发写 _douyin_store 不应崩溃"""
        from blueprints.douyin_api import _douyin_store, _douyin_lock

        errors = []

        def writer(thread_id):
            for i in range(100):
                try:
                    sid = f'thread-{thread_id}-iter-{i}'
                    with _douyin_lock:
                        _douyin_store[sid] = {
                            'mode': 'test',
                            'cursor': i,
                            'last_activity_time': time.time(),
                        }
                except Exception as e:
                    errors.append(f'write error: {e}')

        threads = [threading.Thread(target=writer, args=(tid,), daemon=True) for tid in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f'并发写入 _douyin_store 出现错误: {errors}'

        # 清理
        with _douyin_lock:
            _douyin_store.clear()

    def test_concurrent_read_write_no_crash(self):
        """并发读写同一 sid 不应崩溃"""
        from blueprints.douyin_api import _douyin_store, _douyin_lock

        sid = f'test-sid-{uuid.uuid4().hex[:8]}'
        with _douyin_lock:
            _douyin_store[sid] = {
                'mode': 'test',
                'cursor': 0,
                'buffer': [],
                'has_more': True,
                'last_activity_time': time.time(),
            }

        errors = []

        def reader():
            for _ in range(200):
                try:
                    with _douyin_lock:
                        state = _douyin_store.get(sid)
                        if state:
                            _ = state['cursor']
                            state['last_activity_time'] = time.time()
                except Exception as e:
                    errors.append(f'read error: {e}')

        def writer():
            for i in range(200):
                try:
                    with _douyin_lock:
                        if sid in _douyin_store:
                            _douyin_store[sid]['cursor'] = i
                            _douyin_store[sid]['last_activity_time'] = time.time()
                except Exception as e:
                    errors.append(f'write error: {e}')

        threads = [threading.Thread(target=reader, daemon=True),
                   threading.Thread(target=writer, daemon=True),
                   threading.Thread(target=reader, daemon=True),
                   threading.Thread(target=writer, daemon=True)]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f'并发读写 _douyin_store 出现错误: {errors}'

        # 清理
        with _douyin_lock:
            _douyin_store.clear()

    def test_cleanup_during_write_no_crash(self):
        """并发 cleanup 遍历 + 写入不应崩溃"""
        from blueprints.douyin_api import _douyin_store, _douyin_lock, _cleanup_stale

        # 预填一些过期数据
        with _douyin_lock:
            for i in range(50):
                _douyin_store[f'stale-{i}'] = {
                    'mode': 'test',
                    'last_activity_time': time.time() - 7200,  # 2小时前 -> 过期
                }
            for i in range(50):
                _douyin_store[f'fresh-{i}'] = {
                    'mode': 'test',
                    'last_activity_time': time.time(),
                }

        errors = []

        def cleaner():
            for _ in range(20):
                try:
                    _cleanup_stale()
                except Exception as e:
                    errors.append(f'cleanup error: {e}')

        def writer():
            for i in range(200):
                try:
                    with _douyin_lock:
                        _douyin_store[f'new-{threading.get_ident()}-{i}'] = {
                            'mode': 'test',
                            'last_activity_time': time.time(),
                        }
                except Exception as e:
                    errors.append(f'write error: {e}')

        threads = [threading.Thread(target=cleaner, daemon=True),
                   threading.Thread(target=writer, daemon=True),
                   threading.Thread(target=writer, daemon=True)]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f'并发 cleanup + write 出现错误: {errors}'

        with _douyin_lock:
            _douyin_store.clear()

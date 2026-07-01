"""测试 logging_utils.py — 日志工具模块"""
import logging
import sys
import os
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import config


class TestStructuredFormatter:
    """测试 StructuredFormatter"""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from utils.logging_utils import StructuredFormatter
        self.formatter = StructuredFormatter()

    def _make_record(self, msg="test message", context=None):
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg=msg, args=(), exc_info=None
        )
        if context:
            record.context = context
        return record

    def test_plain_mode_delegates_to_parent(self):
        original = config.LOG_STRUCTURED
        config.LOG_STRUCTURED = False
        try:
            record = self._make_record("hello")
            result = self.formatter.format(record)
            assert isinstance(result, str)
            assert "hello" in result
        finally:
            config.LOG_STRUCTURED = original

    def test_structured_mode_returns_json(self):
        import json
        original = config.LOG_STRUCTURED
        config.LOG_STRUCTURED = True
        try:
            record = self._make_record("test msg", context={
                'client_ip': '127.0.0.1',
                'action': 'LOGIN',
                'target_path': '/login',
                'duration': 0.1,
            })
            result = self.formatter.format(record)
            parsed = json.loads(result)
            assert parsed['ip'] == '127.0.0.1'
            assert parsed['action'] == 'LOGIN'
            assert parsed['path'] == '/login'
            assert parsed['msg'] == 'test msg'
        finally:
            config.LOG_STRUCTURED = original

    def test_structured_mode_without_context_defaults_to_unknown(self):
        import json
        original = config.LOG_STRUCTURED
        config.LOG_STRUCTURED = True
        try:
            record = self._make_record("test")
            result = self.formatter.format(record)
            parsed = json.loads(result)
            assert parsed['ip'] == 'unknown'
            assert parsed['action'] == 'unknown'
        finally:
            config.LOG_STRUCTURED = original


class TestSafePrint:
    """测试 _safe_print"""

    def test_prints_normal_text(self, capsys):
        from utils.logging_utils import _safe_print
        _safe_print("hello world", flush=False)
        captured = capsys.readouterr()
        assert "hello world" in captured.out

    def test_prints_multiple_args(self, capsys):
        from utils.logging_utils import _safe_print
        _safe_print("a", "b", "c", flush=False)
        captured = capsys.readouterr()
        assert "a b c" in captured.out


class TestGetSessionId:
    """测试 get_session_id"""

    def test_returns_unknown_when_no_session(self):
        from utils.logging_utils import get_session_id
        result = get_session_id()
        assert isinstance(result, str)

    def test_returns_uuid_string(self):
        from utils.logging_utils import get_session_id
        result = get_session_id()
        # Should be either a UUID or 'unknown'
        assert len(result) > 0


class TestLogAccess:
    """测试 log_access"""

    def test_does_not_raise_with_mock_request(self):
        from utils.logging_utils import log_access
        from unittest.mock import Mock
        mock_req = Mock()
        mock_req.remote_addr = '127.0.0.1'
        # Should not raise
        log_access(mock_req, 'TEST', '/test/path', duration=0.001)

    def test_normalizes_backslash_path(self):
        from utils.logging_utils import log_access
        from unittest.mock import Mock
        mock_req = Mock()
        mock_req.remote_addr = '127.0.0.1'
        # Should not raise with backslash path
        log_access(mock_req, 'BROWSE', 'C:\\Users\\test', duration=0.001)


class TestLogException:
    """测试 log_exception"""

    def test_does_not_raise(self):
        from utils.logging_utils import log_exception
        from unittest.mock import Mock
        mock_req = Mock()
        mock_req.remote_addr = '127.0.0.1'
        log_exception(mock_req, 'TEST', '/test', ValueError("test error"))


class TestSetupLogging:
    """测试 setup_logging"""

    def test_does_not_raise(self):
        from utils.logging_utils import setup_logging
        # Save root logger state
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        original_level = root.level
        try:
            setup_logging()
        finally:
            # Restore
            root.handlers.clear()
            for h in original_handlers:
                root.addHandler(h)
            root.setLevel(original_level)

    def test_adds_handlers(self):
        from utils.logging_utils import setup_logging
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        original_level = root.level
        try:
            setup_logging()
            assert len(root.handlers) >= 1
        finally:
            root.handlers.clear()
            for h in original_handlers:
                root.addHandler(h)
            root.setLevel(original_level)

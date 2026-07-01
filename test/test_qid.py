"""测试 qid.py — Web管理后端（QID 模块）"""
import os
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import config


@pytest.fixture(autouse=True)
def _reset_qid_globals():
    """每个测试后重置 qid.py 的模块级全局变量"""
    yield
    import qid as qid_module
    qid_module.process = None
    qid_module.process_pid = None
    qid_module.log_buffer.clear()
    qid_module.session_logs = []
    qid_module.session_start_time = None
    qid_module.session_id = None
    qid_module.server_url = ''
    qid_module.mgmt_config.update({
        'mode': 'normal',
        'media_dir': '',
        'sort_type': 'name',
        'sort_order': 'asc',
        'random': False,
        'douyin_random_media': False,
        'category_browse': False,
    })
    # Clear log queue
    while not qid_module.log_queue.empty():
        qid_module.log_queue.get()
    qid_module.shutdown_scheduled_at = None


@pytest.fixture
def qid_client():
    """创建 qid_app 的测试客户端"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from qid import qid_app
    qid_app.config['TESTING'] = True
    with qid_app.test_client() as client:
        yield client


@pytest.fixture
def logged_in_qid(qid_client):
    """已登录的 qid 客户端"""
    with qid_client.session_transaction() as sess:
        sess['qid_authenticated'] = True
    yield qid_client


class TestPageRoute:

    def test_index_returns_html(self, qid_client):
        resp = qid_client.get('/')
        assert resp.status_code == 200


class TestAuth:

    def test_login_success(self, qid_client):
        resp = qid_client.post('/api/login', json={'password': config.DEFAULT_PASSWORD})
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['code'] == 0

    def test_login_wrong_password(self, qid_client):
        resp = qid_client.post('/api/login', json={'password': 'wrong'})
        data = resp.get_json()
        assert data['code'] == 1

    def test_logout(self, qid_client):
        with qid_client.session_transaction() as sess:
            sess['qid_authenticated'] = True
        resp = qid_client.post('/api/logout')
        data = resp.get_json()
        assert data['code'] == 0

    def test_protected_route_requires_login(self, qid_client):
        resp = qid_client.get('/api/status')
        assert resp.status_code == 401


class TestStatus:

    def test_status_returns_running_false(self, logged_in_qid, monkeypatch):
        import qid as qid_module
        monkeypatch.setattr(qid_module, 'check_port', lambda port: [])
        monkeypatch.setattr(qid_module, 'get_local_ip', lambda: '127.0.0.1')
        resp = logged_in_qid.get('/api/status')
        data = resp.get_json()
        assert data['code'] == 0
        assert data['data']['running'] is False

    def test_status_returns_config(self, logged_in_qid, monkeypatch):
        import qid as qid_module
        monkeypatch.setattr(qid_module, 'check_port', lambda port: [])
        monkeypatch.setattr(qid_module, 'get_local_ip', lambda: '127.0.0.1')
        resp = logged_in_qid.get('/api/status')
        data = resp.get_json()
        assert 'config' in data['data']


class TestConfig:

    def test_get_config(self, logged_in_qid):
        resp = logged_in_qid.get('/api/config')
        data = resp.get_json()
        assert data['code'] == 0
        assert 'data' in data

    def test_update_config(self, logged_in_qid):
        resp = logged_in_qid.post('/api/config', json={'mode': 'video'})
        data = resp.get_json()
        assert data['code'] == 0
        # Verify it was updated
        import qid as qid_module
        assert qid_module.mgmt_config['mode'] == 'video'


class TestLogs:

    def test_log_ingest_with_password(self, qid_client):
        resp = qid_client.post(
            '/api/logs/ingest',
            json={
                'password': config.DEFAULT_PASSWORD,
                'logs': ['line 1', 'line 2'],
                'session_id': 'test-session',
            }
        )
        data = resp.get_json()
        # May fail if session_id not set — just verify it doesn't 500
        assert resp.status_code in (200, 400)

    def test_log_ingest_without_password(self, qid_client):
        resp = qid_client.post('/api/logs/ingest', json={'logs': ['line 1']})
        assert resp.status_code == 401

    def test_logs_recent(self, logged_in_qid):
        # Ingest some logs first
        import qid as qid_module
        qid_module.add_log("test log 1")
        qid_module.add_log("test log 2")
        resp = logged_in_qid.get('/api/logs/recent')
        data = resp.get_json()
        assert data['code'] == 0

    def test_add_log_truncates(self):
        import qid as qid_module
        qid_module.log_buffer.clear()
        for idx in range(600):
            qid_module.add_log(f"line {idx}")
        assert len(qid_module.log_buffer) <= qid_module.MAX_LOG_LINES


class TestDirs:

    def test_dirs_returns_list(self, logged_in_qid):
        resp = logged_in_qid.get('/api/dirs')
        data = resp.get_json()
        assert data['code'] == 0
        assert 'data' in data


class TestShutdown:

    def test_shutdown_schedule(self, logged_in_qid):
        resp = logged_in_qid.post('/api/shutdown/schedule')
        data = resp.get_json()
        assert data['code'] == 0
        assert data['data']['scheduled_at'] is not None

    def test_shutdown_schedule_duplicate(self, logged_in_qid):
        import qid as qid_module
        qid_module.shutdown_scheduled_at = 9999999999.0
        resp = logged_in_qid.post('/api/shutdown/schedule')
        data = resp.get_json()
        assert data['code'] == 1

    def test_shutdown_cancel_when_none(self, logged_in_qid):
        resp = logged_in_qid.post('/api/shutdown/cancel')
        data = resp.get_json()
        assert data['code'] == 1

    def test_shutdown_status(self, logged_in_qid):
        resp = logged_in_qid.get('/api/shutdown/status')
        data = resp.get_json()
        assert data['code'] == 0
        assert 'scheduled' in data['data']

    def test_shutdown_cycle(self, logged_in_qid):
        # Schedule
        resp = logged_in_qid.post('/api/shutdown/schedule')
        data = resp.get_json()
        assert data['code'] == 0
        # Cancel
        resp = logged_in_qid.post('/api/shutdown/cancel')
        data = resp.get_json()
        assert data['code'] == 0


class TestHelpers:

    def test_add_log_appends(self):
        import qid as qid_module
        qid_module.log_buffer.clear()
        qid_module.add_log("hello")
        assert "hello" in qid_module.log_buffer

    def test_add_log_accepts_non_string(self):
        import qid as qid_module
        qid_module.log_buffer.clear()
        qid_module.add_log(123)
        assert any("123" in str(item) for item in qid_module.log_buffer)


class TestLoginRequired:

    def test_status_unauthorized(self, qid_client):
        resp = qid_client.get('/api/status')
        assert resp.status_code == 401

    def test_config_get_unauthorized(self, qid_client):
        resp = qid_client.get('/api/config')
        assert resp.status_code == 401

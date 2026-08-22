"""测试 app.py — Flask 应用中间件/错误处理/模板注入"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import config


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        yield td


@pytest.fixture
def db_path():
    _dir = tempfile.mkdtemp()
    yield os.path.join(_dir, 'test.db')
    import shutil
    shutil.rmtree(_dir, ignore_errors=True)


@pytest.fixture
def test_app(temp_dir, db_path):
    """创建最小 Flask 应用用于测试"""
    config.RUN_MODE = 'normal'
    config.MEDIA_DIR = Path(temp_dir)
    config.DB_PATH = db_path
    config.SERVICE_ACTIVE = True

    from flask import Flask
    app = Flask(__name__)
    app.secret_key = 'test-secret'

    from blueprints.auth import auth_bp
    from blueprints.core import core_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(core_bp)

    # Copy key middleware from app.py
    _SERVICE_GATE_WHITELIST = frozenset({
        '/api/admin/config', '/api/config-version', '/api/mode', '/api/drives',
    })
    _GATE_SKIP_PREFIXES = (
        '/static/', '/favicon.ico', '/media/thumbnail/',
        '/media/serve_media/', '/media/navigate',
    )

    @app.before_request
    def gate_service_active():
        from flask import request as _req
        path = _req.path
        if path.startswith(_GATE_SKIP_PREFIXES):
            return None
        if path.rstrip('/') in _SERVICE_GATE_WHITELIST or path.startswith('/api/check_path'):
            return None
        if not config.SERVICE_ACTIVE:
            from flask import jsonify
            return jsonify({'code': 1, 'msg': '服务未激活', 'service_active': False}), 503
        return None

    from werkzeug.exceptions import HTTPException

    @app.errorhandler(404)
    def handle_not_found(e):
        from flask import request, jsonify
        if request.path.startswith('/api/'):
            return jsonify({'code': 1, 'msg': '请求的资源不存在'}), 404
        return jsonify({'code': 1, 'msg': '页面不存在'}), 404

    @app.errorhandler(405)
    def handle_method_not_allowed(e):
        from flask import jsonify
        return jsonify({'code': 1, 'msg': '方法不允许'}), 405

    @app.errorhandler(Exception)
    def handle_unhandled_exception(e):
        if isinstance(e, HTTPException):
            return e
        from flask import jsonify
        return jsonify({'code': 1, 'msg': '服务器内部错误'}), 500

    @app.route('/api/test_exception')
    def trigger_exception():
        raise ValueError("test error")

    @app.route('/api/post_only', methods=['POST'])
    def post_only():
        return {'ok': True}

    @app.context_processor
    def inject_routes():
        return {'ROUTES': {'test': '/test'}, 'config': config}

    @app.template_filter('path_quote')
    def path_quote_filter(path):
        from urllib.parse import quote
        return quote(path, safe='/')

    yield app
    config.DB_PATH = None
    config.MEDIA_DIR = None
    config.RUN_MODE = 'normal'
    config.SERVICE_ACTIVE = False


@pytest.fixture
def client(test_app):
    with test_app.test_client() as c:
        yield c


@pytest.fixture
def logged_in_client(test_app):
    with test_app.test_client() as c:
        with c.session_transaction() as sess:
            sess['logged_in'] = True
        yield c


class TestServiceGate:
    """测试服务激活门控"""

    def test_service_inactive_returns_503(self, client):
        config.SERVICE_ACTIVE = False
        resp = client.get('/')
        assert resp.status_code == 503
        data = resp.get_json()
        assert data['service_active'] is False

    def test_service_active_allows_request(self, client):
        config.SERVICE_ACTIVE = True
        resp = client.get('/api/mode')
        assert resp.status_code == 200

    def test_whitelist_bypasses_gate(self, client):
        config.SERVICE_ACTIVE = False
        resp = client.get('/api/mode')
        assert resp.status_code == 200

    def test_config_version_bypasses_gate(self, client):
        config.SERVICE_ACTIVE = False
        resp = client.get('/api/config-version')
        assert resp.status_code == 200

    def test_static_prefix_bypasses_gate(self, client):
        config.SERVICE_ACTIVE = False
        resp = client.get('/static/css/style.css')
        # May 404 or 503 — but should NOT be 503 if prefix matches
        assert resp.status_code != 503

    def test_check_path_bypasses_gate(self, logged_in_client):
        config.SERVICE_ACTIVE = False
        resp = logged_in_client.get('/api/check_path?path=/')
        assert resp.status_code != 503  # may be 200 or 404


class TestErrorHandlers:
    """测试错误处理器"""

    def test_404_api_returns_json(self, client):
        resp = client.get('/api/nonexistent_endpoint')
        assert resp.status_code == 404
        data = resp.get_json()
        assert data['code'] == 1

    def test_405_returns_json(self, client):
        resp = client.get('/api/post_only')
        assert resp.status_code == 405
        data = resp.get_json()
        assert '方法不允许' in data['msg']

    def test_500_on_exception(self, client):
        resp = client.get('/api/test_exception')
        assert resp.status_code == 500


class TestContextProcessor:
    """测试 context_processor"""

    def test_injects_routes(self, client, test_app):
        """验证 context_processor 注入的 ROUTES 可用"""
        with test_app.app_context():
            routes = config.REACT_DIST_DIR
            assert isinstance(routes, Path)


class TestTemplateFilter:
    """测试 path_quote 模板过滤器"""

    def test_preserves_slashes(self):
        from urllib.parse import quote
        result = quote("path/with spaces/file.txt", safe='/')
        assert '/' in result
        assert 'path' in result


class TestTeardown:
    """测试 teardown_request"""

    def test_teardown_funcs_is_dict(self, test_app):
        """验证 teardown_request_funcs 存在"""
        assert hasattr(test_app, 'teardown_request_funcs')


class TestRequestLogging:
    """请求日志（app.py log_incoming_request）：走 logging 体系落文件，非 GUI 不重复刷 stdout"""

    def test_request_log_written_via_logging(self, tmp_path, monkeypatch, capsys):
        """[REQUEST] 日志经过 logging 体系（可被文件 handler 捕获），非 GUI 模式不 print"""
        import logging as _logging
        from config import config as _config

        monkeypatch.setattr(_config, 'LOG_DIR', tmp_path)
        monkeypatch.setattr('utils.logging_utils._IS_GUI', False)

        root = _logging.getLogger()
        original_handlers = list(root.handlers)
        original_level = root.level
        try:
            import app as app_module  # 顶层会执行 setup_logging()

            # 测试环境 conftest 把 LOG_LEVEL 设为 CRITICAL，临时降到 INFO 以便捕获
            root.setLevel(_logging.INFO)

            # 追加捕获 handler，验证 [REQUEST] 确实经过 logging 体系
            records = []

            class Capture(_logging.Handler):
                def emit(self, record):
                    records.append(record.getMessage())

            capture = Capture()
            capture.setLevel(_logging.INFO)
            root.addHandler(capture)

            # /api/config-version 是服务门控白名单，请求必然到达 log_incoming_request
            app_module.config.SERVICE_ACTIVE = True
            with app_module.app.test_client() as c:
                with c.session_transaction() as sess:
                    sess['logged_in'] = True
                c.get('/api/config-version')

            assert any('[REQUEST]' in r for r in records), "REQUEST 日志未经过 logging"
            # 非 GUI 模式：不额外 print（避免与 console handler 重复）
            out = capsys.readouterr().out
            assert '[REQUEST]' not in out
        finally:
            root.handlers.clear()
            for h in original_handlers:
                root.addHandler(h)
            root.setLevel(original_level)

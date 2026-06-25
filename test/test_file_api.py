"""测试 file_api.py — 文件下载/预览/批量操作"""
import os
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
def app(temp_dir, db_path):
    """Flask 应用，normal 模式 + 测试目录"""
    config.RUN_MODE = 'normal'
    config.MEDIA_DIR = Path(temp_dir)
    config.DB_PATH = db_path

    from flask import Flask
    app = Flask(__name__)
    app.secret_key = 'test-secret'

    from blueprints.auth import auth_bp
    from blueprints.file_api import file_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(file_bp)
    yield app
    config.DB_PATH = None


@pytest.fixture
def client(app):
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['logged_in'] = True
        yield c


def _create_file(path, content='test content'):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)


class TestServeRaw:

    def test_returns_file_content(self, client, temp_dir):
        """serve_raw 返回文件内容"""
        _create_file(os.path.join(temp_dir, 'readme.txt'), 'hello world')
        filepath = os.path.join(temp_dir, 'readme.txt')

        resp = client.get(f'/file/raw/{filepath}')
        assert resp.status_code == 200
        assert b'hello world' in resp.data

    def test_file_not_found(self, client):
        """不存在文件返回 404"""
        resp = client.get('/file/raw/nonexistent/file.txt')
        assert resp.status_code == 404


class TestViewFile:

    def test_downloads_with_attachment(self, client, temp_dir):
        """view_file 触发下载"""
        _create_file(os.path.join(temp_dir, 'download.txt'), 'download me')
        filepath = os.path.join(temp_dir, 'download.txt')

        resp = client.get(f'/file/view/{filepath}')
        assert resp.status_code == 200
        assert b'download me' in resp.data


class TestDownloadFolder:

    def test_returns_zip(self, client, temp_dir):
        """download_folder 返回 ZIP 文件"""
        sub = os.path.join(temp_dir, 'sub')
        _create_file(os.path.join(sub, 'a.txt'), 'aaa')
        _create_file(os.path.join(sub, 'b.txt'), 'bbb')

        resp = client.get(f'/file/download_folder?path={sub}')
        assert resp.status_code == 200
        assert resp.content_type == 'application/zip'

    def test_missing_path(self, client):
        """缺少路径参数返回 400"""
        resp = client.get('/file/download_folder')
        assert resp.status_code == 400

    def test_nonexistent_path(self, client):
        """不存在路径返回 404"""
        resp = client.get('/file/download_folder?path=/nonexistent/path')
        assert resp.status_code == 404

    def test_empty_folder(self, client, temp_dir):
        """空文件夹返回 400"""
        empty = os.path.join(temp_dir, 'empty')
        os.makedirs(empty)

        resp = client.get(f'/file/download_folder?path={empty}')
        assert resp.status_code == 400


class TestDownloadSelected:

    def test_batch_download(self, client, temp_dir):
        """批量下载返回 ZIP"""
        _create_file(os.path.join(temp_dir, 'x.txt'), 'x')
        _create_file(os.path.join(temp_dir, 'y.txt'), 'y')

        resp = client.post('/file/download_selected', json={
            'base': temp_dir,
            'paths': [
                os.path.join(temp_dir, 'x.txt'),
                os.path.join(temp_dir, 'y.txt'),
            ],
        })
        assert resp.status_code == 200
        assert resp.content_type == 'application/zip'

    def test_path_traversal_blocked(self, client, temp_dir):
        """路径穿越被拒绝"""
        resp = client.post('/file/download_selected', json={
            'base': temp_dir,
            'paths': ['/etc/passwd'],
        })
        assert resp.status_code == 400

"""测试 category_api.py — 分类数据与网格分页从 DB 读取"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        yield td


def _create_file(path, content='test'):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)


@pytest.fixture
def db_path():
    """独立 DB 路径，避免文件锁定影响 temp_dir 清理"""
    _dir = tempfile.mkdtemp()
    yield os.path.join(_dir, 'test.db')
    import shutil
    shutil.rmtree(_dir, ignore_errors=True)


@pytest.fixture
def app(temp_dir, db_path):
    """Flask 应用，video 模式 + 隔离的测试数据库"""
    config.RUN_MODE = 'video'
    config.MEDIA_DIR = Path(temp_dir)
    config.DB_PATH = db_path

    from flask import Flask
    app = Flask(__name__)
    app.secret_key = 'test-secret'

    from blueprints.auth import auth_bp
    from blueprints.category_api import category_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(category_bp)
    yield app
    config.DB_PATH = None


@pytest.fixture
def client(app):
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['logged_in'] = True
        yield c


class TestCategoryData:

    def _seed_subfolders(self, base):
        """创建子文件夹结构用于分类测试"""
        sub_a = os.path.join(base, 'SubA')
        sub_b = os.path.join(base, 'SubB')
        os.makedirs(sub_a)
        os.makedirs(sub_b)
        _create_file(os.path.join(sub_a, 'video1.mp4'))
        _create_file(os.path.join(sub_a, 'video2.mp4'))
        _create_file(os.path.join(sub_b, 'video3.mp4'))
        return sub_a, sub_b

    def test_returns_categories(self, client, temp_dir):
        """/category/data 返回分类结构"""
        self._seed_subfolders(temp_dir)

        resp = client.get('/category/data')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 0

        info = data['data']
        assert info['is_leaf'] is False
        assert info['total_categories'] == 2
        assert len(info['categories']) == 2
        assert info['categories'][0]['has_files'] is True

    def test_category_has_preview_files(self, client, temp_dir):
        """每个分类区块包含预览文件"""
        self._seed_subfolders(temp_dir)

        resp = client.get('/category/data')
        info = resp.get_json()['data']

        for cat in info['categories']:
            assert len(cat['files']) > 0
            for f in cat['files']:
                assert 'name' in f
                assert 'relative_path' in f
                assert f['is_video'] is True

    def test_leaf_folder_no_subdirs(self, client, temp_dir):
        """叶子文件夹返回空分类列表"""
        os.makedirs(os.path.join(temp_dir, 'SubA'))
        resp = client.get('/category/data?path=SubA')
        assert resp.status_code == 200
        info = resp.get_json()['data']
        # SubA 没有子文件夹，所以 is_leaf 应为 True
        assert info['is_leaf'] is True or info['total_categories'] == 0

    def test_root_files_included(self, client, temp_dir):
        """根目录下的直接文件包含在 root_files 中"""
        _create_file(os.path.join(temp_dir, 'root_video.mp4'))
        self._seed_subfolders(temp_dir)

        resp = client.get('/category/data')
        info = resp.get_json()['data']

        assert len(info['root_files']) >= 1
        names = [f['name'] for f in info['root_files']]
        assert 'root_video.mp4' in names

    def test_root_files_not_capped_when_folder_has_subfolders(self, client, temp_dir):
        """文件夹同时含视频+子文件夹时，root_files 应全部返回，不受 CATEGORY_PAGE_SIZE 限制"""
        # 创建超过 CATEGORY_PAGE_SIZE(=6) 的直接视频 + 一个子文件夹
        for i in range(10):
            _create_file(os.path.join(temp_dir, f'root_video_{i}.mp4'))
        self._seed_subfolders(temp_dir)

        resp = client.get('/category/data')
        info = resp.get_json()['data']

        assert info['is_leaf'] is False
        assert len(info['root_files']) == 10
        names = [f['name'] for f in info['root_files']]
        assert all(f'root_video_{i}.mp4' in names for i in range(10))

    def test_empty_folder(self, client, temp_dir):
        """空文件夹返回空分类"""
        resp = client.get('/category/data')
        info = resp.get_json()['data']
        assert info['total_categories'] == 0
        assert info['is_leaf'] is True


class TestCategoryGridMore:

    def _seed_files(self, base):
        """在 base 下直接创建媒体文件"""
        for i in range(5):
            _create_file(os.path.join(base, f'video{i}.mp4'))

    def test_pagination(self, client, temp_dir):
        """grid_more 分页返回"""
        self._seed_files(temp_dir)

        resp = client.get('/category/grid_more?path=&offset=0&limit=2')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 0
        assert len(data['data']) == 2
        assert data['has_more'] is True

    def test_full_pagination(self, client, temp_dir):
        """多次分页取完"""
        self._seed_files(temp_dir)

        r1 = client.get('/category/grid_more?path=&offset=0&limit=3')
        d1 = r1.get_json()
        assert len(d1['data']) == 3

        r2 = client.get(f'/category/grid_more?path=&offset={d1["next_offset"]}&limit=3')
        d2 = r2.get_json()
        assert len(d2['data']) == 2
        assert d2['has_more'] is False

    def test_empty_subfolder_grid(self, client, temp_dir):
        """空子文件夹的 grid_more 返回空列表"""
        sub = os.path.join(temp_dir, 'SubEmpty')
        os.makedirs(sub)
        rel = os.path.relpath(sub, temp_dir).replace('\\', '/')
        resp = client.get(f'/category/grid_more?path={rel}&offset=0&limit=10')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 0
        assert len(data['data']) == 0
        assert data['has_more'] is False

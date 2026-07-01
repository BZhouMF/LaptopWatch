"""测试 routes_config.py — 路由常量模块"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from routes_config import Routes, FRONTEND_ROUTES


class TestRoutes:
    """Routes 类常量定义"""

    def test_auth_routes(self):
        assert Routes.AUTH_LOGIN == '/login'
        assert Routes.AUTH_LOGOUT == '/logout'

    def test_core_routes(self):
        assert Routes.CORE_INDEX == '/'
        assert Routes.CORE_BROWSE == '/browse/<path:dirpath>'

    def test_api_routes(self):
        assert Routes.API_CHECK_PATH == '/api/check_path'
        assert Routes.API_LIST == '/api/list'
        assert Routes.API_LIST_ALL == '/api/list_all'

    def test_media_routes(self):
        assert Routes.MEDIA_LOAD_MORE == '/media/load_more'
        assert Routes.MEDIA_THUMBNAIL == '/media/thumbnail/<path:relative_path>'
        assert Routes.MEDIA_SERVE == '/media/serve_media/<path:relative_path>'
        assert Routes.MEDIA_DOWNLOAD == '/media/download_media/<path:relative_path>'
        assert Routes.MEDIA_NAVIGATE == '/media/navigate'

    def test_file_routes(self):
        assert Routes.FILE_RAW == '/file/raw/<path:filepath>'
        assert Routes.FILE_VIEW == '/file/view/<path:filepath>'
        assert Routes.FILE_TEXT == '/file/text/<path:filepath>'
        assert Routes.FILE_DOWNLOAD_FOLDER == '/file/download_folder'
        assert Routes.FILE_DOWNLOAD_SELECTED == '/file/download_selected'

    def test_douyin_routes(self):
        assert Routes.DOUYIN_INIT == '/api/douyin/init'
        assert Routes.DOUYIN_NEXT == '/api/douyin/next'

    def test_static_routes(self):
        assert Routes.STATIC_CSS_STYLE == '/static/css/style.css'
        assert Routes.STATIC_JS_MODAL == '/static/js/modal.js'
        assert Routes.STATIC_JS_UTILS == '/static/js/utils.js'
        assert Routes.STATIC_JS_BROWSE == '/static/js/browse.js'
        assert Routes.STATIC_JS_MEDIA_INDEX == '/static/js/media_index.js'
        assert Routes.STATIC_JS_VIDEO_PLAYER == '/static/js/Video_Player.js'

    def test_no_duplicate_values(self):
        """路由值不应重复"""
        members = [
            v for k, v in vars(Routes).items()
            if not k.startswith('_') and isinstance(v, str)
        ]
        assert len(members) == len(set(members)), f"发现重复路由值"


class TestFrontendRoutes:
    """FRONTEND_ROUTES 字典"""

    def test_contains_expected_keys(self):
        expected_keys = [
            'apiCheckPath', 'apiList', 'apiListAll',
            'mediaLoadMore', 'mediaThumbnail', 'mediaDownload', 'mediaNavigate',
            'fileRaw', 'fileView', 'fileText',
            'fileDownloadFolder', 'fileDownloadSelected',
            'douyinInit', 'douyinNext',
            'browse', 'categoryData', 'categoryBrowse', 'categoryGrid',
            'categoryGridMore', 'mediaPlayer',
        ]
        for key in expected_keys:
            assert key in FRONTEND_ROUTES, f"缺少 key: {key}"

    def test_all_values_are_strings(self):
        for key, value in FRONTEND_ROUTES.items():
            assert isinstance(value, str), f"{key} 的值不是字符串: {value!r}"

    def test_values_start_with_slash(self):
        for key, value in FRONTEND_ROUTES.items():
            assert value.startswith('/'), f"{key} 的值不以 / 开头: {value!r}"

    def test_media_serve_injected_by_context_processor(self):
        """mediaServe 由 app.py context_processor 动态注入，不在 FRONTEND_ROUTES 中"""
        assert 'mediaServe' not in FRONTEND_ROUTES

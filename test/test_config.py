"""测试 config.py — Config 类"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestUpdateRuntime:
    """测试 update_runtime() 方法"""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from config import config
        self.config = config
        self._original_db_path = self.config._db_path_override
        yield
        self.config._db_path_override = self._original_db_path

    def test_mode_video_without_media_dir_fails(self):
        self.config.MEDIA_DIR = None
        ok, result = self.config.update_runtime(mode='video')
        assert ok is False
        assert result['code'] == 1

    def test_mode_video_with_media_dir_succeeds(self, tmp_path):
        self.config.MEDIA_DIR = tmp_path
        ok, result = self.config.update_runtime(mode='video')
        assert ok is True
        assert result['run_mode'] == 'video'
        assert self.config.RUN_MODE == 'video'

    def test_mode_normal_always_succeeds(self):
        ok, result = self.config.update_runtime(mode='normal')
        assert ok is True
        assert result['run_mode'] == 'normal'

    def test_douyin_mode_disables_category_browse(self, tmp_path):
        self.config.MEDIA_DIR = tmp_path
        self.config.CATEGORY_BROWSE = True
        ok, result = self.config.update_runtime(mode='douyin')
        assert ok is True
        assert result['run_mode'] == 'douyin'
        assert result['category_browse'] is False

    def test_media_dir_empty_string_sets_none(self):
        ok, result = self.config.update_runtime(media_dir='')
        assert ok is True
        assert self.config.MEDIA_DIR is None

    def test_media_dir_path_resolves(self, tmp_path):
        ok, _ = self.config.update_runtime(media_dir=str(tmp_path))
        assert ok is True
        assert self.config.MEDIA_DIR == tmp_path.resolve()

    def test_random_mode_toggle(self):
        original = self.config.RANDOM_MODE
        ok, result = self.config.update_runtime(random_mode=not original)
        assert ok is True
        assert result['random_mode'] == (not original)

    def test_douyin_random_media_toggle(self):
        original = self.config.DOUYIN_RANDOM_MEDIA
        ok, result = self.config.update_runtime(douyin_random_media=not original)
        assert ok is True
        assert result['douyin_random_media'] == (not original)

    def test_service_active_toggle(self):
        original = self.config.SERVICE_ACTIVE
        ok, result = self.config.update_runtime(service_active=not original)
        assert ok is True
        assert result['service_active'] == (not original)
        self.config.SERVICE_ACTIVE = original  # restore

    def test_config_version_increments_on_change(self):
        # Align RUN_MODE to current value so update_runtime is a no-op
        self.config.RUN_MODE = 'normal'
        before = self.config.CONFIG_VERSION
        self.config.update_runtime(mode='normal')  # no change
        assert self.config.CONFIG_VERSION == before

        self.config.update_runtime(category_browse=not self.config.CATEGORY_BROWSE)
        assert self.config.CONFIG_VERSION > before

    def test_result_contains_all_keys(self):
        ok, result = self.config.update_runtime(mode='normal')
        expected = ['run_mode', 'category_browse', 'random_mode',
                    'douyin_random_media', 'service_active', 'config_version']
        for key in expected:
            assert key in result, f"缺少 key: {key}"

    def test_bool_coercion(self):
        ok, result = self.config.update_runtime(
            category_browse=1, random_mode=0, douyin_random_media='yes',
            service_active=''
        )
        assert ok is True
        assert result['category_browse'] is True
        assert result['random_mode'] is False
        assert result['douyin_random_media'] is True
        assert result['service_active'] is False


class TestDBPath:
    """测试 DB_PATH 属性"""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from config import config
        self.config = config
        self._original = self.config._db_path_override
        yield
        self.config._db_path_override = self._original

    def test_default_db_path_ends_with_laptopwatch_db(self):
        self.config._db_path_override = None
        db_path = self.config.DB_PATH
        assert db_path.endswith('laptopwatch.db'), f"Got: {db_path}"

    def test_db_path_setter_override(self, tmp_path):
        overridden = str(tmp_path / 'custom.db')
        self.config.DB_PATH = overridden
        assert self.config.DB_PATH == overridden


class TestGetBasePath:
    """测试 get_base_path() 静态方法"""

    def test_returns_path_object(self):
        from config import Config
        base = Config.get_base_path()
        assert isinstance(base, Path)

    def test_returns_existing_directory(self):
        from config import Config
        base = Config.get_base_path()
        assert base.is_dir()


class TestProperties:
    """测试路径属性"""

    def test_template_folder_is_string(self):
        from config import config
        assert isinstance(config.TEMPLATE_FOLDER, str)

    def test_static_folder_is_string(self):
        from config import config
        assert isinstance(config.STATIC_FOLDER, str)

    def test_react_dist_dir_is_path(self):
        from config import config
        assert isinstance(config.REACT_DIST_DIR, Path)

    def test_properties_dont_raise(self):
        from config import config
        # All properties should be accessible without exception
        _ = config.BASE_PATH
        _ = config.TEMPLATE_FOLDER
        _ = config.STATIC_FOLDER
        _ = config.STATIC_URL_PATH
        _ = config.REACT_DIST_DIR

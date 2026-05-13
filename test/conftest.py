"""pytest 配置：测试所需的环境变量和 fixtures"""
import os
import sys
import pytest

# 在导入项目模块前设置测试环境变量
os.environ.setdefault('LAPTOPWATCH_MODE', 'video')
os.environ.setdefault('LAPTOPWATCH_MEDIA_DIR', os.path.join(os.path.dirname(__file__), 'test_media'))
os.environ.setdefault('LAPTOPWATCH_LOG_LEVEL', 'CRITICAL')
os.environ.setdefault('LAPTOPWATCH_SAVE_SESSION_LOGS', 'false')

# 添加项目根目录到 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def reset_config():
    """每个测试后重置配置到默认值（不覆盖环境变量）"""
    from config import config
    yield
    # 恢复环境变量设置的值
    config.RUN_MODE = os.getenv('LAPTOPWATCH_MODE', 'video')
    config.SORT_TYPE = os.getenv('LAPTOPWATCH_SORT_TYPE', 'name')
    config.SORT_ORDER = os.getenv('LAPTOPWATCH_SORT_ORDER', 'asc')
    config.RANDOM_MODE = os.getenv('LAPTOPWATCH_RANDOM', 'false').lower() == 'true'

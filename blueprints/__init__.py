from .auth import auth_bp
from .core import core_bp
from .normal_api import normal_bp
from .media_api import media_bp
from .file_api import file_bp
from .douyin_api import douyin_bp
from .category_api import category_bp

__all__ = [
    "auth_bp", "core_bp", "normal_bp", "media_bp",
    "file_bp", "douyin_bp", "category_bp",
]

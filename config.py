"""
配置文件
集中管理所有配置常量、环境变量和路径设置
"""
import os
from pathlib import Path

class Config:
    """应用配置类"""

    # ==================== 基础配置 ====================
    SECRET_KEY = os.getenv('LAPTOPWATCH_SECRET_KEY', 'laptopwatch_secure_key_2024')
    SESSION_LIFETIME_HOURS = 24

    # ==================== 运行模式配置 ====================
    RUN_MODE = os.getenv('LAPTOPWATCH_MODE', 'normal')
    MEDIA_DIR = Path(os.getenv('LAPTOPWATCH_MEDIA_DIR', '')).resolve() if os.getenv('LAPTOPWATCH_MEDIA_DIR') else None
    
    # ==================== 是否开启debug ====================
    # IsDebug =  True
    IsDebug =  False

    # ==================== 排序配置 ====================
    SORT_TYPE = os.getenv('LAPTOPWATCH_SORT_TYPE', 'name')
    SORT_ORDER = os.getenv('LAPTOPWATCH_SORT_ORDER', 'asc')
    RANDOM_MODE = os.getenv('LAPTOPWATCH_RANDOM', 'false').lower() == 'true'

    # ==================== 随机模式配置 ====================
    # 每次刷新网页是否重新生成随机起始位置
    REGENERATE_RANDOM_ON_REFRESH = os.getenv('LAPTOPWATCH_REGENERATE_ON_REFRESH', 'true').lower() == 'true'

    # ==================== 抖音模式配置 ====================
    # 是否启用随机媒体模式（true=每次滑动随机推送一个视频, false=按目录顺序或随机游走）
    DOUYIN_RANDOM_MEDIA = os.getenv('LAPTOPWATCH_DOUYIN_RANDOM_MEDIA', 'false').lower() == 'true'
    # 视频播放完毕后是否自动切换到下一个视频（true=自动下一个, false=从头循环当前视频）
    DOUYIN_AUTO_PLAY = os.getenv('LAPTOPWATCH_DOUYIN_AUTO_PLAY', 'true').lower() == 'true'
    # 是否默认静音（true=默认静音, false=默认有声音）
    DOUYIN_MUTED = os.getenv('LAPTOPWATCH_DOUYIN_MUTED', 'true').lower() == 'true'
    # 历史记录/反重复表最大保留条数
    DOUYIN_HISTORY_MAX = 200

    # ==================== 日志配置 ====================
    LOG_LEVEL = os.getenv('LAPTOPWATCH_LOG_LEVEL', 'INFO').upper()
    LOG_STRUCTURED = os.getenv('LAPTOPWATCH_LOG_STRUCTURED', 'false').lower() == 'true'
    LOG_ROTATE = os.getenv('LAPTOPWATCH_LOG_ROTATE', 'true').lower() == 'true'
    LOG_DIR = Path(os.getenv('LAPTOPWATCH_LOG_DIR', './logs')).resolve()
    LOG_RETENTION = int(os.getenv('LAPTOPWATCH_LOG_RETENTION', 7))

    # 是否保存会话日志（记录用户每次访问的URL和时间戳），仅在LOG_STRUCTURED为true时生效
    # SAVE_SESSION_LOGS = False
    SAVE_SESSION_LOGS = True

    # ==================== 文件限制配置 ====================
    MAX_IMAGE_SIZE = 30 * 1024 * 1024  # 30MB
    THUMBNAIL_SIZE = (150, 150)
    MAX_FOLDER_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
    MAX_FOLDER_FILES = 5000
    MAX_HISTORY_LENGTH = 64
    CACHE_EXPIRE = 3600  # 预览缓存过期时间（秒）

    # ==================== 分页配置 ====================
    PAGE_FIRST = 36
    PAGE_LOAD = 36

    # ==================== 目录浏览模式配置 ====================
    # 每个分类区块首页最多展示的文件数（先设 6 方便测试）
    CATEGORY_PAGE_SIZE = 6
    # 进入叶子文件夹后的每页展示数（类似原有 PAGE_FIRST 的值）
    CATEGORY_DETAIL_PAGE_SIZE = 24
    # 是否启用目录浏览模式（由 GUI 环境变量传入）
    CATEGORY_BROWSE = os.getenv('LAPTOPWATCH_CATEGORY_BROWSE', 'false').lower() == 'true'

    # ==================== 认证配置 ====================
    DEFAULT_PASSWORD = '574406731'

    # ==================== 文件扩展名定义 ====================
    VIDEO_EXT = {
        '.3gp', '.3g2', '.264', '.265', '.avi', '.divx', '.f4v', '.flv',
        '.h264', '.hevc', '.m2t', '.m2ts', '.m2v', '.m4v', '.mkv', '.mov',
        '.mp4', '.mp4v', '.mpe', '.mpeg', '.mpg', '.mpv', '.mpv4', '.mqv',
        '.mts', '.ogg', '.ogv', '.qt', '.rm', '.rmvb', '.ts', '.vob',
        '.webm', '.wmv', '.xvid'
    }

    IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'}

    # ==================== 打包exe资源路径适配 ====================
    @staticmethod
    def get_base_path():
        """获取基础路径，支持打包exe"""
        import sys
        if getattr(sys, 'frozen', False):
            base_path = Path(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))))
        else:
            base_path = Path(__file__).parent
        return base_path

    # ==================== 路径配置 ====================
    @property
    def BASE_PATH(self):
        return self.get_base_path()

    @property
    def TEMPLATE_FOLDER(self):
        return str(self.BASE_PATH / 'templates')

    @property
    def STATIC_FOLDER(self):
        return str(self.BASE_PATH / 'static')

    @property
    def STATIC_URL_PATH(self):
        return '/static'

# 创建全局配置实例
config = Config()
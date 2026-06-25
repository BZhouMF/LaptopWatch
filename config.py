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
    VIDEO_SERVE_PORT = int(os.getenv('LAPTOPWATCH_VIDEO_PORT', 5003))
    
    # ==================== 是否开启debug ====================
    IsDebug = False
    # IsDebug = True   # 开启会导致 reloader 父子进程残留，端口无法释放

    # ==================== 排序配置 ====================
    SORT_TYPE = os.getenv('LAPTOPWATCH_SORT_TYPE', 'name')
    SORT_ORDER = os.getenv('LAPTOPWATCH_SORT_ORDER', 'asc')
    RANDOM_MODE = os.getenv('LAPTOPWATCH_RANDOM', 'false').lower() == 'true'

    # ==================== 随机模式配置 ====================
    # 每次刷新网页是否重新生成随机起始位置
    REGENERATE_RANDOM_ON_REFRESH = os.getenv('LAPTOPWATCH_REGENERATE_ON_REFRESH', 'false').lower() == 'true'

    # ==================== 抖音模式配置 ====================
    DOUYIN_AUTO_PLAY = True
    # 是否默认静音（true=默认静音, false=默认有声音）
    DOUYIN_MUTED = False
    # 是否启用随机媒体（false=按排序顺序播放）
    DOUYIN_RANDOM_MEDIA = True
    # 历史记录/反重复表最大保留条数
    DOUYIN_HISTORY_MAX = 200
    # 全屏策略：true=浏览器原生播放器(兼容最好,无自定义手势UI)
    #         false=自定义UI全屏(保留手势/倍速/亮度等,默认)
    NATIVE_FULLSCREEN = True

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
    PAGE_FIRST = 35
    PAGE_LOAD = 35

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
        '.qt', '.rm', '.rmvb', '.vob',
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

    @property
    def REACT_DIST_DIR(self):
        return self.BASE_PATH / 'react' / 'dist'

    _db_path_override = None

    @property
    def DB_PATH(self):
        """固定单一数据库路径（测试可覆盖）"""
        if self._db_path_override:
            return self._db_path_override
        return str(self.get_base_path() / 'db_path' / 'laptopwatch.db')

    @DB_PATH.setter
    def DB_PATH(self, value):
        self._db_path_override = value

# 创建全局配置实例
config = Config()
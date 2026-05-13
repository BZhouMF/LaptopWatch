"""
路由配置常量
集中定义所有 API 路由路径，前后端统一引用，避免硬编码。
"""


class Routes:
    """路由常量定义"""

    # ==================== 认证 ====================
    AUTH_LOGIN = '/login'
    AUTH_LOGOUT = '/logout'

    # ==================== 核心页面 ====================
    CORE_INDEX = '/'
    CORE_BROWSE = '/browse/<path:dirpath>'

    # ==================== 普通模式 API（/api 前缀） ====================
    API_CHECK_PATH = '/api/check_path'
    API_LIST = '/api/list'
    API_LIST_ALL = '/api/list_all'

    # ==================== 媒体 API（/media 前缀） ====================
    MEDIA_LOAD_MORE = '/media/load_more'
    MEDIA_THUMBNAIL = '/media/thumbnail/<path:relative_path>'
    MEDIA_SERVE = '/media/serve_media/<path:relative_path>'
    MEDIA_DOWNLOAD = '/media/download_media/<path:relative_path>'
    MEDIA_NAVIGATE = '/media/navigate'

    # ==================== 文件操作 API（/file 前缀） ====================
    FILE_RAW = '/file/raw/<path:filepath>'
    FILE_VIEW = '/file/view/<path:filepath>'
    FILE_TEXT = '/file/text/<path:filepath>'
    FILE_DOWNLOAD_FOLDER = '/file/download_folder'
    FILE_DOWNLOAD_SELECTED = '/file/download_selected'

    # ==================== 抖音 API（/api/douyin 前缀） ====================
    DOUYIN_INIT = '/api/douyin/init'
    DOUYIN_NEXT = '/api/douyin/next'

    # ==================== 静态资源 ====================
    STATIC_CSS_STYLE = '/static/css/style.css'
    STATIC_JS_MODAL = '/static/js/modal.js'
    STATIC_JS_UTILS = '/static/js/utils.js'
    STATIC_JS_BROWSE = '/static/js/browse.js'
    STATIC_JS_MEDIA_INDEX = '/static/js/media_index.js'
    STATIC_JS_VIDEO_PLAYER = '/static/js/Video_Player.js'


# 前端需要用到的路由键值对（使用干净的基础路径，便于 JS 拼接查询参数或路径段）
FRONTEND_ROUTES = {
    'apiCheckPath': '/api/check_path',
    'apiList': '/api/list',
    'apiListAll': '/api/list_all',
    'mediaLoadMore': '/media/load_more',
    'mediaThumbnail': '/media/thumbnail/',
    'mediaServe': '/media/serve_media/',
    'mediaDownload': '/media/download_media/',
    'mediaNavigate': '/media/navigate',
    'fileRaw': '/file/raw/',
    'fileView': '/file/view/',
    'fileText': '/file/text/',
    'fileDownloadFolder': '/file/download_folder',
    'fileDownloadSelected': '/file/download_selected',
    'douyinInit': '/api/douyin/init',
    'douyinNext': '/api/douyin/next',
    'browse': '/browse/',
    # 目录浏览模式
    'categoryData': '/category/data',
    'categoryBrowse': '/category/browse/',
    'categoryGrid': '/category/grid/',
    'categoryGridMore': '/category/grid_more',
    'mediaPlayer': '/media/player',
}

# LaptopWatch 局域网文件管理器

一个基于 Flask 的轻量级跨设备文件共享工具，通过桌面 GUI 快速搭建局域网文件服务，支持电脑、手机、平板等设备通过浏览器访问和管理文件。特别适合在家庭/办公局域网内多设备之间共享文件、观看视频、浏览图片。

## 项目结构

```
LaptopWatch/
├── gui.py                  # 可视化控制面板（推荐使用）
├── qid.py                  # 管理后台服务（Web 控制面板）
├── app.py                  # Flask 主服务程序
├── config.py               # 全局配置文件
├── routes_config.py        # 前端路由配置
├── requirements.txt        # 依赖清单
├── start_gui.bat           # Windows 快捷启动脚本
├── blueprints/             # 模块化功能蓝图
│   ├── auth.py             # 认证相关接口
│   ├── core.py             # 核心路由
│   ├── normal_api.py       # 普通模式 API
│   ├── media_api.py        # 媒体模式（视频/图片）API
│   ├── douyin_api.py       # 抖音模式 API
│   ├── category_api.py     # 目录浏览模式 API
│   └── file_api.py         # 文件操作 API
├── models/                 # 数据模型
│   └── cache_models.py     # 缓存管理
├── utils/                  # 工具函数库
│   ├── process_utils.py    # 进程/端口管理（gui.py 与 qid.py 共享）
│   ├── logging_utils.py    # 日志工具
│   ├── thumbnail_utils.py  # 缩略图生成工具
│   ├── media_utils.py      # 媒体文件遍历工具
│   └── file_utils.py       # 文件操作工具
├── templates/              # HTML 模板
│   ├── login.html          # 通用登录页
│   ├── normal_login.html   # 普通模式登录页
│   ├── media_login.html    # 媒体模式登录页
│   ├── index.html          # 普通模式首页
│   ├── browse.html         # 普通模式浏览页
│   ├── media_index.html    # 媒体模式主页
│   ├── douyin.html         # 抖音模式播放页
│   ├── text_viewer.html    # 文本查看器
│   └── unpage.html         # 路径不存在错误页
├── static/                 # 静态文件
│   ├── css/
│   │   └── style.css       # 样式文件
│   └── js/
│       ├── script.js       # 前端脚本
│       └── Video_Player.js # 抖音模式视频播放器
└── test/                   # 测试
    ├── conftest.py         # pytest 配置
    ├── test_cache_models.py
    ├── test_process_utils.py
    ├── test_media_utils.py
    └── test_douyin_store.py
```

## 安装和运行

### 方式一：推荐（使用 GUI 控制面板）

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 运行控制面板：
```bash
python gui.py
```

3. 在 GUI 中选择运行模式，配置参数，点击"启动服务"即可

### 方式二：命令行启动

```bash
# 普通模式
python app.py

# 视频模式
set LAPTOPWATCH_MODE=video
set LAPTOPWATCH_MEDIA_DIR=D:\Videos
python app.py

# 图片模式
set LAPTOPWATCH_MODE=image
set LAPTOPWATCH_MEDIA_DIR=D:\Pictures
python app.py

# 抖音模式
set LAPTOPWATCH_MODE=douyin
set LAPTOPWATCH_MEDIA_DIR=D:\Videos
python app.py
```

### 访问应用

- 电脑端：打开浏览器访问 `http://localhost:5000`
- 移动端：扫描 GUI 显示的二维码（确保设备在同一局域网下）

## 默认密码

默认登录密码：`574406731`

## 功能特性

### 核心功能
- 密码保护访问，保障数据安全
- 四种运行模式：普通文件管理、视频专属模式、图片专属模式、抖音模式
- 图片在线预览，支持画廊视图和幻灯片播放
- 视频在线播放，自动生成缩略图，支持常见视频格式
- 文本文件在线查看，支持代码高亮
- 单文件/批量文件下载
- 完全响应式设计，适配手机、平板、电脑各种屏幕

### 抖音模式
- 上下滑动切换视频，仿抖音交互体验
- 双视频元素无缝切换动画（350ms 滑动过渡）
- 智能预加载：播放当前视频时后台加载下一个，消除等待
- 全屏手势控制：左侧上下滑调节亮度，右侧上下滑调节音量
- 水平滑动快进快退，带时间指示器
- 全屏自动横竖屏锁定（根据视频宽高比）
- 快进/后退 15 秒快捷按钮
- 倍速播放（0.5x / 1x / 1.5x / 2x / 3x）
- 随机媒体推送模式（可选）
- 播放历史记录与反重复机制

### 目录浏览模式
- 卡片式分类展示，按文件夹分组
- 支持递归/随机位置文件收集
- 单叶子分类兜底机制，避免页面跳转循环

### 管理后台
- 独立 Web 管理界面（端口 5001）
- 一键启停主服务
- 会话日志查看与监控
- 定时关机功能

### 其他特性
- 随机浏览模式：媒体模式支持从随机位置开始浏览
- 多种视图模式：大图标、中图标、小图标、列表视图自由切换
- 智能排序：支持按名称、时间升序/降序排列
- 浏览历史记录导航，支持前进后退
- 自动生成访问二维码，手机扫码即可访问
- 完整的运行日志记录，支持会话日志导出
- 多线程服务，支持多设备同时访问

## 测试

```bash
# 安装测试依赖
pip install pytest

# 运行全部测试
python -m pytest test/

# 运行特定测试文件
python -m pytest test/test_media_utils.py -v
```

## 注意事项

- 支持 Windows 系统（主要开发平台），理论上可运行于所有支持 Python 的平台
- 视频缩略图生成依赖 OpenCV，已自动包含在依赖中
- 建议使用 Python 3.10+ 版本运行
- 图片预览大小限制：30MB
- 文本文件查看限制：1MB
- 仅限局域网内使用，请勿直接暴露到公网

# LaptopWatch 局域网文件管理器

一个基于 Flask + FastAPI 双服务器的轻量级跨设备文件共享工具，通过桌面 GUI（PyWebView）快速搭建局域网文件服务，支持电脑、手机、平板等设备通过浏览器访问和管理文件。

## 项目结构

```
LaptopWatch/
├── gui.py                  # PyWebView 桌面控制面板（GUI 入口）
├── app.py                  # Flask 主服务（页面/API，端口 5002）
├── video_server.py         # FastAPI 视频流服务（端口 5003）
├── qid.py                  # 管理后台服务（端口 5001）
├── config.py               # 全局配置文件
├── routes_config.py        # 前端路由配置
├── start_gui.bat           # Windows 快捷启动脚本
├── blueprints/             # Flask 蓝图模块
│   ├── auth.py             # 认证与登录
│   ├── core.py             # 核心路由与页面
│   ├── normal_api.py       # 普通模式 API
│   ├── media_api.py        # 媒体模式（视频/图片）API
│   ├── douyin_api.py       # 抖音模式 API
│   ├── category_api.py     # 目录浏览模式 API
│   └── file_api.py         # 文件操作 API
├── utils/                  # 工具函数库
│   ├── db_utils.py         # 数据库操作与媒体遍历
│   ├── file_utils.py       # 文件类型判断与安全发送
│   ├── logging_utils.py    # 日志工具
│   ├── media_utils.py      # 媒体文件遍历工具
│   ├── process_utils.py    # 进程/端口管理
│   └── thumbnail_utils.py  # 缩略图生成（图片/视频）
├── templates/              # HTML 模板
│   ├── login.html          # 通用登录页
│   ├── index.html          # 普通模式首页（文件夹视图）
│   ├── browse.html         # 目录浏览模式
│   ├── category_index.html # 分类浏览首页
│   ├── category_grid.html  # 分类网格视图
│   ├── media_index.html    # 媒体模式主页
│   ├── douyin.html         # 抖音模式播放页
│   ├── player.html         # 全屏播放器页面
│   ├── setup.html          # 管理后台页面
│   ├── qid.html            # QID 管理控制台
│   ├── text_viewer.html    # 文本查看器
│   └── unpage.html         # 路径不存在错误页
├── static/                 # 静态文件
│   ├── css/
│   │   ├── style.css       # 主样式
│   │   └── setup.css       # 管理后台样式
│   └── js/
│       ├── script.js       # 普通模式脚本
│       ├── browse.js       # 目录浏览脚本
│       ├── Video_Player.js # 视频/抖音播放器
│       ├── modal.js        # 模态预览窗口
│       ├── media_index.js  # 媒体模式首页
│       ├── setup.js        # 管理后台脚本
│       └── utils.js        # 前端工具函数
└── test/                   # 测试
    ├── conftest.py         # pytest 配置
    ├── test_cache_models.py
    ├── test_category_api.py
    ├── test_cover.py
    ├── test_db_utils.py
    ├── test_douyin_api.py
    ├── test_gui_fixes.py
    ├── test_media_api.py
    ├── test_media_utils.py
    ├── test_normal_api.py
    ├── test_process_utils.py
    ├── test_queries.py
    └── test_sync_folder.py
```

## 架构说明

项目采用 **双服务器 + 管理后台** 架构，共使用 3 个端口：

### 端口总览

| 端口 | 服务 | 框架 | 服务器 | 职责 |
|------|------|------|--------|------|
| **5002** | Flask 主服务 | Flask | Waitress (16 线程) | 页面渲染、API 接口、鉴权、缩略图 |
| **5003** | FastAPI 流媒体 | FastAPI | uvicorn | 视频/图片/音频文件流式传输 |
| **5001** | QID 管理后台 | Flask | Flask dev | 服务启停、日志监控、定时关机 |

### 端口 5002 — Flask 主服务

用户直接访问的端口，承载全部页面和业务 API。

| 路由前缀 | 蓝图 | 功能 |
|----------|------|------|
| `/` `/browse/` `/setup` | `core.py` | 首页磁盘列表、文件浏览页、GUI 配置页 |
| `/auth/login` `/auth/logout` `/auth/register` | `auth.py` | 登录、登出、注册（SHA-256 + 盐哈希） |
| `/api/list` `/api/check-path` `/api/list-all` | `normal_api.py` | 普通模式：目录列表、路径校验、全量文件列举 |
| `/api/media/*` | `media_api.py` | 媒体模式：分页加载、缩略图、上一个/下一个导航 |
| `/api/douyin/*` | `douyin_api.py` | 抖音模式：随机推送、历史防重、自动播放队列 |
| `/api/category/*` | `category_api.py` | 目录浏览模式：按文件夹分类、递归收集 |
| `/file/text/` `/file/view/` `/file/download/*` | `file_api.py` | 文本查看（自动编码检测）、文件下载、文件夹 ZIP 打包、批量下载 |

### 端口 5003 — FastAPI 流媒体服务

独立于 Flask 的异步视频/图片传输服务，避免长连接占用 Flask worker 线程。

| 端点 | 功能 |
|------|------|
| `GET /media/serve_media/{path}` | 视频流式传输（Range 分段，512KB 分块）、图片/音频直传 |
| `GET /media/serve_media/` | 空路径守卫，返回 400 |

- 视频：读取浏览器 `Range` 头，返回 `206 Partial Content`，匀速分块传输
- 图片/音频：`FileResponse` 直接返回完整文件
- 路径安全检查：禁止越权访问 `MEDIA_DIR` 之外的目录
- 会话验证：解析 Flask session cookie，未登录返回 403

### 端口 5001 — QID 管理后台

独立的管理面板，可远程启停主服务和流媒体服务、查看实时日志、预定系统关机。

| 端点 | 功能 |
|------|------|
| `GET /` | 管理后台页面（qid.html） |
| `POST /api/login` `/api/logout` | 管理台独立登录（与主服务密码相同） |
| `GET /api/status` | 查询主服务运行状态（进程存活 + 端口监听） |
| `GET /api/config` `POST /api/config` | 读取/修改运行配置（模式、目录、排序等） |
| `POST /api/start` | 以子进程方式启动主服务 + 流媒体服务，实时采集 stdout 日志 |
| `POST /api/stop` | 优雅终止主服务进程树，保存会话日志 |
| `POST /api/kill-all` | 一键终止全部服务（含 GUI 进程 + 自身） |
| `POST /api/shutdown/schedule` | 预定 2 分钟后系统关机（调用系统 `shutdown` 命令） |
| `POST /api/shutdown/cancel` | 取消预定关机 |
| `GET /api/shutdown/status` | 查询关机预定状态及剩余秒数 |
| `GET /api/dirs` | 浏览服务器文件系统目录（供 GUI 目录选择器使用） |
| `POST /api/logs/ingest` | 接收 GUI 推送的日志行（密码认证，无需 session） |
| `GET /api/logs/recent` | 拉取最近 N 条日志（支持增量 `since` 参数） |
| `GET /api/logs/stream` | SSE 实时日志流（`text/event-stream`） |

### 访问链路

```
浏览器/手机
    │
    ├─ :5002 ── Flask ── HTML 页面、API JSON、缩略图
    │              │
    │              └─ 页面中 <img>/<video> 标签直接指向 :5003
    │
    ├─ :5003 ── FastAPI ── 视频流、图片、音频（长连接传输）
    │
    └─ :5001 ── QID ── 管理面板（仅管理员使用）
```

前端页面通过绝对 URL 直接访问 FastAPI 获取媒体文件流，不经过 Flask，避免视频长连接占用 Flask worker 线程。

## 安装和运行

### 方式一：GUI 控制面板（推荐）

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 启动 GUI：
```bash
python gui.py
```

3. 在 GUI 中选择运行模式，配置媒体目录，点击"启动服务"

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

# 目录浏览模式
set LAPTOPWATCH_MODE=normal
set LAPTOPWATCH_MEDIA_DIR=D:\Media
set LAPTOPWATCH_CATEGORY_BROWSE=true
python app.py
```

### 访问应用

- 电脑端：`http://localhost:5002`
- 移动端：扫描 GUI 显示的二维码（确保设备在同一局域网下）

## 默认密码

默认登录密码：`574406731`

## 运行模式

| 模式 | 说明 |
|------|------|
| normal | 普通文件管理，支持文件夹浏览、文件下载 |
| video | 视频专属模式，网格展示视频列表 |
| image | 图片专属模式，网格展示图片列表 |
| douyin | 竖屏滑动视频，仿抖音交互 |

普通模式下可通过环境变量 `LAPTOPWATCH_CATEGORY_BROWSE=true` 启用目录浏览模式，按文件夹分类展示媒体文件。

## 功能特性

### 核心功能
- 密码保护访问，保障数据安全
- 四种运行模式：普通文件管理、视频模式、图片模式、抖音模式
- 图片在线预览，支持画廊视图和幻灯片播放
- 视频在线播放，512KB 匀速分块流式传输
- 文本文件在线查看，自动编码检测
- 单文件/批量文件下载，文件夹 ZIP 打包下载
- 响应式设计，适配手机、平板、电脑

### 抖音模式
- 上下滑动切换视频，仿抖音交互体验
- 双视频缓冲无缝切换（350ms 滑动过渡）
- 智能预加载：播放时后台加载下一个视频
- 全屏手势控制：左侧调节亮度，右侧调节音量
- 水平滑动快进快退，带时间指示器
- 倍速播放（0.5x / 1x / 1.5x / 2x / 3x）
- 随机媒体推送模式
- 播放历史记录与反重复机制

### 目录浏览模式
- 卡片式分类展示，按文件夹分组
- 支持递归文件收集
- 单文件/批量选择下载
- 切换列表/大图标/中图标视图

### 全屏播放器
- 双缓冲视频切换，无闪烁
- 手势控制：亮度、音量、进度
- 导航按钮（上一个/下一个）
- 倍速播放设置

### 管理后台
- 独立 Web 管理界面（端口 5001）
- 一键启停 Flask + FastAPI 服务
- 实时日志查看与监控
- 定时关机功能

### 其他特性
- 随机浏览模式：媒体模式支持随机起始位置
- 多种视图模式：大图标、中图标、小图标、列表
- 智能排序：按名称、时间升序/降序
- 浏览历史记录导航
- 自动生成访问二维码
- 会话日志记录与导出

## 测试

```bash
# 安装测试依赖
pip install pytest

# 运行全部测试
python -m pytest test/

# 运行特定测试文件
python -m pytest test/test_media_api.py -v
```

## 注意事项

- 支持 Windows 系统（主要开发平台）
- 视频缩略图依赖 OpenCV，已包含在依赖中
- 建议 Python 3.10+
- 图片预览大小限制：30MB
- 文本文件查看限制：1MB
- 仅限局域网使用，请勿暴露到公网

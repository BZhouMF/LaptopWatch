# LaptopWatch 前端重构结构设计（HTML + CSS + JS 原生方案）

> 状态：**设计方案（v1）**，尚未创建目录。
> 目标：用原生 HTML + CSS + JavaScript 重写前端，替换现有 `react/` 前端；不引入任何构建工具和框架。
> 依据：现有功能清单（README + `react/src` 页面）与后端 API（见 `API_MAP.md`）。

---

## 1. 总体设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 应用形态 | **MPA 多页面应用**（每页独立 HTML） | 原生三件套的自然形态：页面间 `<a>` 跳转，无前端路由库；每页独立加载，结构一目了然 |
| JS 组织 | **原生 ES Modules**（`<script type="module">`） | 现代浏览器原生支持 import/export，无需打包器；文件即模块 |
| 样式方案 | **CSS 自定义属性（变量）+ BEM 命名**，手写样式 | 不引入 Tailwind，保持零构建依赖；CSS 变量实现换肤/深色模式 |
| 请求方式 | **fetch 封装**（对齐原 axios 行为） | 统一超时、带 cookie、401 自动跳登录、503 静默 |
| 页面数量 | 9 个 HTML 页面 | 与现有 React 8 页面功能一一对应 + 404 |
| 后端接口 | **完全复用，零改动** | 只换前端壳，不动 `blueprints/` 的 API |
| 目录位置 | 新建 `frontend/` 目录 | 前后端清晰分离；`react/` 保留待新前端验收后再删 |
| 管理页 | `templates/` + `static/` 的 setup/qid 暂不动 | 它们本来就是原生三件套，可作新前端的风格参考，后期再统一迁入 |

**关键权衡（如实说明）**：
- 收益：零构建、无框架黑盒、每个文件职责肉眼可查、任意编辑器可改、部署即 Flask 直出。
- 代价：**播放器页（player）是最大难点**——双缓冲、手势、倍速都要手写，估计占整个前端 40% 工作量；组件复用靠"函数返回 HTML 字符串 + 事件委托"，没有框架的响应式更新，数据变了要手动重新渲染（这是原生方案的固有模式，习惯后可控）。
- 风险控制：先做简单页面（登录/首页/浏览）验证模式，再做播放器；`react/` 保留到验收通过。

---

## 2. 完整目录结构

```
LaptopWatch/
├── frontend/                          # ★ 新前端根目录（纯静态，无构建）
│   ├── pages/                         # 页面 HTML（每页 = 一个功能）
│   │   ├── index.html                 # 首页：运行模式分发 + 磁盘列表
│   │   ├── login.html                 # 登录页
│   │   ├── register.html              # 注册页
│   │   ├── browse.html                # 普通模式：文件浏览/预览/下载/批量选择
│   │   ├── media.html                 # 视频/图片模式：媒体网格（滚动加载）
│   │   ├── category.html              # 分类目录浏览（卡片 + 滚动加载）
│   │   ├── player.html                # 抖音模式：全屏滑动播放器
│   │   ├── text_viewer.html           # 文本查看器（编码自动识别）
│   │   └── 404.html                   # 错误页
│   ├── css/
│   │   ├── base.css                   # ① CSS 变量（主题色/间距/字号）+ 重置 + 排版
│   │   ├── layout.css                 # ② 页面骨架：顶栏/内容区/底栏/导航
│   │   ├── components.css             # ③ 通用组件：按钮/卡片/表单/弹窗/网格/徽标
│   │   ├── utilities.css              # ④ 工具类：间距/显隐/动画/响应式断点
│   │   └── pages/                     # 页面专属样式（与 pages/ 一一对应）
│   │       ├── home.css  login.css  register.css  browse.css
│   │       ├── media.css  category.css  player.css  text_viewer.css
│   │       └── 404.css
│   ├── js/
│   │   ├── core/                      # 基础设施（不依赖页面）
│   │   │   ├── api.js                 # fetch 封装：超时/cookie/401 跳登录/503 静默/错误统一
│   │   │   ├── auth.js                # 登录态检查、页面守卫、登出、会话探针
│   │   │   ├── constants.js           # 接口地址常量（对齐后端 routes_config.py）
│   │   │   ├── utils.js               # 工具：文件大小格式化/URL 编解码/防抖节流/编码识别
│   │   │   └── toast.js               # 轻提示（成功/错误 toast）
│   │   ├── components/                # 可复用 UI 组件（导出函数，返回 HTML/绑定事件）
│   │   │   ├── media_grid.js          # 媒体网格：渲染 + 滚动触底加载 + 随机模式
│   │   │   ├── thumb_img.js           # 缩略图：懒加载 IntersectionObserver + 占位 + 失败兜底
│   │   │   ├── preview_modal.js       # 预览弹窗：大图/视频（复用 serve_media 流）
│   │   │   ├── selection_bar.js       # 批量选择工具条：全选/取消/打包下载
│   │   │   ├── file_icon.js           # 文件类型图标（按扩展名）
│   │   │   ├── spinner.js             # 加载动画
│   │   │   └── dropdown.js            # 下拉菜单（排序/视图切换）
│   │   ├── pages/                     # 页面控制器（与 pages/*.html 一一对应）
│   │   │   ├── home.js                # 首页：拉取 /api/mode、/api/drives，渲染模式卡片
│   │   │   ├── login.js               # 登录：表单提交、会话预检、redirect 回跳
│   │   │   ├── register.js            # 注册
│   │   │   ├── browse.js              # 浏览：目录列表/分页/排序/预览/下载/ZIP
│   │   │   ├── media.js               # 媒体：网格加载、视图切换、随机起点
│   │   │   ├── category.js            # 分类：树导航、滚动加载、刷新重扫
│   │   │   ├── text_viewer.js         # 文本：arraybuffer 拉取 + 编码探测 + 复制
│   │   │   └── player/                # ★ 播放器子模块（工作量最大）
│   │   │       ├── player.js          # 主控：状态机（idle/loading/playing/end）、播放队列
│   │   │       ├── gestures.js        # 触摸手势：上下滑动切换/左右快进/左侧亮度/右侧音量
│   │   │       ├── buffer.js          # 双视频缓冲：预加载下一个、无缝切换
│   │   │       └── controls.js        # UI 控制：进度条/倍速菜单/导航按钮/全屏
│   │   └── main.js                    # 全局入口：页面守卫（未登录跳 login）+ 公共初始化
│   ├── assets/
│   │   ├── icons/                     # SVG 图标（一个图标一个文件，供 <use> 引用）
│   │   ├── images/                    # logo、占位图、错误图
│   │   └── favicon.ico
│   └── README.md                      # 前端自述：结构说明、约定、页面-接口对照
├── react/                             # 旧前端：新前端验收前保留，之后删除（见 §7）
├── blueprints/  utils/  config.py ... # 后端：API 零改动，仅改页面路由（见 §6）
└── docs/
    ├── API_MAP.md                     # 已有：前后端 API 对照表
    ├── FRONTEND_GUIDE.md              # 已有：旧 React 前端说明书（验收后归档）
    └── FRONTEND_STRUCTURE.md          # 本文件
```

---

## 3. 各页面职责与对应后端接口

| HTML 页面 | 页面控制器 | 主要功能 | 调用的接口（详见 API_MAP.md） |
|-----------|-----------|---------|------------------------------|
| `index.html` | `home.js` | 模式分发入口、磁盘列表 | `GET /api/mode`、`GET /api/drives` |
| `login.html` | `login.js` | 登录表单、会话预检 | `POST /login`、`GET /api/check_path` |
| `register.html` | `register.js` | 注册表单 | `POST /register` |
| `browse.html` | `browse.js` | 目录树/文件列表、分页排序、预览弹窗、单选/全选/批量 ZIP、文件夹 ZIP、文本跳转 | `GET /api/list`、`GET /api/list_all`、`POST /file/download_selected`、`GET /file/download_folder`、`GET /file/view/*`、`/media/serve_media/*`（预览）、`/media/thumbnail/*` |
| `media.html` | `media.js` | 视频/图片网格、滚动加载、视图切换（大/中/小/列表）、随机起点、点击进播放器/预览 | `GET /media/load_more`、`/media/serve_media/*`、`/media/thumbnail/*`、`/media/download_media/*` |
| `category.html` | `category.js` | 分类卡片、子目录导航、滚动加载更多、强制刷新重扫 | `GET /category/data`、`GET /category/grid_more`、`/media/thumbnail/*` |
| `player.html` | `player/*` | 抖音模式播放器：init 取首个视频、滑动换片、双缓冲、手势、倍速、预加载 | `GET /api/douyin/init`、`GET /api/douyin/next`、`GET /media/navigate`、`/media/serve_media/*`、`/media/thumbnail/*`（封面） |
| `text_viewer.html` | `text_viewer.js` | 文本内容展示、编码自动识别、复制 | `GET /file/raw/<path>`（arraybuffer） |
| `404.html` | — | 静态错误页 | — |

**页面跳转关系**：
```
login → index → media / browse / category / player（按模式分发）
index ←→ 各模式页面（顶栏导航）
browse → text_viewer（点文本文件）、media（点媒体文件预览）
media  → player（点视频播放）
```

---

## 4. 关键模块设计说明

### 4.1 `js/core/api.js` —— 全前端唯一"电话机"（对齐原 `api/client.ts`）
- 封装 `fetch`，统一：`credentials: 'include'`（带 cookie）、30s 超时（AbortController）、JSON 自动解析；
- 响应拦截：**401 → 跳 `/login?redirect=当前页`**；**503 → 抛出可识别错误**（调用方自行处理，不跳登录）；其他错误统一转成友好提示；
- 导出 `api.get(url, params)` / `api.post(url, body)` 两个方法，所有页面只 import 它。

### 4.2 `js/core/auth.js` + `js/main.js` —— 页面守卫
- 每个受保护页面 `<head>` 引入 `main.js`，它先调 `/api/check_path` 探针：失败 → `location.replace('/login?redirect=...')`；
- 登录页反向逻辑：探针成功 → 直接跳回 redirect 目标。

### 4.3 `js/components/*` —— 无框架的组件复用约定
- 每个组件导出 `render(props) → HTML字符串` 和 `mount(container, props)` 两个函数；
- 交互事件用**事件委托**绑定在容器上（避免重复绑定）；
- 数据变化后由页面控制器重新调用 `render` 替换容器内容（手动刷新模式，替代 React 的自动更新）。

### 4.4 `js/pages/player/*` —— 播放器（最大工程）
- `player.js` 状态机：`idle → loading → playing → (ended|error) → loading(next)`；
- `buffer.js`：双 `<video>` 元素轮换，当前播放完成前预加载下一个（对齐原双缓冲无缝切换）；
- `gestures.js`：触摸事件（touchstart/move/end）计算位移：垂直滑动切换、水平快进、屏幕左半区上下=亮度、右半区上下=音量；
- `controls.js`：进度条、倍速（0.5/1/1.5/2/3）、上/下一个、全屏。

### 4.5 CSS 分层
- `base.css`：`:root` 定义全部设计变量（颜色/圆角/间距/字号/阴影），浅色主题先行，深色主题用 `[data-theme=dark]` 覆盖变量（零改动页面代码即可换肤）；
- `layout.css`：顶栏（logo + 导航 + 用户区）、内容容器、最大宽度、响应式断点（手机 <768px 优先，参考现有移动端优先设计）；
- `components.css`：`.btn`、`.card`、`.modal`、`.grid`、`.form-*`、`.badge`、`.empty` 等，BEM 命名（`.card__title`）；
- `utilities.css`：`.u-mt-4`、`.u-hidden`、`.u-flex`、动画 keyframes（如登录页 slide-up）等高频工具类。

---

## 5. 页面 HTML 骨架约定（示例：browse.html）

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>文件浏览 - LaptopWatch</title>
  <link rel="stylesheet" href="/frontend/css/base.css" />
  <link rel="stylesheet" href="/frontend/css/layout.css" />
  <link rel="stylesheet" href="/frontend/css/components.css" />
  <link rel="stylesheet" href="/frontend/css/pages/browse.css" />
</head>
<body>
  <header id="topbar"><!-- layout.css 提供的顶栏 --></header>
  <main id="app"><!-- 页面控制器渲染目标 --></main>
  <script type="module" src="/frontend/js/main.js"></script>
  <script type="module" src="/frontend/js/pages/browse.js"></script>
</body>
</html>
```

> 约定：页面 HTML 只留骨架容器，具体内容由页面控制器 JS 渲染；静态部分（顶栏）也可直接写在 HTML 里。两种风格都允许，**推荐骨架+JS 渲染**以保持各页一致。

---

## 6. 后端衔接（唯一需要改的后端部分）

现有 Flask 把 `/`、`/browse/*`、`/category/*` 等路由都返回 React 的 `dist/index.html`（见 `app.py` 与 `category_api.py` 的 SPA 入口逻辑）。切换后：

| 现状 | 改为 |
|------|------|
| `/` → `react/dist/index.html` | `/` → `frontend/pages/index.html` |
| `/login` `/register` → React SPA | `/login` → `login.html`，`/register` → `register.html` |
| `/browse/*` `/category/*` `/media/player` `/file/text/*` → React SPA | 对应 `browse.html` `category.html` `player.html` `text_viewer.html` |
| `/static/`、`/frontend/*` | 新增/复用静态目录映射，直接 serve `frontend/` 下文件 |

实现建议：在 `app.py` 加一个统一的"页面路由表"（字典：URL 模式 → HTML 文件），用 `send_from_directory` 直出；**API 路由一律不动**。路径参数（如 `/browse/D:/Videos`）由页面 JS 从 `location.pathname` 自行解析后作为 query 传给 API。

---

## 7. 实施顺序（里程碑，每步可验收）

| 阶段 | 内容 | 验收标准 |
|------|------|---------|
| **M1 地基** | `frontend/` 骨架、`core/`（api/auth/constants/utils/toast）、`base.css`/`layout.css`、页面守卫 | 访问任意页未登录 → 跳登录页 |
| **M2 认证 + 首页** | `login.html`/`register.html`/`index.html` 及控制器 | 登录 → 首页正确显示模式卡片与磁盘 |
| **M3 浏览页** | `browse.html` + 组件（grid/thumb/preview/selection/file_icon） | 目录浏览、预览、单/批量下载可用 |
| **M4 媒体 + 分类** | `media.html`、`category.html` | 滚动加载、视图切换、分类树可用 |
| **M5 播放器** | `player/` 四个模块 | 滑动切换、双缓冲、手势、倍速可用 |
| **M6 文本查看 + 收尾** | `text_viewer.html`、404、README、深色主题 | 文本编码识别正确 |
| **M7 替换** | 后端路由切换至 `frontend/`；`react/` 归档删除 | 全功能回归通过 |

---

## 8. 风险与对策

| 风险 | 对策 |
|------|------|
| 播放器手势/双缓冲手写复杂 | M5 独立成阶段；参考现有 `usePlayerGestures.ts` 与 `MediaPlayerPage.tsx` 逻辑**移植**（复制算法，不是复制框架代码） |
| 原生无响应式更新，状态易乱 | 控制器内统一"状态对象 → render"模式；每页一个状态机，禁止散落全局变量 |
| 页面守卫与 401 双重重定向 | `auth.js` 提供唯一判断函数，登录页与受保护页复用同一探针逻辑 |
| 旧路由/旧静态资源引用残留 | 后端路由表集中管理；`routes_config.py` 死路径在 M7 一并清理 |
| 移动端兼容（手机是主要使用场景） | 所有页面移动端优先开发，桌面端增强；CSS 断点统一在 `utilities.css` 定义 |

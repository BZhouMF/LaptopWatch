# 前端文件白话说明书

> 用途：不熟悉 React 也能看懂 `react/` 目录里每个文件是干什么的。
> 阅读建议：先看第 1、2 节（整体思路），再按需翻目录说明。全程不涉及任何代码修改。

---

## 1. 前端到底是什么

- 这个项目的"前端" = `react/` 目录里的一套程序，**运行在浏览器里**，负责两件事：**把界面画出来**（HTML 长什么样）、**替用户向后端要数据**（HTTP 请求）。
- 它是用 **React + TypeScript + Vite** 写的。你不必学会 React 才能维护它——只要知道下面这句话：
  > 前端启动后，用户看到的每个页面都是一个"组件文件"；组件里发请求、拿数据、把数据画到屏幕上。要改哪个页面，就改哪个文件。

- 构建流程：开发时执行 `npm run dev` 起热更新服务；上线时执行 `npm run build`，产物输出到 `react/dist/`，由 Flask 直接把 `dist/index.html` 发给浏览器（后端只负责"把前端成品递给浏览器"和"提供 API 数据"，**Flask 不参与画界面**）。

---

## 2. 打开网页后发生了什么（启动链）

```
浏览器输入 http://localhost:5002
   │
   ▼
Flask 返回 react/dist/index.html（一个几乎空的 HTML 壳）
   │
   ▼
index.html 里的 <script> 加载打包后的 JS → 执行 main.tsx（入口）
   │
   ▼
main.tsx 挂载 App.tsx（全局外壳）→ 里面套着 router.tsx（路由表）
   │
   ▼
router.tsx 根据网址决定显示哪个页面：
   /login → LoginPage     / → HomePage        /browse/* → BrowsePage
   /category/* → CategoryBrowsePage           /media/player → MediaPlayerPage
   /file/text/* → TextViewerPage              /register → RegisterPage
   其余 → NotFoundPage
   │
   ▼
每个页面里：发 HTTP 请求（api_client）→ 拿到 JSON → 画到屏幕上
```

**路由表 `router.tsx` = "网址 ↔ 页面文件"的对照表**，是理解前端结构的第一把钥匙。

---

## 3. 目录逐文件白话说明

### 3.1 根目录几个文件（`react/` 下）

| 文件 | 作用（白话） |
|------|-------------|
| `index.html` | 唯一真实存在的 HTML 壳。所有页面都是 JS 动态画出来的，它只是"容器" |
| `package.json` | 前端"购物清单"：声明用哪些库（React、axios…）、有哪些命令（dev/build/test） |
| `package-lock.json` | 自动生成的依赖锁定文件，**不要手改** |
| `vite.config.ts` | 构建工具配置（开发服务器端口、打包方式） |
| `vitest.config.ts` | 前端测试工具配置 |
| `tsconfig.json` | TypeScript 语法检查配置 |
| `eslint.config.mjs` | 代码规范检查配置 |
| `postcss.config.mjs` / `tailwindcss` | 样式工具配置（Tailwind 是"用 class 名直接写样式"的方案） |
| `dist/` | **构建产物**（`npm run build` 生成），Flask 实际发送给浏览器的是它，不是 src |
| `coverage/` | 测试覆盖率报告（可删，不入库） |
| `node_modules/` | 依赖库本体（`npm install` 生成，可删可重建） |

### 3.2 `src/` 核心目录

| 文件/目录 | 作用（白话） | 类比 |
|-----------|-------------|------|
| `main.tsx` | 程序入口：把整个 App 挂到 HTML 上 | 大楼的"地基+大门" |
| `App.tsx` | 全局外壳：每 15 秒问一次后端"配置变了吗"，变了就刷新页面（避免播放视频时打断，有保护逻辑） | 大楼的"总监控室" |
| `router.tsx` | 网址 → 页面的对照表（见第 2 节） | 大楼的"楼层索引" |
| `index.css` / `legacy.css` | 全局样式。`legacy.css` 是旧版遗留样式，**重构候选** | 大楼的"外墙涂料" |
| `vite-env.d.ts` | 给编辑器用的类型声明，不用管 | — |

### 3.3 `src/pages/` —— 一页一个文件（最重要的目录）

| 文件 | 页面 | 白话职责 |
|------|------|---------|
| `HomePage.tsx` | 首页 `/` | 问后端"现在什么模式 + 有哪些磁盘"，列出模式入口卡片 |
| `BrowsePage.tsx` | 普通文件浏览 `/browse/*` | 列目录、分页列文件、预览图片/视频、单选/全选/批量下载、文件夹 ZIP 下载。**逻辑最重的页面之一**（约 685 行） |
| `CategoryBrowsePage.tsx` | 分类目录浏览 `/category/*` | 按文件夹分类展示媒体、滚动加载更多 |
| `MediaPlayerPage.tsx` | 媒体播放器 `/media/player` | 仿抖音播放器：上下滑动切换、双视频缓冲、手势调亮度/音量/快进、倍速、预加载。**技术含量最高、约 1200 行的页面** |
| `TextViewerPage.tsx` | 文本查看 `/file/text/*` | 拉取文件原始字节，前端自动识别编码（UTF-8/GBK/GB2312/Latin-1）后显示 |
| `LoginPage.tsx` | 登录页 `/login` | 账号密码表单，提交登录；若已有会话自动跳首页 |
| `RegisterPage.tsx` | 注册页 `/register` | 注册表单（⚠️ 后端该接口带历史"陷阱"，勿随意触发，见 API 对照表） |
| `NotFoundPage.tsx` | 404 | 网址不存在时的提示页 |

### 3.4 `src/components/` —— 可复用的"积木"

| 文件 | 白话职责 |
|------|---------|
| `Layout.tsx` | 页面公共骨架（顶栏/导航/内容区），所有受保护页面都套它 |
| `ProtectedRoute.tsx` | **门卫**：进每个页面先问后端"登录了吗？"（调 `/api/check_path`），没登录就踢到 `/login` |
| `MediaGrid.tsx` | 媒体网格：滚动到底自动加载下一页（调 `/media/load_more`） |
| `ThumbImg.tsx` | 缩略图图片组件：自动拼 `/media/thumbnail/...` 地址，加载失败显示占位图 |
| `browse/PreviewModal.tsx` | 预览弹窗：点文件弹出的大图/视频查看窗 |
| `browse/SelectionBar.tsx` | 底部批量操作条：全选/取消/下载 |

### 3.5 `src/contexts/`、`src/hooks/`、`src/api/`、`src/utils/`

| 文件 | 白话职责 |
|------|---------|
| `contexts/AuthContext.tsx` | "全局便签"：记录登录状态/加载中/错误信息，任何页面都能读它；登录、登出的请求也在这里发 |
| `hooks/usePlayerGestures.ts` | 播放器手势逻辑：识别触摸滑动方向、亮度/音量手势、快进手势（纯逻辑，不画界面） |
| `api/client.ts` | **全前端唯一的"电话机"**：创建 axios 实例，统一超时、带 cookie、401 自动跳登录页。所有页面都通过它打电话 |
| `utils/thumbnailQueue.ts` | 缩略图加载队列：控制并发数量，避免一次发太多请求卡死 |
| `test/` | 21 个测试文件，用 Vitest 模拟浏览器环境验证各页面行为；跑 `npm test` 执行 |

---

## 4. 一个完整的数据流示例（文件浏览）

```
用户在 BrowsePage 输入目录 → 页面调用 api_client.get("/api/list", {params:{path:...}})
   → 浏览器发 HTTP GET 到 Flask :5002
   → Flask 的 blueprints/normal_api.py 里 api_list() 读磁盘/数据库
   → 返回 JSON（文件名、大小、缩略图地址…）
   → BrowsePage 拿到 JSON，用 setState 存起来
   → React 发现数据变了，自动重新画列表
```

**React 的核心就这一句：数据（state）变了 → 界面自动重画。** 你不用手动操作 DOM。

---

## 5. 开发常用命令（在 `react/` 目录下执行）

```bash
npm install        # 首次：安装依赖
npm run dev        # 开发模式：改代码浏览器自动刷新（默认端口 5173，需配代理）
npm run build      # 生产构建：产物到 dist/，Flask 直接 serve
npm test           # 跑全部前端测试
npm run lint       # 代码规范检查
```

---

## 6. 常见改动速查

| 想做什么 | 改哪里 |
|---------|--------|
| 改首页布局 | `src/pages/HomePage.tsx` + 样式 class |
| 改顶栏/导航 | `src/components/Layout.tsx` |
| 加一个新页面 | ① 在 `src/pages/` 新建文件 → ② 在 `src/router.tsx` 注册路径 → ③ 需要登录就放进 `ProtectedRoute` 里 |
| 改登录逻辑 | `src/contexts/AuthContext.tsx` |
| 改某个接口的调用参数 | 找到对应页面里 `api_client.xxx(` 那行 |
| 改全局配色/字体 | `src/index.css`（Tailwind 主题变量） |
| 换 Logo/图标 | 页面里的 `<svg>` 或 `public/` 资源 |
| 视频播放体验 | `src/pages/MediaPlayerPage.tsx` + `src/hooks/usePlayerGestures.ts` |
| 测试不过 | 看 `src/test/` 对应文件，多数是 mock 数据与后端返回不一致 |

---

## 7. 结论

- 前端 = `react/src/` 下十几个文件，**按"页面-组件-工具"三层组织**，已经相当规整。
- 你不需要学会 React 的全部，只需要：**改页面找 `pages/`，改积木找 `components/`，发请求找 `api/client.ts`，看路由找 `router.tsx`**。
- 重构的方向不是换框架，而是：补 `types/`、把 `api/` 拆细、把 1200 行的播放器页面拆组件、删 `legacy.css` 与死代码——这些做完后，前端会更接近第 8 节的目标结构。

## 8. 目标结构（重构后的样子，供后续参考）

```
react/src/
├── main.tsx / App.tsx / router.tsx      # 入口与路由（保持）
├── types/                               # 新增：与后端对齐的类型定义
├── api/                                 # 拆细：client + auth/media/file/category/douyin
├── contexts/  hooks/  utils/            # 保持，hooks 从播放器页面抽出更多
├── pages/                               # 保持 8 页，播放器页瘦身
├── components/  (+ player/ 子目录)      # 从播放器页拆出 VideoPlayer 等
├── styles/index.css                     # 删 legacy.css，统一样式入口
└── test/                                # 按目录镜像组织
```

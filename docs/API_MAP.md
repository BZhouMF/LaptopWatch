# 前端 ↔ 后端 API 对照表

> 用途：不看代码也能知道"前端每个页面调用了后端的哪个接口、收发什么数据"。
> 依据：直接核对 `blueprints/` 与 `react/src/` 源码整理，**以代码为准**（README 中个别描述已过时，见文末"与 README 的差异"）。
> 更新日期：随重构进行应同步维护本表。

---

## 0. 总览：前端怎么和后端说话

- 前端（浏览器里的 React 程序）通过 **HTTP 请求** 与后端（Flask）沟通，协议和页面本身是什么框架无关。
- 所有请求都经过 `react/src/api/client.ts` 里创建的一个 axios 实例（`api_client`），它统一负责：
  - **超时**：30 秒；
  - **带凭证**：`withCredentials: true`（登录后浏览器自动携带 session cookie，后端靠 cookie 识别"你是谁"）；
  - **401 拦截**：任何接口返回 401（未登录）→ 自动跳转 `/login` 登录页；
  - **503 拦截例外**：503（服务未激活）不跳登录页，由调用方自行处理。
- 前端只访问 **一个端口 :5002**（Flask）。视频/图片的 `<video>`、`<img>` 标签也使用**同源相对路径** `/media/serve_media/...`，由 Flask 5002 直接处理（README 所说"媒体直连 5003 FastAPI"与当前代码不符，见文末差异说明）。

**登录状态判断**：后端在登录成功时写入 session cookie；几乎所有业务接口都有 `@login_required` 装饰器，未登录返回 401。

---

## 1. API 总表（按功能分组）

### 1.1 认证（`blueprints/auth.py`）

| 方法 | 路径 | 参数 | 返回 | 前端调用方 |
|------|------|------|------|-----------|
| POST | `/login` | 表单：`account`、`password` | `{'code':0,'msg':'登录成功'}` 或 `{'code':1,'msg':...}`（401/500） | `AuthContext.tsx`（登录按钮） |
| GET | `/logout` | 无 | 重定向到登录页 | `AuthContext.tsx`（退出登录） |
| POST | `/register` | 表单：`account`、`password`、`confirm_password` | JSON `{'code':0/1,'msg':...}` | `RegisterPage.tsx` |

> 注意：注册接口带"陷阱"——任何人提交合法表单即触发全服务终止（源码注释原文如此，属历史行为，重构时需复核）。

### 1.2 首页 / 核心（`blueprints/core.py`）

| 方法 | 路径 | 参数 | 返回 | 前端调用方 |
|------|------|------|------|-----------|
| GET | `/api/drives` | 无 | `{'drives':['C:','D:',...]}` | `HomePage.tsx`（首页磁盘列表） |
| GET | `/api/mode` | 无 | `{'run_mode','category_browse','random_mode','douyin_random_media','page_first','page_load'}` | `HomePage.tsx`、`CategoryBrowsePage.tsx` |
| GET | `/api/config-version` | 无 | `{'version':int,'service_active':bool}` | `App.tsx`（每 15 秒轮询，配置变更则刷新页面） |
| POST | `/api/start_service` | JSON：`mode/media_dir/sort_type/sort_order/random/douyin_random/category_browse` | `{'code','msg','local_url','lan_url','qr_base64','settings'}` | （GUI/管理页使用） |
| POST | `/api/stop_service` | 无 | `{'code':0,'msg':'服务已停止'}` | （GUI/管理页使用） |
| POST | `/api/admin/config` | JSON：`mode/category_browse/random_mode/douyin_random_media/service_active/media_dir`，或 `X-Auth-Password` 头 | `{'code','msg','config'}` | （管理页使用） |
| GET | `/favicon.ico` | 无 | 204 空响应 | 浏览器自动请求 |

### 1.3 普通模式（`blueprints/normal_api.py`，需 normal 模式）

| 方法 | 路径 | 参数 | 返回 | 前端调用方 |
|------|------|------|------|-----------|
| GET | `/api/check_path` | `path`（可为空串） | 200（路径存在/会话有效）或 401/400 | `LoginPage.tsx`、`ProtectedRoute.tsx`（**用它当"是否已登录"探针**） |
| GET | `/api/list` | `path`、`type=files\|folders`、`sort=name\|date\|size`、`order=asc\|desc`、`offset`、`limit`(默认20) | `type=folders` 时返回文件夹数组；`type=files` 时返回 `{'items':[...],'has_more':bool}`；items 含 `name/path/thumb/icon/is_video/is_image/is_previewable/is_text_readable/raw_url/date/size` | `BrowsePage.tsx`（目录列表、文件分页） |
| GET | `/api/list_all` | `path` | 数组：`{'path','name','is_dir'}`（无分页） | `BrowsePage.tsx`（"全选"功能） |

### 1.4 媒体模式（`blueprints/media_api.py`，需 video/image/douyin 模式）

| 方法 | 路径 | 参数 | 返回 | 前端调用方 |
|------|------|------|------|-----------|
| GET | `/media/load_more` | `offset`、`limit` | `{'code':0,'data':...}` 或 503（DB 不可用） | `MediaGrid.tsx`（滚动加载） |
| GET | `/media/thumbnail/<relative_path>` | 或带 `path` 参数传绝对路径（普通模式） | 图片字节流（jpeg，带 Cache-Control），404/403 | `<img>` 标签（`ThumbImg.tsx` / `MediaGrid.tsx`） |
| GET | `/media/serve_media/<relative_path>` | 支持 HTTP Range 头 | 视频分块流（206）/ 图片音频直传；空路径返回 400 | `<video>`/`<img>` 标签 + 预览弹窗（**全部页面共用**） |
| GET | `/media/download_media/<relative_path>` | 无 | 文件下载（attachment） | 媒体下载按钮 |
| GET | `/media/navigate` | `current_path`（相对路径）、`direction=prev\|next` | `{'code':0,'data':{'relative_path','name','is_video'}}`；`code:2` = 已到边界 | `MediaPlayerPage.tsx`（上一张/下一张） |

### 1.5 抖音模式（`blueprints/douyin_api.py`，需 douyin 模式）

| 方法 | 路径 | 参数 | 返回 | 前端调用方 |
|------|------|------|------|-----------|
| GET | `/api/douyin/init` | 无 | `{'code':0,'data':{'relative_path','name',...}}`；`code:1` = 没有视频 | `MediaPlayerPage.tsx`（进入播放器时初始化） |
| GET | `/api/douyin/next` | 无 | `{'code':0,'data':...}`；`code:2` = 没有更多 | `MediaPlayerPage.tsx`（滑动切换、预加载） |

### 1.6 分类目录浏览（`blueprints/category_api.py`，需 video/image 模式 + 分类开关）

| 方法 | 路径 | 参数 | 返回 | 前端调用方 |
|------|------|------|------|-----------|
| GET | `/category/data` | `path`（相对路径，空=根）、`refresh=1`（强制重扫） | `{'code':0,'data':<分类树信息>}` | `CategoryBrowsePage.tsx`（页面打开/刷新） |
| GET | `/category/grid_more` | `path`、`offset`、`limit`、`refresh=1` | `{'code':0,'data':files,'has_more':bool,'next_offset':int}` | `CategoryBrowsePage.tsx`（叶子文件夹滚动加载） |
| GET | `/category/browse/<path>` | `refresh=1` | **返回 React SPA 入口页**（HTML，非 JSON；前端路由接管渲染） | 浏览器直接访问 / 刷新 |
| GET | `/category/grid/<path>` | `refresh=1` | 同上（SPA 入口） | 浏览器直接访问 / 刷新 |

### 1.7 文件操作（`blueprints/file_api.py`，需 normal 模式）

| 方法 | 路径 | 参数 | 返回 | 前端调用方 |
|------|------|------|------|-----------|
| GET | `/file/raw/<path>` | 无 | 文件原始字节流（可带 Range） | `TextViewerPage.tsx`（以 arraybuffer 拉取后前端解码文本） |
| GET | `/file/view/<path>` | 无 | 文件流（浏览器下载或内联查看） | `BrowsePage.tsx`（单独下载） |
| GET | `/file/download_folder` | `path`（绝对路径） | ZIP 文件流（attachment）；超限返回 400 | `BrowsePage.tsx`（文件夹打包下载） |
| POST | `/file/download_selected` | JSON：`{'base':绝对路径,'paths':[绝对路径...]}` | ZIP 文件流 | `BrowsePage.tsx`（批量下载，前端转 blob 保存） |

> 限制：ZIP 打包受 `MAX_FOLDER_SIZE` 与 `MAX_FOLDER_FILES` 限制（以 `config.py` 为准）。

### 1.8 旧版兼容重定向（`blueprints/core.py`，历史遗留）

| 旧路径 | 重定向到 |
|--------|---------|
| GET `/serve_media/<path>` | `/media/serve_media/<path>` |
| GET `/load_more` | `/media/load_more`（保留 query） |
| GET `/raw/<path>` | `/file/raw/<path>` |
| GET `/view/<path>` | `/file/view/<path>` |
| GET `/text/<path>` | `/file/text/<path>` |

> 这些是 React 化之前旧页面的 URL，属于**兼容死代码**，重构时可评估删除。

---

## 2. 前端调用点索引（文件 → 它调的 API）

| 前端文件 | 调用的 API |
|---------|-----------|
| `App.tsx` | `GET /api/config-version`（15s 轮询） |
| `components/ProtectedRoute.tsx` | `GET /api/check_path`（登录探针） |
| `components/MediaGrid.tsx` | `GET /media/load_more`；点击视频跳 `/media/serve_media/...` |
| `components/ThumbImg.tsx` | `<img src="/media/thumbnail/...">` |
| `contexts/AuthContext.tsx` | `POST /login`、`GET /logout` |
| `pages/HomePage.tsx` | `GET /api/mode`、`GET /api/drives` |
| `pages/BrowsePage.tsx` | `GET /api/list`、`GET /api/list_all`、`POST /file/download_selected`、`GET /file/view/*`、`GET /file/download_folder`、预览用 `/media/serve_media/*` |
| `pages/CategoryBrowsePage.tsx` | `GET /api/mode`、`GET /category/data`、`GET /category/grid_more` |
| `pages/MediaPlayerPage.tsx` | `GET /api/douyin/init`、`GET /api/douyin/next`、`GET /media/navigate`、`/media/serve_media/*`（视频源）、`/media/thumbnail/*`（封面） |
| `pages/TextViewerPage.tsx` | `GET /file/raw/<path>`（arraybuffer） |
| `pages/LoginPage.tsx` | `GET /api/check_path`（已有会话则直接跳转） |
| `pages/RegisterPage.tsx` | `POST /register` |

---

## 3. 与 README.md 的差异（以代码为准）

1. **登录路径**：README 写 `/auth/login`，实际蓝图无前缀，是 `POST /login`（前端调用与后端代码一致）。
2. **媒体流端口**：README 说视频/图片由 :5003 FastAPI 直连；实际前端全部使用同源相对路径 `/media/serve_media/...`（:5002 的 Flask `media_api.serve_media` 实现分块传输），`:5003` 的 video_server.py 在当前前端代码中**未被引用**（需复核是否已废弃，重构时确认）。
3. **`routes_config.py` 的 FRONTEND_ROUTES**：声明了 `/static/css/style.css`、`/static/js/browse.js` 等旧静态资源路径，这些文件已不存在，属 React 化之前的死配置。

---

## 4. 想改东西时怎么查

- **想看某功能后端怎么实现**：按上表找到 `blueprints/` 下对应文件与函数。
- **想看某页面发了什么请求**：在 `react/src/pages/<页面>.tsx` 里搜 `api_client.`。
- **想加一个接口**：在对应蓝图中加路由 → 在前端 `pages/` 或 `api/` 中用 `api_client.get/post(...)` 调用 → 两端路径保持一致（可参考 `routes_config.py` 集中管理）。

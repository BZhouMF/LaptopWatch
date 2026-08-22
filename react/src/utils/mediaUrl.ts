/**
 * 媒体流 URL 工具
 *
 * 媒体内容（视频/图片/音频）统一走 FastAPI 媒体服务（端口 5003），
 * 与 Flask 页面/API（5002）隔离：视频长连接不再占用 Flask worker 线程。
 *
 * 端口从 /api/mode 动态拉取并缓存（允许后端配置 LAPTOPWATCH_VIDEO_PORT），
 * 拉取失败或尚未就绪时回退到默认端口 5003。
 * host 用 window.location.hostname 动态获取，手机等设备经局域网 IP 访问时
 * 也能正确指向媒体服务。
 */

const DEFAULT_VIDEO_PORT = 5003;

let videoPort: number | null = null;
let portPromise: Promise<number> | null = null;

/** 拉取并缓存媒体服务端口（幂等；多组件并发调用只发一次请求） */
function fetchVideoPort(): Promise<number> {
  if (videoPort !== null) return Promise.resolve(videoPort);
  if (!portPromise) {
    portPromise = fetch("/api/mode")
      .then((resp) => resp.json())
      .then((data) => {
        videoPort = Number(data.video_port) || DEFAULT_VIDEO_PORT;
        return videoPort;
      })
      .catch(() => {
        videoPort = DEFAULT_VIDEO_PORT;
        return videoPort;
      });
  }
  return portPromise;
}

/** 预取媒体服务端口（页面挂载时调用，避免首次播放等待） */
export function initVideoPort(): Promise<number> {
  return fetchVideoPort();
}

/** 构造媒体内容 URL（指向 FastAPI 5003） */
export function mediaServeUrl(relativePath: string): string {
  const port = videoPort ?? DEFAULT_VIDEO_PORT;
  const host = window.location.hostname || "127.0.0.1";
  return `http://${host}:${port}/media/serve_media/${encodeURIComponent(relativePath)}`;
}

/** 构造缩略图 URL（仍走 Flask 5002：短请求 + CPU 密集生成，留在 Flask 更合适） */
export function thumbnailUrl(relativePath: string): string {
  return `/media/thumbnail/${encodeURIComponent(relativePath)}`;
}

/** 仅供测试：重置端口缓存 */
export function __resetMediaUrlCache(): void {
  videoPort = null;
  portPromise = null;
}

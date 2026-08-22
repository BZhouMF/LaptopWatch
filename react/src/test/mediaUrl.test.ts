import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  mediaServeUrl,
  thumbnailUrl,
  initVideoPort,
  __resetMediaUrlCache,
} from "../utils/mediaUrl";

/**
 * 媒体 URL 工具测试：
 * 媒体流指向 FastAPI 5003（与 Flask API 隔离），端口由 /api/mode 动态下发。
 */
describe("mediaUrl", () => {
  beforeEach(() => {
    __resetMediaUrlCache();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("未拉取端口时回退默认端口 5003 构造媒体 URL", () => {
    const url = mediaServeUrl("videos/a.mp4");
    expect(url).toBe("http://localhost:5003/media/serve_media/videos%2Fa.mp4");
  });

  it("initVideoPort 拉取后端端口并缓存（只请求一次）", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      json: () => Promise.resolve({ video_port: 5003 }),
    } as Response);

    const port = await initVideoPort();
    expect(port).toBe(5003);
    // 端口已缓存：再次调用不再发请求
    await initVideoPort();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    expect(mediaServeUrl("a.mp4")).toBe("http://localhost:5003/media/serve_media/a.mp4");
  });

  it("支持后端自定义视频端口", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      json: () => Promise.resolve({ video_port: 9000 }),
    } as Response);
    await initVideoPort();
    expect(mediaServeUrl("a.mp4")).toBe("http://localhost:9000/media/serve_media/a.mp4");
  });

  it("端口拉取失败时回退默认端口 5003", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network"));
    await initVideoPort();
    expect(mediaServeUrl("a.mp4")).toBe("http://localhost:5003/media/serve_media/a.mp4");
  });

  it("缩略图 URL 走 Flask 相对路径（5002）", () => {
    expect(thumbnailUrl("videos/a.mp4")).toBe("/media/thumbnail/videos%2Fa.mp4");
  });
});

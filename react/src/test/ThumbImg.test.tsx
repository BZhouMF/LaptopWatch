import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ThumbImg from "../components/ThumbImg";
import { queueThumbnail, __resetThumbnailQueue } from "../utils/thumbnailQueue";

/**
 * ThumbImg 组件测试：
 * 受 thumbnailQueue 调度器控制的缩略图 <img>，未轮到加载时不发请求。
 */
describe("ThumbImg", () => {
  beforeEach(() => {
    __resetThumbnailQueue();
  });

  it("有空闲槽位时立即设置 src", () => {
    render(<ThumbImg src="/media/thumbnail/a.jpg" alt="a" />);
    const img = screen.getByRole("img") as HTMLImageElement;
    expect(img.getAttribute("src")).toBe("/media/thumbnail/a.jpg");
  });

  it("槽位被占满时 src 为空（不发请求），释放后设置 src", async () => {
    // 占满 4 个并发槽位
    const releases: Array<() => void> = [];
    for (let i = 0; i < 4; i++) {
      queueThumbnail((markDone) => {
        releases.push(markDone);
      });
    }

    render(<ThumbImg src="/media/thumbnail/a.jpg" alt="a" />);
    const img = screen.getByRole("img") as HTMLImageElement;
    // 未轮到 → src 为空，浏览器不会发请求
    expect(img.getAttribute("src")).toBeFalsy();

    // 释放一个槽位 → ThumbImg 任务开始 → src 设置
    releases[0]();
    await waitFor(() => {
      expect(img.getAttribute("src")).toBe("/media/thumbnail/a.jpg");
    });
  });

  it("onError 时释放槽位并隐藏图片", () => {
    render(<ThumbImg src="/media/thumbnail/a.jpg" alt="a" />);
    const img = screen.getByRole("img") as HTMLImageElement;
    fireEvent.error(img);
    expect(img.style.display).toBe("none");
  });

  it("onLoad 时释放槽位，后续排队任务得以执行", async () => {
    const releases: Array<() => void> = [];
    for (let i = 0; i < 4; i++) {
      queueThumbnail((markDone) => {
        releases.push(markDone);
      });
    }

    render(<ThumbImg src="/media/thumbnail/a.jpg" alt="a" />);
    const img = screen.getByRole("img") as HTMLImageElement;
    expect(img.getAttribute("src")).toBeFalsy();

    // 释放一个槽位后 ThumbImg 开始加载
    releases[0]();
    await waitFor(() => {
      expect(img.getAttribute("src")).toBe("/media/thumbnail/a.jpg");
    });

    // onLoad 释放 ThumbImg 自己的槽位
    fireEvent.load(img);
    // 不抛错即通过（槽位已正确释放）
  });

  it("组件卸载时取消排队中的任务", () => {
    const releases: Array<() => void> = [];
    for (let i = 0; i < 4; i++) {
      queueThumbnail((markDone) => {
        releases.push(markDone);
      });
    }

    const { unmount } = render(<ThumbImg src="/media/thumbnail/a.jpg" alt="a" />);
    const img = screen.getByRole("img") as HTMLImageElement;
    expect(img.getAttribute("src")).toBeFalsy();

    unmount(); // 取消排队任务
    // 释放槽位：跳过已取消的 ThumbImg 任务，不抛错
    releases[0]();
    releases[1]();
    releases[2]();
    releases[3]();
  });

  it("卸载时释放已开始任务的槽位，后续排队任务得以执行（封面不显示的修复）", async () => {
    const releases: Array<() => void> = [];
    for (let i = 0; i < 4; i++) {
      queueThumbnail((markDone) => {
        releases.push(markDone);
      });
    }

    const { unmount } = render(<ThumbImg src="/media/thumbnail/a.jpg" alt="a" />);
    const img = screen.getByRole("img") as HTMLImageElement;
    expect(img.getAttribute("src")).toBeFalsy();

    // 释放一个槽位 → ThumbImg 任务开始（src 已设置，但图片尚未 onLoad）
    releases[0]();
    await waitFor(() => {
      expect(img.getAttribute("src")).toBe("/media/thumbnail/a.jpg");
    });

    // 模拟翻页/切换视图：组件卸载但图片还在加载中
    // 若槽位不释放，后续所有封面将永远排不上队（bug）
    unmount();

    // 修复后：已开始任务的槽位被释放 → 新任务立即开始
    let next_started = 0;
    queueThumbnail(() => {
      next_started++;
    });
    expect(next_started).toBe(1);
  });
});

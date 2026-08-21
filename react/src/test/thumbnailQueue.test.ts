import { describe, it, expect, beforeEach } from "vitest";
import { queueThumbnail, __resetThumbnailQueue } from "../utils/thumbnailQueue";

/**
 * thumbnailQueue 并发调度器测试：
 * 缩略图请求最多同时 MAX_CONCURRENT(4) 个在途，给 API 请求留出连接。
 */
describe("thumbnailQueue", () => {
  beforeEach(() => {
    __resetThumbnailQueue();
  });

  it("最多同时 4 个任务在途，第 5 个排队等待释放", () => {
    const started: number[] = [];
    const releases: Array<() => void> = [];

    for (let i = 0; i < 6; i++) {
      queueThumbnail((markDone) => {
        started.push(i);
        releases.push(markDone);
      });
    }

    // 只有前 4 个立即开始
    expect(started).toEqual([0, 1, 2, 3]);

    // 释放一个槽位 → 第 5 个开始
    releases[0]();
    expect(started).toEqual([0, 1, 2, 3, 4]);

    // 全部释放 → 第 6 个开始
    releases[1]();
    releases[2]();
    releases[3]();
    releases[4]();
    expect(started).toEqual([0, 1, 2, 3, 4, 5]);
  });

  it("取消的排队任务会被跳过，不占执行机会", () => {
    const started: number[] = [];
    const releases: Array<() => void> = [];
    const cancels: Array<() => void> = [];

    for (let i = 0; i < 6; i++) {
      const cancel = queueThumbnail((markDone) => {
        started.push(i);
        releases.push(markDone);
      });
      cancels.push(cancel);
    }
    expect(started).toEqual([0, 1, 2, 3]);

    // 取消排队的第 5 个任务
    cancels[4]();
    // 释放一个槽位 → 跳过已取消的 4，直接执行 5
    releases[0]();
    expect(started).toEqual([0, 1, 2, 3, 5]);
  });

  it("已开始的任务无法被取消（取消只对排队中任务生效）", () => {
    const started: number[] = [];
    const releases: Array<() => void> = [];
    const cancels: Array<() => void> = [];

    for (let i = 0; i < 4; i++) {
      const cancel = queueThumbnail((markDone) => {
        started.push(i);
        releases.push(markDone);
      });
      cancels.push(cancel);
    }
    // 全部已开始
    expect(started).toEqual([0, 1, 2, 3]);

    // 取消已开始的任务：不应阻止其已开始的执行
    cancels[0]();
    cancels[1]();
    // 释放槽位仍正常推进（第 5 个任务排队中）
    releases[0]();
    expect(started).toEqual([0, 1, 2, 3]);
  });

  it("markDone 幂等：重复调用只释放一次槽位", () => {
    const started: number[] = [];
    const releases: Array<() => void> = [];

    for (let i = 0; i < 5; i++) {
      queueThumbnail((markDone) => {
        started.push(i);
        releases.push(markDone);
      });
    }
    // 第 6 个任务排队
    let sixth = 0;
    queueThumbnail(() => {
      sixth++;
    });

    expect(started).toEqual([0, 1, 2, 3]);

    // 释放第 1 个槽 → 第 5 个开始执行
    releases[0]();
    expect(started).toEqual([0, 1, 2, 3, 4]);
    expect(sixth).toBe(0);

    // markDone 幂等：重复调用不再次释放，第 6 个仍排队
    releases[0]();
    releases[0]();
    releases[0]();
    expect(sixth).toBe(0);

    // 释放其余槽位 → 第 6 个开始
    releases[1]();
    expect(sixth).toBe(1);
  });
});

/**
 * 缩略图请求并发调度器
 *
 * 浏览器对同一源（HTTP/1.1）只维持约 6 个并发连接。媒体网格一页会同时
 * 挂起几十个缩略图请求（视频封面需 cv2 抽帧，单个可能几百毫秒），如果全部
 * 同时发出会占满连接池，导致翻页等 API 请求排队（表现为"必须等第一页封面
 * 处理完才能翻页"）。
 *
 * 这里把缩略图加载限制为同时最多 MAX_CONCURRENT 个在途请求，给 API 请求
 * 留出空闲连接；封面逐张加载、就绪即显示，不再阻塞任何交互。
 */

const MAX_CONCURRENT = 4;

interface QueueItem {
  /** 轮到该任务时执行；markDone 由任务在真正完成后调用以释放槽位。 */
  onStart: (markDone: () => void) => void;
  cancelled: boolean;
}

const pending: QueueItem[] = [];
let inFlight = 0;

function pump(): void {
  while (inFlight < MAX_CONCURRENT && pending.length > 0) {
    const item = pending.shift()!;
    if (item.cancelled) continue;
    inFlight += 1;
    let released = false;
    const markDone = () => {
      if (released) return;
      released = true;
      inFlight = Math.max(0, inFlight - 1);
      pump();
    };
    item.onStart(markDone);
  }
}

/**
 * 将一次缩略图加载加入调度队列。
 * @param onStart 轮到该任务时回调（此时应设置 img 的 src）；参数 markDone
 *                需在图片 onLoad/onError 时调用，用于释放并发槽位。
 * @returns 取消函数：组件卸载时调用；若任务尚未开始则跳过，已开始则无法中止。
 */
export function queueThumbnail(onStart: (markDone: () => void) => void): () => void {
  const item: QueueItem = { onStart, cancelled: false };
  pending.push(item);
  pump();
  return () => {
    item.cancelled = true;
  };
}

/** 仅供测试使用：重置调度器状态。 */
export function __resetThumbnailQueue(): void {
  pending.length = 0;
  inFlight = 0;
}

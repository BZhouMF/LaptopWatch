import { useEffect, useRef, useState } from "react";
import { queueThumbnail, markThumbnailLoaded, isThumbnailLoaded } from "../utils/thumbnailQueue";

interface ThumbImgProps {
  src: string;
  alt: string;
  className?: string;
}

/**
 * 受并发调度器控制的缩略图 <img>。
 *
 * 未轮到加载时 src 为空（不发请求），显示背景占位；轮到后设置 src 由浏览器
 * 加载，onLoad/onError 时释放调度槽位。加载失败时隐藏自身（保留原行为）。
 *
 * 本会话内已成功加载过的封面：重新挂载（返回视图/翻回原页）时直接设置 src，
 * 浏览器 HTTP 缓存命中立即显示，不再排队，避免"返回后封面重新加载"的闪烁。
 */
export default function ThumbImg({ src, alt, className }: ThumbImgProps) {
  const [thumbSrc, setThumbSrc] = useState<string | undefined>(undefined);
  const doneRef = useRef<() => void>(() => {});

  useEffect(() => {
    let alive = true;
    // 当前已开始任务的槽位释放函数（任务开始时由调度器注入）
    let release: (() => void) | null = null;

    // 已加载过的封面：直接显示（浏览器缓存命中），不走调度器
    if (isThumbnailLoaded(src)) {
      setThumbSrc(src);
      return;
    }

    setThumbSrc(undefined);
    doneRef.current = () => {};
    const cancel = queueThumbnail((markDone) => {
      if (!alive) {
        markDone();
        return;
      }
      release = markDone;
      doneRef.current = markDone;
      setThumbSrc(src);
    });
    return () => {
      alive = false;
      cancel();
      // 关键：任务已开始（图片还在加载）时，卸载/换 src 也要释放调度槽位。
      // 否则已开始但未 onLoad 的请求会让槽位永久占用，后续封面全部排不上队。
      if (release) {
        doneRef.current = () => {};
        release();
      }
    };
  }, [src]);

  return (
    <img
      src={thumbSrc}
      alt={alt}
      loading="lazy"
      className={className}
      onLoad={() => {
        doneRef.current();
        markThumbnailLoaded(src);
      }}
      onError={(e) => {
        doneRef.current();
        (e.target as HTMLImageElement).style.display = "none";
      }}
    />
  );
}

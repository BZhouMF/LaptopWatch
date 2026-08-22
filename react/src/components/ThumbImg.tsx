import { useEffect, useRef, useState } from "react";
import { queueThumbnail } from "../utils/thumbnailQueue";

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
 */
export default function ThumbImg({ src, alt, className }: ThumbImgProps) {
  const [thumbSrc, setThumbSrc] = useState<string | undefined>(undefined);
  const doneRef = useRef<() => void>(() => {});

  useEffect(() => {
    let alive = true;
    // 当前已开始任务的槽位释放函数（任务开始时由调度器注入）
    let release: (() => void) | null = null;
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
      onLoad={() => doneRef.current()}
      onError={(e) => {
        doneRef.current();
        (e.target as HTMLImageElement).style.display = "none";
      }}
    />
  );
}

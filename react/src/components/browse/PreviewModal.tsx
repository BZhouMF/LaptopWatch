import { useState, useEffect, useCallback, type MouseEvent } from "react";

interface PreviewModalProps {
  url: string;
  name: string;
  is_video: boolean;
  download_url: string;
  on_close: () => void;
}

export default function PreviewModal({
  url,
  name,
  is_video,
  download_url,
  on_close,
}: PreviewModalProps) {
  const [is_closing, set_is_closing] = useState(false);

  const handle_close = useCallback(() => {
    if (is_closing) return;
    set_is_closing(true);
    setTimeout(() => on_close(), 200);
  }, [is_closing, on_close]);

  const handle_keydown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Escape") handle_close();
    },
    [handle_close]
  );

  useEffect(() => {
    document.addEventListener("keydown", handle_keydown);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handle_keydown);
      document.body.style.overflow = "";
    };
  }, [handle_keydown]);

  const handle_backdrop_click = (event: MouseEvent<HTMLDivElement>) => {
    if (event.target === event.currentTarget) handle_close();
  };

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center bg-black/95 backdrop-blur-sm ${
        is_closing ? "animate-fade-out" : "animate-fade-in"
      }`}
      onClick={handle_backdrop_click}
    >
      {/* Close button */}
      <button
        onClick={handle_close}
        className="absolute right-4 top-4 z-10 flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-white/80 transition hover:bg-white/20 hover:text-white hover:scale-105"
        aria-label="关闭"
      >
        <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      {/* File name */}
      <p className="absolute left-4 top-4 text-sm text-white/60 truncate max-w-[60%]">{name}</p>

      {/* Content */}
      {is_video ? (
        <video
          src={url}
          controls
          autoPlay
          className="max-h-[90vh] max-w-[90vw] rounded-xl"
        >
          <a href={download_url} download>下载</a>
        </video>
      ) : (
        <img
          src={url}
          alt={name}
          className="max-h-[90vh] max-w-[90vw] rounded-xl object-contain"
        />
      )}

      {/* Download button */}
      <a
        href={download_url}
        download
        className="absolute bottom-4 right-4 rounded-lg bg-white/10 px-4 py-2 text-sm text-white/80 transition hover:bg-white/20 hover:text-white"
      >
        下载
      </a>
    </div>
  );
}

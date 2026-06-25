import { useEffect, useCallback, type MouseEvent } from "react";

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
  const handle_keydown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Escape") on_close();
    },
    [on_close]
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
    if (event.target === event.currentTarget) on_close();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/90"
      onClick={handle_backdrop_click}
    >
      <button
        onClick={on_close}
        className="absolute right-4 top-4 z-10 flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-2xl text-white transition hover:bg-white/20"
        aria-label="关闭"
      >
        &times;
      </button>

      {is_video ? (
        <video
          src={url}
          controls
          autoPlay
          className="max-h-[90vh] max-w-[90vw] rounded-lg"
        >
          <a href={download_url} download>
            下载
          </a>
        </video>
      ) : (
        <img
          src={url}
          alt={name}
          className="max-h-[90vh] max-w-[90vw] rounded-lg object-contain"
        />
      )}

      <a
        href={download_url}
        download
        className="absolute bottom-4 right-4 rounded-lg bg-white/10 px-4 py-2 text-sm text-white transition hover:bg-white/20"
      >
        下载
      </a>
    </div>
  );
}

import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api_client from "../api/client";

interface TextState {
  filename: string;
  content: string;
  encoding: string;
  file_size: string;
}

export default function TextViewerPage() {
  const { "*": filepath } = useParams<{ "*": string }>();
  const navigate = useNavigate();
  const [state, set_state] = useState<TextState | null>(null);
  const [is_loading, set_is_loading] = useState(true);
  const [error, set_error] = useState<string | null>(null);
  const [is_copied, set_is_copied] = useState(false);

  useEffect(() => {
    if (!filepath) return;
    let cancelled = false;

    api_client
      .get(`/file/raw/${filepath}`, { responseType: "arraybuffer" })
      .then((response) => {
        if (cancelled) return;
        const buffer = response.data as ArrayBuffer;
        let text_content = "";
        let detected_encoding = "UTF-8";

        const encodings: { label: string; decoder: TextDecoder }[] = [
          { label: "UTF-8", decoder: new TextDecoder("utf-8", { fatal: true }) },
          { label: "GBK", decoder: new TextDecoder("gbk", { fatal: true }) },
          { label: "GB2312", decoder: new TextDecoder("gb2312", { fatal: true }) },
          { label: "Latin-1", decoder: new TextDecoder("latin1", { fatal: false }) },
        ];

        for (const enc of encodings) {
          try {
            text_content = enc.decoder.decode(new Uint8Array(buffer));
            detected_encoding = enc.label;
            break;
          } catch {
            continue;
          }
        }

        const cl = response.headers["content-length"];
        const size_bytes = cl ? parseInt(String(cl), 10) : buffer.byteLength;
        const size_str =
          size_bytes >= 1024 * 1024
            ? `${(size_bytes / (1024 * 1024)).toFixed(1)} MB`
            : size_bytes >= 1024
              ? `${(size_bytes / 1024).toFixed(1)} KB`
              : `${size_bytes} B`;

        const filename = decodeURIComponent(filepath.split("/").pop() || filepath);

        set_state({
          filename,
          content: text_content,
          encoding: detected_encoding,
          file_size: size_str,
        });
      })
      .catch(() => {
        if (!cancelled) set_error("无法加载文件内容");
      })
      .finally(() => {
        if (!cancelled) set_is_loading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [filepath]);

  const handle_copy = useCallback(async () => {
    if (!state) return;
    try {
      await navigator.clipboard.writeText(state.content);
      set_is_copied(true);
      setTimeout(() => set_is_copied(false), 2000);
    } catch {
      set_is_copied(false);
    }
  }, [state]);

  const handle_download = useCallback(() => {
    if (!filepath) return;
    window.open(`/file/raw/${filepath}`, "_blank");
  }, [filepath]);

  if (is_loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-300 border-t-indigo-500" />
      </div>
    );
  }

  if (error || !state) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-zinc-500">{error || "文件不存在"}</p>
      </div>
    );
  }

  const line_count = state.content.split("\n").length;

  return (
    <div className="flex flex-col h-full">
      <header className="flex items-center justify-between border-b border-zinc-200 bg-white px-5 py-3 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex items-center gap-4 min-w-0">
          <h1 className="text-base font-medium text-zinc-800 truncate dark:text-zinc-100">
            {state.filename}
          </h1>
          <span className="shrink-0 text-xs text-zinc-400">编码: {state.encoding}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={handle_download}
            className="rounded-lg border border-zinc-300 px-3 py-1.5 text-xs text-zinc-600 transition hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800"
          >
            下载文件
          </button>
          <button
            onClick={handle_copy}
            className="rounded-lg border border-zinc-300 px-3 py-1.5 text-xs text-zinc-600 transition hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800"
          >
            {is_copied ? "已复制" : "复制内容"}
          </button>
          <button
            onClick={() => navigate(-1)}
            className="rounded-lg bg-indigo-500 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-indigo-600"
          >
            返回
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-auto bg-zinc-50 dark:bg-zinc-950">
        <pre className="p-5 text-sm leading-relaxed text-zinc-800 dark:text-zinc-200 font-mono whitespace-pre-wrap break-all">
{state.content.split("\n").map((line, index) => (
            <span key={index} className="flex">
              <span className="select-none shrink-0 w-12 text-right pr-4 text-zinc-300 dark:text-zinc-600">
                {index + 1}
              </span>
              <span>{line}</span>
            </span>
          ))}
        </pre>
      </div>

      <footer className="border-t border-zinc-200 bg-white px-5 py-2 text-xs text-zinc-400 dark:border-zinc-800 dark:bg-zinc-950">
        文件大小: {state.file_size} | 总行数: {line_count}
      </footer>
    </div>
  );
}

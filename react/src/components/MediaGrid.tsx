import { useState, useEffect, useCallback, useRef } from "react";
import api_client from "../api/client";

interface MediaItem {
  name: string;
  relative_path: string;
  is_video: boolean;
  modify_time: number;
  size_str?: string;
  duration_str?: string;
}

interface PageCache {
  [page: number]: { items: MediaItem[]; has_more: boolean; total: number };
}

interface MediaGridProps {
  page_first: number;
  page_load: number;
  is_random: boolean;
}

export default function MediaGrid({ page_first, page_load, is_random }: MediaGridProps) {
  const [current_page, set_current_page] = useState(1);
  const [total_pages, set_total_pages] = useState(1);
  const [has_more, set_has_more] = useState(true);
  const [is_loading, set_is_loading] = useState(true);
  const [items, set_items] = useState<MediaItem[]>([]);
  const page_cache = useRef<PageCache>({});
  const abort_ref = useRef<AbortController | null>(null);

  const load_page = useCallback(
    async (page: number) => {
      if (page_cache.current[page]) {
        const cached = page_cache.current[page];
        set_items(cached.items);
        set_has_more(cached.has_more);
        set_current_page(page);
        window.scrollTo({ top: 0, behavior: "smooth" });
        return;
      }

      abort_ref.current?.abort();
      const controller = new AbortController();
      abort_ref.current = controller;

      set_is_loading(true);
      let offset: number;
      let limit: number;
      if (page === 1) {
        offset = 0;
        limit = page_first;
      } else {
        offset = page_first + (page - 2) * page_load;
        limit = page_load;
      }

      try {
        const resp = await api_client.get<{
          code: number; data: MediaItem[]; has_more: boolean; total: number;
        }>("/media/load_more", {
          params: { offset, limit },
          signal: controller.signal,
          timeout: 30000,
        });
        const data = resp.data;
        page_cache.current[page] = { items: data.data, has_more: data.has_more, total: data.total };
        set_items(data.data);
        set_has_more(data.has_more);
        set_current_page(page);
        if (!is_random && data.total > 0) {
          const tp = Math.ceil(data.total / page_load);
          set_total_pages(Math.max(tp, page));
        }
        window.scrollTo({ top: 0, behavior: "smooth" });
      } catch (err: unknown) {
        if ((err as Error).name === "AbortError" || (err as Error).name === "CanceledError") return;
      } finally {
        set_is_loading(false);
      }
    },
    [page_first, page_load, is_random]
  );

  useEffect(() => {
    load_page(1);
    return () => abort_ref.current?.abort();
  }, []);

  const handle_prev = useCallback(() => {
    if (current_page > 1 && !is_loading) load_page(current_page - 1);
  }, [current_page, is_loading, load_page]);

  const handle_next = useCallback(() => {
    if (has_more && !is_loading) load_page(current_page + 1);
  }, [current_page, has_more, is_loading, load_page]);

  const open_player = useCallback((relative_path: string) => {
    window.location.href = `/media/player?path=${encodeURIComponent(relative_path)}`;
  }, []);

  const visible_pages = (): (number | "dots")[] => {
    const max_visible = 5;
    const pages: (number | "dots")[] = [];
    pages.push(1);

    const start = Math.max(2, current_page - 1);
    const end = Math.min(total_pages - 1, current_page + 1);

    if (start > 2) pages.push("dots");
    for (let p = start; p <= end; p++) pages.push(p);
    if (end < total_pages - 1) pages.push("dots");

    if (total_pages > 1) pages.push(total_pages);
    // In random mode with has_more, show trailing dots
    if (is_random && has_more && !pages.includes("dots") && pages[pages.length - 1] !== "dots") {
      pages.push("dots");
    }
    return pages;
  };

  if (is_loading && items.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-300 border-t-indigo-500" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-auto p-4">
        {items.length === 0 ? (
          <div className="flex items-center justify-center p-20">
            <p className="text-zinc-400">没有找到媒体文件</p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3">
              {items.map((item) => (
                <button
                  key={item.relative_path}
                  onClick={() => open_player(item.relative_path)}
                  className="group relative flex flex-col overflow-hidden rounded-xl bg-white shadow-sm border border-zinc-200/50 transition hover:shadow-md dark:bg-zinc-900 dark:border-zinc-800"
                >
                  <div className="relative aspect-video bg-zinc-100 dark:bg-zinc-800">
                    <img
                      src={`/media/thumbnail/${encodeURIComponent(item.relative_path)}`}
                      alt={item.name}
                      loading="lazy"
                      className="h-full w-full object-cover"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                      }}
                    />
                    {item.is_video && (
                      <div className="absolute inset-0 flex items-center justify-center">
                        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-black/50 text-white transition group-hover:scale-110">
                          ▶
                        </div>
                      </div>
                    )}
                    {item.duration_str && (
                      <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1.5 py-0.5 text-[10px] text-white">
                        {item.duration_str}
                      </span>
                    )}
                  </div>
                  <div className="p-2">
                    <p className="text-xs text-zinc-700 truncate text-left dark:text-zinc-300">
                      {item.name}
                    </p>
                    {item.size_str && (
                      <p className="text-[10px] text-zinc-400 text-left mt-0.5">{item.size_str}</p>
                    )}
                  </div>
                </button>
              ))}
            </div>

            {is_loading && (
              <div className="flex justify-center py-8">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-300 border-t-indigo-500" />
              </div>
            )}
          </>
        )}
      </div>

      {/* Pagination */}
      {items.length > 0 && (total_pages > 1 || has_more) && (
        <div className="flex items-center justify-center gap-2 border-t border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-950">
          <button
            onClick={handle_prev}
            disabled={current_page <= 1 || is_loading}
            className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm text-zinc-600 transition hover:bg-zinc-100 disabled:opacity-30 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800"
          >
            上一页
          </button>
          <div className="flex items-center gap-1">
            {visible_pages().map((p, idx) =>
              p === "dots" ? (
                <span key={`dots-${idx}`} className="px-1 text-zinc-400">...</span>
              ) : (
                <button
                  key={p}
                  onClick={() => load_page(p)}
                  disabled={is_loading}
                  className={`min-w-[32px] rounded-lg px-2 py-1.5 text-sm transition ${
                    p === current_page
                      ? "bg-indigo-500 text-white"
                      : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
                  }`}
                >
                  {p}
                </button>
              )
            )}
          </div>
          <button
            onClick={handle_next}
            disabled={!has_more || is_loading}
            className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm text-zinc-600 transition hover:bg-zinc-100 disabled:opacity-30 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800"
          >
            下一页
          </button>
        </div>
      )}

      {!has_more && items.length > 0 && !is_loading && (
        <p className="py-3 text-center text-xs text-zinc-300 dark:text-zinc-700">已加载全部内容</p>
      )}
    </div>
  );
}

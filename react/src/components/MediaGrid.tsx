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

function Spinner({ size }: { size: "sm" | "md" }) {
  const dims = size === "sm" ? "h-5 w-5" : "h-8 w-8";
  return (
    <div className="flex justify-center py-10">
      <div className={`${dims} animate-spin rounded-full border-2 border-accent/20 border-t-accent`} />
    </div>
  );
}

export default function MediaGrid({ page_first, page_load, is_random }: MediaGridProps) {
  const [current_page, set_current_page] = useState(1);
  const [total_pages, set_total_pages] = useState(1);
  const [has_more, set_has_more] = useState(true);
  const [is_loading, set_is_loading] = useState(true);
  const [items, set_items] = useState<MediaItem[]>([]);
  const page_cache = useRef<PageCache>({});
  const abort_ref = useRef<AbortController | null>(null);

  // Invalidate cache when page size props change
  useEffect(() => {
    page_cache.current = {};
  }, [page_first, page_load, is_random]);

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
        if (is_random && data.total > 0) {
          const tp = Math.ceil(data.total / page_load);
          set_total_pages(Math.max(tp, page));
        } else if (!is_random) {
          // Backend doesn't return total for non-random mode, infer from has_more
          set_total_pages((prev) => {
            if (data.has_more) return Math.max(prev, page + 1);
            return Math.max(prev, page);
          });
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
  }, [load_page]);

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
    if (is_random && has_more && !pages.includes("dots") && pages[pages.length - 1] !== "dots") {
      pages.push("dots");
    }
    return pages;
  };

  if (is_loading && items.length === 0) return <Spinner size="md" />;

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-auto p-4">
        {items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-bg-card border border-border-primary">
              <svg className="h-8 w-8 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
            </div>
            <p className="text-text-muted">没有找到媒体文件</p>
          </div>
        ) : (
          <>
            <div className="grid max-w-[1262px] mx-auto grid-cols-2 sm:grid-cols-3 md:grid-cols-[repeat(auto-fill,minmax(170px,1fr))] gap-3 max-sm:gap-2">
              {items.map((item) => (
                <button
                  key={item.relative_path}
                  onClick={() => open_player(item.relative_path)}
                  className="group relative flex flex-col overflow-hidden rounded-xl bg-bg-card border border-border-primary transition-all hover:border-accent-border hover:shadow-lg hover:-translate-y-0.5 active:scale-[0.98]"
                >
                  <div className="relative aspect-video bg-bg-secondary overflow-hidden">
                    <img
                      src={`/media/thumbnail/${encodeURIComponent(item.relative_path)}`}
                      alt={item.name}
                      loading="lazy"
                      className="h-full w-full object-cover transition duration-300 group-hover:scale-105"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                      }}
                    />
                    {/* Gradient overlay on hover */}
                    <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />

                    {item.is_video && (
                      <div className="absolute inset-0 flex items-center justify-center">
                        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white/15 backdrop-blur text-white transition group-hover:scale-110 group-hover:bg-accent/80">
                          <svg className="h-4 w-4 ml-0.5" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M8 5v14l11-7z" />
                          </svg>
                        </div>
                      </div>
                    )}
                    {item.duration_str && (
                      <span className="absolute bottom-1.5 right-1.5 rounded-md bg-black/70 px-1.5 py-0.5 text-[10px] font-medium text-white backdrop-blur">
                        {item.duration_str}
                      </span>
                    )}
                  </div>
                  <div className="p-2.5">
                    <p className="text-xs font-medium text-text-primary truncate text-left">
                      {item.name}
                    </p>
                    {item.size_str && (
                      <p className="text-[10px] text-text-muted text-left mt-0.5">{item.size_str}</p>
                    )}
                  </div>
                </button>
              ))}
            </div>

            {is_loading && <Spinner size="sm" />}
          </>
        )}
      </div>

      {/* Pagination — show whenever there are items and more than one page worth */}
      {items.length > 0 && (total_pages > 1 || has_more || current_page > 1) && (
        <div className="flex items-center justify-center gap-1.5 border-t border-border-primary bg-bg-secondary/80 backdrop-blur px-4 py-3">
          <button
            onClick={handle_prev}
            disabled={current_page <= 1 || is_loading}
            className="rounded-lg border border-border-primary px-3 py-1.5 text-xs font-medium text-text-secondary transition hover:bg-bg-card-hover hover:text-text-primary disabled:opacity-30 disabled:cursor-not-allowed"
          >
            上一页
          </button>
          <div className="flex items-center gap-0.5">
            {visible_pages().map((p, idx) =>
              p === "dots" ? (
                <span key={`dots-${idx}`} className="px-1 text-text-muted text-xs">...</span>
              ) : (
                <button
                  key={p}
                  onClick={() => load_page(p)}
                  disabled={is_loading}
                  className={`min-w-[32px] rounded-lg px-2 py-1.5 text-xs font-medium transition ${
                    p === current_page
                      ? "bg-accent text-white shadow-sm"
                      : "text-text-secondary hover:bg-bg-card-hover hover:text-text-primary"
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
            className="rounded-lg border border-border-primary px-3 py-1.5 text-xs font-medium text-text-secondary transition hover:bg-bg-card-hover hover:text-text-primary disabled:opacity-30 disabled:cursor-not-allowed"
          >
            下一页
          </button>
        </div>
      )}

      {!has_more && items.length > 0 && !is_loading && (
        <p className="py-3 text-center text-[11px] text-text-muted">已加载全部内容</p>
      )}
    </div>
  );
}

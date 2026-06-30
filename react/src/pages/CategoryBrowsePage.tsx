import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import api_client from "../api/client";

// ─── Types ────────────────────────────────────────────

interface MediaItem {
  name: string;
  relative_path: string;
  is_video: boolean;
  modify_time: number;
  size_str?: string;
  duration_str?: string;
}

interface CategoryInfo {
  folder_name: string;
  folder_path: string;
  parent_path: string;
  categories: CategorySection[];
  root_files: MediaItem[];
  total_categories: number;
  single_leaf_override?: boolean;
}

interface CategorySection {
  name: string;
  path: string;
  files: MediaItem[];
  total_files: number;
  has_more: boolean;
  folder_count?: number;
}

interface GridEntry {
  view: "grid";
  folder_path: string;
  folder_name: string;
  parent_path: string;
  current_page: number;
  page_cache: Record<number, { items: MediaItem[]; has_more: boolean }>;
  page_first: number;
  page_load: number;
}

interface CategoryEntry {
  view: "category";
  data: CategoryInfo;
}

type NavEntry = CategoryEntry | GridEntry;

const STORAGE_KEY = "category_spa_stack";
const RETURNING_KEY = "category_spa_returning";
const MAX_STACK = 60;

// ─── Reusable components ──────────────────────────────

function Spinner() {
  return (
    <div className="flex justify-center py-10">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-accent/20 border-t-accent" />
    </div>
  );
}

function MediaCard({ file, on_click }: { file: MediaItem; on_click: () => void }) {
  return (
    <button
      onClick={on_click}
      className="group relative flex flex-col overflow-hidden rounded-xl bg-bg-card border border-border-primary transition-all hover:border-accent-border hover:shadow-lg hover:-translate-y-0.5 active:scale-[0.98]"
    >
      <div className="relative aspect-video bg-bg-secondary overflow-hidden">
        <img
          src={`/media/thumbnail/${encodeURIComponent(file.relative_path)}`}
          alt={file.name}
          loading="lazy"
          className="h-full w-full object-cover transition duration-300 group-hover:scale-105"
          onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
        {file.is_video && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white/15 backdrop-blur text-white transition group-hover:scale-110 group-hover:bg-accent/80">
              <svg className="h-4 w-4 ml-0.5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z" />
              </svg>
            </div>
          </div>
        )}
      </div>
      <div className="p-2.5">
        <p className="text-xs font-medium text-text-primary truncate text-left">{file.name}</p>
      </div>
    </button>
  );
}

// ─── Component ────────────────────────────────────────

interface ModeConfig {
  page_first: number;
  page_load: number;
}

export default function CategoryBrowsePage() {
  const navigate = useNavigate();

  const [nav_stack, set_nav_stack] = useState<NavEntry[]>([]);
  const [current_index, set_current_index] = useState(-1);
  const [is_loading, set_is_loading] = useState(false);
  const [mode_config, set_mode_config] = useState<ModeConfig>({ page_first: 28, page_load: 28 });
  const grid_abort_ref = useRef<AbortController | null>(null);

  const current_entry = nav_stack[current_index] || null;

  // Refs to avoid stale closures in callbacks (eliminates cascade rebuilds)
  const current_index_ref = useRef(current_index);
  useEffect(() => { current_index_ref.current = current_index; }, [current_index]);
  const nav_stack_ref = useRef(nav_stack);
  useEffect(() => { nav_stack_ref.current = nav_stack; }, [nav_stack]);

  // Fetch mode config for page size
  useEffect(() => {
    api_client.get<ModeConfig>("/api/mode")
      .then((resp) => set_mode_config(resp.data))
      .catch(() => {});
  }, []);

  // ── Stack persistence ───────────────────────────────

  const save_stack = useCallback((stack: NavEntry[], index: number) => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ navStack: stack, currentIndex: index }));
  }, []);

  const push_entry = useCallback(
    (entry: NavEntry) => {
      const cur = current_index_ref.current;
      set_nav_stack((prev) => {
        const next = prev.slice(0, cur + 1);
        next.push(entry);
        if (next.length > MAX_STACK) next.shift();
        const new_index = next.length - 1;
        save_stack(next, new_index);
        return next;
      });
      set_current_index((prev) => {
        const new_index = Math.min(prev + 1, MAX_STACK - 1);
        return new_index;
      });
    },
    [save_stack]
  );

  // ── Initialize ───────────────────────────────────────

  useEffect(() => {
    const init = async () => {
      if (sessionStorage.getItem(RETURNING_KEY) === "1") {
        sessionStorage.removeItem(RETURNING_KEY);
        const saved = sessionStorage.getItem(STORAGE_KEY);
        if (saved) {
          try {
            const parsed = JSON.parse(saved);
            set_nav_stack(parsed.navStack);
            set_current_index(parsed.currentIndex);
            return;
          } catch { /* ignore */ }
        }
      }

      set_is_loading(true);
      try {
        const resp = await api_client.get<{ code: number; data: CategoryInfo }>(
          "/category/data",
          { params: { path: "" } }
        );
        if (resp.data.code === 0) {
          const info = resp.data.data;
          if (info.single_leaf_override && info.categories.length === 1) {
            const cat = info.categories[0];
            navigate_to_grid_internal(cat.path, cat.name, info.parent_path || "", false);
            return;
          }
          const entry: CategoryEntry = { view: "category", data: info };
          set_nav_stack([entry]);
          set_current_index(0);
          save_stack([entry], 0);
          window.history.replaceState({ spaIndex: 0 }, "");
        }
      } catch { /* ignore */ }
      finally { set_is_loading(false); }
    };
    init();
  }, []);

  // ── popstate handler ─────────────────────────────────

  useEffect(() => {
    const handle_popstate = (event: PopStateEvent) => {
      if (event.state?.spaIndex !== undefined) {
        set_current_index(event.state.spaIndex);
      }
    };
    window.addEventListener("popstate", handle_popstate);
    return () => window.removeEventListener("popstate", handle_popstate);
  }, []);

  // ── Navigation ───────────────────────────────────────

  const navigate_to_grid_internal = useCallback(
    (folder_path: string, folder_name: string, parent_path: string, push_history: boolean) => {
      const entry: GridEntry = {
        view: "grid",
        folder_path,
        folder_name,
        parent_path,
        current_page: 1,
        page_cache: {},
        page_first: mode_config.page_first,
        page_load: mode_config.page_load,
      };
      const new_index = current_index_ref.current + 1;
      set_nav_stack((prev) => {
        const next = prev.slice(0, new_index);
        next.push(entry);
        if (next.length > MAX_STACK) next.shift();
        return next;
      });
      set_current_index(new_index);
      if (push_history) {
        window.history.pushState({ spaIndex: new_index }, "");
      }
    },
    [mode_config]
  );

  const navigate_to_category = useCallback(
    async (folder_path: string, push_history: boolean) => {
      set_is_loading(true);
      try {
        const resp = await api_client.get<{ code: number; data: CategoryInfo }>(
          "/category/data",
          { params: { path: folder_path } }
        );
        if (resp.data.code !== 0) return;
        const info = resp.data.data;

        if (info.single_leaf_override && info.categories.length === 1) {
          const cat = info.categories[0];
          navigate_to_grid_internal(cat.path, cat.name, info.parent_path || "", push_history);
          return;
        }

        if (info.categories.length === 0 && info.root_files.length > 0) {
          navigate_to_grid_internal(info.folder_path, info.folder_name, info.parent_path, push_history);
          return;
        }

        const entry: CategoryEntry = { view: "category", data: info };
        const new_index = current_index_ref.current + 1;
        set_nav_stack((prev) => {
          const next = prev.slice(0, new_index);
          next.push(entry);
          if (next.length > MAX_STACK) next.shift();
          return next;
        });
        set_current_index(new_index);
        if (push_history) {
          window.history.pushState({ spaIndex: new_index }, "");
        }
        save_stack([...nav_stack_ref.current.slice(0, new_index), entry], new_index);
      } catch { /* ignore */ }
      finally { set_is_loading(false); }
    },
    [save_stack, navigate_to_grid_internal]
  );

  const navigate_to_grid = useCallback(
    (folder_path: string, folder_name: string, parent_path: string) => {
      navigate_to_grid_internal(folder_path, folder_name, parent_path, true);
    },
    [navigate_to_grid_internal]
  );

  const navigate_back = useCallback(() => {
    const cur = current_index_ref.current;
    if (cur <= 0) {
      navigate("/");
      return;
    }
    set_current_index(cur - 1);
    window.history.replaceState({ spaIndex: cur - 1 }, "");
  }, [navigate]);

  const do_refresh = useCallback(async () => {
    if (!current_entry) return;
    set_is_loading(true);
    try {
      if (current_entry.view === "category") {
        const folder_path = current_entry.data.folder_path || "";
        await api_client.get("/category/data", { params: { path: folder_path, refresh: "1" } });
        // Reload by navigating to the same category
        await navigate_to_category(folder_path, false);
      } else {
        const entry = current_entry as GridEntry;
        const resp = await api_client.get<{
          code: number; data: MediaItem[]; has_more: boolean;
        }>("/category/grid_more", {
          params: { path: entry.folder_path, offset: 0, limit: entry.page_first, refresh: "1" },
        });
        if (resp.data.code === 0) {
          entry.page_cache = { 1: { items: resp.data.data, has_more: resp.data.has_more } };
        } else {
          entry.page_cache = {};
        }
        entry.current_page = 1;
        set_nav_stack((prev) => [...prev]);
      }
    } catch { /* ignore */ }
    finally { set_is_loading(false); }
  }, [current_entry, navigate_to_category]);

  // ── Grid operations ──────────────────────────────────

  const grid_load_page = useCallback(
    async (entry: GridEntry, page: number) => {
      if (entry.page_cache[page]) {
        entry.current_page = page;
        set_nav_stack((prev) => [...prev]);
        return;
      }

      grid_abort_ref.current?.abort();
      const controller = new AbortController();
      grid_abort_ref.current = controller;

      const limit = page === 1 ? entry.page_first : entry.page_load;
      const offset = page === 1 ? 0 : entry.page_first + (page - 2) * entry.page_load;

      try {
        const resp = await api_client.get<{
          code: number; data: MediaItem[]; has_more: boolean;
        }>("/category/grid_more", {
          params: { path: entry.folder_path, offset, limit },
          signal: controller.signal,
        });
        if (resp.data.code === 0) {
          entry.page_cache[page] = {
            items: resp.data.data,
            has_more: resp.data.has_more,
          };
          entry.current_page = page;
          set_nav_stack((prev) => [...prev]);
        }
      } catch (err: unknown) {
        if ((err as Error).name === "AbortError" || (err as Error).name === "CanceledError") return;
      }
    },
    []
  );

  useEffect(() => {
    if (current_entry?.view === "grid" && !current_entry.page_cache[current_entry.current_page]) {
      grid_load_page(current_entry, current_entry.current_page);
    }
  }, [current_entry]);

  const grid_change_page = useCallback(
    (page: number) => {
      if (!current_entry || current_entry.view !== "grid") return;
      grid_load_page(current_entry, page);
    },
    [current_entry, grid_load_page]
  );

  const open_media = useCallback(
    (relative_path: string) => {
      sessionStorage.setItem(RETURNING_KEY, "1");
      save_stack(nav_stack_ref.current, current_index_ref.current);
      navigate(`/media/player?path=${encodeURIComponent(relative_path)}`);
    },
    [save_stack]
  );

  // ── Render helpers ───────────────────────────────────

  const can_go_back = current_index > 0;
  const parent_path = current_entry
    ? current_entry.view === "category"
      ? current_entry.data.parent_path
      : current_entry.parent_path
    : "";

  const handle_click = useCallback(
    (event: React.MouseEvent) => {
      const target = event.target as HTMLElement;
      const anchor = target.closest("a");
      if (!anchor) return;
      const href = anchor.getAttribute("href");
      if (!href || href.startsWith("http")) return;

      const spa_nav = anchor.getAttribute("data-spa-nav");
      const spa_path = anchor.getAttribute("data-spa-path");

      if (spa_nav === "back") {
        event.preventDefault();
        navigate_back();
      } else if (spa_nav === "category" && spa_path) {
        event.preventDefault();
        navigate_to_category(spa_path, true);
      }
    },
    [navigate_back, navigate_to_category]
  );

  // ── Loading ──────────────────────────────────────────

  if (is_loading && nav_stack.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent/20 border-t-accent" />
      </div>
    );
  }

  if (!current_entry) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-text-muted">加载失败</p>
      </div>
    );
  }

  // ── Category View ────────────────────────────────────

  if (current_entry.view === "category") {
    const info = current_entry.data;

    return (
      <div className="flex flex-col h-full bg-bg-primary" onClick={handle_click}>
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-border-primary bg-bg-secondary/80 backdrop-blur px-4 py-3">
          {can_go_back && (
            <button
              onClick={navigate_back}
              className="rounded-lg px-3 py-1.5 text-xs font-medium text-text-secondary transition hover:bg-bg-card-hover hover:text-text-primary"
            >
              ← 返回
            </button>
          )}
          <h1 className="text-base font-semibold text-text-primary truncate">
            {info.folder_name}
          </h1>
          <button
            onClick={do_refresh}
            className="ml-auto shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium text-text-muted transition hover:bg-bg-card-hover hover:text-text-primary"
          >
            刷新
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {info.categories.map((cat) => (
            <section key={cat.path} className="mb-1">
              <div className="flex items-center justify-between px-4 py-3">
                <h2 className="text-sm font-semibold text-text-primary truncate">
                  {cat.name}
                  {cat.folder_count !== undefined && (
                    <span className="ml-1.5 text-xs font-normal text-text-muted">
                      ({cat.total_files})
                    </span>
                  )}
                </h2>
                <a
                  href="#"
                  data-spa-nav="category"
                  data-spa-path={cat.path}
                  className="shrink-0 rounded-md bg-accent px-3 py-1 text-xs font-medium text-white transition hover:bg-accent-hover"
                >
                  显示更多
                </a>
              </div>
              <div className="grid max-w-[1262px] mx-auto grid-cols-2 sm:grid-cols-3 md:grid-cols-[repeat(auto-fill,minmax(170px,1fr))] gap-3 max-sm:gap-2">
                {cat.files.slice(0, 10).map((file) => (
                  <MediaCard key={file.relative_path} file={file} on_click={() => open_media(file.relative_path)} />
                ))}
              </div>
            </section>
          ))}

          {/* Root files */}
          {info.root_files.length > 0 && (
            <section className="mb-1">
              <div className="px-4 py-3">
                <h2 className="text-sm font-semibold text-text-primary">
                  根目录文件
                  <span className="ml-1.5 text-xs font-normal text-text-muted">({info.root_files.length})</span>
                </h2>
              </div>
              <div className="grid max-w-[1262px] mx-auto grid-cols-2 sm:grid-cols-3 md:grid-cols-[repeat(auto-fill,minmax(170px,1fr))] gap-3 max-sm:gap-2">
                {info.root_files.map((file) => (
                  <MediaCard key={file.relative_path} file={file} on_click={() => open_media(file.relative_path)} />
                ))}
              </div>
            </section>
          )}

          {info.categories.length === 0 && info.root_files.length === 0 && (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-bg-card border border-border-primary">
                <svg className="h-8 w-8 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                </svg>
              </div>
              <p className="text-text-muted">此目录为空</p>
            </div>
          )}
        </div>
      </div>
    );
  }

  // ── Grid View ────────────────────────────────────────

  const grid_entry = current_entry as GridEntry;
  const grid_page = grid_entry.page_cache[grid_entry.current_page];
  const grid_items = grid_page?.items || [];
  const grid_has_more = grid_page?.has_more ?? true;

  const visible_pages = () => {
    const pages: (number | "dots")[] = [];
    pages.push(1);
    if (grid_entry.current_page > 3) pages.push("dots");
    for (let p = Math.max(2, grid_entry.current_page - 1); p <= grid_entry.current_page + 1; p++) {
      if (p > 1 && grid_page && !grid_has_more && p > grid_entry.current_page) continue;
      pages.push(p);
    }
    if (grid_has_more && grid_entry.current_page < grid_entry.current_page + 2) pages.push("dots");
    return pages;
  };

  return (
    <div className="flex flex-col h-full bg-bg-primary">
      {/* Grid Header */}
      <div className="flex items-center gap-3 border-b border-border-primary bg-bg-secondary/80 backdrop-blur px-4 py-3">
        <button
          onClick={navigate_back}
          className="rounded-lg px-3 py-1.5 text-xs font-medium text-text-secondary transition hover:bg-bg-card-hover hover:text-text-primary"
        >
          ← 返回
        </button>
        <h1 className="text-base font-semibold text-text-primary truncate">
          {grid_entry.folder_name}
        </h1>
        <button
          onClick={do_refresh}
          className="ml-auto shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium text-text-muted transition hover:bg-bg-card-hover hover:text-text-primary"
        >
          刷新
        </button>
      </div>

      {/* Grid Content */}
      <div className="flex-1 overflow-auto p-4">
        {grid_items.length === 0 && !grid_page ? (
          <Spinner />
        ) : grid_items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-bg-card border border-border-primary">
              <svg className="h-8 w-8 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
            </div>
            <p className="text-text-muted">此目录没有媒体文件</p>
          </div>
        ) : (
          <div className="grid max-w-[1262px] mx-auto grid-cols-2 sm:grid-cols-3 md:grid-cols-[repeat(auto-fill,minmax(170px,1fr))] gap-3 max-sm:gap-2">
            {grid_items.map((file) => (
              <MediaCard key={file.relative_path} file={file} on_click={() => open_media(file.relative_path)} />
            ))}
          </div>
        )}
      </div>

      {/* Grid Pagination */}
      {grid_items.length > 0 && (
        <div className="flex items-center justify-center gap-1.5 border-t border-border-primary bg-bg-secondary/80 backdrop-blur px-4 py-3">
          <button
            onClick={() => grid_change_page(grid_entry.current_page - 1)}
            disabled={grid_entry.current_page <= 1}
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
                  onClick={() => grid_change_page(p)}
                  className={`min-w-[32px] rounded-lg px-2 py-1.5 text-xs font-medium transition ${
                    p === grid_entry.current_page
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
            onClick={() => grid_change_page(grid_entry.current_page + 1)}
            disabled={!grid_has_more}
            className="rounded-lg border border-border-primary px-3 py-1.5 text-xs font-medium text-text-secondary transition hover:bg-bg-card-hover hover:text-text-primary disabled:opacity-30 disabled:cursor-not-allowed"
          >
            下一页
          </button>
        </div>
      )}

      {!grid_has_more && grid_items.length > 0 && (
        <p className="py-3 text-center text-[11px] text-text-muted">已加载全部内容</p>
      )}
    </div>
  );
}

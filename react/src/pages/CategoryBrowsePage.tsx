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

// ─── Component ────────────────────────────────────────

export default function CategoryBrowsePage() {
  const navigate = useNavigate();

  const [nav_stack, set_nav_stack] = useState<NavEntry[]>([]);
  const [current_index, set_current_index] = useState(-1);
  const [is_loading, set_is_loading] = useState(false);
  const grid_abort_ref = useRef<AbortController | null>(null);

  const current_entry = nav_stack[current_index] || null;

  // ── Stack persistence ───────────────────────────────

  const save_stack = useCallback((stack: NavEntry[], index: number) => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ navStack: stack, currentIndex: index }));
  }, []);

  const push_entry = useCallback(
    (entry: NavEntry) => {
      set_nav_stack((prev) => {
        const next = prev.slice(0, current_index + 1);
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
    [current_index, save_stack]
  );

  // ── Initialize ───────────────────────────────────────

  useEffect(() => {
    const init = async () => {
      // Returning from player?
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

      // Fresh entry: fetch initial category data
      set_is_loading(true);
      try {
        const resp = await api_client.get<{ code: number; data: CategoryInfo }>(
          "/category/data",
          { params: { path: "" } }
        );
        if (resp.data.code === 0) {
          const info = resp.data.data;
          // Single leaf auto-forward
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
        const new_index = current_index + 1;
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
        save_stack([...nav_stack.slice(0, new_index), entry], new_index);
      } catch { /* ignore */ }
      finally { set_is_loading(false); }
    },
    [current_index, nav_stack, save_stack]
  );

  const navigate_to_grid_internal = useCallback(
    (folder_path: string, folder_name: string, parent_path: string, push_history: boolean) => {
      const entry: GridEntry = {
        view: "grid",
        folder_path,
        folder_name,
        parent_path,
        current_page: 1,
        page_cache: {},
        page_first: 35,
        page_load: 35,
      };
      const new_index = current_index + 1;
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
    [current_index]
  );

  const navigate_to_grid = useCallback(
    (folder_path: string, folder_name: string, parent_path: string) => {
      navigate_to_grid_internal(folder_path, folder_name, parent_path, true);
    },
    [navigate_to_grid_internal]
  );

  const navigate_back = useCallback(() => {
    if (current_index <= 0) {
      navigate("/");
      return;
    }
    set_current_index(current_index - 1);
    window.history.replaceState({ spaIndex: current_index - 1 }, "");
  }, [current_index, navigate]);

  const navigate_forward = useCallback(() => {
    if (current_index < nav_stack.length - 1) {
      set_current_index(current_index + 1);
      window.history.replaceState({ spaIndex: current_index + 1 }, "");
    }
  }, [current_index, nav_stack.length]);

  // ── Grid operations ──────────────────────────────────

  const grid_load_page = useCallback(
    async (entry: GridEntry, page: number) => {
      if (entry.page_cache[page]) return;

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

  // Open media player
  const open_media = useCallback(
    (relative_path: string) => {
      sessionStorage.setItem(RETURNING_KEY, "1");
      save_stack(nav_stack, current_index);
      window.location.href = `/media/player?path=${encodeURIComponent(relative_path)}`;
    },
    [nav_stack, current_index, save_stack]
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
      if (!href || href.startsWith("http")) return; // external link

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
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-300 border-t-indigo-500" />
      </div>
    );
  }

  if (!current_entry) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-zinc-500">加载失败</p>
      </div>
    );
  }

  // ── Category View ────────────────────────────────────

  if (current_entry.view === "category") {
    const info = current_entry.data;

    return (
      <div className="flex flex-col h-full" onClick={handle_click}>
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-950">
          {can_go_back && (
            <button
              onClick={navigate_back}
              className="rounded-lg px-3 py-1.5 text-sm text-zinc-600 transition hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
            >
              ← 返回
            </button>
          )}
          <h1 className="text-base font-semibold text-zinc-800 dark:text-zinc-100 truncate">
            {info.folder_name}
          </h1>
          <a
            href={`/category/browse/${encodeURIComponent(parent_path)}?refresh=1`}
            className="ml-auto shrink-0 rounded-lg px-3 py-1.5 text-sm text-zinc-500 transition hover:bg-zinc-100 dark:hover:bg-zinc-800"
            data-spa-nav="ignore"
          >
            刷新
          </a>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto">
          {info.categories.map((cat) => (
            <section key={cat.path} className="mb-2">
              <div className="flex items-center justify-between px-4 py-2">
                <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-200 truncate">
                  {cat.name}
                  {cat.folder_count !== undefined && (
                    <span className="ml-1 text-xs font-normal text-zinc-400">
                      ({cat.total_files})
                    </span>
                  )}
                </h2>
                {cat.has_more && (
                  <a
                    href="#"
                    data-spa-nav="category"
                    data-spa-path={cat.path}
                    className="shrink-0 text-xs text-indigo-500 hover:underline"
                  >
                    查看更多 →
                  </a>
                )}
              </div>
              <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-2 px-4">
                {cat.files.slice(0, 10).map((file) => (
                  <button
                    key={file.relative_path}
                    onClick={() => open_media(file.relative_path)}
                    className="group relative flex flex-col overflow-hidden rounded-xl bg-white shadow-sm border border-zinc-200/50 transition hover:shadow-md dark:bg-zinc-900 dark:border-zinc-800"
                  >
                    <div className="relative aspect-video bg-zinc-100 dark:bg-zinc-800">
                      <img
                        src={`/media/thumbnail/${encodeURIComponent(file.relative_path)}`}
                        alt={file.name}
                        loading="lazy"
                        className="h-full w-full object-cover"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                      />
                      {file.is_video && (
                        <div className="absolute inset-0 flex items-center justify-center">
                          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-black/50 text-white text-sm transition group-hover:scale-110">
                            ▶
                          </div>
                        </div>
                      )}
                    </div>
                    <div className="p-2">
                      <p className="text-xs text-zinc-700 truncate text-left dark:text-zinc-300">
                        {file.name}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            </section>
          ))}

          {/* Root files */}
          {info.root_files.length > 0 && (
            <section className="mb-2">
              <div className="px-4 py-2">
                <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-200">
                  根目录文件 ({info.root_files.length})
                </h2>
              </div>
              <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-2 px-4">
                {info.root_files.map((file) => (
                  <button
                    key={file.relative_path}
                    onClick={() => open_media(file.relative_path)}
                    className="group relative flex flex-col overflow-hidden rounded-xl bg-white shadow-sm border border-zinc-200/50 transition hover:shadow-md dark:bg-zinc-900 dark:border-zinc-800"
                  >
                    <div className="relative aspect-video bg-zinc-100 dark:bg-zinc-800">
                      <img
                        src={`/media/thumbnail/${encodeURIComponent(file.relative_path)}`}
                        alt={file.name}
                        loading="lazy"
                        className="h-full w-full object-cover"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                      />
                      {file.is_video && (
                        <div className="absolute inset-0 flex items-center justify-center">
                          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-black/50 text-white text-sm transition group-hover:scale-110">
                            ▶
                          </div>
                        </div>
                      )}
                    </div>
                    <div className="p-2">
                      <p className="text-xs text-zinc-700 truncate text-left dark:text-zinc-300">
                        {file.name}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            </section>
          )}

          {info.categories.length === 0 && info.root_files.length === 0 && (
            <div className="flex items-center justify-center py-20">
              <p className="text-zinc-400">此目录为空</p>
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
    <div className="flex flex-col h-full">
      {/* Grid Header */}
      <div className="flex items-center gap-3 border-b border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-950">
        <button
          onClick={navigate_back}
          className="rounded-lg px-3 py-1.5 text-sm text-zinc-600 transition hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
        >
          ← 返回
        </button>
        <h1 className="text-base font-semibold text-zinc-800 dark:text-zinc-100 truncate">
          {grid_entry.folder_name}
        </h1>
        <a
          href={`/category/grid/${encodeURIComponent(grid_entry.folder_path)}?refresh=1`}
          className="ml-auto shrink-0 rounded-lg px-3 py-1.5 text-sm text-zinc-500 transition hover:bg-zinc-100 dark:hover:bg-zinc-800"
        >
          刷新
        </a>
      </div>

      {/* Grid Content */}
      <div className="flex-1 overflow-auto p-4">
        {grid_items.length === 0 && !grid_page ? (
          <div className="flex items-center justify-center py-20">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-300 border-t-indigo-500" />
          </div>
        ) : grid_items.length === 0 ? (
          <div className="flex items-center justify-center py-20">
            <p className="text-zinc-400">此目录没有媒体文件</p>
          </div>
        ) : (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
            {grid_items.map((file) => (
              <button
                key={file.relative_path}
                onClick={() => open_media(file.relative_path)}
                className="group relative flex flex-col overflow-hidden rounded-xl bg-white shadow-sm border border-zinc-200/50 transition hover:shadow-md dark:bg-zinc-900 dark:border-zinc-800"
              >
                <div className="relative aspect-video bg-zinc-100 dark:bg-zinc-800">
                  <img
                    src={`/media/thumbnail/${encodeURIComponent(file.relative_path)}`}
                    alt={file.name}
                    loading="lazy"
                    className="h-full w-full object-cover"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                  />
                  {file.is_video && (
                    <div className="absolute inset-0 flex items-center justify-center">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-black/50 text-white text-sm transition group-hover:scale-110">
                        ▶
                      </div>
                    </div>
                  )}
                </div>
                <div className="p-2">
                  <p className="text-xs text-zinc-700 truncate text-left dark:text-zinc-300">
                    {file.name}
                  </p>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Grid Pagination */}
      {grid_items.length > 0 && (
        <div className="flex items-center justify-center gap-2 border-t border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-950">
          <button
            onClick={() => grid_change_page(grid_entry.current_page - 1)}
            disabled={grid_entry.current_page <= 1}
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
                  onClick={() => grid_change_page(p)}
                  className={`min-w-[32px] rounded-lg px-2 py-1.5 text-sm transition ${
                    p === grid_entry.current_page
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
            onClick={() => grid_change_page(grid_entry.current_page + 1)}
            disabled={!grid_has_more}
            className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm text-zinc-600 transition hover:bg-zinc-100 disabled:opacity-30 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800"
          >
            下一页
          </button>
        </div>
      )}

      {!grid_has_more && grid_items.length > 0 && (
        <p className="py-3 text-center text-xs text-zinc-300 dark:text-zinc-700">已加载全部内容</p>
      )}
    </div>
  );
}

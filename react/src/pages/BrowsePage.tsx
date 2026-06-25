import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import api_client from "../api/client";
import PreviewModal from "../components/browse/PreviewModal";
import SelectionBar from "../components/browse/SelectionBar";

const MAX_HISTORY = 20;
const LOAD_LIMIT = 20;
const INITIAL_LIMIT = 40;

interface FolderItem {
  name: string;
  path: string;
  icon: string;
  mtime: number;
  date: string;
}

interface FileItem {
  name: string;
  path: string;
  icon: string;
  is_video: boolean;
  is_image: boolean;
  is_previewable: boolean;
  is_text_readable: boolean;
  raw_url: string;
  date: string;
  size: string;
}

type ViewMode = "large" | "medium" | "small" | "list";
type SortField = "name" | "date" | "size";
type SortOrder = "asc" | "desc";

const VIEW_CLASS: Record<ViewMode, string> = {
  large: "grid-cols-[repeat(auto-fill,minmax(140px,1fr))]",
  medium: "grid-cols-[repeat(auto-fill,minmax(120px,1fr))]",
  small: "grid-cols-[repeat(auto-fill,minmax(96px,1fr))]",
  list: "",
};

function get_view_label(view: ViewMode): string {
  switch (view) {
    case "large": return "大图标";
    case "medium": return "中图标";
    case "small": return "小图标";
    case "list": return "列表";
  }
}

function get_sort_label(sort: SortField): string {
  switch (sort) {
    case "name": return "名称";
    case "date": return "日期";
    case "size": return "大小";
  }
}

function Spinner() {
  return (
    <div className="flex justify-center py-8">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-accent/20 border-t-accent" />
    </div>
  );
}

function SidebarButton({ active, children, onClick }: { active?: boolean; children: React.ReactNode; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`w-full rounded-lg px-3 py-2 text-left text-sm font-medium transition-all ${
        active
          ? "bg-accent text-white shadow-sm"
          : "text-text-secondary hover:bg-bg-card-hover hover:text-text-primary"
      }`}
    >
      {children}
    </button>
  );
}

export default function BrowsePage() {
  const { "*": dirpath = "" } = useParams<{ "*": string }>();
  const navigate = useNavigate();
  const [search_params] = useSearchParams();
  const decoded_path = useMemo(() => decodeURIComponent(dirpath || ""), [dirpath]);

  const [current_view, set_current_view] = useState<ViewMode>(
    () => (localStorage.getItem("currentView") as ViewMode) || "large"
  );
  const [current_sort, set_current_sort] = useState<SortField>(
    () => (localStorage.getItem("currentSort") as SortField) || "name"
  );
  const [current_order, set_current_order] = useState<SortOrder>(
    () => (localStorage.getItem("currentOrder") as SortOrder) || "asc"
  );

  const [folders, set_folders] = useState<FolderItem[]>([]);
  const [files, set_files] = useState<FileItem[]>([]);
  const [offset, set_offset] = useState(0);
  const [has_more, set_has_more] = useState(true);
  const [is_loading, set_is_loading] = useState(true);
  const [folders_loaded, set_folders_loaded] = useState(false);
  const [error, set_error] = useState<string | null>(null);

  const [sidebar_open, set_sidebar_open] = useState(
    () => localStorage.getItem("sidebarOpen") === "true"
  );

  const [selection_mode, set_selection_mode] = useState(false);
  const [selected_paths, set_selected_paths] = useState<Set<string>>(new Set());

  const [preview, set_preview] = useState<{
    url: string; name: string; is_video: boolean; download_url: string;
  } | null>(null);

  const abort_ref = useRef<AbortController | null>(null);
  const sentinel_ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => { localStorage.setItem("currentView", current_view); }, [current_view]);
  useEffect(() => { localStorage.setItem("currentSort", current_sort); }, [current_sort]);
  useEffect(() => { localStorage.setItem("currentOrder", current_order); }, [current_order]);
  useEffect(() => { localStorage.setItem("sidebarOpen", String(sidebar_open)); }, [sidebar_open]);

  // History management
  useEffect(() => {
    const history: string[] = JSON.parse(localStorage.getItem("fileHistory") || "[]");
    const last = history[history.length - 1];
    if (last !== decoded_path) {
      history.push(decoded_path);
      if (history.length > MAX_HISTORY) history.shift();
      localStorage.setItem("fileHistory", JSON.stringify(history));
    }
  }, [decoded_path]);

  // Reset and load on path/sort/order change
  useEffect(() => {
    let cancelled = false;
    abort_ref.current?.abort();
    const controller = new AbortController();
    abort_ref.current = controller;

    set_offset(0);
    set_has_more(true);
    set_folders_loaded(false);
    set_is_loading(true);
    set_error(null);
    set_folders([]);
    set_files([]);

    const load = async () => {
      const signal = controller.signal;
      try {
        const folder_resp = await api_client.get<FolderItem[]>("/api/list", {
          params: { path: decoded_path, type: "folders", sort: current_sort, order: current_order },
          signal,
        });
        if (!cancelled) {
          set_folders(folder_resp.data);
          set_folders_loaded(true);
        }
      } catch (err: unknown) {
        if ((err as Error).name === "CanceledError" || (err as Error).name === "AbortError") return;
        if (!cancelled) {
          set_error("文件夹加载失败");
          set_is_loading(false);
        }
        return;
      }

      try {
        const file_resp = await api_client.get<{ items: FileItem[]; has_more: boolean }>("/api/list", {
          params: { path: decoded_path, type: "files", sort: current_sort, order: current_order, offset: 0, limit: INITIAL_LIMIT },
          signal,
        });
        if (!cancelled) {
          set_files(file_resp.data.items);
          set_offset(INITIAL_LIMIT);
          set_has_more(file_resp.data.has_more);
          set_is_loading(false);
        }
      } catch (err: unknown) {
        if ((err as Error).name === "CanceledError" || (err as Error).name === "AbortError") return;
        if (!cancelled) {
          set_error("文件加载失败");
          set_is_loading(false);
        }
      }
    };

    load();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [decoded_path, current_sort, current_order]);

  // Handle refresh param
  useEffect(() => {
    if (search_params.get("refresh") === "1") {
      const new_params = new URLSearchParams(search_params);
      new_params.delete("refresh");
      navigate(`/browse/${dirpath}${new_params.toString() ? "?" + new_params.toString() : ""}`, { replace: true });
    }
  }, []);

  // Infinite scroll via IntersectionObserver
  useEffect(() => {
    if (!sentinel_ref.current || !has_more || is_loading) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && has_more && !is_loading) {
          load_more_files();
        }
      },
      { rootMargin: "300px" }
    );
    observer.observe(sentinel_ref.current);
    return () => observer.disconnect();
  }, [has_more, is_loading, decoded_path, current_sort, current_order, offset]);

  const load_more_files = useCallback(async () => {
    if (is_loading || !has_more) return;
    set_is_loading(true);
    try {
      const resp = await api_client.get<{ items: FileItem[]; has_more: boolean }>("/api/list", {
        params: { path: decoded_path, type: "files", sort: current_sort, order: current_order, offset, limit: LOAD_LIMIT },
        signal: abort_ref.current?.signal,
      });
      set_files((prev) => [...prev, ...resp.data.items]);
      set_offset((prev) => prev + LOAD_LIMIT);
      set_has_more(resp.data.has_more);
    } catch (err: unknown) {
      if ((err as Error).name === "CanceledError" || (err as Error).name === "AbortError") return;
    } finally {
      set_is_loading(false);
    }
  }, [is_loading, has_more, decoded_path, current_sort, current_order, offset]);

  // Navigation
  const handle_folder_click = useCallback((path: string) => {
    navigate(`/browse/${encodeURIComponent(path)}`);
  }, [navigate]);

  const handle_go_back = useCallback(async () => {
    const history: string[] = JSON.parse(localStorage.getItem("fileHistory") || "[]");
    // Remove current path
    history.pop();
    localStorage.setItem("fileHistory", JSON.stringify(history));

    while (history.length > 0) {
      const candidate = history.pop()!;
      try {
        const resp = await api_client.get<{ exists: boolean; is_dir: boolean }>("/api/check_path", {
          params: { path: candidate },
        });
        if (resp.data.exists && resp.data.is_dir) {
          // Persist trimmed history before navigating so the effect won't push duplicates
          localStorage.setItem("fileHistory", JSON.stringify(history));
          navigate(`/browse/${encodeURIComponent(candidate)}`);
          return;
        }
      } catch { /* try next */ }
    }
    localStorage.removeItem("fileHistory");
    navigate("/");
  }, [navigate]);

  const handle_go_home = useCallback(() => navigate("/"), [navigate]);

  const handle_refresh = useCallback(() => {
    navigate(`/browse/${dirpath}?refresh=1`);
  }, [navigate, dirpath]);

  const cycle_view = useCallback(() => {
    const views: ViewMode[] = ["large", "medium", "small", "list"];
    const idx = views.indexOf(current_view);
    set_current_view(views[(idx + 1) % views.length]);
  }, [current_view]);

  const cycle_sort = useCallback(() => {
    const sorts: SortField[] = ["name", "date", "size"];
    const idx = sorts.indexOf(current_sort);
    set_current_sort(sorts[(idx + 1) % sorts.length]);
  }, [current_sort]);

  const toggle_order = useCallback(() => {
    set_current_order((prev) => (prev === "asc" ? "desc" : "asc"));
  }, []);

  // Selection
  const toggle_selection_mode = useCallback(() => {
    set_selection_mode((prev) => !prev);
    set_selected_paths(new Set());
  }, []);

  const toggle_select_item = useCallback((path: string) => {
    set_selected_paths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  const select_all = useCallback(async () => {
    try {
      const resp = await api_client.get<{ path: string; name: string; is_dir: boolean }[]>("/api/list_all", {
        params: { path: decoded_path },
      });
      const paths = new Set(resp.data.map((item) => item.path));
      set_selected_paths(paths);
    } catch { /* ignore */ }
  }, [decoded_path]);

  const download_merge = useCallback(async () => {
    if (selected_paths.size === 0) return;
    try {
      const resp = await api_client.post(
        "/file/download_selected",
        { base: decoded_path, paths: Array.from(selected_paths) },
        { responseType: "blob" }
      );
      const url = URL.createObjectURL(resp.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "selected.zip";
      a.click();
      URL.revokeObjectURL(url);
    } catch { /* ignore */ }
  }, [selected_paths, decoded_path]);

  const download_separate = useCallback(() => {
    if (selected_paths.size === 0) return;
    const paths = Array.from(selected_paths);
    paths.forEach((path, index) => {
      setTimeout(() => {
        const a = document.createElement("a");
        a.href = `/file/view/${encodeURIComponent(path)}`;
        a.download = "";
        a.click();
      }, index * 500);
    });
  }, [selected_paths]);

  // Preview
  const open_preview = useCallback((url: string, name: string, is_video: boolean, download_url: string) => {
    set_preview({ url, name, is_video, download_url });
  }, []);

  const close_preview = useCallback(() => set_preview(null), []);

  // Breadcrumb segments
  const breadcrumbs = useMemo(() => {
    if (!decoded_path) return [];
    const parts = decoded_path.replace(/\\/g, "/").split("/").filter(Boolean);
    const segments: { label: string; path: string }[] = [];
    let accum = "";
    for (const part of parts) {
      accum = accum ? `${accum}/${part}` : part;
      segments.push({ label: part, path: accum });
    }
    return segments;
  }, [decoded_path]);

  const is_grid = current_view !== "list";
  const is_empty = !is_loading && folders.length === 0 && files.length === 0;

  const selected_class = (path: string) =>
    selected_paths.has(path)
      ? "ring-2 ring-accent bg-accent-subtle"
      : "";

  return (
    <div className="flex h-[calc(100vh-0px)] flex-col bg-bg-primary">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-border-primary bg-bg-secondary/80 backdrop-blur px-4 py-2">
        <div className="flex items-center gap-2 min-w-0">
          <button
            onClick={() => set_sidebar_open((prev) => !prev)}
            className="shrink-0 rounded-lg p-2 text-text-muted transition hover:bg-bg-card-hover hover:text-text-primary"
            title="侧边栏"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <button
            onClick={handle_go_home}
            className="shrink-0 text-sm font-semibold text-text-primary transition hover:text-accent"
          >
            LaptopWatch
          </button>
          <span className="text-text-muted">/</span>
          <nav className="flex items-center gap-0.5 overflow-x-auto text-sm whitespace-nowrap">
            {breadcrumbs.map((segment, index) => (
              <span key={segment.path} className="flex items-center gap-0.5">
                {index > 0 && <span className="text-text-muted">/</span>}
                <button
                  onClick={() => handle_folder_click(segment.path)}
                  className="rounded-md px-1.5 py-0.5 text-text-muted transition hover:bg-bg-card-hover hover:text-text-primary"
                >
                  {segment.label}
                </button>
              </span>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={handle_go_back}
            className="rounded-lg px-3 py-1.5 text-xs font-medium text-text-secondary transition hover:bg-bg-card-hover hover:text-text-primary"
          >
            返回
          </button>
          <button
            onClick={handle_refresh}
            className="rounded-lg px-3 py-1.5 text-xs font-medium text-text-secondary transition hover:bg-bg-card-hover hover:text-text-primary"
          >
            刷新
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar overlay */}
        {sidebar_open && (
          <div
            className="fixed inset-0 z-20 bg-black/50 backdrop-blur-sm lg:hidden"
            onClick={() => set_sidebar_open(false)}
          />
        )}

        {/* Sidebar */}
        <aside
          className={`${
            sidebar_open ? "translate-x-0" : "-translate-x-full"
          } fixed left-0 top-[49px] bottom-0 z-30 w-64 border-r border-border-primary bg-bg-secondary/95 backdrop-blur p-4 transition-transform lg:static lg:translate-x-0`}
        >
          <div className="flex flex-col gap-4">
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wider text-text-muted">视图模式</label>
              <div className="mt-1.5">
                <SidebarButton onClick={cycle_view}>{get_view_label(current_view)}</SidebarButton>
              </div>
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wider text-text-muted">排序方式</label>
              <div className="mt-1.5">
                <SidebarButton onClick={cycle_sort}>{get_sort_label(current_sort)}</SidebarButton>
              </div>
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wider text-text-muted">排序方向</label>
              <div className="mt-1.5">
                <SidebarButton onClick={toggle_order}>
                  {current_order === "asc" ? "升序 ↑" : "降序 ↓"}
                </SidebarButton>
              </div>
            </div>
            <hr className="border-border-primary" />
            <button
              onClick={toggle_selection_mode}
              className={`w-full rounded-lg px-3 py-2 text-sm font-medium transition-all ${
                selection_mode
                  ? "bg-accent text-white shadow-sm"
                  : "text-text-secondary hover:bg-bg-card-hover hover:text-text-primary"
              }`}
            >
              {selection_mode ? "退出选择模式" : "选择模式"}
            </button>
            {selection_mode && (
              <button
                onClick={select_all}
                className="w-full rounded-lg px-3 py-2 text-sm font-medium text-text-secondary transition hover:bg-bg-card-hover hover:text-text-primary"
              >
                全选
              </button>
            )}
          </div>
        </aside>

        {/* Main Content */}
        <div className="flex-1 overflow-auto">
          {error && (
            <div className="p-4">
              <p className="rounded-lg bg-danger/10 border border-danger/20 px-4 py-3 text-sm text-danger">
                {error}
              </p>
            </div>
          )}

          {is_empty && (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-bg-card border border-border-primary">
                <svg className="h-8 w-8 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                </svg>
              </div>
              <p className="text-text-muted">此文件夹为空</p>
            </div>
          )}

          {/* Folders */}
          {folders.length > 0 && (
            <div className="p-3">
              {is_grid ? (
                <div className={`grid ${VIEW_CLASS[current_view]} gap-2`}>
                  {folders.map((folder) => (
                    <button
                      key={folder.path}
                      onClick={() => {
                        if (selection_mode) toggle_select_item(folder.path);
                        else handle_folder_click(folder.path);
                      }}
                      className={`flex flex-col items-center rounded-xl p-4 text-center transition-all hover:bg-bg-card-hover active:scale-[0.98] ${selected_class(folder.path)}`}
                    >
                      {selection_mode && (
                        <input
                          type="checkbox"
                          checked={selected_paths.has(folder.path)}
                          onChange={() => toggle_select_item(folder.path)}
                          className="mb-1.5 accent-accent"
                          onClick={(e) => e.stopPropagation()}
                        />
                      )}
                      <span className="text-3xl mb-2">📁</span>
                      <span className="text-xs font-medium text-text-primary break-all line-clamp-2">
                        {folder.name}
                      </span>
                    </button>
                  ))}
                </div>
              ) : (
                <div>
                  {folders.map((folder) => (
                    <div
                      key={folder.path}
                      onClick={() => {
                        if (selection_mode) toggle_select_item(folder.path);
                        else handle_folder_click(folder.path);
                      }}
                      className={`flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 transition-all hover:bg-bg-card-hover ${selected_class(folder.path)}`}
                    >
                      {selection_mode && (
                        <input
                          type="checkbox"
                          checked={selected_paths.has(folder.path)}
                          onChange={() => toggle_select_item(folder.path)}
                          className="accent-accent"
                          onClick={(e) => e.stopPropagation()}
                        />
                      )}
                      <span className="text-xl">📁</span>
                      <span className="flex-1 text-sm font-medium text-text-primary truncate">{folder.name}</span>
                      <span className="text-xs text-text-muted">{folder.date}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Files - Grid */}
          {files.length > 0 && is_grid && (
            <div className="px-3 pb-3">
              <div className={`grid ${VIEW_CLASS[current_view]} gap-2`}>
                {files.map((file) => (
                  <button
                    key={file.path}
                    onClick={() => {
                      if (selection_mode) {
                        toggle_select_item(file.path);
                      } else if (file.is_previewable) {
                        const media_url = `/media/serve_media/${encodeURIComponent(file.path)}`;
                        const download_url = `/media/download_media/${encodeURIComponent(file.path)}`;
                        open_preview(media_url, file.name, file.is_video, download_url);
                      } else if (file.is_text_readable) {
                        navigate(`/file/text/${encodeURIComponent(file.path)}`);
                      } else {
                        window.open(`/file/raw/${encodeURIComponent(file.path)}`, "_blank");
                      }
                    }}
                    className={`relative flex flex-col items-center rounded-xl p-3 text-center transition-all hover:bg-bg-card-hover active:scale-[0.98] ${selected_class(file.path)}`}
                  >
                    {selection_mode && (
                      <input
                        type="checkbox"
                        checked={selected_paths.has(file.path)}
                        onChange={() => toggle_select_item(file.path)}
                        className="mb-1 accent-accent"
                        onClick={(e) => e.stopPropagation()}
                      />
                    )}
                    <span className="text-3xl mb-1">{file.icon}</span>
                    {file.is_video && (
                      <span className="absolute top-2 right-2 flex h-5 w-5 items-center justify-center rounded-full bg-accent/80 text-[10px] text-white">
                        ▶
                      </span>
                    )}
                    <span className="text-xs font-medium text-text-primary break-all line-clamp-2">
                      {file.name}
                    </span>
                    <span className="text-[10px] text-text-muted mt-0.5">{file.date}</span>
                    <span className="text-[10px] text-text-muted">{file.size}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Files - List */}
          {files.length > 0 && !is_grid && (
            <div className="pb-3">
              <div className="flex items-center gap-3 border-b border-border-primary px-4 py-2 text-[11px] font-medium uppercase tracking-wider text-text-muted">
                {selection_mode && <span className="w-5 shrink-0" />}
                <span className="w-8 shrink-0" />
                <span className="flex-1">名称</span>
                <span className="w-36 shrink-0">日期</span>
                <span className="w-20 shrink-0 text-right">大小</span>
              </div>
              {files.map((file) => (
                <div
                  key={file.path}
                  onClick={() => {
                    if (selection_mode) {
                      toggle_select_item(file.path);
                    } else if (file.is_previewable) {
                      const media_url = `/media/serve_media/${encodeURIComponent(file.path)}`;
                      const download_url = `/media/download_media/${encodeURIComponent(file.path)}`;
                      open_preview(media_url, file.name, file.is_video, download_url);
                    } else if (file.is_text_readable) {
                      navigate(`/file/text/${encodeURIComponent(file.path)}`);
                    } else {
                      window.open(`/file/raw/${encodeURIComponent(file.path)}`, "_blank");
                    }
                  }}
                  className={`flex cursor-pointer items-center gap-3 border-b border-border-primary/50 px-4 py-2.5 transition-all hover:bg-bg-card-hover ${selected_class(file.path)}`}
                >
                  {selection_mode && (
                    <input
                      type="checkbox"
                      checked={selected_paths.has(file.path)}
                      onChange={() => toggle_select_item(file.path)}
                      onClick={(e) => e.stopPropagation()}
                      className="w-5 shrink-0 accent-accent"
                    />
                  )}
                  <span className="w-8 shrink-0 text-xl text-center">{file.icon}</span>
                  <span className="flex-1 truncate text-sm font-medium text-text-primary">{file.name}</span>
                  <span className="w-36 shrink-0 text-xs text-text-muted">{file.date}</span>
                  <span className="w-20 shrink-0 text-right text-xs text-text-muted">{file.size}</span>
                </div>
              ))}
            </div>
          )}

          <div ref={sentinel_ref} className="h-1" />

          {is_loading && <Spinner />}

          {!has_more && files.length > 0 && (
            <p className="py-6 text-center text-[11px] text-text-muted">已加载全部内容</p>
          )}
        </div>
      </div>

      {/* Selection bar */}
      {selection_mode && (
        <SelectionBar
          count={selected_paths.size}
          on_download_merge={download_merge}
          on_download_separate={download_separate}
          on_cancel={toggle_selection_mode}
        />
      )}

      {/* Preview modal */}
      {preview && (
        <PreviewModal
          url={preview.url}
          name={preview.name}
          is_video={preview.is_video}
          download_url={preview.download_url}
          on_close={close_preview}
        />
      )}
    </div>
  );
}

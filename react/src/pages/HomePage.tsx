import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api_client from "../api/client";
import MediaGrid from "../components/MediaGrid";
import CategoryBrowsePage from "./CategoryBrowsePage";

interface ModeConfig {
  run_mode: string;
  category_browse: boolean;
  random_mode: boolean;
  page_first: number;
  page_load: number;
}

function Spinner() {
  return (
    <div className="flex flex-1 items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent/20 border-t-accent" />
    </div>
  );
}

function Header({ label, count }: { label: string; count?: number }) {
  return (
    <header className="flex items-center justify-between border-b border-border-primary bg-bg-secondary/80 backdrop-blur px-5 py-3">
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-subtle border border-accent-border">
          <svg className="h-4 w-4 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
        </div>
        <span className="text-base font-semibold tracking-tight text-text-primary">
          LaptopWatch
        </span>
        <span className="rounded-full bg-accent-subtle px-2.5 py-0.5 text-[11px] font-medium text-accent border border-accent-border">
          {label}
        </span>
      </div>
      {count !== undefined && (
        <span className="text-xs text-text-muted">{count} 个磁盘</span>
      )}
    </header>
  );
}

export default function HomePage() {
  const [drives, set_drives] = useState<string[]>([]);
  const [mode_config, set_mode_config] = useState<ModeConfig | null>(null);
  const [is_loading, set_is_loading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      api_client.get<ModeConfig>("/api/mode"),
      api_client.get<{ drives: string[] }>("/api/drives").catch(() => ({ data: { drives: [] } })),
    ])
      .then(([mode_resp, drives_resp]) => {
        if (!cancelled) {
          set_mode_config(mode_resp.data);
          set_drives(drives_resp.data.drives);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) set_is_loading(false);
      });

    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    localStorage.setItem("currentView", localStorage.getItem("currentView") || "large");
    localStorage.setItem("currentSort", localStorage.getItem("currentSort") || "name");
    localStorage.setItem("currentOrder", localStorage.getItem("currentOrder") || "asc");
  }, []);

  const handle_drive_click = useCallback(
    (drive: string) => navigate(`/browse/${drive}:/`),
    [navigate]
  );

  if (is_loading) return <Spinner />;

  if (!mode_config) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-text-muted">加载失败</p>
      </div>
    );
  }

  // Media modes: video, image, or douyin
  if (["video", "image", "douyin"].includes(mode_config.run_mode)) {
    if (mode_config.category_browse) {
      return <CategoryBrowsePage />;
    }
    if (mode_config.run_mode === "douyin") {
      return (
        <div className="flex flex-1 items-center justify-center">
          <p className="text-text-muted">抖音模式 - 即将实现</p>
        </div>
      );
    }
    const mode_label = mode_config.run_mode === "video" ? "视频模式" : "图片模式";
    return (
      <div className="flex flex-col h-full">
        <Header label={mode_label} />
        <MediaGrid
          page_first={mode_config.page_first}
          page_load={mode_config.page_load}
          is_random={mode_config.random_mode}
        />
      </div>
    );
  }

  // Normal mode: drive grid
  return (
    <div className="flex flex-col h-full">
      <Header label="普通模式" count={drives.length} />

      <div className="flex-1 max-w-[1000px] mx-auto w-full p-6">
        {drives.length === 0 ? (
          <div className="flex flex-col items-center justify-center mt-20 gap-3">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-bg-card border border-border-primary">
              <svg className="h-8 w-8 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
              </svg>
            </div>
            <p className="text-text-muted">未检测到可用磁盘</p>
          </div>
        ) : (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-4 max-sm:grid-cols-[repeat(auto-fill,minmax(120px,1fr))] max-sm:gap-3">
            {drives.map((drive) => (
              <button
                key={drive}
                onClick={() => handle_drive_click(drive)}
                className="group flex flex-col items-center justify-center rounded-2xl bg-bg-card p-6 text-center border border-border-primary transition-all hover:border-accent-border hover:bg-bg-card-hover hover:shadow-lg hover:-translate-y-0.5 active:scale-[0.98]"
              >
                <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-accent-subtle border border-accent-border transition group-hover:scale-105">
                  <span className="text-2xl font-bold text-accent">
                    {drive}
                  </span>
                </div>
                <span className="text-sm font-semibold text-text-primary">
                  {drive} 盘
                </span>
                <span className="mt-1 text-[11px] text-text-muted">本地磁盘</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

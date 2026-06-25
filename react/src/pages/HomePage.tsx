import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api_client from "../api/client";

interface Drive {
  letter: string;
}

export default function HomePage() {
  const [drives, set_drives] = useState<string[]>([]);
  const [is_loading, set_is_loading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    api_client
      .get<{ drives: string[] }>("/api/drives")
      .then((response) => {
        if (!cancelled) set_drives(response.data.drives);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) set_is_loading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    localStorage.setItem("currentView", localStorage.getItem("currentView") || "large");
    localStorage.setItem("currentSort", localStorage.getItem("currentSort") || "name");
    localStorage.setItem("currentOrder", localStorage.getItem("currentOrder") || "asc");
  }, []);

  const handle_drive_click = useCallback(
    (drive: string) => {
      navigate(`/browse/${drive}:/`);
    },
    [navigate]
  );

  if (is_loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-300 border-t-indigo-500" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <header className="flex items-center justify-between border-b border-zinc-200 bg-white px-5 py-3 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex items-center gap-3">
          <span className="text-base font-bold tracking-tight text-zinc-800 dark:text-zinc-100">
            LaptopWatch
          </span>
          <span className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-[11px] font-medium text-indigo-600 border border-indigo-200/50 dark:bg-indigo-500/10 dark:text-indigo-400 dark:border-indigo-500/20">
            普通模式
          </span>
        </div>
        <span className="text-xs text-zinc-400">{drives.length} 个磁盘</span>
      </header>

      <div className="flex-1 max-w-[1000px] mx-auto w-full p-5">
        {drives.length === 0 ? (
          <p className="text-center text-zinc-400 mt-20">未检测到可用磁盘</p>
        ) : (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-3 max-sm:grid-cols-[repeat(auto-fill,minmax(110px,1fr))] max-sm:gap-2">
            {drives.map((drive) => (
              <button
                key={drive}
                onClick={() => handle_drive_click(drive)}
                className="flex flex-col items-center justify-center rounded-xl bg-white p-5 text-center shadow-sm border border-zinc-200/50 transition hover:shadow-md hover:border-indigo-200 dark:bg-zinc-900 dark:border-zinc-800 dark:hover:border-indigo-800 min-h-[140px] cursor-pointer"
              >
                <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-indigo-50 dark:bg-indigo-500/10">
                  <span className="text-2xl font-bold text-indigo-600 dark:text-indigo-400">
                    {drive}
                  </span>
                </div>
                <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">
                  {drive} 盘
                </span>
                <span className="mt-1 text-[11px] text-zinc-400">本地磁盘</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

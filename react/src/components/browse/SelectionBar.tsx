interface SelectionBarProps {
  count: number;
  on_download_merge: () => void;
  on_download_separate: () => void;
  on_cancel: () => void;
}

export default function SelectionBar({
  count,
  on_download_merge,
  on_download_separate,
  on_cancel,
}: SelectionBarProps) {
  return (
    <div className="fixed bottom-0 left-0 right-0 z-40 flex items-center justify-between border-t border-zinc-200 bg-white px-5 py-3 shadow-lg dark:border-zinc-800 dark:bg-zinc-900">
      <span className="text-sm text-zinc-600 dark:text-zinc-400">
        已选择 <strong className="text-indigo-600 dark:text-indigo-400">{count}</strong> 项
      </span>
      <div className="flex items-center gap-2">
        <button
          onClick={on_download_merge}
          disabled={count === 0}
          className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-600 disabled:opacity-50"
        >
          合并下载
        </button>
        <button
          onClick={on_download_separate}
          disabled={count === 0}
          className="rounded-lg border border-zinc-300 px-4 py-2 text-sm text-zinc-600 transition hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800"
        >
          分别下载
        </button>
        <button
          onClick={on_cancel}
          className="rounded-lg border border-zinc-300 px-4 py-2 text-sm text-zinc-600 transition hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800"
        >
          取消
        </button>
      </div>
    </div>
  );
}

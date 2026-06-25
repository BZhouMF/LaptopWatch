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
    <div className="fixed bottom-0 left-0 right-0 z-40 flex items-center justify-between border-t border-border-primary bg-bg-secondary/95 backdrop-blur px-5 py-3 shadow-lg">
      <span className="text-sm text-text-secondary">
        已选择 <strong className="text-accent">{count}</strong> 项
      </span>
      <div className="flex items-center gap-2">
        <button
          onClick={on_download_merge}
          disabled={count === 0}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition hover:bg-accent-hover hover:shadow-lg hover:shadow-accent/20 disabled:opacity-50 active:scale-[0.98]"
        >
          合并下载
        </button>
        <button
          onClick={on_download_separate}
          disabled={count === 0}
          className="rounded-lg border border-border-primary px-4 py-2 text-sm font-medium text-text-secondary transition hover:bg-bg-card-hover hover:text-text-primary disabled:opacity-50"
        >
          分别下载
        </button>
        <button
          onClick={on_cancel}
          className="rounded-lg border border-border-primary px-4 py-2 text-sm font-medium text-text-secondary transition hover:bg-bg-card-hover hover:text-text-primary"
        >
          取消
        </button>
      </div>
    </div>
  );
}

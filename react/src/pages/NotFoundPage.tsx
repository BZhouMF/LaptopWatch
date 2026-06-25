import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";

export default function NotFoundPage() {
  const [seconds, set_seconds] = useState(3);
  const navigate = useNavigate();
  const interval_ref = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    interval_ref.current = setInterval(() => {
      set_seconds((prev) => {
        if (prev <= 1) {
          if (interval_ref.current) clearInterval(interval_ref.current);
          const referrer = document.referrer;
          if (referrer) {
            try {
              const url = new URL(referrer, window.location.origin);
              url.searchParams.set("refresh", "1");
              window.location.href = url.toString();
              return 0;
            } catch {
              // fall through
            }
          }
          navigate("/", { replace: true });
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (interval_ref.current) clearInterval(interval_ref.current);
    };
  }, [navigate]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg-primary p-5">
      <div className="w-full max-w-sm card rounded-xl p-10 text-center">
        <div className="mb-5 text-5xl text-danger">&#x2716;</div>
        <h2 className="mb-2 text-2xl font-bold text-danger">路径不存在</h2>
        <p className="mb-8 text-base text-text-muted">
          您访问的文件夹可能已被删除或移动
        </p>
        <p className="text-sm text-text-muted">
          {seconds > 0 ? `${seconds} 秒后自动返回上一页...` : "正在跳转..."}
        </p>
      </div>
    </div>
  );
}

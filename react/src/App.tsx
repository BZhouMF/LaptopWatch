import { useEffect, useRef } from "react";
import AppRouter from "./router";
import api_client from "./api/client";

export default function App() {
  const versionRef = useRef<number | null>(null);

  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const resp = await api_client.get<{
          version: number;
          service_active: boolean;
        }>("/api/config-version");
        const { version } = resp.data;

        if (versionRef.current === null) {
          versionRef.current = version;
          return;
        }

        if (version !== versionRef.current) {
          // Don't interrupt video playback — defer the reload
          const active_video = document.querySelector("video");
          if (active_video && !active_video.paused) {
            // Video is playing; accept the new version but defer navigation
            versionRef.current = version;
            return;
          }
          window.location.href = "/";
        }
      } catch {
        // 503 or network error — service not active yet, silently wait
      }
    }, 15000);

    return () => clearInterval(interval);
  }, []);

  return <AppRouter />;
}

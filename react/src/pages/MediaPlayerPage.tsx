import { useState, useEffect, useCallback, useRef, useMemo, type JSX } from "react";
import { useSearchParams } from "react-router-dom";
import api_client from "../api/client";
import { usePlayerGestures, type GestureCallbacks } from "../hooks/usePlayerGestures";

// ═══════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════

interface MediaData {
  relative_path: string;
  name: string;
  is_video: boolean;
}

interface DouyinConfig {
  autoPlay: boolean;
  muted: boolean;
  nativeFullscreen: boolean;
  mode: string;
}

type PlayerStatus = "loading" | "playing" | "paused" | "ended" | "error";

const SPEED_OPTIONS = [2, 1.75, 1.5, 1.25, 1, 0.75];
const PLAY_ICON = "M8 5v14l11-7z";
const PAUSE_ICON = "M6 19h4V5H6v14zm8-14v14h4V5h-4z";

function format_time(seconds: number): string {
  if (isNaN(seconds) || !isFinite(seconds)) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s < 10 ? "0" : ""}${s}`;
}

// ═══════════════════════════════════════════════════════
// Component
// ═══════════════════════════════════════════════════════

export default function MediaPlayerPage(): JSX.Element {
  const [search_params] = useSearchParams();

  // ── Mode ──────────────────────────────────────────
  const config_ref = useRef<DouyinConfig>(
    (window as unknown as Record<string, unknown>).DOUYIN_CONFIG as DouyinConfig || {
      autoPlay: false, muted: false, nativeFullscreen: false, mode: "douyin",
    }
  );
  const mode = config_ref.current.mode;
  const is_grid = mode === "grid";
  const auto_play = !is_grid && config_ref.current.autoPlay;

  // ── Refs ───────────────────────────────────────────
  const container_ref = useRef<HTMLDivElement>(null);
  const video_a_ref = useRef<HTMLVideoElement>(null);
  const video_b_ref = useRef<HTMLVideoElement>(null);
  const image_ref = useRef<HTMLImageElement>(null);
  const progress_ref = useRef<HTMLDivElement>(null);
  const controls_timer_ref = useRef<ReturnType<typeof setTimeout> | null>(null);
  const safety_timer_ref = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abort_ref = useRef<AbortController | null>(null);
  const seek_base_ref = useRef(0);
  const is_fullscreen_ref = useRef(false);
  const indicator_timer_ref = useRef<ReturnType<typeof setTimeout> | null>(null);

  // State proxy refs (for event handlers to avoid stale closures)
  const state_ref = useRef({
    is_transitioning: false,
    is_dragging: false,
    selected_speed: 1,
  });

  // ── Player state ───────────────────────────────────
  const [status, set_status] = useState<PlayerStatus>("loading");
  const [error_msg, set_error_msg] = useState("");
  const [current_media, set_current_media] = useState<MediaData | null>(null);
  const [current_time, set_current_time] = useState(0);
  const [duration, set_duration] = useState(0);
  const [is_playing, set_is_playing] = useState(false);
  const [is_muted, set_is_muted] = useState(config_ref.current.muted);
  const [selected_speed, set_selected_speed] = useState(1);
  const [controls_visible, set_controls_visible] = useState(true);
  const [settings_open, set_settings_open] = useState(false);
  const [speed_menu_open, set_speed_menu_open] = useState(false);
  const [is_fullscreen, set_is_fullscreen] = useState(false);
  const [speed_active, set_speed_active] = useState(false);
  const [seek_indicator, set_seek_indicator] = useState<{ active: boolean; time: string }>({ active: false, time: "" });
  const [vol_indicator, set_vol_indicator] = useState<{ active: boolean; pct: number }>({ active: false, pct: 100 });
  const [bright_indicator, set_bright_indicator] = useState<{ active: boolean; pct: number }>({ active: false, pct: 100 });

  // Dual-buffer control: always read from refs, use state only for rendering triggers
  const [active_buffer, set_active_buffer] = useState<"A" | "B">("A");
  const [slide_anim, set_slide_anim] = useState<{ direction: "next" | "prev"; active: boolean } | null>(null);
  const [video_a_src, set_video_a_src] = useState("");
  const [video_b_src, set_video_b_src] = useState("");
  const [show_video, set_show_video] = useState(true);

  // Douyin state
  const [play_history, set_play_history] = useState<MediaData[]>([]);
  const [history_index, set_history_index] = useState(-1);
  const preload_index_ref = useRef(-1);

  // Grid state
  const grid_path_ref = useRef("");
  const grid_is_video_ref = useRef(true);

  // ── Helper: get active/inactive video refs ──────────
  const get_active_video = useCallback(() =>
    active_buffer === "A" ? video_a_ref.current : video_b_ref.current,
  [active_buffer]);
  const get_inactive_video = useCallback(() =>
    active_buffer === "A" ? video_b_ref.current : video_a_ref.current,
  [active_buffer]);

  // ── Controls timer ──────────────────────────────────
  const reset_controls_timer = useCallback(() => {
    if (controls_timer_ref.current) clearTimeout(controls_timer_ref.current);
    controls_timer_ref.current = setTimeout(() => {
      set_controls_visible(false);
      set_settings_open(false);
      set_speed_menu_open(false);
    }, 5000);
  }, []);

  const show_controls = useCallback(() => {
    set_controls_visible(true);
    reset_controls_timer();
  }, [reset_controls_timer]);

  // ── Progress / seek ────────────────────────────────
  const update_progress = useCallback(() => {
    const video = get_active_video();
    if (!video || !video.duration) return;
    set_current_time(video.currentTime);
    set_duration(video.duration);
  }, [get_active_video]);

  const seek_to = useCallback((client_x: number) => {
    const video = get_active_video();
    if (!video || !progress_ref.current) return;
    const rect = progress_ref.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(client_x - rect.left, rect.width));
    const pct = x / rect.width;
    video.currentTime = pct * video.duration;
    update_progress();
  }, [get_active_video, update_progress]);

  // ── Fullscreen ──────────────────────────────────────
  const update_fullscreen_state = useCallback(() => {
    const fs = !!(document.fullscreenElement || (document as unknown as { webkitFullscreenElement?: Element }).webkitFullscreenElement);
    set_is_fullscreen(fs);
  }, []);

  const toggle_fullscreen = useCallback(() => {
    const fs_el = document.fullscreenElement || (document as unknown as { webkitFullscreenElement?: Element }).webkitFullscreenElement;
    if (fs_el) {
      if (document.exitFullscreen) document.exitFullscreen();
      else if ((document as unknown as { webkitExitFullscreen?: () => void }).webkitExitFullscreen)
        (document as unknown as { webkitExitFullscreen: () => void }).webkitExitFullscreen();
      return;
    }
    const video = get_active_video() as HTMLVideoElement & {
      webkitEnterFullscreen?: () => void;
      webkitSetPresentationMode?: (mode: string) => void;
    };
    // iOS path
    if (video?.webkitEnterFullscreen) {
      video.webkitEnterFullscreen();
      update_fullscreen_state();
      return;
    }
    if (video?.webkitSetPresentationMode) {
      video.webkitSetPresentationMode("fullscreen");
      update_fullscreen_state();
      return;
    }
    // Container fullscreen
    const el = container_ref.current;
    if (el) {
      const promise = el.requestFullscreen ? el.requestFullscreen() :
        (el as HTMLElement & { webkitRequestFullscreen?: () => Promise<void> }).webkitRequestFullscreen?.();
      promise?.catch(() => {});
    }
  }, [get_active_video, update_fullscreen_state]);

  // ── Video switching ─────────────────────────────────
  const finish_video_switch = useCallback(() => {
    if (safety_timer_ref.current) {
      clearTimeout(safety_timer_ref.current);
      safety_timer_ref.current = null;
    }
    set_slide_anim(null);
    const inactive = get_inactive_video();
    const active = get_active_video();
    if (inactive) {
      inactive.style.transition = "";
      inactive.style.transform = "";
    }
    if (active) {
      active.pause();
      active.style.transition = "";
      active.style.transform = "";
    }
    set_active_buffer((prev) => (prev === "A" ? "B" : "A"));
    // Clear old buffer source after swap
    setTimeout(() => {
      if (active_buffer === "A") set_video_b_src("");
      else set_video_a_src("");
    }, 200);
    state_ref.current.is_transitioning = false;
  }, [get_active_video, get_inactive_video, active_buffer]);

  const animate_slide_in = useCallback((direction: "next" | "prev") => {
    if (state_ref.current.is_transitioning) return;
    state_ref.current.is_transitioning = true;
    // Mute active video during transition
    const active = get_active_video();
    if (active) active.muted = true;

    set_slide_anim({ direction, active: true });

    if (safety_timer_ref.current) clearTimeout(safety_timer_ref.current);
    safety_timer_ref.current = setTimeout(() => {
      const active_v = get_active_video();
      const inactive_v = get_inactive_video();
      if (active_v) {
        active_v.style.transition = "";
        active_v.style.transform = "";
      }
      if (inactive_v) {
        inactive_v.style.transition = "";
        inactive_v.style.transform = "";
      }
      set_active_buffer((prev) => (prev === "A" ? "B" : "A"));
      const now_active = active_buffer === "A" ? video_b_ref.current : video_a_ref.current;
      if (now_active) {
        now_active.muted = is_muted;
        now_active.playbackRate = selected_speed;
        now_active.play().catch(() => {});
      }
      set_slide_anim(null);
      state_ref.current.is_transitioning = false;
      set_is_playing(true);
    }, 1500);
  }, [get_active_video, get_inactive_video, active_buffer, is_muted, selected_speed]);

  const play_media = useCallback((media: MediaData, direction: "next" | "prev" | null) => {
    if (state_ref.current.is_transitioning) return;
    set_current_media(media);
    set_status("loading");
    set_error_msg("");

    if (!media.is_video) {
      set_show_video(false);
      set_status("playing");
      return;
    }

    set_show_video(true);
    const url = `/media/serve_media/${encodeURIComponent(media.relative_path)}`;

    if (!direction) {
      // First load: set active buffer directly
      if (active_buffer === "A") set_video_a_src(url);
      else set_video_b_src(url);
      return;
    }

    // Transition: load into inactive buffer
    state_ref.current.is_transitioning = true;
    if (active_buffer === "A") set_video_b_src(url);
    else set_video_a_src(url);

    // Wait for canplay then animate
    const handle_canplay = () => {
      const inactive = get_inactive_video();
      if (inactive) {
        inactive.removeEventListener("canplay", handle_canplay);
        inactive.muted = is_muted;
        inactive.playbackRate = selected_speed;
      }
      animate_slide_in(direction);
    };

    // Safety timeout
    const timer = setTimeout(() => {
      const inactive = get_inactive_video();
      if (inactive) inactive.removeEventListener("canplay", handle_canplay);
      if (state_ref.current.is_transitioning) animate_slide_in(direction);
    }, 600);

    const inactive = get_inactive_video();
    if (inactive) {
      inactive.addEventListener("canplay", () => {
        clearTimeout(timer);
        handle_canplay();
      }, { once: true });
    }
  }, [active_buffer, get_inactive_video, is_muted, selected_speed, animate_slide_in]);

  // ── Video events setup ──────────────────────────────
  const setup_video_events = useCallback((video: HTMLVideoElement) => {
    const on_loaded = () => { set_duration(video.duration); set_current_time(0); };
    const on_time = () => {
      if (!state_ref.current.is_dragging) {
        set_current_time(video.currentTime);
        set_duration(video.duration);
      }
    };
    const on_play = () => { set_is_playing(true); show_controls(); };
    const on_pause = () => { set_is_playing(false); show_controls(); };
    const on_waiting = () => { if (!video.paused) set_status("loading"); };
    const on_canplay = () => { set_status("playing"); set_is_playing(!video.paused); };
    const on_ended = () => {
      if (auto_play) {
        handle_nav_next();
      } else {
        video.currentTime = 0;
        video.play().catch(() => {});
      }
    };
    const on_err = () => {
      set_status("error");
      set_error_msg("视频加载失败");
      state_ref.current.is_transitioning = false;
      set_slide_anim(null);
    };

    video.addEventListener("loadedmetadata", on_loaded);
    video.addEventListener("timeupdate", on_time);
    video.addEventListener("play", on_play);
    video.addEventListener("pause", on_pause);
    video.addEventListener("waiting", on_waiting);
    video.addEventListener("canplay", on_canplay);
    video.addEventListener("ended", on_ended);
    video.addEventListener("error", on_err);

    return () => {
      video.removeEventListener("loadedmetadata", on_loaded);
      video.removeEventListener("timeupdate", on_time);
      video.removeEventListener("play", on_play);
      video.removeEventListener("pause", on_pause);
      video.removeEventListener("waiting", on_waiting);
      video.removeEventListener("canplay", on_canplay);
      video.removeEventListener("ended", on_ended);
      video.removeEventListener("error", on_err);
    };
  }, [auto_play, show_controls]);

  // Attach events to both video elements
  useEffect(() => {
    const cleanups: (() => void)[] = [];
    if (video_a_ref.current) cleanups.push(setup_video_events(video_a_ref.current));
    if (video_b_ref.current) cleanups.push(setup_video_events(video_b_ref.current));
    return () => cleanups.forEach((fn) => fn());
  }, [setup_video_events]);

  // ── Fullscreen change listener ──────────────────────
  useEffect(() => {
    const handler = () => update_fullscreen_state();
    document.addEventListener("fullscreenchange", handler);
    document.addEventListener("webkitfullscreenchange", handler);
    return () => {
      document.removeEventListener("fullscreenchange", handler);
      document.removeEventListener("webkitfullscreenchange", handler);
    };
  }, [update_fullscreen_state]);

  useEffect(() => { is_fullscreen_ref.current = is_fullscreen; }, [is_fullscreen]);

  // ── Navigation ──────────────────────────────────────
  const handle_nav_next = useCallback(() => {
    if (state_ref.current.is_transitioning || status === "loading") return;

    if (is_grid) {
      navigate_grid("next");
    } else {
      // Douyin mode
      if (history_index < play_history.length - 1) {
        const next_idx = history_index + 1;
        set_history_index(next_idx);
        set_status("ended");
        play_media(play_history[next_idx], "next");
      } else {
        fetch_douyin_next();
      }
    }
  }, [is_grid, status, history_index, play_history, play_media]);

  const handle_nav_prev = useCallback(() => {
    if (state_ref.current.is_transitioning || status === "loading") return;

    if (is_grid) {
      navigate_grid("prev");
    } else {
      if (history_index > 0) {
        const prev_idx = history_index - 1;
        set_history_index(prev_idx);
        play_media(play_history[prev_idx], "prev");
      }
    }
  }, [is_grid, status, history_index, play_history, play_media]);

  // ── Grid navigation ─────────────────────────────────
  const navigate_grid = useCallback(async (direction: "next" | "prev") => {
    if (!grid_path_ref.current) return;
    set_status("loading");
    try {
      const resp = await api_client.get<{ code: number; data: MediaData }>("/media/navigate", {
        params: { current_path: grid_path_ref.current, direction },
      });
      if (resp.data.code === 0 && resp.data.data) {
        const data = resp.data.data;
        grid_path_ref.current = data.relative_path;
        grid_is_video_ref.current = data.is_video;
        if (data.is_video) {
          set_show_video(true);
          play_media(data, direction);
        } else {
          set_show_video(false);
          set_current_media(data);
          set_status("playing");
        }
      } else if (resp.data.code === 2) {
        set_status("error");
        set_error_msg(direction === "next" ? "没有更多了" : "已经是第一个了");
        setTimeout(() => set_error_msg(""), 3000);
      }
    } catch {
      set_status("error");
      set_error_msg("导航失败");
      setTimeout(() => set_error_msg(""), 3000);
    } finally {
      if (status === "loading") set_status("playing");
    }
  }, [play_media, status]);

  // ── Douyin API ──────────────────────────────────────
  const fetch_douyin_init = useCallback(async () => {
    set_status("loading");
    try {
      const resp = await api_client.get<{ code: number; data: MediaData }>("/api/douyin/init", { timeout: 8000 });
      if (resp.data.code === 0 && resp.data.data) {
        set_play_history([resp.data.data]);
        set_history_index(0);
        play_media(resp.data.data, null);
        return;
      }
    } catch { /* fallback to next */ }
    fetch_douyin_next();
  }, [play_media]);

  const fetch_douyin_next = useCallback(async () => {
    if (state_ref.current.is_transitioning) return;
    set_status("loading");
    try {
      const resp = await api_client.get<{ code: number; data: MediaData; msg?: string }>("/api/douyin/next", { timeout: 8000 });
      if (resp.data.code === 0 && resp.data.data) {
        set_play_history((prev) => {
          const next = prev.slice(0, history_index + 1);
          next.push(resp.data.data);
          if (next.length > 100) next.shift();
          return next;
        });
        const new_idx = Math.min(history_index + 1, play_history.length);
        set_history_index(new_idx);
        play_media(resp.data.data, "next");
      } else if (resp.data.code === 2) {
        set_status("ended");
        set_error_msg("没有更多视频了");
      } else {
        set_status("error");
        set_error_msg(resp.data.msg || "获取失败");
      }
    } catch {
      set_status("error");
      set_error_msg("网络错误");
    }
  }, [history_index, play_history.length, play_media]);

  // ── Initialize ──────────────────────────────────────
  useEffect(() => {
    if (is_grid) {
      const path = search_params.get("path") || "";
      grid_path_ref.current = path;
      if (!path) {
        set_status("error");
        set_error_msg("未指定文件路径");
        return;
      }
      // Determine if video by extension
      const ext = path.split(".").pop()?.toLowerCase() || "";
      const is_vid = ["mp4", "avi", "mkv", "mov", "wmv", "flv", "webm", "m4v", "3gp"].includes(ext);
      grid_is_video_ref.current = is_vid;
      set_show_video(is_vid);
      const media: MediaData = {
        relative_path: path,
        name: decodeURIComponent(path.split("/").pop() || path),
        is_video: is_vid,
      };
      set_current_media(media);
      if (is_vid) {
        play_media(media, null);
      } else {
        set_status("playing");
      }
    } else {
      fetch_douyin_init();
    }
    show_controls();
  }, []);

  // ── Preload next (douyin mode) ──────────────────────
  const preload_next = useCallback(async () => {
    if (is_grid || state_ref.current.is_transitioning) return;
    const next_idx = history_index + 1;
    if (next_idx < play_history.length) {
      preload_index_ref.current = next_idx;
      const url = `/media/serve_media/${encodeURIComponent(play_history[next_idx].relative_path)}`;
      if (active_buffer === "A") set_video_b_src(url);
      else set_video_a_src(url);
      return;
    }
    try {
      const resp = await api_client.get<{ code: number; data: MediaData }>("/api/douyin/next");
      if (resp.data.code === 0 && resp.data.data) {
        set_play_history((prev) => [...prev, resp.data.data]);
        preload_index_ref.current = play_history.length;
        const url = `/media/serve_media/${encodeURIComponent(resp.data.data.relative_path)}`;
        if (active_buffer === "A") set_video_b_src(url);
        else set_video_a_src(url);
      }
    } catch { /* ignore */ }
  }, [is_grid, history_index, play_history, active_buffer]);

  useEffect(() => { if (!is_grid) preload_next(); }, [history_index, play_history.length]);

  // ── Actions ─────────────────────────────────────────
  const toggle_play = useCallback(() => {
    const video = get_active_video();
    if (!video) return;
    if (video.paused) video.play().catch(() => {});
    else video.pause();
  }, [get_active_video]);

  const set_speed = useCallback((speed: number) => {
    set_selected_speed(speed);
    state_ref.current.selected_speed = speed;
    const av = get_active_video();
    const iv = get_inactive_video();
    if (av) av.playbackRate = speed;
    if (iv) iv.playbackRate = speed;
    set_speed_menu_open(false);
    set_settings_open(false);
  }, [get_active_video, get_inactive_video]);

  const toggle_mute = useCallback(() => {
    set_is_muted((prev) => {
      const next = !prev;
      const av = get_active_video();
      const iv = get_inactive_video();
      if (av) av.muted = next;
      if (iv) iv.muted = next;
      return next;
    });
  }, [get_active_video, get_inactive_video]);

  const skip_time = useCallback((delta: number) => {
    const video = get_active_video();
    if (!video) return;
    video.currentTime = Math.max(0, Math.min(video.currentTime + delta, video.duration || 0));
    update_progress();
  }, [get_active_video, update_progress]);

  // ── Gesture system ─────────────────────────────────
  const gesture_callbacks = useMemo<GestureCallbacks>(() => ({
    on_swipe_next: handle_nav_next,
    on_swipe_prev: handle_nav_prev,
    on_toggle_play: toggle_play,
    on_toggle_controls: () => {
      set_controls_visible((prev) => { if (!prev) reset_controls_timer(); return !prev; });
    },
    on_seek: (seconds: number) => {
      const video = get_active_video();
      if (!video) return;
      const target = Math.max(0, Math.min(seek_base_ref.current + seconds, video.duration || 0));
      video.currentTime = target;
      set_current_time(target);
      set_seek_indicator({ active: true, time: format_time(target) });
    },
    on_seek_start: () => {
      seek_base_ref.current = get_active_video()?.currentTime || 0;
    },
    on_seek_end: () => {
      if (indicator_timer_ref.current) clearTimeout(indicator_timer_ref.current);
      indicator_timer_ref.current = setTimeout(() => set_seek_indicator({ active: false, time: "" }), 600);
    },
    on_adjust_volume: (delta: number) => {
      const video = get_active_video();
      if (!video) return;
      const new_vol = Math.max(0, Math.min(1, video.volume + delta));
      video.volume = new_vol;
      set_vol_indicator({ active: true, pct: Math.round(new_vol * 100) });
    },
    on_adjust_brightness: (delta: number) => {
      set_bright_indicator((prev) => {
        const cur_pct = prev.pct;
        const new_pct = Math.max(10, Math.min(100, cur_pct + Math.round(delta * 100)));
        return { active: true, pct: new_pct };
      });
    },
    on_adjust_end: () => {
      if (indicator_timer_ref.current) clearTimeout(indicator_timer_ref.current);
      indicator_timer_ref.current = setTimeout(() => {
        set_vol_indicator({ active: false, pct: 100 });
        set_bright_indicator({ active: false, pct: 100 });
      }, 800);
    },
    on_long_press_start: () => {
      set_speed_active(true);
      const av = get_active_video();
      if (av) av.playbackRate = 3;
    },
    on_long_press_end: () => {
      set_speed_active(false);
      const av = get_active_video();
      if (av) av.playbackRate = selected_speed;
    },
    is_fullscreen: () => is_fullscreen_ref.current,
    is_video_active: () => show_video && !!(current_media?.is_video),
  }), [handle_nav_next, handle_nav_prev, toggle_play, reset_controls_timer, get_active_video, selected_speed, show_video, current_media?.is_video]);

  const gesture = usePlayerGestures(gesture_callbacks);

  // ── Progress bar drag ───────────────────────────────
  const handle_progress_pointer_down = useCallback((event: React.PointerEvent) => {
    state_ref.current.is_dragging = true;
    (state_ref.current as unknown as { seek_base: number }).seek_base = get_active_video()?.currentTime || 0;
    seek_to(event.clientX);
    event.preventDefault();
  }, [seek_to, get_active_video]);

  const handle_progress_pointer_move = useCallback((event: React.PointerEvent) => {
    if (!state_ref.current.is_dragging) return;
    seek_to(event.clientX);
  }, [seek_to]);

  const handle_progress_pointer_up = useCallback(() => {
    state_ref.current.is_dragging = false;
  }, []);

  // ── Keyboard ────────────────────────────────────────
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "ArrowUp" || event.key === "ArrowLeft") { event.preventDefault(); handle_nav_prev(); }
      else if (event.key === "ArrowDown" || event.key === "ArrowRight") { event.preventDefault(); handle_nav_next(); }
      else if (event.key === " ") { event.preventDefault(); toggle_play(); }
      else if (event.key === "f" || event.key === "F") toggle_fullscreen();
      else if (event.key === "m" || event.key === "M") toggle_mute();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [handle_nav_next, handle_nav_prev, toggle_play, toggle_fullscreen, toggle_mute]);

  // ── Render helpers ──────────────────────────────────
  const progress_pct = duration > 0 ? (current_time / duration) * 100 : 0;

  const render_video_element = (ref: React.RefObject<HTMLVideoElement | null>, src: string, z_index: number, transform: string, transition: string) => (
    <video
      ref={ref}
      src={src}
      muted={is_muted}
      playsInline
      preload="auto"
      className="absolute inset-0 w-full h-full object-contain bg-black"
      style={{ zIndex: z_index, transform, transition }}
    />
  );

  // ── Slide animation CSS ─────────────────────────────
  const slide_a_style: React.CSSProperties = {};
  const slide_b_style: React.CSSProperties = {};

  if (slide_anim?.active) {
    const is_a_active = active_buffer === "A";
    const from_y = slide_anim.direction === "next" ? "translateY(100%)" : "translateY(-100%)";
    const out_y = slide_anim.direction === "next" ? "translateY(-100%)" : "translateY(100%)";
    const trans = "transform 0.35s cubic-bezier(0.25, 0.46, 0.45, 0.94)";

    if (is_a_active) {
      slide_a_style.transform = out_y;
      slide_a_style.transition = trans;
      slide_a_style.zIndex = 1;
      slide_b_style.transform = from_y;
      slide_b_style.transition = "none";
      slide_b_style.zIndex = 2;
      // Trigger reflow then animate
      setTimeout(() => {
        if (video_b_ref.current) {
          video_b_ref.current.style.transition = trans;
          video_b_ref.current.style.transform = "translateY(0)";
        }
      }, 16);
    } else {
      slide_b_style.transform = out_y;
      slide_b_style.transition = trans;
      slide_b_style.zIndex = 1;
      slide_a_style.transform = from_y;
      slide_a_style.transition = "none";
      slide_a_style.zIndex = 2;
      setTimeout(() => {
        if (video_a_ref.current) {
          video_a_ref.current.style.transition = trans;
          video_a_ref.current.style.transform = "translateY(0)";
        }
      }, 16);
    }
  } else {
    if (active_buffer === "A") {
      slide_a_style.zIndex = 2;
      slide_b_style.zIndex = 1;
    } else {
      slide_b_style.zIndex = 2;
      slide_a_style.zIndex = 1;
    }
    const inactive_src = active_buffer === "A" ? video_b_src : video_a_src;
    if (inactive_src) {
      if (active_buffer === "A") slide_b_style.transform = "translateY(100%)";
      else slide_a_style.transform = "translateY(100%)";
    }
  }

  return (
    <div
      ref={container_ref}
      className="relative h-screen w-screen overflow-hidden bg-black select-none touch-none"
      onTouchStart={gesture.handle_touch_start}
      onTouchMove={gesture.handle_touch_move}
      onTouchEnd={gesture.handle_touch_end}
      onClick={gesture.handle_click}
      onMouseDown={gesture.handle_mouse_down}
      onMouseUp={gesture.handle_mouse_up}
      onWheel={gesture.handle_wheel}
    >
      {/* ─── Video / Image Display ─────────────────── */}
      {show_video ? (
        <div className="absolute inset-0">
          {render_video_element(video_a_ref, video_a_src, slide_a_style.zIndex ?? 1, slide_a_style.transform || "", slide_a_style.transition || "")}
          {render_video_element(video_b_ref, video_b_src, slide_b_style.zIndex ?? 1, slide_b_style.transform || "", slide_b_style.transition || "")}
        </div>
      ) : (
        <img
          ref={image_ref}
          src={current_media ? `/media/serve_media/${encodeURIComponent(current_media.relative_path)}` : ""}
          alt={current_media?.name || ""}
          className="absolute inset-0 w-full h-full object-contain"
        />
      )}

      {/* ─── Brightness overlay ────────────────────── */}
      {bright_indicator.active && (
        <div
          className="pointer-events-none absolute inset-0 bg-black transition-opacity"
          style={{ opacity: 1 - bright_indicator.pct / 100 }}
        />
      )}

      {/* ─── Loading / Error / End ──────────────────── */}
      {status === "loading" && (
        <div className="absolute inset-0 flex items-center justify-center z-10">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-white/30 border-t-white" />
        </div>
      )}
      {status === "ended" && (
        <div className="absolute inset-0 flex items-center justify-center z-10">
          <p className="text-white/70 text-lg">没有更多视频了</p>
        </div>
      )}
      {error_msg && (
        <div className="absolute top-16 left-1/2 -translate-x-1/2 z-20 rounded-lg bg-red-500/80 px-4 py-2 text-sm text-white">
          {error_msg}
        </div>
      )}

      {/* ─── Top Bar ────────────────────────────────── */}
      {controls_visible && (
        <div className="player-controls-area absolute top-0 left-0 right-0 z-20 flex items-center gap-3 bg-gradient-to-b from-black/60 to-transparent px-4 py-3">
          <button
            onClick={() => window.history.back()}
            className="rounded-lg px-3 py-1.5 text-sm text-white/80 transition hover:text-white"
          >
            ← 返回
          </button>
          <span className="truncate text-sm text-white/80">{current_media?.name || ""}</span>
          <div className="ml-auto flex items-center gap-2">
            {is_grid && (
              <>
                <button onClick={handle_nav_prev} className="rounded-full p-2 text-white/80 transition hover:text-white">
                  <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                  </svg>
                </button>
                <button onClick={handle_nav_next} className="rounded-full p-2 text-white/80 transition hover:text-white">
                  <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* ─── Center: Skip buttons + Play/Pause ──────── */}
      {controls_visible && show_video && (
        <div className="player-controls-area absolute inset-0 z-10 flex items-center justify-center pointer-events-none">
          <div className="flex items-center gap-8 pointer-events-auto">
            <button onClick={() => skip_time(-15)} className="rounded-full bg-white/15 p-3 text-white/80 transition hover:bg-white/25">
              <svg className="h-6 w-6" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/>
              </svg>
              <span className="block text-[10px] mt-0.5">15</span>
            </button>
            <button onClick={toggle_play} className="rounded-full bg-white/15 p-4 text-white transition hover:bg-white/25">
              <svg className="h-8 w-8" fill="currentColor" viewBox="0 0 24 24">
                {show_video ? (is_playing ? <path d={PAUSE_ICON}/> : <path d={PLAY_ICON}/>) : <path d={PLAY_ICON}/>}
              </svg>
            </button>
            <button onClick={() => skip_time(15)} className="rounded-full bg-white/15 p-3 text-white/80 transition hover:bg-white/25">
              <svg className="h-6 w-6 rotate-180" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/>
              </svg>
              <span className="block text-[10px] mt-0.5">15</span>
            </button>
          </div>
        </div>
      )}

      {/* ─── Bottom Controls ────────────────────────── */}
      {controls_visible && show_video && (
        <div className="player-controls-area absolute bottom-0 left-0 right-0 z-20 bg-gradient-to-t from-black/60 to-transparent px-4 pb-3 pt-8">
          {/* Progress bar */}
          <div
            ref={progress_ref}
            className="relative h-8 cursor-pointer flex items-center -mx-2 px-2"
            onPointerDown={handle_progress_pointer_down}
            onPointerMove={handle_progress_pointer_move}
            onPointerUp={handle_progress_pointer_up}
          >
            <div className="w-full h-1 rounded-full bg-white/20">
              <div className="h-full rounded-full bg-indigo-400 relative" style={{ width: `${progress_pct}%` }}>
                <div className="absolute right-0 top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white shadow" />
              </div>
            </div>
          </div>

          {/* Controls row */}
          <div className="flex items-center gap-3 mt-1">
            <button onClick={toggle_play} className="text-white/80 hover:text-white">
              <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
                {is_playing ? <path d={PAUSE_ICON}/> : <path d={PLAY_ICON}/>}
              </svg>
            </button>
            <span className="text-xs text-white/60 tabular-nums min-w-[90px]">
              {format_time(current_time)} / {format_time(duration)}
            </span>
            <div className="flex-1" />
            {/* Settings: mute + speed */}
            <div className="relative">
              <button
                onClick={() => { set_settings_open((prev) => !prev); set_speed_menu_open(false); }}
                className="text-white/80 hover:text-white text-sm"
              >
                设置
              </button>
              {settings_open && (
                <div className="absolute bottom-full right-0 mb-2 rounded-lg bg-zinc-900/95 py-1 shadow-xl backdrop-blur min-w-[120px]">
                  <button
                    onClick={() => { toggle_mute(); set_settings_open(false); }}
                    className="flex w-full items-center gap-2 px-4 py-2 text-sm text-white/80 hover:bg-white/10"
                  >
                    {is_muted ? "🔇 取消静音" : "🔊 静音"}
                  </button>
                  <div className="relative">
                    <button
                      onClick={() => set_speed_menu_open((prev) => !prev)}
                      className="flex w-full items-center justify-between px-4 py-2 text-sm text-white/80 hover:bg-white/10"
                    >
                      倍速 <span>{selected_speed.toFixed(2)}x</span>
                    </button>
                    {speed_menu_open && (
                      <div className="absolute right-full bottom-0 mr-1 rounded-lg bg-zinc-900/95 py-1 shadow-xl backdrop-blur">
                        {SPEED_OPTIONS.map((speed) => (
                          <button
                            key={speed}
                            onClick={() => set_speed(speed)}
                            className={`block w-full px-4 py-2 text-left text-sm whitespace-nowrap ${
                              selected_speed === speed ? "text-indigo-400" : "text-white/80 hover:bg-white/10"
                            }`}
                          >
                            {speed.toFixed(2)}x
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
            <button onClick={toggle_fullscreen} className="text-white/80 hover:text-white ml-1">
              <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
                {is_fullscreen ? (
                  <path d="M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z"/>
                ) : (
                  <path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/>
                )}
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* ─── Indicators ─────────────────────────────── */}
      {speed_active && (
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-30 rounded-lg bg-black/70 px-4 py-2 text-lg font-bold text-white">
          3x
        </div>
      )}
      {seek_indicator.active && (
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-30 rounded-lg bg-black/70 px-4 py-2 text-white">
          {seek_indicator.time}
        </div>
      )}
      {vol_indicator.active && (
        <div className="absolute right-6 top-1/2 -translate-y-1/2 z-30 flex flex-col items-center gap-1">
          <div className="h-32 w-2 rounded-full bg-white/20 overflow-hidden">
            <div className="w-full bg-white rounded-full transition-all" style={{ height: `${vol_indicator.pct}%`, marginTop: `${100 - vol_indicator.pct}%` }} />
          </div>
          <span className="text-xs text-white/80">{vol_indicator.pct}%</span>
        </div>
      )}
      {bright_indicator.active && (
        <div className="absolute left-6 top-1/2 -translate-y-1/2 z-30 flex flex-col items-center gap-1">
          <div className="h-32 w-2 rounded-full bg-white/20 overflow-hidden">
            <div className="w-full bg-white rounded-full transition-all" style={{ height: `${bright_indicator.pct}%`, marginTop: `${100 - bright_indicator.pct}%` }} />
          </div>
          <span className="text-xs text-white/80">{bright_indicator.pct}%</span>
        </div>
      )}
    </div>
  );
}

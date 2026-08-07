import { useState, useEffect, useCallback, useRef, useMemo, type JSX } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
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
  const navigate = useNavigate();

  // ── Mode ──────────────────────────────────────────
  // Grid mode: a specific file path was provided via ?path= (from BrowsePage / CategoryBrowsePage)
  // Douyin mode: no path — fetch from API feed (only works when server is in douyin mode)
  const grid_path_param = search_params.get("path") || "";
  const is_grid = !!grid_path_param;

  // ── Refs ───────────────────────────────────────────
  const container_ref = useRef<HTMLDivElement>(null);
  const video_a_ref = useRef<HTMLVideoElement>(null);
  const video_b_ref = useRef<HTMLVideoElement>(null);
  const image_ref = useRef<HTMLImageElement>(null);
  const progress_ref = useRef<HTMLDivElement>(null);
  const controls_timer_ref = useRef<ReturnType<typeof setTimeout> | null>(null);
  const safety_timer_ref = useRef<ReturnType<typeof setTimeout> | null>(null);
  const transition_timer_ref = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abort_ref = useRef<AbortController | null>(null);
  const seek_base_ref = useRef(0);
  const is_fullscreen_ref = useRef(false);
  const indicator_timer_ref = useRef<ReturnType<typeof setTimeout> | null>(null);
  const preload_pending_ref = useRef(false);
  const is_fetching_ref = useRef(false);

  // State proxy refs (for event handlers to avoid stale closures)
  const state_ref = useRef({
    is_transitioning: false,
    is_dragging: false,
    selected_speed: 1,
  });

  // Buffer ref — updated synchronously so get_active_video/get_inactive_video
  // never read a stale buffer after finish_video_switch swaps before React re-renders
  const active_buffer_ref = useRef<"A" | "B">("A");

  // ── Player state ───────────────────────────────────
  const [status, set_status] = useState<PlayerStatus>("loading");
  const [error_msg, set_error_msg] = useState("");
  const [current_media, set_current_media] = useState<MediaData | null>(null);
  const [current_time, set_current_time] = useState(0);
  const [duration, set_duration] = useState(0);
  const [is_playing, set_is_playing] = useState(false);
  const [is_muted, set_is_muted] = useState(false);
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
  const [slide_anim, set_slide_anim] = useState<{ direction: "next" | "prev"; phase: "start" | "animating" } | null>(null);
  const [video_a_src, set_video_a_src] = useState("");
  const [video_b_src, set_video_b_src] = useState("");
  const [show_video, set_show_video] = useState(true);

  // Douyin state
  const [play_history, set_play_history] = useState<MediaData[]>([]);
  const [history_index, set_history_index] = useState(-1);
  const preload_index_ref = useRef(-1);
  const history_index_ref = useRef(-1);
  const play_history_ref = useRef<MediaData[]>([]);
  const handle_nav_next_ref = useRef<() => void>(() => {});
  const fetch_douyin_next_ref = useRef<() => void>(() => {});
  const animate_slide_in_ref = useRef<(direction: "next" | "prev") => void>(() => {});
  const preload_next_ref = useRef<() => void>(() => {});

  // Grid state
  const grid_path_ref = useRef("");
  const grid_is_video_ref = useRef(true);

  // ── Helper: get active/inactive video refs ──────────
  const get_active_video = useCallback(() =>
    active_buffer_ref.current === "A" ? video_a_ref.current : video_b_ref.current,
  []);
  const get_inactive_video = useCallback(() =>
    active_buffer_ref.current === "A" ? video_b_ref.current : video_a_ref.current,
  []);

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
  const force_video_repaint = useCallback((video: HTMLVideoElement) => {
    if (!video) return;
    // Skip on touch devices — native fullscreen handles rendering correctly
    if (navigator.maxTouchPoints > 0) return;
    video.style.display = "none";
    video.offsetHeight;
    requestAnimationFrame(() => {
      if (!document.fullscreenElement && !(document as unknown as { webkitFullscreenElement?: Element }).webkitFullscreenElement) return;
      video.style.display = "block";
      video.style.width = (screen.width - 1) + "px";
      video.style.height = (screen.height - 1) + "px";
      video.offsetHeight;
      requestAnimationFrame(() => {
        if (!document.fullscreenElement && !(document as unknown as { webkitFullscreenElement?: Element }).webkitFullscreenElement) return;
        video.style.width = "100%";
        video.style.height = "100%";
      });
    });
  }, []);

  const update_fullscreen_state = useCallback(() => {
    const fs = !!(document.fullscreenElement || (document as unknown as { webkitFullscreenElement?: Element }).webkitFullscreenElement);
    set_is_fullscreen(fs);
    if (!fs) {
      // 退出全屏：恢复视频 CSS（来自原始 onFullscreenChange 逻辑）
      [video_a_ref.current, video_b_ref.current].forEach((v) => {
        if (!v) return;
        v.style.willChange = "";
        v.style.display = "";
        v.style.width = "";
        v.style.height = "";
      });
      set_vol_indicator({ active: false, pct: 100 });
      set_bright_indicator({ active: false, pct: 100 });
    }
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
    // Container fullscreen：清除 GPU 合成层诱因（来自原始 enterContainerFullscreen）
    const active = get_active_video();
    const inactive = get_inactive_video();
    if (active) {
      active.style.willChange = "auto";
      active.style.transform = "";
    }
    if (inactive) {
      inactive.style.willChange = "auto";
      inactive.style.transform = "";
    }
    const el = container_ref.current;
    if (el) {
      const promise = el.requestFullscreen ? el.requestFullscreen() :
        (el as HTMLElement & { webkitRequestFullscreen?: () => Promise<void> }).webkitRequestFullscreen?.();
      promise?.then(() => {
        if (active) force_video_repaint(active);
      }).catch(() => {});
    }
  }, [get_active_video, get_inactive_video, update_fullscreen_state, force_video_repaint]);

  // ── Video switching ─────────────────────────────────
  const finish_video_switch = useCallback(() => {
    if (!state_ref.current.is_transitioning) return;
    if (safety_timer_ref.current) {
      clearTimeout(safety_timer_ref.current);
      safety_timer_ref.current = null;
    }
    if (transition_timer_ref.current) {
      clearTimeout(transition_timer_ref.current);
      transition_timer_ref.current = null;
    }
    // Pause the outgoing video — do NOT touch CSS styles imperatively.
    // React cleans up transforms/transitions when slide_anim is set to null
    // and active_buffer is swapped. Imperative clearing causes both videos
    // to snap to visible position for one frame → "two videos" flash.
    const old_active = get_active_video();
    if (old_active) {
      old_active.pause();
    }
    // Swap buffers: the inactive video becomes active
    const new_active_buffer = active_buffer_ref.current === "A" ? "B" : "A";
    active_buffer_ref.current = new_active_buffer;
    set_active_buffer(new_active_buffer);
    set_slide_anim(null);
    // Clear the old buffer's src (now the new inactive) to free memory
    setTimeout(() => {
      if (new_active_buffer === "A") set_video_b_src("");
      else set_video_a_src("");
    }, 200);
    // Play the new active video
    const new_active = new_active_buffer === "A" ? video_a_ref.current : video_b_ref.current;
    if (new_active) {
      new_active.muted = is_muted;
      new_active.playbackRate = selected_speed;
      new_active.play().catch(() => {});
    }
    state_ref.current.is_transitioning = false;
    set_is_playing(true);
    // Trigger preload for the next video after transition
    if (!is_grid) {
      setTimeout(() => preload_next_ref.current(), 0);
    }
  }, [get_active_video, get_inactive_video, is_muted, selected_speed, is_grid]);

  const animate_slide_in = useCallback((direction: "next" | "prev") => {
    state_ref.current.is_transitioning = true;
    // Mute active video during transition
    const active = get_active_video();
    if (active) active.muted = true;

    set_slide_anim({ direction, phase: "start" });

    // Set up primary completion: transitionend event on the incoming video
    const incoming = get_inactive_video();
    const cleanup_transitionend = () => {
      clearTimeout(fallback_timer);
      if (incoming) {
        incoming.removeEventListener("transitionend", on_transitionend);
        (incoming as HTMLVideoElement & { _transitionend_fired?: boolean })._transitionend_fired = true;
      }
    };
    const on_transitionend = () => {
      cleanup_transitionend();
      finish_video_switch();
    };
    if (incoming) {
      incoming.addEventListener("transitionend", on_transitionend, { once: true });
    }

    // Fallback timer at 400ms
    const fallback_timer = setTimeout(() => {
      cleanup_transitionend();
      finish_video_switch();
    }, 400);

    // Safety timer at 1500ms
    if (safety_timer_ref.current) clearTimeout(safety_timer_ref.current);
    safety_timer_ref.current = setTimeout(() => {
      clearTimeout(fallback_timer);
      cleanup_transitionend();
      finish_video_switch();
    }, 1500);
  }, [get_active_video, get_inactive_video, finish_video_switch]);

  const play_media = useCallback((media: MediaData, direction: "next" | "prev" | null) => {
    if (state_ref.current.is_transitioning) return;
    set_current_media(media);
    set_error_msg("");

    if (!media.is_video) {
      set_show_video(false);
      set_status("playing");
      return;
    }

    set_show_video(true);
    const url = `/media/serve_media/${encodeURIComponent(media.relative_path)}`;

    if (!direction) {
      // First load: load into active buffer — matching original playVideo(null)
      const active = get_active_video();
      const inactive = get_inactive_video();
      if (active) {
        active.src = url;
        active.muted = is_muted;
        active.playbackRate = selected_speed;
        active.style.zIndex = "2";
        active.play().catch(() => {});
      }
      if (inactive) inactive.style.zIndex = "1";
      // Sync React state for rendering
      if (active_buffer_ref.current === "A") set_video_a_src(url);
      else set_video_b_src(url);
      set_is_playing(true);
      return;
    }

    // Transition: load into inactive buffer — matching original playVideo(transition)
    state_ref.current.is_transitioning = true;
    const inactive = get_inactive_video();
    if (!inactive) return;

    // Set muted + playbackRate BEFORE setting src (original lines 497-499)
    inactive.muted = is_muted;
    inactive.playbackRate = selected_speed;
    inactive.src = url;
    // Sync React state
    if (active_buffer_ref.current === "A") set_video_b_src(url);
    else set_video_a_src(url);
    // Hide loading immediately after setting src (original line 500)
    set_status("playing");

    let canplay_fired = false;
    const handle_canplay = () => {
      canplay_fired = true;
      inactive.removeEventListener("canplay", handle_canplay);
      if (transition_timer_ref.current) {
        clearTimeout(transition_timer_ref.current);
        transition_timer_ref.current = null;
      }
      animate_slide_in(direction);
    };

    inactive.addEventListener("canplay", handle_canplay);

    // 500ms fallback timer (matching original)
    transition_timer_ref.current = setTimeout(() => {
      transition_timer_ref.current = null;
      if (state_ref.current.is_transitioning && !canplay_fired) {
        inactive.removeEventListener("canplay", handle_canplay);
        animate_slide_in(direction);
      }
    }, 500);
  }, [get_active_video, get_inactive_video, is_muted, selected_speed, animate_slide_in]);

  // ── Video events setup ──────────────────────────────
  const setup_video_events = useCallback((video: HTMLVideoElement) => {
    const is_active = () =>
      (active_buffer_ref.current === "A" && video === video_a_ref.current) ||
      (active_buffer_ref.current === "B" && video === video_b_ref.current);

    const on_loaded = () => { if (is_active()) { set_duration(video.duration); set_current_time(0); } };
    const on_time = () => {
      if (!state_ref.current.is_dragging && is_active()) {
        set_current_time(video.currentTime);
        set_duration(video.duration);
      }
    };
    const on_play = () => { if (is_active()) { set_is_playing(true); show_controls(); } };
    const on_pause = () => { if (is_active()) { set_is_playing(false); show_controls(); } };
    const on_waiting = () => { if (!video.paused && is_active()) set_status("loading"); };
    const on_canplay = () => {
      if (is_active()) {
        set_status("playing");
        set_is_playing(!video.paused);
      }
    };
    const on_ended = () => {
      if (!is_grid) {
        handle_nav_next_ref.current();
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
  }, [is_grid, show_controls]);

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
  useEffect(() => { history_index_ref.current = history_index; }, [history_index]);
  useEffect(() => { play_history_ref.current = play_history; }, [play_history]);
  useEffect(() => { active_buffer_ref.current = active_buffer; }, [active_buffer]);

  // ── Navigation ──────────────────────────────────────
  const handle_nav_next = useCallback(() => {
    if (state_ref.current.is_transitioning || is_fetching_ref.current) return;

    if (is_grid) {
      navigate_grid("next");
    } else {
      // Douyin mode
      if (history_index < play_history.length - 1) {
        const next_idx = history_index + 1;
        set_history_index(next_idx);
        // Use preloaded buffer if available to skip reloading
        if (preload_index_ref.current === next_idx) {
          const media = play_history[next_idx];
          set_current_media(media);
          set_status("playing");
          animate_slide_in_ref.current("next");
        } else {
          play_media(play_history[next_idx], "next");
        }
      } else {
        fetch_douyin_next_ref.current();
      }
    }
  }, [is_grid, history_index, play_history, play_media]);

  const handle_nav_prev = useCallback(() => {
    if (state_ref.current.is_transitioning || is_fetching_ref.current) return;

    if (is_grid) {
      navigate_grid("prev");
    } else {
      const cur_idx = history_index_ref.current;
      if (cur_idx > 0) {
        const prev_idx = cur_idx - 1;
        set_history_index(prev_idx);
        preload_index_ref.current = -1;
        play_media(play_history_ref.current[prev_idx], "prev");
      }
    }
  }, [is_grid, play_media]);

  // ── Grid navigation ─────────────────────────────────
  const navigate_grid = useCallback(async (direction: "next" | "prev") => {
    if (!grid_path_ref.current) return;
    is_fetching_ref.current = true;
    set_status("loading");
    try {
      const resp = await api_client.get<{ code: number; data: MediaData }>("/media/navigate", {
        params: { current_path: grid_path_ref.current, direction },
      });
      if (resp.data.code === 0 && resp.data.data) {
        const data = resp.data.data;
        grid_path_ref.current = data.relative_path;
        grid_is_video_ref.current = data.is_video;
        set_current_media(data);
        if (data.is_video) {
          set_show_video(true);
          set_status("loading");
          const url = `/media/serve_media/${encodeURIComponent(data.relative_path)}`;
          load_grid_video(url);
        } else {
          set_show_video(false);
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
      is_fetching_ref.current = false;
      if (status === "loading") set_status("playing");
    }
  }, [load_grid_video, status]);

  // ── Grid mode: simple video load (single element, no dual-buffer) ──
  const load_grid_video = useCallback((url: string) => {
    const video = video_a_ref.current;
    if (!video) return;
    video.src = url;
    video.muted = is_muted;
    video.playbackRate = selected_speed;
    video.play().catch(() => {});
    set_video_a_src(url);
  }, [is_muted, selected_speed]);

  // ── Preload next (douyin mode) ──────────────────────
  const preload_next = useCallback(async () => {
    if (is_grid || state_ref.current.is_transitioning || preload_pending_ref.current) return;
    const cur_idx = history_index_ref.current;
    const cur_history = play_history_ref.current;
    const next_idx = cur_idx + 1;
    if (next_idx < cur_history.length) {
      preload_index_ref.current = next_idx;
      const url = `/media/serve_media/${encodeURIComponent(cur_history[next_idx].relative_path)}`;
      // Set via React state only — avoids one-frame flash where inactive video
      // has src but no translateY(100%) transform yet (visible on slower browsers)
      if (active_buffer_ref.current === "A") set_video_b_src(url);
      else set_video_a_src(url);
      return;
    }
    preload_pending_ref.current = true;
    try {
      const resp = await api_client.get<{ code: number; data: MediaData }>("/api/douyin/next");
      // Re-check after await: a transition may have started while we were fetching
      if (state_ref.current.is_transitioning) return;
      if (resp.data.code === 0 && resp.data.data) {
        set_play_history((prev) => {
          // Avoid duplicating the same video in history
          const existing_idx = prev.findIndex((m) => m.relative_path === resp.data.data.relative_path);
          if (existing_idx >= 0 && existing_idx >= cur_idx) {
            preload_index_ref.current = existing_idx;
            return prev;
          }
          const next = [...prev, resp.data.data];
          preload_index_ref.current = next.length - 1;
          return next;
        });
        const url = `/media/serve_media/${encodeURIComponent(resp.data.data.relative_path)}`;
        // Set via React state only — same reason as above
        if (active_buffer_ref.current === "A") set_video_b_src(url);
        else set_video_a_src(url);
      }
    } catch { /* ignore */ }
    finally { preload_pending_ref.current = false; }
  }, [is_grid, is_muted, selected_speed, get_inactive_video]);

  // ── Douyin API ──────────────────────────────────────
  const fetch_douyin_next = useCallback(async () => {
    if (state_ref.current.is_transitioning) return;
    preload_pending_ref.current = true;
    is_fetching_ref.current = true;
    set_status("loading");
    try {
      const resp = await api_client.get<{ code: number; data: MediaData; msg?: string }>("/api/douyin/next", { timeout: 8000 });
      // Re-check: a transition may have started during the fetch
      if (state_ref.current.is_transitioning) return;
      if (resp.data.code === 0 && resp.data.data) {
        const cur_idx = history_index_ref.current;
        set_play_history((prev) => {
          const next = prev.slice(0, cur_idx + 1);
          next.push(resp.data.data);
          if (next.length > 100) next.shift();
          return next;
        });
        set_history_index(cur_idx + 1);
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
    } finally {
      preload_pending_ref.current = false;
      is_fetching_ref.current = false;
    }
  }, [play_media]);

  const fetch_douyin_init = useCallback(async () => {
    set_status("loading");
    try {
      const resp = await api_client.get<{ code: number; data: MediaData }>("/api/douyin/init", { timeout: 8000 });
      if (resp.data.code === 0 && resp.data.data) {
        set_play_history([resp.data.data]);
        set_history_index(0);
        play_media(resp.data.data, null);
        // Preload next video immediately (matching original's preloadNextVideo call)
        preload_next();
        return;
      }
    } catch { /* fallback to next */ }
    fetch_douyin_next();
  }, [play_media, fetch_douyin_next, preload_next]);

  // ── Initialize ──────────────────────────────────────
  useEffect(() => {
    if (is_grid) {
      grid_path_ref.current = grid_path_param;
      // Determine if video by extension
      const ext = grid_path_param.split(".").pop()?.toLowerCase() || "";
      const is_vid = ["mp4", "avi", "mkv", "mov", "wmv", "flv", "webm", "m4v", "3gp"].includes(ext);
      grid_is_video_ref.current = is_vid;
      set_show_video(is_vid);
      const media: MediaData = {
        relative_path: grid_path_param,
        name: decodeURIComponent(grid_path_param.split("/").pop() || grid_path_param),
        is_video: is_vid,
      };
      set_current_media(media);
      if (is_vid) {
        const url = `/media/serve_media/${encodeURIComponent(media.relative_path)}`;
        load_grid_video(url);
      } else {
        set_status("playing");
      }
    } else {
      fetch_douyin_init();
    }
    show_controls();
  }, []);

  // Sync refs for functions referenced in event handlers (avoids stale closures)
  useEffect(() => { handle_nav_next_ref.current = handle_nav_next; }, [handle_nav_next]);
  useEffect(() => { fetch_douyin_next_ref.current = fetch_douyin_next; }, [fetch_douyin_next]);
  useEffect(() => { animate_slide_in_ref.current = animate_slide_in; }, [animate_slide_in]);
  useEffect(() => { preload_next_ref.current = preload_next; }, [preload_next]);

  // Transition slide animation from "start" to "animating" phase
  useEffect(() => {
    if (slide_anim?.phase !== "start") return;
    const raf = requestAnimationFrame(() => {
      set_slide_anim({ direction: slide_anim.direction, phase: "animating" });
    });
    return () => cancelAnimationFrame(raf);
  }, [slide_anim]);

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
      else if (!is_grid && event.key === " ") { event.preventDefault(); toggle_play(); }
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
      preload={is_grid ? "metadata" : "auto"}
      className="absolute inset-0 w-full h-full object-contain bg-black"
      style={{ zIndex: z_index, transform, transition }}
    />
  );

  // ── Slide animation CSS ─────────────────────────────
  const slide_a_style: React.CSSProperties = {};
  const slide_b_style: React.CSSProperties = {};

  if (slide_anim) {
    const is_a_active = active_buffer === "A";
    const from_y = slide_anim.direction === "next" ? "translateY(100%)" : "translateY(-100%)";
    const out_y = slide_anim.direction === "next" ? "translateY(-100%)" : "translateY(100%)";
    const trans = "transform 0.35s cubic-bezier(0.25, 0.46, 0.45, 0.94)";
    const is_start = slide_anim.phase === "start";

    if (is_a_active) {
      slide_a_style.transform = out_y;
      slide_a_style.transition = trans;
      slide_a_style.zIndex = 1;
      slide_b_style.transform = is_start ? from_y : "translateY(0)";
      slide_b_style.transition = is_start ? "none" : trans;
      slide_b_style.zIndex = 2;
    } else {
      slide_b_style.transform = out_y;
      slide_b_style.transition = trans;
      slide_b_style.zIndex = 1;
      slide_a_style.transform = is_start ? from_y : "translateY(0)";
      slide_a_style.transition = is_start ? "none" : trans;
      slide_a_style.zIndex = 2;
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
      className="relative h-dvh w-screen overflow-hidden bg-black select-none touch-none"
      {...(!is_grid ? {
        onTouchStart: gesture.handle_touch_start,
        onTouchMove: gesture.handle_touch_move,
        onTouchEnd: gesture.handle_touch_end,
        onClick: gesture.handle_click,
        onMouseDown: gesture.handle_mouse_down,
        onMouseUp: gesture.handle_mouse_up,
        onWheel: gesture.handle_wheel,
      } : {
        onClick: () => set_controls_visible((prev) => !prev),
      })}
    >
      {/* ─── Video / Image Display ─────────────────── */}
      {is_grid && show_video ? (
        <video
          ref={video_a_ref}
          src={video_a_src}
          controls
          muted={is_muted}
          playsInline
          className="absolute inset-0 w-full h-full object-contain bg-black"
        />
      ) : show_video ? (
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
      {!is_grid && bright_indicator.active && (
        <div
          className="pointer-events-none absolute inset-0 bg-black transition-opacity"
          style={{ opacity: 1 - bright_indicator.pct / 100 }}
        />
      )}

      {/* ─── Loading / Error / End ──────────────────── */}
      {status === "loading" && (
        <div className="absolute inset-0 flex items-center justify-center z-10">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-white/20 border-t-white" />
        </div>
      )}
      {status === "ended" && (
        <div className="absolute inset-0 flex items-center justify-center z-10">
          <div className="rounded-xl bg-black/60 backdrop-blur px-6 py-3">
            <p className="text-white/80 text-base font-medium">没有更多视频了</p>
          </div>
        </div>
      )}
      {error_msg && (
        <div className="absolute top-20 left-1/2 -translate-x-1/2 z-20 rounded-xl bg-danger/90 backdrop-blur px-4 py-2.5 text-sm font-medium text-white shadow-lg animate-fade-in">
          {error_msg}
        </div>
      )}

      {/* ─── Top Bar ────────────────────────────────── */}
      {(is_grid || controls_visible) && (
        <div className="player-controls-area absolute top-0 left-0 right-0 z-20 flex items-center gap-3 bg-gradient-to-b from-black/70 to-transparent px-4 pt-4 pb-6">
          {is_grid && (
            <button
              onClick={() => {
                if (document.fullscreenElement) toggle_fullscreen();
                else navigate(-1);
              }}
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-white/80 transition hover:text-white hover:bg-white/10"
            >
              ← 返回
            </button>
          )}
          <span className="truncate text-sm font-medium text-white/90">{current_media?.name || ""}</span>
          <div className="ml-auto flex items-center gap-1">
            <button onClick={handle_nav_prev} className="rounded-full p-2 text-white/70 transition hover:text-white hover:bg-white/10">
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
              </svg>
            </button>
            <button onClick={handle_nav_next} className="rounded-full p-2 text-white/70 transition hover:text-white hover:bg-white/10">
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* ─── Center: Skip buttons + Play/Pause ──────── */}
      {controls_visible && show_video && !is_grid && (
        <div className="player-controls-area absolute inset-0 z-10 flex items-center justify-center pointer-events-none">
          <div className="flex items-center gap-6 pointer-events-auto">
            <button onClick={() => skip_time(-15)} className="flex flex-col items-center justify-center rounded-full bg-white/10 w-14 h-14 text-white/80 transition hover:bg-white/20 hover:scale-105 active:scale-95">
              <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/>
              </svg>
              <span className="text-[10px] font-medium mt-0.5">15</span>
            </button>
            <button onClick={toggle_play} className="flex items-center justify-center rounded-full bg-white/15 w-16 h-16 text-white transition hover:bg-white/25 hover:scale-105 active:scale-95">
              <svg className="h-7 w-7" fill="currentColor" viewBox="0 0 24 24">
                {show_video ? (is_playing ? <path d={PAUSE_ICON}/> : <path d={PLAY_ICON}/>) : <path d={PLAY_ICON}/>}
              </svg>
            </button>
            <button onClick={() => skip_time(15)} className="flex flex-col items-center justify-center rounded-full bg-white/10 w-14 h-14 text-white/80 transition hover:bg-white/20 hover:scale-105 active:scale-95">
              <svg className="h-5 w-5 rotate-180" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/>
              </svg>
              <span className="text-[10px] font-medium mt-0.5">15</span>
            </button>
          </div>
        </div>
      )}

      {/* ─── Bottom Controls ────────────────────────── */}
      {controls_visible && show_video && !is_grid && (
        <div className="player-controls-area absolute bottom-0 left-0 right-0 z-20 bg-gradient-to-t from-black/80 to-transparent px-4 pb-6 pt-10">
          {/* Progress bar */}
          <div
            ref={progress_ref}
            className="relative h-10 cursor-pointer flex items-center group -mx-1 px-1"
            onPointerDown={handle_progress_pointer_down}
            onPointerMove={handle_progress_pointer_move}
            onPointerUp={handle_progress_pointer_up}
          >
            <div className="w-full h-1 rounded-full bg-white/20 group-hover:h-1.5 transition-all">
              <div className="h-full rounded-full bg-accent relative" style={{ width: `${progress_pct}%` }}>
                <div className="absolute right-0 top-1/2 -translate-y-1/2 w-3.5 h-3.5 rounded-full bg-white shadow-lg opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
            </div>
          </div>

          {/* Controls row */}
          <div className="flex items-center gap-3 mt-2">
            <button onClick={toggle_play} className="text-white/80 hover:text-white transition">
              <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
                {is_playing ? <path d={PAUSE_ICON}/> : <path d={PLAY_ICON}/>}
              </svg>
            </button>
            <span className="text-xs text-white/50 tabular-nums min-w-[90px] font-medium">
              {format_time(current_time)} / {format_time(duration)}
            </span>
            <div className="flex-1" />
            {/* Settings: mute + speed */}
            <div className="relative">
              <button
                onClick={() => { set_settings_open((prev) => !prev); set_speed_menu_open(false); }}
                className="text-sm text-white/70 hover:text-white transition"
              >
                设置
              </button>
              {settings_open && (
                <div className="absolute bottom-full right-0 mb-2 rounded-xl bg-black/90 border border-white/10 py-1.5 shadow-xl backdrop-blur min-w-[130px] animate-fade-in">
                  <button
                    onClick={() => { toggle_mute(); set_settings_open(false); }}
                    className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-white/80 hover:bg-white/10 transition"
                  >
                    {is_muted ? "🔇 取消静音" : "🔊 静音"}
                  </button>
                  <div className="relative">
                    <button
                      onClick={() => set_speed_menu_open((prev) => !prev)}
                      className="flex w-full items-center justify-between px-4 py-2.5 text-sm text-white/80 hover:bg-white/10 transition"
                    >
                      倍速 <span className="text-white/50">{selected_speed.toFixed(2)}x</span>
                    </button>
                    {speed_menu_open && (
                      <div className="absolute right-full bottom-0 mr-1 rounded-xl bg-black/90 border border-white/10 py-1.5 shadow-xl backdrop-blur animate-fade-in">
                        {SPEED_OPTIONS.map((speed) => (
                          <button
                            key={speed}
                            onClick={() => set_speed(speed)}
                            className={`block w-full px-4 py-2.5 text-left text-sm whitespace-nowrap transition ${
                              selected_speed === speed ? "text-accent font-medium" : "text-white/70 hover:bg-white/10"
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
            <button onClick={toggle_fullscreen} className="text-white/70 hover:text-white ml-1 transition">
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
      {!is_grid && speed_active && (
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-30 rounded-xl bg-black/75 backdrop-blur px-5 py-3 text-xl font-bold text-white shadow-lg">
          3x
        </div>
      )}
      {!is_grid && seek_indicator.active && (
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-30 rounded-xl bg-black/75 backdrop-blur px-5 py-3 text-base font-medium text-white shadow-lg animate-fade-in">
          {seek_indicator.time}
        </div>
      )}
      {!is_grid && vol_indicator.active && (
        <div className="absolute right-6 top-1/2 -translate-y-1/2 z-30 flex flex-col items-center gap-2">
          <div className="h-32 w-2.5 rounded-full bg-white/15 overflow-hidden">
            <div className="w-full bg-white/90 rounded-full transition-all" style={{ height: `${vol_indicator.pct}%`, marginTop: `${100 - vol_indicator.pct}%` }} />
          </div>
          <span className="text-xs font-medium text-white/80">{vol_indicator.pct}</span>
        </div>
      )}
      {!is_grid && bright_indicator.active && (
        <div className="absolute left-6 top-1/2 -translate-y-1/2 z-30 flex flex-col items-center gap-2">
          <div className="h-32 w-2.5 rounded-full bg-white/15 overflow-hidden">
            <div className="w-full bg-white/90 rounded-full transition-all" style={{ height: `${bright_indicator.pct}%`, marginTop: `${100 - bright_indicator.pct}%` }} />
          </div>
          <span className="text-xs font-medium text-white/80">{bright_indicator.pct}</span>
        </div>
      )}
    </div>
  );
}

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

// ── 自适应预加载 / 滑动过渡参数（兼顾老设备）──
const PRELOAD_BUFFER_SECONDS = 2.5;     // 当前视频缓冲余量达到该秒数就开始预取下一集（滑动切换更快就绪）
const PRELOAD_NEAR_END_SECONDS = 8;     // 当前视频剩余不足该秒数时提前预取，确保衔接
const PRELOAD_CHECK_INTERVAL_MS = 800;  // 缓冲检查间隔
const PRELOAD_MAX_CHECKS = 30;          // 最多重试次数（约 24s 后放弃）
const TRANSITION_TIMEOUT_MS = 2500;     // 滑动切换等待下一集 canplay 的兜底超时

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
  const video_c_ref = useRef<HTMLVideoElement>(null);
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
  const preload_timer_ref = useRef<ReturnType<typeof setTimeout> | null>(null);
  const preload_check_count_ref = useRef(0);

  // State proxy refs (for event handlers to avoid stale closures)
  const state_ref = useRef({
    is_transitioning: false,
    is_dragging: false,
    selected_speed: 1,
  });

  // 三缓冲：active_slot 指向当前视频槽位（0|1|2），前一个槽位=上一集缓存、后一个=下一集预载
  const active_slot_ref = useRef(0);

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
  // 当前视频是否为横屏（videoWidth > videoHeight）；全屏横屏时锁横屏观看
  const [is_landscape_video_active, set_is_landscape_video_active] = useState(false);
  // 设备是否处于竖屏（横屏观看模式下用于提示用户旋转手机）
  const [is_portrait, setIs_portrait] = useState(false);
  const [speed_active, set_speed_active] = useState(false);
  const [seek_indicator, set_seek_indicator] = useState<{ active: boolean; time: string }>({ active: false, time: "" });
  const [vol_indicator, set_vol_indicator] = useState<{ active: boolean; pct: number }>({ active: false, pct: 100 });
  const [bright_indicator, set_bright_indicator] = useState<{ active: boolean; pct: number }>({ active: false, pct: 100 });

  // 三缓冲控制：始终读 ref，state 仅用于渲染触发
  const [active_slot, set_active_slot] = useState(0);
  // 垂直拖拽跟手（抖音风格翻页）：用 ref 直接操作 DOM，避免每次 touchmove 触发 React 重渲染
  const drag_direction_ref = useRef<"next" | "prev">("next");
  const drag_y_ref = useRef(0);
  const drag_active_ref = useRef(false);
  const drag_timer_ref = useRef<ReturnType<typeof setTimeout> | null>(null);
  // 翻页/回弹动画（rAF 驱动）状态
  const animating_ref = useRef(false);
  const raf_id_ref = useRef(0);
  // 新手势打断动画时，以当前画面偏移为基准，实现无缝接管
  const base_offset_ref = useRef(0);
  const [video_a_src, set_video_a_src] = useState("");
  const [video_b_src, set_video_b_src] = useState("");
  const [video_c_src, set_video_c_src] = useState("");
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

  // ── Helper: 槽位访问（三缓冲）─────────────────
  const get_slot_video = useCallback((i: number) => {
    if (i === 0) return video_a_ref.current;
    if (i === 1) return video_b_ref.current;
    return video_c_ref.current;
  }, []);
  const get_active_video = useCallback(() => get_slot_video(active_slot_ref.current), [get_slot_video]);
  // 相邻视频：next=后一个槽位(+1)，prev=前一个槽位(+2 即 -1)
  const get_adjacent_video = useCallback((dir: "next" | "prev") =>
    get_slot_video((active_slot_ref.current + (dir === "next" ? 1 : 2)) % 3),
  [get_slot_video]);

  // 直接改视频元素 transform（跟手 + 动画驱动用，不触发 React 重渲染）。
  // 三槽位都跟随偏移：当前在中间、上一在上、下一在下。
  const apply_drag_y = useCallback((dy: number, _dir: "next" | "prev") => {
    const cur = active_slot_ref.current;
    const set_transform = (v: HTMLVideoElement | null, transform: string) => {
      if (v) {
        v.style.transition = "none";
        v.style.transform = transform;
      }
    };
    set_transform(get_slot_video(cur), `translateY(${dy}px)`);
    set_transform(get_slot_video((cur + 2) % 3), `translateY(calc(${dy}px - 100%))`);
    set_transform(get_slot_video((cur + 1) % 3), `translateY(calc(${dy}px + 100%))`);
  }, [get_slot_video]);

  // 取消进行中的翻页/回弹动画（可打断：新手势立即接管当前进度）
  const cancel_offset_animation = useCallback(() => {
    if (animating_ref.current) {
      animating_ref.current = false;
      if (raf_id_ref.current) cancelAnimationFrame(raf_id_ref.current);
      raf_id_ref.current = 0;
    }
  }, []);

  // 用 rAF 驱动 offset 从 start_y 平滑运动到 target_y（翻页/回弹统一入口）
  const start_offset_animation = useCallback(
    (start_y: number, target_y: number, duration: number, on_complete?: () => void) => {
      cancel_offset_animation();
      animating_ref.current = true;
      const dir = drag_direction_ref.current;
      const start_t = performance.now();
      const step = (t: number) => {
        if (!animating_ref.current) return; // 被新手势打断
        const p = Math.min(1, (t - start_t) / duration);
        const eased = 1 - Math.pow(1 - p, 3); // ease-out cubic（先快后慢）
        const dy = start_y + (target_y - start_y) * eased;
        drag_y_ref.current = dy;
        apply_drag_y(dy, dir);
        if (p < 1) {
          raf_id_ref.current = requestAnimationFrame(step);
        } else {
          animating_ref.current = false;
          raf_id_ref.current = 0;
          // 先完成切换（交换缓冲）再复位拖拽状态，避免画面闪回
          if (on_complete) on_complete();
        }
      };
      raf_id_ref.current = requestAnimationFrame(step);
    },
    [apply_drag_y, cancel_offset_animation]
  );

  // ── 自适应预加载：等当前视频缓冲足够（或临近结束）再预取下一集，避免与当前播放抢带宽 ──
  const schedule_next_preload = useCallback(() => {
    if (is_grid) return;
    preload_check_count_ref.current = 0;
    const try_preload = () => {
      if (state_ref.current.is_transitioning) return;
      const video = get_active_video();
      if (!video) return;
      preload_check_count_ref.current += 1;
      if (preload_check_count_ref.current > PRELOAD_MAX_CHECKS) return;
      let buffered_ahead = 0;
      let remaining = 0;
      if (isFinite(video.duration) && video.duration > 0) {
        remaining = video.duration - video.currentTime;
        if (video.buffered.length > 0) {
          buffered_ahead = video.buffered.end(video.buffered.length - 1) - video.currentTime;
        }
      }
      if (buffered_ahead >= PRELOAD_BUFFER_SECONDS
          || (video.duration > 0 && remaining <= PRELOAD_NEAR_END_SECONDS && buffered_ahead >= remaining)) {
        preload_next_ref.current();
      } else {
        if (preload_timer_ref.current) clearTimeout(preload_timer_ref.current);
        preload_timer_ref.current = setTimeout(try_preload, PRELOAD_CHECK_INTERVAL_MS);
      }
    };
    try_preload();
  }, [is_grid, get_active_video]);

  // 卸载时清理预加载/拖拽定时器/动画
  useEffect(() => {
    return () => {
      cancel_offset_animation();
      if (preload_timer_ref.current) clearTimeout(preload_timer_ref.current);
      if (drag_timer_ref.current) clearTimeout(drag_timer_ref.current);
    };
  }, [cancel_offset_animation]);

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
      [video_a_ref.current, video_b_ref.current, video_c_ref.current].forEach((v) => {
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
    [get_slot_video(0), get_slot_video(1), get_slot_video(2)].forEach((v) => {
      if (v) {
        v.style.willChange = "auto";
        v.style.transform = "";
      }
    });
    const active = get_active_video();
    const el = container_ref.current;
    if (el) {
      const promise = el.requestFullscreen ? el.requestFullscreen() :
        (el as HTMLElement & { webkitRequestFullscreen?: () => Promise<void> }).webkitRequestFullscreen?.();
      promise?.then(() => {
        if (active) force_video_repaint(active);
      }).catch(() => {});
    }
  }, [get_slot_video, get_active_video, update_fullscreen_state, force_video_repaint]);

  // ── Video switching ─────────────────────────────────
  const finish_video_switch = useCallback((direction: "next" | "prev") => {
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
    const old_slot = active_slot_ref.current;
    const old_active = get_slot_video(old_slot);
    if (old_active) {
      old_active.pause();
    }
    // 槽位轮换：next=+1，prev=-1（即 +2 mod 3）
    const new_slot = (old_slot + (direction === "next" ? 1 : 2)) % 3;
    active_slot_ref.current = new_slot;
    set_active_slot(new_slot);
    // 不清理刚离开的槽位（作为上一集缓存，下滑秒切）；最远槽位留给下一次预载覆盖
    const new_active = get_slot_video(new_slot);
    if (new_active) {
      if (new_active.error) {
        // 切到的视频加载失败 → 显示错误兜底，而不是黑屏卡死
        set_status("error");
        set_error_msg("视频加载失败");
        state_ref.current.is_transitioning = false;
        return;
      }
      new_active.muted = is_muted;
      new_active.playbackRate = selected_speed;
      new_active.play().catch(() => {});
    }
    state_ref.current.is_transitioning = false;
    set_is_playing(true);
    // Trigger preload for the next video after transition（自适应：等当前缓冲足够再预取）
    if (!is_grid) {
      schedule_next_preload();
    }
  }, [get_slot_video, is_muted, selected_speed, is_grid, schedule_next_preload]);

  const animate_slide_in = useCallback((direction: "next" | "prev", start_y = 0) => {
    state_ref.current.is_transitioning = true;
    // Mute active video during transition（维持视觉连续，避免双声）
    const active = get_active_video();
    if (active) active.muted = true;
    drag_direction_ref.current = direction;
    drag_active_ref.current = true;
    const target_y = direction === "next" ? -window.innerHeight : window.innerHeight;
    // 用 rAF 驱动翻页（可被打断），动画自然结束后完成缓冲切换
    start_offset_animation(start_y, target_y, 250, () => {
      finish_video_switch(direction);
      drag_active_ref.current = false;
      drag_y_ref.current = 0;
    });
  }, [get_active_video, start_offset_animation, finish_video_switch]);

  const set_slot_src = useCallback((slot: number, u: string) => {
    if (slot === 0) set_video_a_src(u);
    else if (slot === 1) set_video_b_src(u);
    else set_video_c_src(u);
  }, []);

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
      // First load: load into active slot
      const active = get_active_video();
      if (active) {
        active.src = url;
        active.muted = is_muted;
        active.playbackRate = selected_speed;
        active.style.zIndex = "2";
        active.play().catch(() => {});
      }
      set_slot_src(active_slot_ref.current, url);
      set_is_playing(true);
      return;
    }

    // Transition: load into adjacent slot（next=后一个，prev=前一个）
    state_ref.current.is_transitioning = true;
    const adjacent_slot = (active_slot_ref.current + (direction === "next" ? 1 : 2)) % 3;
    const inactive = get_slot_video(adjacent_slot);
    if (!inactive) return;

    // Set muted + playbackRate BEFORE setting src
    inactive.muted = is_muted;
    inactive.playbackRate = selected_speed;
    inactive.src = url;
    set_slot_src(adjacent_slot, url);
    // 等待 canplay 期间显示加载状态（老设备缓冲较慢时避免黑屏无反馈）
    set_status("loading");

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

    // fallback timer：等待 canplay 优先，超时后兜底切换（老设备给更多缓冲时间）。
    // 下一集完全无数据时不强制切到黑屏（避免"卡死"），重试一轮后报错并复位。
    let fallback_retries = 0;
    const try_fallback = () => {
      if (!state_ref.current.is_transitioning || canplay_fired) return;
      const has_data = inactive.readyState >= 2 || inactive.buffered.length > 0;
      if (has_data) {
        inactive.removeEventListener("canplay", handle_canplay);
        animate_slide_in(direction);
      } else if (fallback_retries < 2) {
        fallback_retries += 1;
        transition_timer_ref.current = setTimeout(try_fallback, TRANSITION_TIMEOUT_MS);
      } else {
        inactive.removeEventListener("canplay", handle_canplay);
        set_status("error");
        set_error_msg("视频加载失败");
        state_ref.current.is_transitioning = false;
      }
    };
    transition_timer_ref.current = setTimeout(try_fallback, TRANSITION_TIMEOUT_MS);
  }, [get_active_video, get_slot_video, is_muted, selected_speed, animate_slide_in]);

  // ── Video events setup ──────────────────────────────
  const setup_video_events = useCallback((video: HTMLVideoElement) => {
    const is_active = () => video === get_slot_video(active_slot_ref.current);

    const on_loaded = () => {
      if (is_active()) {
        set_duration(video.duration);
        set_current_time(0);
        set_is_landscape_video_active(video.videoWidth > video.videoHeight);
      }
    };
    const on_time = () => {
      if (!state_ref.current.is_dragging && is_active()) {
        set_current_time(video.currentTime);
        set_duration(video.duration);
      }
    };
    const on_play = () => { if (is_active()) { set_is_playing(true); set_status("playing"); show_controls(); } };
    const on_pause = () => { if (is_active()) { set_is_playing(false); show_controls(); } };
    const on_waiting = () => { if (!video.paused && is_active()) set_status("loading"); };
    const on_canplay = () => {
      if (is_active()) {
        set_status("playing");
        set_is_playing(!video.paused);
      }
    };
    const on_ended = () => {
      // 只处理当前缓冲的结束事件；播放完毕从头重播（不再自动切下一集）
      if (!is_active()) return;
      video.currentTime = 0;
      video.play().catch(() => {});
    };
    const on_err = () => {
      // 预载的下一集失败：不打扰当前播放，切换时会检测 error 兜底
      if (!is_active()) return;
      set_status("error");
      set_error_msg("视频加载失败");
      state_ref.current.is_transitioning = false;
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
  }, [is_grid, show_controls, get_slot_video]);

  // Attach events to both video elements
  useEffect(() => {
    const cleanups: (() => void)[] = [];
    if (video_a_ref.current) cleanups.push(setup_video_events(video_a_ref.current));
    if (video_b_ref.current) cleanups.push(setup_video_events(video_b_ref.current));
    if (video_c_ref.current) cleanups.push(setup_video_events(video_c_ref.current));
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

  // ── 横屏视频全屏观看模式：锁定横屏 + 竖屏提示旋转设备 ──
  useEffect(() => {
    const landscape_watch = is_fullscreen && is_landscape_video_active;
    let mql: MediaQueryList | null = null;

    if (landscape_watch) {
      // 尝试锁定横屏（Android 支持；iOS 不支持则靠设备物理旋转）
      try {
        const lock_promise = (screen.orientation as unknown as { lock?: (o: string) => Promise<void> })?.lock?.("landscape");
        if (lock_promise && typeof lock_promise.catch === "function") lock_promise.catch(() => {});
      } catch { /* 不支持则忽略 */ }

      // 检测设备是否竖屏，竖屏时提示用户横放手机
      mql = window.matchMedia("(orientation: portrait)");
      setIs_portrait(mql.matches);
      const handler = (e: MediaQueryListEvent) => setIs_portrait(e.matches);
      mql.addEventListener("change", handler);
      return () => {
        mql?.removeEventListener("change", handler);
        // 离开横屏观看模式时解锁
        try { (screen.orientation as unknown as { unlock?: () => void })?.unlock?.(); } catch { /* ignore */ }
      };
    }

    setIs_portrait(false);
    return undefined;
  }, [is_fullscreen, is_landscape_video_active]);

  useEffect(() => { is_fullscreen_ref.current = is_fullscreen; }, [is_fullscreen]);
  useEffect(() => { history_index_ref.current = history_index; }, [history_index]);
  useEffect(() => { play_history_ref.current = play_history; }, [play_history]);
  useEffect(() => { active_slot_ref.current = active_slot; }, [active_slot]);

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

  // ── Preload next (douyin mode) ──────────────────────
  const preload_next = useCallback(async () => {
    if (is_grid || state_ref.current.is_transitioning || preload_pending_ref.current) return;
    const cur_idx = history_index_ref.current;
    const cur_history = play_history_ref.current;
    const next_idx = cur_idx + 1;
    if (next_idx < cur_history.length) {
      preload_index_ref.current = next_idx;
      const url = `/media/serve_media/${encodeURIComponent(cur_history[next_idx].relative_path)}`;
      // 预载下一集到 next 槽位（active+1）
      set_slot_src((active_slot_ref.current + 1) % 3, url);
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
        set_slot_src((active_slot_ref.current + 1) % 3, url);
      }
    } catch { /* ignore */ }
    finally { preload_pending_ref.current = false; }
  }, [is_grid, is_muted, selected_speed, set_slot_src]);

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
        // 自适应预加载下一集（等当前视频缓冲足够，避免老设备抢带宽）
        schedule_next_preload();
        return;
      }
    } catch { /* fallback to next */ }
    fetch_douyin_next();
  }, [play_media, fetch_douyin_next, schedule_next_preload]);

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
    [get_slot_video(0), get_slot_video(1), get_slot_video(2)].forEach((v) => {
      if (v) v.playbackRate = speed;
    });
    set_speed_menu_open(false);
    set_settings_open(false);
  }, [get_slot_video]);

  const toggle_mute = useCallback(() => {
    set_is_muted((prev) => {
      const next = !prev;
      [get_slot_video(0), get_slot_video(1), get_slot_video(2)].forEach((v) => {
        if (v) v.muted = next;
      });
      return next;
    });
  }, [get_slot_video]);

  // 音量/亮度调整（垂直滑动已改为翻页，这里通过设置面板 +/- 调整）
  const step_volume = useCallback((delta: number) => {
    const video = get_active_video();
    if (!video) return;
    const new_vol = Math.max(0, Math.min(1, (video.volume || 0) + delta));
    video.volume = new_vol;
    set_vol_indicator({ active: true, pct: Math.round(new_vol * 100) });
    if (indicator_timer_ref.current) clearTimeout(indicator_timer_ref.current);
    indicator_timer_ref.current = setTimeout(() => {
      set_vol_indicator({ active: false, pct: Math.round((get_active_video()?.volume || 0) * 100) });
    }, 600);
  }, [get_active_video]);

  const step_brightness = useCallback((delta: number) => {
    set_bright_indicator((prev) => {
      const new_pct = Math.max(10, Math.min(100, prev.pct + delta));
      return { active: true, pct: new_pct };
    });
    if (indicator_timer_ref.current) clearTimeout(indicator_timer_ref.current);
    indicator_timer_ref.current = setTimeout(() => {
      set_bright_indicator((prev) => ({ ...prev, active: false }));
    }, 600);
  }, []);

  const skip_time = useCallback((delta: number) => {
    const video = get_active_video();
    if (!video) return;
    // 元数据未就绪（duration 为 NaN/Infinity）时不 seek，避免媒体管线挂起
    if (!isFinite(video.duration)) return;
    video.currentTime = Math.max(0, Math.min(video.currentTime + delta, video.duration));
    update_progress();
  }, [get_active_video, update_progress]);

  // 播放失败后重试当前视频
  const retry_current = useCallback(() => {
    const media = current_media;
    if (!media || !media.is_video) return;
    const url = `/media/serve_media/${encodeURIComponent(media.relative_path)}`;
    const active = get_active_video();
    if (active) {
      active.src = url;
      active.muted = is_muted;
      active.play().catch(() => {});
    }
    set_status("loading");
    set_error_msg("");
  }, [current_media, get_active_video, is_muted]);

  // ── 垂直拖拽跟手（抖音风格翻页）────────────────
  const reset_drag = useCallback(() => {
    cancel_offset_animation();
    drag_active_ref.current = false;
    drag_y_ref.current = 0;
    drag_direction_ref.current = "next";
    state_ref.current.is_transitioning = false;
  }, [cancel_offset_animation]);

  // 下一集不在历史里时，拖动期间立即拉取，让切换时尽量就绪
  const fetch_next_for_drag = useCallback(() => {
    if (preload_pending_ref.current) return;
    preload_pending_ref.current = true;
    api_client.get<{ code: number; data: MediaData }>("/api/douyin/next", { timeout: 8000 })
      .then((resp) => {
        if (resp.data.code === 0 && resp.data.data) {
          set_play_history((prev) => {
            const existing = prev.findIndex((m) => m.relative_path === resp.data.data.relative_path);
            if (existing >= 0) return prev;
            return [...prev, resp.data.data];
          });
          const url = `/media/serve_media/${encodeURIComponent(resp.data.data.relative_path)}`;
          set_slot_src((active_slot_ref.current + 1) % 3, url);
        }
      })
      .catch(() => {})
      .finally(() => { preload_pending_ref.current = false; });
  }, [set_slot_src]);

  const prepare_inactive_for_drag = useCallback((direction: "next" | "prev") => {
    const history = play_history_ref.current;
    const cur_idx = history_index_ref.current;
    if (direction === "next") {
      const next = history[cur_idx + 1];
      if (next) {
        const url = `/media/serve_media/${encodeURIComponent(next.relative_path)}`;
        set_slot_src((active_slot_ref.current + 1) % 3, url);
      } else {
        // 下一集未预载 → 立即拉取
        fetch_next_for_drag();
      }
    } else {
      const prev = history[cur_idx - 1];
      if (prev) {
        const url = `/media/serve_media/${encodeURIComponent(prev.relative_path)}`;
        set_slot_src((active_slot_ref.current + 2) % 3, url);
      }
    }
  }, [fetch_next_for_drag, set_slot_src]);

  // 新手势开始拖动：以当前画面偏移为基准（打断翻页动画时无缝接管）
  const handle_drag_start = useCallback(() => {
    base_offset_ref.current = drag_y_ref.current;
  }, []);

  const handle_drag_move = useCallback((dy: number) => {
    const direction: "next" | "prev" = dy < 0 ? "next" : "prev";
    // 打断进行中的翻页/回弹动画，从当前偏移继续跟手
    if (animating_ref.current) {
      cancel_offset_animation();
    }
    if (drag_direction_ref.current !== direction) {
      drag_direction_ref.current = direction;
      prepare_inactive_for_drag(direction);
    }
    if (!drag_active_ref.current) {
      drag_active_ref.current = true;
      state_ref.current.is_transitioning = true;
    }
    const offset = base_offset_ref.current + dy;
    drag_y_ref.current = offset;
    apply_drag_y(offset, direction);
  }, [prepare_inactive_for_drag, apply_drag_y, cancel_offset_animation]);

  // 翻页动画自然结束后完成缓冲切换（视觉已滑到位）
  const finish_drag_switch = useCallback((direction: "next" | "prev") => {
    const history = play_history_ref.current;
    const cur_idx = history_index_ref.current;
    if (direction === "next") {
      const next_idx = cur_idx + 1;
      if (next_idx < history.length) {
        set_history_index(next_idx);
        preload_index_ref.current = next_idx;
      } else {
        // 下一集仍未就绪 → 走 fetch 流程接管
        state_ref.current.is_transitioning = false;
        reset_drag();
        fetch_douyin_next();
        return;
      }
    } else {
      const prev_idx = cur_idx - 1;
      if (prev_idx >= 0) {
        set_history_index(prev_idx);
        preload_index_ref.current = prev_idx;
      } else {
        // 没有上一集 → 回弹
        reset_drag();
        return;
      }
    }
    // 交换缓冲 + 播放新视频（复用 finish_video_switch）
    state_ref.current.is_transitioning = true;
    finish_video_switch(direction);
    // 复位拖拽视觉（缓冲交换后 base 分支正确，避免闪回）
    drag_active_ref.current = false;
    drag_y_ref.current = 0;
  }, [fetch_douyin_next, finish_video_switch, reset_drag]);

  const handle_drag_end = useCallback((direction: "next" | "prev" | null) => {
    if (drag_timer_ref.current) clearTimeout(drag_timer_ref.current);
    if (direction === null) {
      // 松手不够距离/速度 → rAF 回弹到原位
      const start_y = drag_y_ref.current;
      start_offset_animation(start_y, 0, 200, () => {
        drag_active_ref.current = false;
        drag_y_ref.current = 0;
        state_ref.current.is_transitioning = false;
        schedule_next_preload();
      });
      return;
    }
    // 翻页：rAF 驱动到 ±屏幕高度，动画自然结束后完成切换
    const target_y = direction === "next" ? -window.innerHeight : window.innerHeight;
    start_offset_animation(drag_y_ref.current, target_y, 250, () => {
      finish_drag_switch(direction);
    });
  }, [finish_drag_switch, schedule_next_preload, start_offset_animation]);

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
      if (!video || !isFinite(video.duration)) return;
      const target = Math.max(0, Math.min(seek_base_ref.current + seconds, video.duration));
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
      const new_vol = Math.max(0, Math.min(1, (video.volume || 0) + delta));
      video.volume = new_vol;
      set_vol_indicator({ active: true, pct: Math.round(new_vol * 100) });
    },
    on_adjust_brightness: (delta: number) => {
      set_bright_indicator((prev) => {
        const new_pct = Math.max(10, Math.min(100, prev.pct + Math.round(delta * 100)));
        return { active: true, pct: new_pct };
      });
    },
    on_adjust_end: () => {
      if (indicator_timer_ref.current) clearTimeout(indicator_timer_ref.current);
      indicator_timer_ref.current = setTimeout(() => {
        set_vol_indicator((prev) => ({ ...prev, active: false }));
        set_bright_indicator((prev) => ({ ...prev, active: false }));
      }, 600);
    },
    on_drag_start: () => {
      handle_drag_start();
    },
    on_drag_move: (dy: number) => {
      handle_drag_move(dy);
    },
    on_drag_end: (direction: "next" | "prev" | null) => {
      handle_drag_end(direction);
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
  }), [handle_nav_next, handle_nav_prev, toggle_play, reset_controls_timer, get_active_video, selected_speed, show_video, current_media?.is_video, handle_drag_start, handle_drag_move, handle_drag_end]);

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

  const render_video_element = (ref: React.RefObject<HTMLVideoElement | null>, src: string, z_index: number | string, transform: string, transition: string, is_active: boolean) => (
    // 单一稳定结构：视频元素不随状态重挂载（避免黑屏/卡顿）
    <video
      ref={ref}
      src={src}
      poster={src ? src.replace("/media/serve_media/", "/media/thumbnail/") : ""}
      muted={is_muted}
      playsInline
      // 非当前缓冲用 metadata 轻量预载：减少拖动/切换时第二个解码器抢资源导致当前视频卡顿
      preload={is_grid ? "metadata" : is_active ? "auto" : "metadata"}
      className="absolute inset-0 h-full w-full object-contain bg-black"
      style={{ zIndex: z_index, transform, transition, willChange: "transform" }}
    />
  );

  // ── 三槽位定位 ────────────────────────────────────
  const slot_styles: React.CSSProperties[] = [{}, {}, {}];
  const cur_slot = active_slot;
  const prev_slot = (cur_slot + 2) % 3;
  const next_slot = (cur_slot + 1) % 3;

  if (drag_active_ref.current) {
    // 跟手/翻页/回弹共用：读 ref（与 imperative DOM 操作一致，重渲染时保持一致）
    const dy = drag_y_ref.current;
    slot_styles[cur_slot].transform = `translateY(${dy}px)`;
    slot_styles[cur_slot].transition = "none";
    slot_styles[cur_slot].zIndex = 2;
    slot_styles[prev_slot].transform = `translateY(calc(${dy}px - 100%))`;
    slot_styles[prev_slot].transition = "none";
    slot_styles[prev_slot].zIndex = 1;
    slot_styles[next_slot].transform = `translateY(calc(${dy}px + 100%))`;
    slot_styles[next_slot].transition = "none";
    slot_styles[next_slot].zIndex = 1;
  } else {
    // 静止：当前在最前，上一/下一在上下待命
    slot_styles[cur_slot].zIndex = 2;
    slot_styles[prev_slot].zIndex = 1;
    slot_styles[next_slot].zIndex = 1;
    slot_styles[prev_slot].transform = "translateY(-100%)";
    slot_styles[next_slot].transform = "translateY(100%)";
  }

  // 当前音量显示（设置面板）
  const active_video_el = get_slot_video(cur_slot);
  const vol_pct = Math.round((active_video_el?.volume || 0) * 100);

  return (
    <div
      ref={container_ref}
      className="fixed inset-0 overflow-hidden bg-black select-none touch-none"
      {...(!is_grid ? {
        onTouchStart: gesture.handle_touch_start,
        onTouchMove: gesture.handle_touch_move,
        onTouchEnd: gesture.handle_touch_end,
        onTouchCancel: () => handle_drag_end(null),
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
          {render_video_element(video_a_ref, video_a_src, slot_styles[0].zIndex ?? 1, slot_styles[0].transform || "", slot_styles[0].transition || "", cur_slot === 0)}
          {render_video_element(video_b_ref, video_b_src, slot_styles[1].zIndex ?? 1, slot_styles[1].transform || "", slot_styles[1].transition || "", cur_slot === 1)}
          {render_video_element(video_c_ref, video_c_src, slot_styles[2].zIndex ?? 1, slot_styles[2].transform || "", slot_styles[2].transition || "", cur_slot === 2)}
        </div>
      ) : (
        <img
          ref={image_ref}
          src={current_media ? `/media/serve_media/${encodeURIComponent(current_media.relative_path)}` : ""}
          alt={current_media?.name || ""}
          className="absolute inset-0 w-full h-full object-contain"
        />
      )}

      {/* ─── Brightness overlay（pct 持久生效，active 只控制指示条显隐）─── */}
      {!is_grid && (
        <div
          className="pointer-events-none absolute inset-0 bg-black transition-opacity"
          style={{ opacity: 1 - bright_indicator.pct / 100 }}
        />
      )}

      {/* ─── Loading / Error / End ──────────────────── */}
      {/* 只在完全无视频可显示（首帧未加载）时才转圈；有 src 就显示 poster 封面兜底，避免转圈盖住画面 */}
      {status === "loading" && !video_a_src && !video_b_src && !video_c_src && (
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
        <div className="absolute top-20 left-1/2 -translate-x-1/2 z-20 flex items-center gap-3 rounded-xl bg-danger/90 backdrop-blur px-4 py-2.5 text-sm font-medium text-white shadow-lg animate-fade-in">
          <span>{error_msg}</span>
          <button
            onClick={retry_current}
            className="shrink-0 rounded-md bg-white/20 px-3 py-1 text-xs font-semibold text-white hover:bg-white/30 transition"
          >
            重试
          </button>
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

      {/* ─── Center: Play/Pause + 左右两侧 Skip 按钮 ──── */}
      {controls_visible && show_video && !is_grid && (
        <div className="player-controls-area absolute inset-0 z-10 pointer-events-none">
          {/* 中心：播放/暂停 */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <button onClick={toggle_play} className="flex items-center justify-center rounded-full bg-white/15 w-16 h-16 text-white transition hover:bg-white/25 hover:scale-105 active:scale-95 pointer-events-auto">
              <svg className="h-7 w-7" fill="currentColor" viewBox="0 0 24 24">
                {show_video ? (is_playing ? <path d={PAUSE_ICON}/> : <path d={PLAY_ICON}/>) : <path d={PLAY_ICON}/>}
              </svg>
            </button>
          </div>
          {/* 左：后退 15s */}
          <button onClick={() => skip_time(-15)} className="absolute left-6 top-1/2 -translate-y-1/2 flex flex-col items-center justify-center rounded-full bg-white/10 w-14 h-14 text-white/80 transition hover:bg-white/20 hover:scale-105 active:scale-95 pointer-events-auto">
            <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/>
            </svg>
            <span className="text-[10px] font-medium mt-0.5">15</span>
          </button>
          {/* 右：前进 15s */}
          <button onClick={() => skip_time(15)} className="absolute right-6 top-1/2 -translate-y-1/2 flex flex-col items-center justify-center rounded-full bg-white/10 w-14 h-14 text-white/80 transition hover:bg-white/20 hover:scale-105 active:scale-95 pointer-events-auto">
            <svg className="h-5 w-5 rotate-180" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/>
            </svg>
            <span className="text-[10px] font-medium mt-0.5">15</span>
          </button>
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
                <div className="absolute bottom-full right-0 mb-2 rounded-xl bg-black/90 border border-white/10 py-1.5 shadow-xl backdrop-blur min-w-[190px] animate-fade-in">
                  <button
                    onClick={() => { toggle_mute(); set_settings_open(false); }}
                    className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-white/80 hover:bg-white/10 transition"
                  >
                    {is_muted ? "🔇 取消静音" : "🔊 静音"}
                  </button>
                  <div className="flex items-center justify-between px-4 py-2 text-sm text-white/80">
                    <span className="shrink-0">音量</span>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => step_volume(-0.1)}
                        className="h-7 w-7 rounded-md bg-white/10 text-white/80 hover:bg-white/20"
                      >−</button>
                      <span className="w-10 text-center text-xs text-white/50">{vol_pct}%</span>
                      <button
                        onClick={() => step_volume(0.1)}
                        className="h-7 w-7 rounded-md bg-white/10 text-white/80 hover:bg-white/20"
                      >+</button>
                    </div>
                  </div>
                  <div className="flex items-center justify-between px-4 py-2 text-sm text-white/80">
                    <span className="shrink-0">亮度</span>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => step_brightness(-10)}
                        className="h-7 w-7 rounded-md bg-white/10 text-white/80 hover:bg-white/20"
                      >−</button>
                      <span className="w-10 text-center text-xs text-white/50">{bright_indicator.pct}%</span>
                      <button
                        onClick={() => step_brightness(10)}
                        className="h-7 w-7 rounded-md bg-white/10 text-white/80 hover:bg-white/20"
                      >+</button>
                    </div>
                  </div>
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
        <div className="absolute top-20 left-1/2 -translate-x-1/2 z-30 rounded-xl bg-black/40 backdrop-blur-md px-4 py-2 text-base font-semibold text-white/60 shadow-lg">
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

      {/* ─── 横屏观看：设备竖屏时提示旋转 ────────────── */}
      {is_portrait && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-5 bg-black/90 text-white">
          <svg className="h-16 w-16 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
          </svg>
          <p className="text-base font-medium">请将手机横过来观看</p>
        </div>
      )}
    </div>
  );
}

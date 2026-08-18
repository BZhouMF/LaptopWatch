import { useRef, useCallback } from "react";

export interface GestureCallbacks {
  on_swipe_next: () => void;
  on_swipe_prev: () => void;
  on_toggle_play: () => void;
  on_toggle_controls: () => void;
  on_seek: (seconds: number) => void;
  on_seek_start: () => void;
  on_seek_end: () => void;
  on_drag_start: () => void;
  on_drag_move: (dy: number) => void;
  on_drag_end: (direction: "next" | "prev" | null) => void;
  on_adjust_volume: (delta: number) => void;
  on_adjust_brightness: (delta: number) => void;
  on_adjust_end: () => void;
  on_long_press_start: () => void;
  on_long_press_end: () => void;
  is_fullscreen: () => boolean;
  is_video_active: () => boolean;
}

const SWIPE_THRESHOLD = 60;   // 松手距离阈值（px）
const SWIPE_VELOCITY = 0.5;   // 松手速度阈值（px/ms）
const DRAG_DEADZONE = 10;     // 拖拽判定死区（px）
const SEEK_PX_PER_SEC = 5;
const ADJUST_SENSITIVITY = 400;  // 全屏下滑动调音量/亮度的灵敏度

export function usePlayerGestures(callbacks: GestureCallbacks) {
  const state_ref = useRef({
    touch_start_x: 0,
    touch_start_y: 0,
    touch_start_time: 0,
    touch_moved: false,
    touch_on_controls: false,
    is_seeking: false,
    drag_active: false,
    adjust_active: false,
    long_press_timer: null as ReturnType<typeof setTimeout> | null,
    click_timer: null as ReturnType<typeof setTimeout> | null,
  });

  const start_long_press = useCallback(() => {
    state_ref.current.long_press_timer = setTimeout(() => {
      callbacks.on_long_press_start();
    }, 500);
  }, [callbacks]);

  const cancel_long_press = useCallback(() => {
    if (state_ref.current.long_press_timer) {
      clearTimeout(state_ref.current.long_press_timer);
      state_ref.current.long_press_timer = null;
    }
    callbacks.on_long_press_end();
  }, [callbacks]);

  const handle_touch_start = useCallback(
    (event: React.TouchEvent) => {
      cancel_long_press();
      const touch = event.touches[0];
      state_ref.current.touch_start_x = touch.clientX;
      state_ref.current.touch_start_y = touch.clientY;
      state_ref.current.touch_start_time = Date.now();
      state_ref.current.touch_moved = false;
      state_ref.current.is_seeking = false;
      state_ref.current.drag_active = false;
      state_ref.current.adjust_active = false;
      state_ref.current.touch_on_controls = !!(event.target as HTMLElement).closest(".player-controls-area");
      if (!state_ref.current.touch_on_controls) start_long_press();
    },
    [start_long_press, cancel_long_press]
  );

  const handle_touch_move = useCallback(
    (event: React.TouchEvent) => {
      state_ref.current.touch_moved = true;
      cancel_long_press();
      if (state_ref.current.touch_on_controls) return;
      if (!callbacks.is_video_active()) return;

      const touch = event.touches[0];
      const dx = touch.clientX - state_ref.current.touch_start_x;
      const dy = touch.clientY - state_ref.current.touch_start_y;
      const abs_dx = Math.abs(dx);
      const abs_dy = Math.abs(dy);

      // 全屏模式：左右滑动调音量/亮度（左半屏=亮度，右半屏=音量），垂直不切视频
      if (callbacks.is_fullscreen()) {
        if (abs_dx > abs_dy && abs_dx > DRAG_DEADZONE) {
          state_ref.current.adjust_active = true;
          const left_half = touch.clientX < window.innerWidth / 2;
          if (left_half) callbacks.on_adjust_brightness(dx / ADJUST_SENSITIVITY);
          else callbacks.on_adjust_volume(dx / ADJUST_SENSITIVITY);
        }
        return;
      }

      // 垂直拖拽 → 跟手翻页（抖音风格：当前视频跟随手指，相邻视频在背后跟随）
      if (abs_dy > abs_dx && abs_dy > DRAG_DEADZONE) {
        if (!state_ref.current.drag_active) {
          state_ref.current.drag_active = true;
          callbacks.on_drag_start();
        }
        callbacks.on_drag_move(dy);
        return;
      }

      // 水平拖拽 → 进度拖动
      if (abs_dx > abs_dy && abs_dx > 15 && !state_ref.current.is_seeking) {
        state_ref.current.is_seeking = true;
        callbacks.on_seek_start();
      }
      if (state_ref.current.is_seeking) {
        callbacks.on_seek(dx / SEEK_PX_PER_SEC);
      }
    },
    [callbacks, cancel_long_press]
  );

  const handle_touch_end = useCallback(
    (event: React.TouchEvent) => {
      cancel_long_press();
      if (state_ref.current.adjust_active) {
        state_ref.current.adjust_active = false;
        callbacks.on_adjust_end();
        return;
      }
      if (state_ref.current.is_seeking) {
        state_ref.current.is_seeking = false;
        callbacks.on_seek_end();
        return;
      }
      if (state_ref.current.drag_active) {
        state_ref.current.drag_active = false;
        const touch = event.changedTouches[0];
        const dy = touch.clientY - state_ref.current.touch_start_y;
        const elapsed = Date.now() - state_ref.current.touch_start_time;
        const velocity = Math.abs(dy) / Math.max(elapsed, 1);
        const distance = Math.abs(dy);
        if (distance > SWIPE_THRESHOLD || velocity > SWIPE_VELOCITY) {
          callbacks.on_drag_end(dy < 0 ? "next" : "prev");
        } else {
          callbacks.on_drag_end(null);
        }
        return;
      }
      if (!state_ref.current.touch_moved || state_ref.current.touch_on_controls) return;
      const touch = event.changedTouches[0];
      const dy = touch.clientY - state_ref.current.touch_start_y;
      const dx = touch.clientX - state_ref.current.touch_start_x;
      if (Math.abs(dy) > Math.abs(dx) && Math.abs(dy) > SWIPE_THRESHOLD) {
        if (dy < 0) callbacks.on_swipe_next();
        else callbacks.on_swipe_prev();
      }
    },
    [callbacks, cancel_long_press]
  );

  const handle_click = useCallback(
    (event: React.MouseEvent) => {
      if ((event.target as HTMLElement).closest(".player-controls-area")) return;
      if (state_ref.current.click_timer) {
        clearTimeout(state_ref.current.click_timer);
        state_ref.current.click_timer = null;
        callbacks.on_toggle_play();
      } else {
        state_ref.current.click_timer = setTimeout(() => {
          state_ref.current.click_timer = null;
          callbacks.on_toggle_controls();
        }, 300);
      }
    },
    [callbacks]
  );

  const handle_mouse_down = useCallback(
    (event: React.MouseEvent) => {
      if ((event.target as HTMLElement).closest(".player-controls-area")) return;
      start_long_press();
    },
    [start_long_press]
  );

  const handle_wheel = useCallback(
    (event: React.WheelEvent) => {
      event.preventDefault();
      if (event.deltaY > 0) callbacks.on_swipe_next();
      else callbacks.on_swipe_prev();
    },
    [callbacks]
  );

  return {
    handle_touch_start,
    handle_touch_move,
    handle_touch_end,
    handle_click,
    handle_mouse_down,
    handle_mouse_up: cancel_long_press,
    handle_wheel,
  };
}

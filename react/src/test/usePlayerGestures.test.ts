import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { usePlayerGestures, type GestureCallbacks } from "../hooks/usePlayerGestures";

function make_callbacks(overrides?: Partial<GestureCallbacks>): GestureCallbacks {
  return {
    on_swipe_next: vi.fn(),
    on_swipe_prev: vi.fn(),
    on_toggle_play: vi.fn(),
    on_toggle_controls: vi.fn(),
    on_seek: vi.fn(),
    on_seek_start: vi.fn(),
    on_seek_end: vi.fn(),
    on_drag_start: vi.fn(),
    on_drag_move: vi.fn(),
    on_drag_end: vi.fn(),
    on_adjust_volume: vi.fn(),
    on_adjust_brightness: vi.fn(),
    on_adjust_end: vi.fn(),
    on_long_press_start: vi.fn(),
    on_long_press_end: vi.fn(),
    is_fullscreen: vi.fn(() => false),
    is_video_active: vi.fn(() => true),
    ...overrides,
  };
}

function fake_touch(target_cls = false): React.TouchEvent {
  const target = document.createElement("div");
  if (target_cls) target.className = "player-controls-area";
  return {
    touches: [{ clientX: 100, clientY: 200 } as Touch],
    changedTouches: [{ clientX: 100, clientY: 200 } as Touch],
    target,
  } as unknown as React.TouchEvent;
}

function fake_mouse(target?: HTMLElement): React.MouseEvent {
  return {
    target: target ?? document.createElement("div"),
  } as unknown as React.MouseEvent;
}

function fake_wheel(deltaY: number): React.WheelEvent {
  return {
    deltaY,
    preventDefault: vi.fn(),
  } as unknown as React.WheelEvent;
}

function move_touch(x: number, y: number): React.TouchEvent {
  return {
    touches: [{ clientX: x, clientY: y } as Touch],
  } as unknown as React.TouchEvent;
}

function end_touch(x: number, y: number): React.TouchEvent {
  return {
    changedTouches: [{ clientX: x, clientY: y } as Touch],
  } as unknown as React.TouchEvent;
}

describe("usePlayerGestures", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("calls on_drag_move then on_drag_end('next') on upward vertical swipe", () => {
    const cb = make_callbacks();
    const { result } = renderHook(() => usePlayerGestures(cb));

    act(() => {
      result.current.handle_touch_start(fake_touch());
    });
    act(() => {
      result.current.handle_touch_move(move_touch(110, 120));
    });
    act(() => {
      result.current.handle_touch_end(end_touch(110, 120));
    });

    expect(cb.on_drag_move).toHaveBeenCalledWith(-80);
    expect(cb.on_drag_end).toHaveBeenCalledWith("next");
    expect(cb.on_swipe_next).not.toHaveBeenCalled();
  });

  it("calls on_drag_end('prev') on downward vertical swipe", () => {
    const cb = make_callbacks();
    const { result } = renderHook(() => usePlayerGestures(cb));

    act(() => {
      result.current.handle_touch_start(fake_touch());
    });
    act(() => {
      result.current.handle_touch_move(move_touch(110, 300));
    });
    act(() => {
      result.current.handle_touch_end(end_touch(110, 300));
    });

    expect(cb.on_drag_move).toHaveBeenCalledWith(100);
    expect(cb.on_drag_end).toHaveBeenCalledWith("prev");
  });

  it("does not trigger drag/swipe if moved less than deadzone", () => {
    const cb = make_callbacks();
    const { result } = renderHook(() => usePlayerGestures(cb));

    act(() => {
      result.current.handle_touch_start(fake_touch());
    });
    act(() => {
      result.current.handle_touch_end(end_touch(105, 205));
    });

    expect(cb.on_drag_move).not.toHaveBeenCalled();
    expect(cb.on_drag_end).not.toHaveBeenCalled();
    expect(cb.on_swipe_next).not.toHaveBeenCalled();
    expect(cb.on_swipe_prev).not.toHaveBeenCalled();
  });

  it("fullscreen vertical swipe does NOT switch videos", () => {
    const cb = make_callbacks({ is_fullscreen: () => true });
    const { result } = renderHook(() => usePlayerGestures(cb));

    Object.defineProperty(window, "innerWidth", { value: 400, writable: true });

    act(() => {
      result.current.handle_touch_start(fake_touch());
    });
    act(() => {
      result.current.handle_touch_move(move_touch(110, 300));
    });
    act(() => {
      result.current.handle_touch_end(end_touch(110, 300));
    });

    expect(cb.on_drag_move).not.toHaveBeenCalled();
    expect(cb.on_drag_end).not.toHaveBeenCalled();
    expect(cb.on_swipe_next).not.toHaveBeenCalled();
  });

  it("fullscreen left-half horizontal swipe adjusts brightness", () => {
    const cb = make_callbacks({ is_fullscreen: () => true });
    const { result } = renderHook(() => usePlayerGestures(cb));

    Object.defineProperty(window, "innerWidth", { value: 400, writable: true });

    act(() => {
      result.current.handle_touch_start(fake_touch());
    });
    act(() => {
      result.current.handle_touch_move(move_touch(50, 200)); // 左半屏 clientX 50 < 200
    });
    act(() => {
      result.current.handle_touch_end(end_touch(50, 200));
    });

    expect(cb.on_adjust_brightness).toHaveBeenCalled();
    expect(cb.on_adjust_volume).not.toHaveBeenCalled();
    expect(cb.on_adjust_end).toHaveBeenCalled();
  });

  it("fullscreen right-half horizontal swipe adjusts volume", () => {
    const cb = make_callbacks({ is_fullscreen: () => true });
    const { result } = renderHook(() => usePlayerGestures(cb));

    Object.defineProperty(window, "innerWidth", { value: 400, writable: true });

    act(() => {
      result.current.handle_touch_start(fake_touch());
    });
    act(() => {
      result.current.handle_touch_move(move_touch(300, 200)); // 右半屏 clientX 300 > 200
    });
    act(() => {
      result.current.handle_touch_end(end_touch(300, 200));
    });

    expect(cb.on_adjust_volume).toHaveBeenCalled();
    expect(cb.on_adjust_brightness).not.toHaveBeenCalled();
  });

  it("starts long press timer on touch start", () => {
    const cb = make_callbacks();
    const { result } = renderHook(() => usePlayerGestures(cb));

    act(() => {
      result.current.handle_touch_start(fake_touch());
    });
    act(() => {
      vi.advanceTimersByTime(500);
    });

    expect(cb.on_long_press_start).toHaveBeenCalled();
  });

  it("cancels long press on touch move", () => {
    const cb = make_callbacks();
    const { result } = renderHook(() => usePlayerGestures(cb));

    act(() => {
      result.current.handle_touch_start(fake_touch());
    });
    act(() => {
      result.current.handle_touch_move(move_touch(120, 210));
    });
    act(() => {
      vi.advanceTimersByTime(500);
    });

    expect(cb.on_long_press_start).not.toHaveBeenCalled();
    expect(cb.on_long_press_end).toHaveBeenCalled();
  });

  it("single click fires on_toggle_controls after delay", () => {
    const cb = make_callbacks();
    const { result } = renderHook(() => usePlayerGestures(cb));

    act(() => {
      result.current.handle_click(fake_mouse());
    });
    expect(cb.on_toggle_controls).not.toHaveBeenCalled();
    expect(cb.on_toggle_play).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(300);
    });

    expect(cb.on_toggle_controls).toHaveBeenCalled();
    expect(cb.on_toggle_play).not.toHaveBeenCalled();
  });

  it("double click fires on_toggle_play", () => {
    const cb = make_callbacks();
    const { result } = renderHook(() => usePlayerGestures(cb));

    act(() => {
      result.current.handle_click(fake_mouse());
    });
    act(() => {
      result.current.handle_click(fake_mouse());
    });

    expect(cb.on_toggle_play).toHaveBeenCalled();
    expect(cb.on_toggle_controls).not.toHaveBeenCalled();
  });

  it("calls on_seek on horizontal touch move", () => {
    const cb = make_callbacks();
    const { result } = renderHook(() => usePlayerGestures(cb));

    act(() => {
      result.current.handle_touch_start(fake_touch());
    });
    act(() => {
      result.current.handle_touch_move(move_touch(150, 200));
    });

    expect(cb.on_seek_start).toHaveBeenCalled();
    expect(cb.on_seek).toHaveBeenCalledWith(50 / 5);
  });

  it("wheel down calls on_swipe_next", () => {
    const cb = make_callbacks();
    const { result } = renderHook(() => usePlayerGestures(cb));

    act(() => {
      result.current.handle_wheel(fake_wheel(100));
    });

    expect(cb.on_swipe_next).toHaveBeenCalled();
  });

  it("wheel up calls on_swipe_prev", () => {
    const cb = make_callbacks();
    const { result } = renderHook(() => usePlayerGestures(cb));

    act(() => {
      result.current.handle_wheel(fake_wheel(-100));
    });

    expect(cb.on_swipe_prev).toHaveBeenCalled();
  });

  it("skips gesture handling when video is not active", () => {
    const cb = make_callbacks({ is_video_active: () => false });
    const { result } = renderHook(() => usePlayerGestures(cb));

    act(() => {
      result.current.handle_touch_start(fake_touch());
    });
    act(() => {
      result.current.handle_touch_move(move_touch(150, 200));
    });

    expect(cb.on_seek_start).not.toHaveBeenCalled();
    expect(cb.on_drag_move).not.toHaveBeenCalled();
  });
});

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

describe("usePlayerGestures", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("calls on_swipe_next on upward vertical swipe", () => {
    const cb = make_callbacks();
    const { result } = renderHook(() => usePlayerGestures(cb));

    act(() => {
      result.current.handle_touch_start(fake_touch());
    });
    // Simulate upward swipe
    const evt = {
      touches: [{ clientX: 110, clientY: 120 } as Touch],
    } as unknown as React.TouchEvent;
    act(() => {
      result.current.handle_touch_move(evt);
    });
    const end_evt = {
      changedTouches: [{ clientX: 110, clientY: 120 } as Touch],
    } as unknown as React.TouchEvent;
    act(() => {
      result.current.handle_touch_end(end_evt);
    });

    expect(cb.on_swipe_next).toHaveBeenCalled();
  });

  it("calls on_swipe_prev on downward vertical swipe", () => {
    const cb = make_callbacks();
    const { result } = renderHook(() => usePlayerGestures(cb));

    act(() => {
      result.current.handle_touch_start(fake_touch());
    });
    const evt = {
      touches: [{ clientX: 110, clientY: 300 } as Touch],
    } as unknown as React.TouchEvent;
    act(() => {
      result.current.handle_touch_move(evt);
    });
    const end_evt = {
      changedTouches: [{ clientX: 110, clientY: 300 } as Touch],
    } as unknown as React.TouchEvent;
    act(() => {
      result.current.handle_touch_end(end_evt);
    });

    expect(cb.on_swipe_prev).toHaveBeenCalled();
  });

  it("does not trigger swipe if moved less than threshold", () => {
    const cb = make_callbacks();
    const { result } = renderHook(() => usePlayerGestures(cb));

    act(() => {
      result.current.handle_touch_start(fake_touch());
    });
    const end_evt = {
      changedTouches: [{ clientX: 105, clientY: 205 } as Touch],
    } as unknown as React.TouchEvent;
    act(() => {
      result.current.handle_touch_end(end_evt);
    });

    expect(cb.on_swipe_next).not.toHaveBeenCalled();
    expect(cb.on_swipe_prev).not.toHaveBeenCalled();
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
    const evt = {
      touches: [{ clientX: 120, clientY: 210 } as Touch],
    } as unknown as React.TouchEvent;
    act(() => {
      result.current.handle_touch_move(evt);
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

  it("calls on_seek on horizontal touch move in non-fullscreen", () => {
    const cb = make_callbacks();
    const { result } = renderHook(() => usePlayerGestures(cb));

    act(() => {
      result.current.handle_touch_start(fake_touch());
    });
    const evt = {
      touches: [{ clientX: 150, clientY: 200 } as Touch],
    } as unknown as React.TouchEvent;
    act(() => {
      result.current.handle_touch_move(evt);
    });

    expect(cb.on_seek_start).toHaveBeenCalled();
    expect(cb.on_seek).toHaveBeenCalledWith(50 / 5);
  });

  it("does not seek in fullscreen when dy > dx", () => {
    const cb = make_callbacks({ is_fullscreen: () => true });
    const { result } = renderHook(() => usePlayerGestures(cb));

    act(() => {
      result.current.handle_touch_start(fake_touch());
    });
    const evt = {
      touches: [{ clientX: 110, clientY: 300 } as Touch],
    } as unknown as React.TouchEvent;
    act(() => {
      result.current.handle_touch_move(evt);
    });

    // dy=100 > dx=10, should be volume or brightness, not seek
    expect(cb.on_seek_start).not.toHaveBeenCalled();
  });

  it("in fullscreen left-half vertical swipe adjusts brightness", () => {
    const cb = make_callbacks({ is_fullscreen: () => true });
    const { result } = renderHook(() => usePlayerGestures(cb));

    Object.defineProperty(window, "innerWidth", { value: 400, writable: true });

    act(() => {
      result.current.handle_touch_start({
        touches: [{ clientX: 100, clientY: 200 } as Touch],
        target: document.createElement("div"),
      } as unknown as React.TouchEvent);
    });
    const move_evt = {
      touches: [{ clientX: 110, clientY: 300 } as Touch],
      target: document.createElement("div"),
    } as unknown as React.TouchEvent;
    act(() => {
      result.current.handle_touch_move(move_evt);
    });

    expect(cb.on_adjust_brightness).toHaveBeenCalled();
  });

  it("in fullscreen right-half vertical swipe adjusts volume", () => {
    const cb = make_callbacks({ is_fullscreen: () => true });
    const { result } = renderHook(() => usePlayerGestures(cb));

    Object.defineProperty(window, "innerWidth", { value: 400, writable: true });

    act(() => {
      result.current.handle_touch_start({
        touches: [{ clientX: 300, clientY: 200 } as Touch],
        target: document.createElement("div"),
      } as unknown as React.TouchEvent);
    });
    const move_evt = {
      touches: [{ clientX: 310, clientY: 300 } as Touch],
      target: document.createElement("div"),
    } as unknown as React.TouchEvent;
    act(() => {
      result.current.handle_touch_move(move_evt);
    });

    expect(cb.on_adjust_volume).toHaveBeenCalled();
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
    const evt = {
      touches: [{ clientX: 150, clientY: 200 } as Touch],
    } as unknown as React.TouchEvent;
    act(() => {
      result.current.handle_touch_move(evt);
    });

    expect(cb.on_seek_start).not.toHaveBeenCalled();
  });
});

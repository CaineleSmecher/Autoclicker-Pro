#!/usr/bin/env python3
"""
AutoClicker Pro (Zero-Dependency Windows Edition)
==================================================
No external packages required — uses only Python's standard library
(tkinter for the GUI, ctypes to call the Windows API directly for
mouse/keyboard simulation and hotkey detection).

Requirements:
    - Windows OS
    - Python 3.8+ (with the standard Windows installer, which already
      includes tkinter and ctypes — nothing to pip install)

Run:
    python autoclicker.py
"""

import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

if sys.platform != "win32":
    raise SystemExit(
        "This zero-dependency edition uses the Windows API directly and "
        "only runs on Windows. See the README for the cross-platform "
        "version (requires 'pip install pynput')."
    )

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32

# ---------------------------------------------------------------------------
# Low-level Windows input simulation (SendInput) — no external deps needed.
# ---------------------------------------------------------------------------

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040

KEYEVENTF_KEYUP = 0x0002

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


def _send_input(inp: INPUT):
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def mouse_click(button="left"):
    down_map = {
        "left": MOUSEEVENTF_LEFTDOWN,
        "right": MOUSEEVENTF_RIGHTDOWN,
        "middle": MOUSEEVENTF_MIDDLEDOWN,
    }
    up_map = {
        "left": MOUSEEVENTF_LEFTUP,
        "right": MOUSEEVENTF_RIGHTUP,
        "middle": MOUSEEVENTF_MIDDLEUP,
    }
    down = INPUT(type=INPUT_MOUSE, union=INPUT_UNION(mi=MOUSEINPUT(0, 0, 0, down_map[button], 0, 0)))
    up = INPUT(type=INPUT_MOUSE, union=INPUT_UNION(mi=MOUSEINPUT(0, 0, 0, up_map[button], 0, 0)))
    _send_input(down)
    _send_input(up)


def key_press(vk_code: int):
    down = INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(ki=KEYBDINPUT(vk_code, 0, 0, 0, 0)))
    up = INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(ki=KEYBDINPUT(vk_code, 0, KEYEVENTF_KEYUP, 0, 0)))
    _send_input(down)
    _send_input(up)


def set_cursor_pos(x, y):
    user32.SetCursorPos(int(x), int(y))


def get_cursor_pos():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def is_key_down(vk_code: int) -> bool:
    # High-order bit set = key is currently pressed
    return bool(user32.GetAsyncKeyState(vk_code) & 0x8000)


# Virtual-key code table for the key names we expose in the UI
VK_MAP = {
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "shift": 0x10, "ctrl": 0x11, "alt": 0x12, "backspace": 0x08,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}


def resolve_vk(key_str: str) -> int:
    k = key_str.strip().lower()
    if k in VK_MAP:
        return VK_MAP[k]
    if len(k) == 1:
        # Letters/digits: virtual-key code equals ASCII uppercase value on Windows
        return ord(k.upper())
    return ord("A")


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class AutoClickerEngine:
    def __init__(self):
        self._thread = None
        self._stop_event = threading.Event()
        self.running = False

        self.mode = "mouse"
        self.mouse_button = "left"
        self.key = "space"
        self.interval_seconds = 0.01
        self.click_count = 0
        self.use_fixed_position = False
        self.fixed_position = (0, 0)
        self.on_stop_callback = None
        self.actions_done = 0

    def _loop(self):
        self.actions_done = 0
        vk = resolve_vk(self.key) if self.mode == "keyboard" else None

        if self.mode == "mouse" and self.use_fixed_position:
            set_cursor_pos(*self.fixed_position)

        next_tick = time.perf_counter()
        while not self._stop_event.is_set():
            if self.mode == "mouse":
                mouse_click(self.mouse_button)
            else:
                key_press(vk)

            self.actions_done += 1
            if self.click_count and self.actions_done >= self.click_count:
                break

            next_tick += self.interval_seconds
            sleep_for = next_tick - time.perf_counter()
            if sleep_for > 0:
                if sleep_for > 0.002:
                    time.sleep(sleep_for)
                else:
                    while time.perf_counter() < next_tick:
                        pass
            else:
                next_tick = time.perf_counter()

        self.running = False
        if self.on_stop_callback:
            self.on_stop_callback(self.actions_done)

    def start(self):
        if self.running:
            return
        self._stop_event.clear()
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        if not self.running:
            return
        self._stop_event.set()


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class AutoClickerApp:
    HOTKEY_OPTIONS = {"F6": 0x75, "F7": 0x76, "F8": 0x77, "F9": 0x78}

    def __init__(self, root):
        self.root = root
        self.root.title("AutoClicker Pro (No Install Needed)")
        self.root.resizable(False, False)
        self.engine = AutoClickerEngine()
        self.engine.on_stop_callback = self._on_engine_stopped

        self.picked_position = (0, 0)
        self._hotkey_was_down = False
        self._hotkey_stop_flag = threading.Event()

        self._build_ui()
        self._start_hotkey_watcher()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}
        frm = ttk.Frame(self.root, padding=12)
        frm.grid(row=0, column=0, sticky="nsew")

        mode_frame = ttk.LabelFrame(frm, text="Mode")
        mode_frame.grid(row=0, column=0, columnspan=2, sticky="ew", **pad)
        self.mode_var = tk.StringVar(value="mouse")
        ttk.Radiobutton(mode_frame, text="Mouse Click", variable=self.mode_var,
                         value="mouse", command=self._refresh_mode).pack(side="left", padx=10, pady=5)
        ttk.Radiobutton(mode_frame, text="Key Press", variable=self.mode_var,
                         value="keyboard", command=self._refresh_mode).pack(side="left", padx=10, pady=5)

        self.mouse_frame = ttk.LabelFrame(frm, text="Mouse Options")
        self.mouse_frame.grid(row=1, column=0, columnspan=2, sticky="ew", **pad)
        ttk.Label(self.mouse_frame, text="Button:").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.button_var = tk.StringVar(value="left")
        ttk.Combobox(self.mouse_frame, textvariable=self.button_var,
                     values=["left", "right", "middle"], width=10, state="readonly"
                     ).grid(row=0, column=1, sticky="w", padx=8, pady=4)

        self.pos_var = tk.StringVar(value="current")
        ttk.Radiobutton(self.mouse_frame, text="Click at current cursor position",
                         variable=self.pos_var, value="current").grid(row=1, column=0, columnspan=2, sticky="w", padx=8)
        pos_row = ttk.Frame(self.mouse_frame)
        pos_row.grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 6))
        ttk.Radiobutton(pos_row, text="Click at fixed position:",
                         variable=self.pos_var, value="fixed").pack(side="left")
        self.pos_label = ttk.Label(pos_row, text="(not set)")
        self.pos_label.pack(side="left", padx=6)
        ttk.Button(pos_row, text="Pick (hover target within 3s)",
                   command=self._pick_position).pack(side="left", padx=6)

        self.key_frame = ttk.LabelFrame(frm, text="Key Options")
        self.key_frame.grid(row=2, column=0, columnspan=2, sticky="ew", **pad)
        ttk.Label(self.key_frame, text="Key to press:").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.key_var = tk.StringVar(value="space")
        ttk.Entry(self.key_frame, textvariable=self.key_var, width=12).grid(row=0, column=1, sticky="w", padx=8, pady=4)
        ttk.Label(self.key_frame, text="e.g. a, space, enter, f5, tab").grid(row=0, column=2, sticky="w", padx=4)

        speed_frame = ttk.LabelFrame(frm, text="Speed")
        speed_frame.grid(row=3, column=0, columnspan=2, sticky="ew", **pad)
        ttk.Label(speed_frame, text="Interval:").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.interval_var = tk.StringVar(value="10")
        ttk.Entry(speed_frame, textvariable=self.interval_var, width=8).grid(row=0, column=1, sticky="w", padx=4)
        self.unit_var = tk.StringVar(value="ms")
        ttk.Combobox(speed_frame, textvariable=self.unit_var, values=["ms", "sec"],
                     width=5, state="readonly").grid(row=0, column=2, sticky="w", padx=4)
        ttk.Label(speed_frame, text="(as low as 1 ms — real max speed depends on your hardware)"
                  ).grid(row=1, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 4))

        count_frame = ttk.LabelFrame(frm, text="Repeat")
        count_frame.grid(row=4, column=0, columnspan=2, sticky="ew", **pad)
        self.repeat_var = tk.StringVar(value="infinite")
        ttk.Radiobutton(count_frame, text="Until stopped", variable=self.repeat_var,
                         value="infinite").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        row2 = ttk.Frame(count_frame)
        row2.grid(row=1, column=0, sticky="w", padx=8, pady=(0, 6))
        ttk.Radiobutton(row2, text="Fixed number of times:", variable=self.repeat_var,
                         value="fixed").pack(side="left")
        self.count_var = tk.StringVar(value="100")
        ttk.Entry(row2, textvariable=self.count_var, width=8).pack(side="left", padx=6)

        hk_frame = ttk.LabelFrame(frm, text="Hotkey")
        hk_frame.grid(row=5, column=0, columnspan=2, sticky="ew", **pad)
        ttk.Label(hk_frame, text="Start/Stop hotkey:").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.hotkey_var = tk.StringVar(value="F6")
        ttk.Combobox(hk_frame, textvariable=self.hotkey_var, values=list(self.HOTKEY_OPTIONS.keys()),
                     width=6, state="readonly").grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(hk_frame, text="works globally, even if this window isn't focused"
                  ).grid(row=0, column=2, sticky="w", padx=4)

        ctrl_frame = ttk.Frame(frm)
        ctrl_frame.grid(row=6, column=0, columnspan=2, sticky="ew", **pad)
        self.start_btn = ttk.Button(ctrl_frame, text="Start (or press hotkey)", command=self.toggle)
        self.start_btn.pack(side="left", padx=4)
        self.status_label = ttk.Label(ctrl_frame, text="Status: Stopped", foreground="red")
        self.status_label.pack(side="left", padx=16)

        self.count_label = ttk.Label(frm, text="Actions performed: 0")
        self.count_label.grid(row=7, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 6))

        self._refresh_mode()

    def _refresh_mode(self):
        if self.mode_var.get() == "mouse":
            self.mouse_frame.grid()
            self.key_frame.grid_remove()
        else:
            self.mouse_frame.grid_remove()
            self.key_frame.grid()

    def _pick_position(self):
        self.status_label.config(text="Status: move mouse to target, capturing in 3s...", foreground="orange")

        def capture():
            time.sleep(3)
            self.picked_position = get_cursor_pos()
            self.pos_var.set("fixed")
            self.pos_label.config(text=f"({self.picked_position[0]}, {self.picked_position[1]})")
            self.status_label.config(text="Status: Stopped", foreground="red")

        threading.Thread(target=capture, daemon=True).start()

    def _gather_config(self):
        engine = self.engine
        engine.mode = self.mode_var.get()

        if engine.mode == "mouse":
            engine.mouse_button = self.button_var.get()
            engine.use_fixed_position = (self.pos_var.get() == "fixed")
            engine.fixed_position = self.picked_position
        else:
            engine.key = self.key_var.get()

        try:
            interval = float(self.interval_var.get())
        except ValueError:
            interval = 10.0
        if self.unit_var.get() == "ms":
            interval = interval / 1000.0
        engine.interval_seconds = max(interval, 0.0001)

        if self.repeat_var.get() == "fixed":
            try:
                engine.click_count = max(0, int(self.count_var.get()))
            except ValueError:
                engine.click_count = 0
        else:
            engine.click_count = 0

    def toggle(self):
        if self.engine.running:
            self.engine.stop()
        else:
            self._gather_config()
            self.engine.start()
            self.status_label.config(text="Status: Running", foreground="green")
            self.start_btn.config(text="Stop (or press hotkey)")

    def _on_engine_stopped(self, actions_done):
        def update():
            self.status_label.config(text="Status: Stopped", foreground="red")
            self.start_btn.config(text="Start (or press hotkey)")
            self.count_label.config(text=f"Actions performed: {actions_done}")
        self.root.after(0, update)

    def _start_hotkey_watcher(self):
        """Poll GetAsyncKeyState in a background thread — no external hook lib needed."""
        def watch():
            while not self._hotkey_stop_flag.is_set():
                vk = self.HOTKEY_OPTIONS[self.hotkey_var.get()]
                down = is_key_down(vk)
                if down and not self._hotkey_was_down:
                    self.root.after(0, self.toggle)
                self._hotkey_was_down = down
                time.sleep(0.03)

        t = threading.Thread(target=watch, daemon=True)
        t.start()
        self._hotkey_thread = t


def main():
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass
    app = AutoClickerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

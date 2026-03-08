from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Iterable, Optional

ULONG_PTR = getattr(wintypes, "ULONG_PTR", ctypes.c_size_t)

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class KeyBdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class InputUnion(ctypes.Union):
    _fields_ = [("ki", KeyBdInput), ("mi", MouseInput), ("hi", HardwareInput)]


class Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("ii", InputUnion)]


SendInput = user32.SendInput
SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int)
SendInput.restype = wintypes.UINT

MapVirtualKeyW = user32.MapVirtualKeyW
MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
MapVirtualKeyW.restype = wintypes.UINT

FindWindowW = user32.FindWindowW
FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
FindWindowW.restype = wintypes.HWND

IsWindowVisible = user32.IsWindowVisible
IsWindowVisible.argtypes = (wintypes.HWND,)
IsWindowVisible.restype = wintypes.BOOL

GetWindowRect = user32.GetWindowRect
GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(RECT))
GetWindowRect.restype = wintypes.BOOL

WindowFromPoint = user32.WindowFromPoint
WindowFromPoint.argtypes = (POINT,)
WindowFromPoint.restype = wintypes.HWND

GetParent = user32.GetParent
GetParent.argtypes = (wintypes.HWND,)
GetParent.restype = wintypes.HWND

GetAsyncKeyState = user32.GetAsyncKeyState
GetAsyncKeyState.argtypes = (wintypes.INT,)
GetAsyncKeyState.restype = wintypes.SHORT

GetCursorPos = user32.GetCursorPos
GetCursorPos.argtypes = (ctypes.POINTER(POINT),)
GetCursorPos.restype = wintypes.BOOL

SCANCODES = {
    "esc": 0x01,
    "w": 0x11,
    "e": 0x12,
    "f": 0x21,
    "space": 0x39,
    "shift": 0x2A,
    "ctrl": 0x1D,
    "i": 0x17,
    "o": 0x18,
    "p": 0x19,
    "q": 0x10,
    "r": 0x13,
}

VKCODES = {
    "left_mouse": 0x01,
    "right_mouse": 0x02,
    "esc": 0x1B,
    "w": 0x57,
    "e": 0x45,
    "f": 0x46,
    "space": 0x20,
    "shift": 0x10,
    "ctrl": 0x11,
    "i": 0x49,
    "o": 0x4F,
    "p": 0x50,
    "q": 0x51,
    "r": 0x52,
}

ROUTE_RECORD_KEYS = ["w", "f", "e", "ctrl", "space", "shift"]
ROUTE_RECORD_MOUSE_BUTTONS = ["left", "right"]


class WindowsController:
    def __init__(self, config: dict):
        self.config = config
        self._last_taskbar_warn_ts = 0.0

    def is_running_as_admin(self) -> bool:
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def get_foreground_window_title(self) -> str:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value

    def is_game_window_foreground(self) -> bool:
        if not self.config.get("only_when_foreground", True):
            return True
        title = self.get_foreground_window_title().lower()
        keywords = [item.lower() for item in self.config.get("game_window_keywords", [])]
        return any(keyword in title for keyword in keywords)

    def is_taskbar_visible(self) -> bool:
        tray = FindWindowW("Shell_TrayWnd", None)
        if not tray:
            return False
        if not IsWindowVisible(tray):
            return False

        rect = RECT()
        if not GetWindowRect(tray, ctypes.byref(rect)):
            return False

        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width <= 0 or height <= 0:
            return False

        sample_x = rect.left + max(width // 2, 1)
        sample_y = rect.top + max(height // 2, 1)
        hit_hwnd = WindowFromPoint(POINT(sample_x, sample_y))
        if not hit_hwnd:
            return False

        current = hit_hwnd
        while current:
            if current == tray:
                return True
            current = GetParent(current)
        return False

    def can_send_keyboard_input(self) -> bool:
        if not self.config.get("block_keyboard_when_taskbar_visible", True):
            return True
        if not self.is_taskbar_visible():
            return True

        now = time.time()
        if now - self._last_taskbar_warn_ts >= 2.0:
            print("[INFO] Taskbar is visible. Keyboard injection paused.")
            self._last_taskbar_warn_ts = now
        return False

    def _send_input(self, inputs) -> bool:
        input_array = (Input * len(inputs))(*inputs)
        sent = SendInput(len(inputs), input_array, ctypes.sizeof(Input))
        if sent != len(inputs):
            err = ctypes.get_last_error()
            print(f"[WARN] SendInput failed: sent={sent}/{len(inputs)}, WinError={err}")
            return False
        return True

    def _send_key_scancode(self, scancode: int, keyup: bool = False) -> bool:
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if keyup else 0)
        ii_ = InputUnion()
        ii_.ki = KeyBdInput(0, scancode, flags, 0, 0)
        return self._send_input([Input(INPUT_KEYBOARD, ii_)])

    def _send_key_vk(self, vk_code: int, keyup: bool = False) -> bool:
        flags = KEYEVENTF_KEYUP if keyup else 0
        ii_ = InputUnion()
        ii_.ki = KeyBdInput(vk_code, 0, flags, 0, 0)
        return self._send_input([Input(INPUT_KEYBOARD, ii_)])

    def _resolve_scancode(self, key: str) -> Optional[int]:
        vk_code = VKCODES.get(key)
        if vk_code is None:
            return SCANCODES.get(key)
        mapped = MapVirtualKeyW(vk_code, 0)
        return mapped if mapped else SCANCODES.get(key)

    def is_physical_key_down(self, key: str) -> bool:
        vk_code = VKCODES.get(key)
        if vk_code is None:
            return False
        return bool(GetAsyncKeyState(vk_code) & 0x8000)

    def get_cursor_position(self) -> Optional[POINT]:
        pt = POINT()
        if not GetCursorPos(ctypes.byref(pt)):
            return None
        return pt

    def move_cursor_absolute(self, x_pos: int, y_pos: int):
        screen_width = user32.GetSystemMetrics(0)
        screen_height = user32.GetSystemMetrics(1)
        x_pos = max(0, min(int(x_pos), screen_width - 1))
        y_pos = max(0, min(int(y_pos), screen_height - 1))
        abs_x = int(x_pos * 65535 / max(screen_width - 1, 1))
        abs_y = int(y_pos * 65535 / max(screen_height - 1, 1))

        ii_ = InputUnion()
        ii_.mi = MouseInput(abs_x, abs_y, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, 0, 0)
        self._send_input([Input(INPUT_MOUSE, ii_)])

    def nudge_cursor_relative(self, px: int = 1):
        if px == 0:
            return
        ii_ = InputUnion()
        ii_.mi = MouseInput(px, 0, 0, MOUSEEVENTF_MOVE, 0, 0)
        back = InputUnion()
        back.mi = MouseInput(-px, 0, 0, MOUSEEVENTF_MOVE, 0, 0)
        self._send_input([Input(INPUT_MOUSE, ii_), Input(INPUT_MOUSE, back)])

    def move_mouse_relative(self, dx: int = 0, dy: int = 0):
        if dx == 0 and dy == 0:
            return
        ii_ = InputUnion()
        ii_.mi = MouseInput(int(dx), int(dy), 0, MOUSEEVENTF_MOVE, 0, 0)
        self._send_input([Input(INPUT_MOUSE, ii_)])

    def _resolve_mouse_button_flags(self, button: str):
        button = str(button).strip().lower()
        if button == "left":
            return MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
        if button == "right":
            return MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
        return None, None

    def mouse_button_down(self, button: str) -> bool:
        down_flag, _ = self._resolve_mouse_button_flags(button)
        if down_flag is None:
            return False
        ii_ = InputUnion()
        ii_.mi = MouseInput(0, 0, 0, down_flag, 0, 0)
        return self._send_input([Input(INPUT_MOUSE, ii_)])

    def mouse_button_up(self, button: str) -> bool:
        _, up_flag = self._resolve_mouse_button_flags(button)
        if up_flag is None:
            return False
        ii_ = InputUnion()
        ii_.mi = MouseInput(0, 0, 0, up_flag, 0, 0)
        return self._send_input([Input(INPUT_MOUSE, ii_)])

    def release_mouse_buttons(self, buttons: Iterable[str]):
        for button in buttons:
            self.mouse_button_up(button)

    def is_physical_mouse_button_down(self, button: str) -> bool:
        button = str(button).strip().lower()
        if button == "left":
            vk_code = VKCODES["left_mouse"]
        elif button == "right":
            vk_code = VKCODES["right_mouse"]
        else:
            return False
        return bool(GetAsyncKeyState(vk_code) & 0x8000)

    def left_click(self, hold_delay: float = 0.1):
        self.mouse_button_down("left")
        time.sleep(hold_delay)
        self.mouse_button_up("left")

    def left_double_click(self, hold_delay: float = 0.06, interval: float = 0.05):
        self.left_click(hold_delay=hold_delay)
        time.sleep(interval)
        self.left_click(hold_delay=hold_delay)

    def press_key(self, key: str, delay: float = 0.1):
        if not self.can_send_keyboard_input():
            return
        if key not in VKCODES and key not in SCANCODES:
            return

        scancode = self._resolve_scancode(key)
        vk_code = VKCODES.get(key)

        pressed = False
        if scancode:
            pressed = self._send_key_scancode(scancode, keyup=False)
        if not pressed and vk_code:
            pressed = self._send_key_vk(vk_code, keyup=False)

        time.sleep(delay)

        released = False
        if scancode:
            released = self._send_key_scancode(scancode, keyup=True)
        if not released and vk_code:
            self._send_key_vk(vk_code, keyup=True)

    def key_down(self, key: str) -> bool:
        if not self.can_send_keyboard_input():
            return False
        if key not in VKCODES and key not in SCANCODES:
            return False

        scancode = self._resolve_scancode(key)
        vk_code = VKCODES.get(key)

        pressed = False
        if scancode:
            pressed = self._send_key_scancode(scancode, keyup=False)
        if not pressed and vk_code:
            pressed = self._send_key_vk(vk_code, keyup=False)
        return pressed

    def key_up(self, key: str) -> bool:
        if key not in VKCODES and key not in SCANCODES:
            return False

        scancode = self._resolve_scancode(key)
        vk_code = VKCODES.get(key)

        released = False
        if scancode:
            released = self._send_key_scancode(scancode, keyup=True)
        if not released and vk_code:
            released = self._send_key_vk(vk_code, keyup=True)
        return released

    def release_keys(self, keys: Iterable[str]):
        for key in keys:
            self.key_up(key)

    def move_and_click(self, x_pos: int, y_pos: int, delay: float = 0.1):
        top_left_x = int(self.config.get("click_reset_x", 2))
        top_left_y = int(self.config.get("click_reset_y", 2))
        self.move_cursor_absolute(top_left_x, top_left_y)
        self.nudge_cursor_relative(px=2)
        time.sleep(float(self.config.get("click_reset_delay", 0.12)))

        self.move_cursor_absolute(x_pos, y_pos)
        time.sleep(float(self.config.get("click_target_settle_delay", 0.08)))

        verify = self.get_cursor_position()
        if verify and (abs(verify.x - x_pos) > 3 or abs(verify.y - y_pos) > 3):
            self.move_cursor_absolute(x_pos, y_pos)
            time.sleep(0.05)

        self.nudge_cursor_relative(px=-2)
        time.sleep(0.02)
        self.nudge_cursor_relative(px=2)
        time.sleep(0.06)

        self.left_click(hold_delay=delay)
        time.sleep(0.05)
        self.nudge_cursor_relative(px=1)
        self.left_click(hold_delay=0.08)

# -*- coding: utf-8 -*-
"""全局快捷键管理。

在独立线程中通过 RegisterHotKey 注册系统级热键（软件不在前台也有效），
消息循环收到 WM_HOTKEY 后回调。退出时注销热键并结束线程。
"""

import ctypes
import threading
from ctypes import wintypes

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_CONTROL = 0x0002
MOD_ALT = 0x0001
MOD_NOREPEAT = 0x4000

VK_F8 = 0x77
VK_F9 = 0x78

HOTKEY_TOGGLE = 1   # Ctrl+Alt+F8 暂停/继续
HOTKEY_STOP = 2     # Ctrl+Alt+F9 停止

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND),
                ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM),
                ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD),
                ("pt", wintypes.POINT)]


class HotkeyManager:
    """注册全局热键并派发回调。start() 后 hotkeys_ok 表示是否全部注册成功。"""

    def __init__(self, on_toggle_pause, on_stop):
        self._on_toggle = on_toggle_pause
        self._on_stop = on_stop
        self._thread = None
        self._thread_id = 0
        self.hotkeys_ok = False
        self.failed_names = []

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="HotkeyLoop")
        self._thread.start()

    def stop(self):
        """注销热键并结束消息循环线程。"""
        tid = self._thread_id
        if tid:
            _user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(1.0)
        self._thread_id = 0
        self._thread = None

    # ---------- 内部 ----------

    def _loop(self):
        self._thread_id = _kernel32.GetCurrentThreadId()
        ok_toggle = _user32.RegisterHotKey(None, HOTKEY_TOGGLE,
                                           MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_F8)
        ok_stop = _user32.RegisterHotKey(None, HOTKEY_STOP,
                                         MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_F9)
        self.hotkeys_ok = ok_toggle and ok_stop
        if not ok_toggle:
            self.failed_names.append("Ctrl+Alt+F8")
        if not ok_stop:
            self.failed_names.append("Ctrl+Alt+F9")
        msg = MSG()
        # GetMessage 返回 0 表示收到 WM_QUIT，-1 表示错误
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                if msg.wParam == HOTKEY_TOGGLE:
                    self._safe_call(self._on_toggle)
                elif msg.wParam == HOTKEY_STOP:
                    self._safe_call(self._on_stop)
        # 循环退出后注销热键
        _user32.UnregisterHotKey(None, HOTKEY_TOGGLE)
        _user32.UnregisterHotKey(None, HOTKEY_STOP)

    @staticmethod
    def _safe_call(func):
        try:
            func()
        except Exception:
            pass

# -*- coding: utf-8 -*-
"""按键发送与任务控制。

使用 Windows SendInput API 以扫描码方式发送按键（兼容性最好），
独立工作线程按高精度计时发送，支持线程安全的暂停/继续/停止。
"""

import ctypes
import enum
import threading
import time

from ctypes import wintypes

# ---------------- 常量与按键表 ----------------

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

# 鼠标事件标志（在鼠标当前位置点击，不移动鼠标）
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040

# 虚拟键码 -> 扫描码（集合1标准扫描码）
KEY_TABLE = {
    "F1":  (0x70, 0x3B), "F2":  (0x71, 0x3C), "F3":  (0x72, 0x3D), "F4":  (0x73, 0x3E),
    "F5":  (0x74, 0x3F), "F6":  (0x75, 0x40), "F7":  (0x76, 0x41), "F8":  (0x77, 0x42),
    "F9":  (0x78, 0x43), "F10": (0x79, 0x44), "F11": (0x7A, 0x57), "F12": (0x7B, 0x58),
    "F13": (0x7C, 0x64), "F14": (0x7D, 0x65), "F15": (0x7E, 0x66), "F16": (0x7F, 0x67),
    "F17": (0x80, 0x68), "F18": (0x81, 0x69), "F19": (0x82, 0x6A), "F20": (0x83, 0x6B),
    "F21": (0x84, 0x6C), "F22": (0x85, 0x6D), "F23": (0x86, 0x6E), "F24": (0x87, 0x76),
}

# 鼠标按键 -> (按下标志, 抬起标志)
MOUSE_TABLE = {
    "鼠标左键": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "鼠标右键": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "鼠标中键": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


def is_supported_key(name):
    return name in MOUSE_TABLE or name in KEY_TABLE

DEFAULT_KEY = "F15"
DEFAULT_COUNT = 100000
DEFAULT_RATE = 500
MAX_COUNT = 100000000
MIN_RATE = 1
MAX_RATE = 5000
TEST_RATE = 25          # 测试 100 次固定用较慢频率，便于观察
MAX_CONSECUTIVE_FAILS = 5
MAX_BATCH = 32          # 单次 SendInput 最多合并的按键数（系统慢时自动批量补发）


class TaskState(enum.Enum):
    IDLE = "未开始"
    RUNNING = "运行中"
    PAUSED = "已暂停"
    STOPPED = "已停止"
    COMPLETED = "已完成"
    ERROR = "运行异常"


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG),
                ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD),
                ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _INPUT(ctypes.Structure):
    # 联合体必须包含全部三个成员，保证 sizeof(INPUT) 与系统一致（x64 上为 40）
    class _U(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_winmm = ctypes.windll.winmm


class KeyController:
    """线程安全的任务控制器，所有方法均可在任意线程调用。"""

    def __init__(self):
        self._lock = threading.RLock()
        self._thread = None
        self._state = TaskState.IDLE
        self._last_error = ""
        self._is_test = False
        # 任务参数（快照，供界面显示）
        self._target = 0
        self._rate = 0
        self._key = DEFAULT_KEY
        # 控制标志：_resume_evt 置位=运行中；清除=暂停（工作线程在 wait() 上休眠）
        self._stop_evt = threading.Event()
        self._resume_evt = threading.Event()
        # 由界面注入的回调：返回本程序窗口的全局矩形 (x1, y1, x2, y2)，
        # 鼠标连点时指针落在窗口内则跳过发送，防止点到自己
        self._window_probe = None

    def set_own_window_probe(self, probe):
        self._window_probe = probe
        # 统计（由工作线程更新）
        self._sent = 0
        self._active_seconds = 0.0   # 不含暂停时间的实际运行秒数
        self._failed_sends = 0

    # ---------- 对外控制接口 ----------

    def start(self, key, target, rate, is_test=False):
        """启动新任务。参数非法抛 ValueError；已在运行返回 False。"""
        if not is_supported_key(key):
            raise ValueError("不支持的按键：%s" % key)
        if not isinstance(target, int) or target < 1 or target > MAX_COUNT:
            raise ValueError("目标次数必须在 1 ~ %d 之间" % MAX_COUNT)
        if not isinstance(rate, int) or rate < MIN_RATE or rate > MAX_RATE:
            raise ValueError("每秒次数必须在 %d ~ %d 之间" % (MIN_RATE, MAX_RATE))
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._key, self._target, self._rate = key, target, rate
            self._is_test = is_test
            self._state = TaskState.RUNNING
            self._last_error = ""
            self._sent = 0
            self._failed_sends = 0
            self._active_seconds = 0.0
            self._stop_evt.clear()
            self._resume_evt.set()
            self._thread = threading.Thread(target=self._run, daemon=True,
                                            name="KeyTaskWorker")
            self._thread.start()
            return True

    def pause(self):
        with self._lock:
            if self._state == TaskState.RUNNING:
                self._resume_evt.clear()
                self._state = TaskState.PAUSED

    def resume(self):
        with self._lock:
            if self._state == TaskState.PAUSED:
                self._resume_evt.set()
                self._state = TaskState.RUNNING

    def toggle_pause(self):
        with self._lock:
            if self._state == TaskState.RUNNING:
                self.pause()
            elif self._state == TaskState.PAUSED:
                self.resume()

    def stop(self):
        with self._lock:
            if self._state in (TaskState.RUNNING, TaskState.PAUSED):
                self._stop_evt.set()
                self._resume_evt.set()   # 唤醒暂停中的线程以便退出
                self._state = TaskState.STOPPED

    def shutdown(self, join_timeout=2.0):
        """程序退出时调用：停止任务并等待线程结束。"""
        self.stop()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(join_timeout)
        with self._lock:
            if self._state in (TaskState.RUNNING, TaskState.PAUSED):
                self._state = TaskState.STOPPED

    def is_busy(self):
        with self._lock:
            return self._state in (TaskState.RUNNING, TaskState.PAUSED)

    # ---------- 统计快照 ----------

    def snapshot(self):
        """返回当前统计信息字典（线程安全）。"""
        with self._lock:
            state = self._state
            sent = self._sent
            target = self._target
            active = self._active_seconds
            avg_rate = (sent / active) if active > 0.05 else 0.0
            remaining_keys = max(0, target - sent)
            if state == TaskState.PAUSED or avg_rate <= 0:
                eta = None
            else:
                eta = remaining_keys / avg_rate
            percent = (sent * 100.0 / target) if target > 0 else 0.0
            return {
                "state": state,
                "state_text": state.value,
                "sent": sent,
                "target": target,
                "percent": min(100.0, percent),
                "avg_rate": avg_rate,
                "eta_seconds": eta,
                "key": self._key,
                "rate": self._rate,
                "is_test": self._is_test,
                "last_error": self._last_error,
            }

    # ---------- 工作线程 ----------

    def _send_keys(self, n):
        """一次 SendInput 调用发送 n 个完整按键（按下+抬起）。

        返回 (成功注入的按键数, 是否完全成功)。
        """
        size = ctypes.sizeof(_INPUT)
        inputs = (_INPUT * (n * 2))()
        if self._key in MOUSE_TABLE:
            down, up = MOUSE_TABLE[self._key]
            for i in range(n):
                inputs[i * 2].type = INPUT_MOUSE
                inputs[i * 2].u.mi.dwFlags = down
                inputs[i * 2 + 1].type = INPUT_MOUSE
                inputs[i * 2 + 1].u.mi.dwFlags = up
        else:
            _, scan = KEY_TABLE[self._key]
            for i in range(n):
                inputs[i * 2].type = INPUT_KEYBOARD
                inputs[i * 2].u.ki.wScan = scan
                inputs[i * 2].u.ki.dwFlags = KEYEVENTF_SCANCODE
                inputs[i * 2 + 1].type = INPUT_KEYBOARD
                inputs[i * 2 + 1].u.ki.wScan = scan
                inputs[i * 2 + 1].u.ki.dwFlags = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP
        injected = _user32.SendInput(n * 2, inputs, size)
        if injected == n * 2:
            return n, True
        return injected // 2, False

    def _wait_until(self, t):
        """睡眠到指定时刻：先粗睡，最后 1.5ms 微旋等待，兼顾精度与 CPU。"""
        remain = t - time.perf_counter()
        if remain > 0.002:
            time.sleep(remain - 0.0015)
        while not self._stop_evt.is_set() and time.perf_counter() < t:
            pass

    def _mouse_over_own_window(self):
        probe = self._window_probe
        if probe is None:
            return False
        try:
            rect = probe()
        except Exception:
            return False
        if not rect:
            return False
        pt = wintypes.POINT()
        _user32.GetCursorPos(ctypes.byref(pt))
        x1, y1, x2, y2 = rect
        return x1 <= pt.x <= x2 and y1 <= pt.y <= y2

    def _run(self):
        period = 1.0 / self._rate
        target = self._target
        sent = 0
        fails = 0
        error = ""
        base_active = 0.0        # 已结算段（暂停前）的累计运行秒数
        seg_start = 0.0          # 当前连续运行段的起点
        in_pause = False         # 退出时是否处于暂停段（暂停时长不计入）
        last_flush = 0.0

        def flush(total_active):
            # 运行中周期性回写统计，供界面实时读取
            with self._lock:
                self._sent = sent
                self._active_seconds = total_active

        _winmm.timeBeginPeriod(1)          # 提升系统计时精度到 1ms
        try:
            next_t = time.perf_counter()
            seg_start = next_t
            last_flush = next_t
            while sent < target:
                if self._stop_evt.is_set():
                    break
                if not self._resume_evt.is_set():    # 已暂停：休眠等待恢复
                    if not in_pause:       # 结算暂停前的这段运行时长
                        in_pause = True
                        base_active += time.perf_counter() - seg_start
                        flush(base_active)
                    self._resume_evt.wait()  # 阻塞直到「继续/停止」，不占 CPU
                    if self._stop_evt.is_set():
                        break
                    in_pause = False
                    seg_start = time.perf_counter()
                    next_t = seg_start
                    continue

                # --- 鼠标连点防自击：指针在本程序窗口内时不发送 ---
                if self._key in MOUSE_TABLE and self._mouse_over_own_window():
                    time.sleep(min(0.02, period))
                    next_t = time.perf_counter()   # 丢弃期间欠账，避免移开后突发
                    continue

                # --- 决定本批发送多少个 ---
                now = time.perf_counter()
                behind = now - next_t
                if behind > MAX_BATCH * period:      # 欠账太多：截断，避免突发
                    next_t = now - (MAX_BATCH - 1) * period
                    behind = now - next_t
                if behind >= period:
                    n = min(int(behind / period) + 1, target - sent, MAX_BATCH)
                else:
                    n = 1
                    self._wait_until(next_t)         # 正常节拍：等到点再发
                    if self._stop_evt.is_set():
                        break
                    now = time.perf_counter()

                # --- 发送一批 ---
                pairs, ok = self._send_keys(n)
                sent += pairs
                if ok:
                    fails = 0
                else:
                    fails += 1
                    if fails >= MAX_CONSECUTIVE_FAILS:
                        error = ("系统连续 %d 次拒绝注入按键（错误码 %d）。"
                                 "目标程序可能不接受模拟按键，或其以管理员权限运行而本程序不是。"
                                 % (MAX_CONSECUTIVE_FAILS, ctypes.get_last_error()))
                        break
                next_t += n * period
                now = time.perf_counter()
                total = base_active + (now - seg_start)
                if now - last_flush >= 0.05:
                    flush(total)
                    last_flush = now
            # 任务结束：结算最终统计
            if not in_pause:
                base_active += time.perf_counter() - seg_start
            flush(base_active)
        finally:
            _winmm.timeEndPeriod(1)
        # --- 写回最终状态 ---
        with self._lock:
            self._failed_sends = fails
            if error:
                self._last_error = error
                self._state = TaskState.ERROR
            elif self._stop_evt.is_set():
                self._state = TaskState.STOPPED
            elif sent >= target:
                self._state = TaskState.COMPLETED
            else:
                self._state = TaskState.STOPPED

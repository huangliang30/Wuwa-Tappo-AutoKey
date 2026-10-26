# -*- coding: utf-8 -*-
"""冒烟测试：离屏模式验证界面构建、任务全流程与统计逻辑（不注册全局热键）。"""
import os
import sys
import time
from ctypes import wintypes

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication

import ui
from key_controller import TaskState

app = QApplication([])
w = ui.MainWindow()
w.show()
app.processEvents()

def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)

pump(0.2)   # 让轮询定时器跑起来

# 1) ETA 格式化
assert ui.fmt_eta(755) == "12 分 35 秒", ui.fmt_eta(755)
assert ui.fmt_eta(12000) == "3 小时 20 分钟", ui.fmt_eta(12000)
assert ui.fmt_eta(203124) == "2 天 8 小时 25 分钟", ui.fmt_eta(203124)
assert ui.fmt_eta(None) == "—"
print("[OK] fmt_eta")

# 2) 初始状态
snap = w.controller.snapshot()
assert snap["state"] == TaskState.IDLE
assert w.target_label.text() == "—"
assert w.btn_start.isEnabled() and not w.btn_stop.isEnabled()
print("[OK] initial state")

# 3) 运行 -> 暂停 -> 继续 -> 停止
w.count_spin.setValue(5000)
w.rate_spin.setValue(400)
w.key_box.setCurrentText("F15")
w._on_start()
assert w.controller.is_busy()
assert not w.key_box.isEnabled()          # 运行中参数锁定

pump(0.8)
s = w.controller.snapshot()
assert s["state"] == TaskState.RUNNING and s["sent"] > 0, (s["state"], s["sent"])
rate = s["sent"] / 0.8
print("[OK] running, sent=%d, ~%.0f keys/s" % (s["sent"], rate))
assert rate > 40, rate   # 实际速率受系统注入管线限制（见 README），只验证在有效发送

w.controller.pause()
pump(0.3)
s = w.controller.snapshot()
assert s["state"] == TaskState.PAUSED
assert w.btn_resume.isEnabled() and not w.btn_pause.isEnabled()
assert w.val_eta.text() == "已暂停"
sent_at_pause = s["sent"]
pump(0.3)
assert w.controller.snapshot()["sent"] == sent_at_pause   # 暂停期间不增长
print("[OK] paused, sent stays at %d" % sent_at_pause)

w.controller.resume()
pump(0.5)
s = w.controller.snapshot()
assert s["state"] == TaskState.RUNNING and s["sent"] > sent_at_pause
print("[OK] resumed, sent=%d, avg=%.0f/s" % (s["sent"], s["avg_rate"]))

w.controller.stop()
pump(0.4)
s = w.controller.snapshot()
assert s["state"] == TaskState.STOPPED, s["state"]
assert w.btn_start.isEnabled() and w.key_box.isEnabled()
print("[OK] stopped at %d" % s["sent"])

# 4) 小任务自然完成
w.count_spin.setValue(30)
w.rate_spin.setValue(300)
w._on_start()
end = time.time() + 5
while time.time() < end:
    app.processEvents()
    if w.controller.snapshot()["state"] == TaskState.COMPLETED:
        break
    time.sleep(0.02)
s = w.controller.snapshot()
assert s["state"] == TaskState.COMPLETED and s["sent"] == 30 and s["percent"] == 100.0, s
print("[OK] completed 30/30, avg=%.0f/s" % s["avg_rate"])

# 5) 非法参数被拒绝
try:
    w.controller.start("F15", 0, 500)
    raise SystemExit("should raise")
except ValueError:
    print("[OK] invalid count rejected")
try:
    w.controller.start("F15", 100, 99999)
    raise SystemExit("should raise")
except ValueError:
    print("[OK] invalid rate rejected")
try:
    w.controller.start("K99", 100, 500)
    raise SystemExit("should raise")
except ValueError:
    print("[OK] invalid key rejected")

# 5.5) 高频大批量任务：即使系统注入慢，也应靠批量发送完成
w.controller.start("F15", 500, 5000)
end = time.time() + 15
while time.time() < end:
    app.processEvents()
    st = w.controller.snapshot()["state"]
    if st in (TaskState.COMPLETED, TaskState.ERROR, TaskState.STOPPED):
        break
    time.sleep(0.02)
s = w.controller.snapshot()
assert s["state"] == TaskState.COMPLETED and s["sent"] == 500, (s["state"], s["sent"])
print("[OK] 500 keys @5000/s completed, avg=%.0f keys/s (system cap)" % s["avg_rate"])

# 5.5) 鼠标点击路径：窗口挪开 + 指针放到屏幕角落（避免点到东西），发 8 次左键后还原
import ctypes
w.move(900, 60)
app.processEvents()
pt = wintypes.POINT()
ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
ctypes.windll.user32.SetCursorPos(2, 2)
try:
    w.controller.start("鼠标左键", 8, 10)
    end = time.time() + 8
    while time.time() < end:
        app.processEvents()
        st = w.controller.snapshot()["state"]
        if st in (TaskState.COMPLETED, TaskState.ERROR, TaskState.STOPPED):
            break
        time.sleep(0.02)
    s = w.controller.snapshot()
    assert s["state"] == TaskState.COMPLETED and s["sent"] == 8, (s["state"], s["sent"])
    print("[OK] mouse left click: 8/8 sent")
finally:
    ctypes.windll.user32.SetCursorPos(pt.x, pt.y)

# 5.6) 防自击：指针停在本程序窗口内时，鼠标任务不发送
w.move(50, 50)
app.processEvents()
ctypes.windll.user32.SetCursorPos(150, 150)   # 窗口矩形 (50,50)-(730,770) 内
try:
    w.controller.start("鼠标左键", 100, 50)
    end = time.time() + 0.8
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)
    s = w.controller.snapshot()
    assert s["state"] == TaskState.RUNNING and s["sent"] == 0, (s["state"], s["sent"])
    print("[OK] pointer over own window: clicks suppressed")
    ctypes.windll.user32.SetCursorPos(2, 2)   # 移出窗口
    end = time.time() + 4.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)
        if w.controller.snapshot()["sent"] >= 10:
            break
    s = w.controller.snapshot()
    assert s["sent"] >= 10, s["sent"]
    print("[OK] pointer moved away: clicks flow (%d sent)" % s["sent"])
    w.controller.stop()
finally:
    ctypes.windll.user32.SetCursorPos(pt.x, pt.y)

# 6) 关闭清理
w.close()
app.processEvents()
assert not (w.controller._thread and w.controller._thread.is_alive())
print("[OK] shutdown clean, no worker thread left")

print("\nALL SMOKE TESTS PASSED")

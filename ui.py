# -*- coding: utf-8 -*-
"""界面实现（PySide6）。

布局自上而下：标题栏（含状态徽标）→ 参数设置区 → 任务控制区
→ 实时统计区（大号计数 + 进度条 + 统计网格）→ 提示信息栏。
界面通过 100ms 轮询控制器快照刷新，避免跨线程直接操作控件。
"""

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QFrame, QGridLayout, QGraphicsDropShadowEffect,
    QGroupBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from config_manager import ConfigManager
from key_controller import (
    KEY_TABLE, MAX_COUNT, MAX_RATE, MIN_RATE, MOUSE_TABLE, TaskState,
    is_supported_key,
)
from key_controller import KeyController

APP_TITLE = "Wuwa Tappo 自动按键"

STATE_COLORS = {
    TaskState.IDLE: "#ffffff",
    TaskState.RUNNING: "#ccff00",
    TaskState.PAUSED: "#ff9500",
    TaskState.STOPPED: "#dddddd",
    TaskState.COMPLETED: "#00d9ff",
    TaskState.ERROR: "#ff006e",
}

STATE_TEXT = {
    TaskState.IDLE: "#444444",
    TaskState.RUNNING: "#006600",
    TaskState.PAUSED: "#a05000",
    TaskState.STOPPED: "#666666",
    TaskState.COMPLETED: "#00779e",
    TaskState.ERROR: "#c4004f",
}

STYLE = """
* { font-family: "Consolas", "Microsoft YaHei UI", monospace;
    font-size: 13px; color: #000000; }
QMainWindow, QWidget#Root { background-color: #ffffff; }
QLabel { background: transparent; }
QLabel#Title { font-size: 22px; font-weight: 900; font-family: "Microsoft YaHei UI"; }
QLabel#Subtitle { color: #444444; font-size: 12px; }
QLabel[badge="true"] {
    font-size: 13px; font-weight: 900; color: #000000;
    border: 3px solid #000000; border-radius: 0px;
    padding: 4px 14px; background-color: #ffffff;
}
QLabel#StatValue { font-size: 15px; font-weight: 900; color: #000000; }
QLabel#SentCounter { font-size: 26px; font-weight: 900; color: #ff006e; }
QLabel#TargetCounter { font-size: 26px; font-weight: 900; color: #000000; }
QGroupBox {
    background-color: #ffffff; border: 3px solid #000000;
    border-radius: 0px; margin-top: 18px; padding: 14px 14px 14px 14px;
    font-weight: 900;
}
QGroupBox::title {
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 10px; top: 3px; padding: 1px 8px; color: #000000;
    background-color: #ccff00; border: 2px solid #000000;
    font-weight: 900; font-family: "Microsoft YaHei UI";
}
QComboBox, QSpinBox {
    background-color: #ffffff; border: 3px solid #000000;
    border-radius: 0px; padding: 5px 10px; min-height: 20px;
    selection-background-color: #ffff00; selection-color: #000000;
    font-family: "Consolas", "Microsoft YaHei UI";
}
QComboBox:hover, QSpinBox:hover { background-color: #ffff00; }
QComboBox:focus, QSpinBox:focus { background-color: #ffff00; }
QComboBox:disabled, QSpinBox:disabled { color: #888888; background-color: #f0f0f0; }
QComboBox::drop-down {
    border: none; width: 26px; background: #ffffff; border-left: 3px solid #000000;
}
QComboBox::down-arrow {
    image: none; border-left: 5px solid transparent;
    border-right: 5px solid transparent; border-top: 6px solid #000000;
    margin-right: 8px;
}
QComboBox::drop-down:editable { background: #ffff00; }
QComboBox QAbstractItemView {
    background-color: #ffffff; border: 3px solid #000000;
    selection-background-color: #ffff00; selection-color: #000000; outline: none;
}
QSpinBox::up-button, QSpinBox::down-button {
    width: 18px; background: #ffffff; border: none; border-left: 2px solid #000000;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: #ffff00; }
QPushButton {
    border: 3px solid #000000; border-radius: 0px;
    padding: 9px 16px; background-color: #ffffff; color: #000000;
    font-weight: 900; font-family: "Microsoft YaHei UI";
}
QPushButton:hover { background-color: #ffff00; color: #000000; }
QPushButton:pressed {
    padding-top: 15px; padding-left: 22px;
    padding-bottom: 3px; padding-right: 10px;
}
QPushButton:disabled { color: #888888; background-color: #f0f0f0; }
QPushButton#StartBtn { background-color: #ff006e; color: #ffffff; }
QPushButton#StartBtn:hover { background-color: #ffff00; color: #000000; }
QPushButton#PauseBtn { background-color: #ff9500; color: #000000; }
QPushButton#StopBtn  { background-color: #000000; color: #ffffff; }
QPushButton#StopBtn:hover  { background-color: #ffff00; color: #000000; }
QPushButton#TestBtn  { background-color: #00d9ff; color: #000000; }
QProgressBar {
    background-color: #ffffff; border: 3px solid #000000;
    border-radius: 0px; height: 22px; text-align: center;
    font-weight: 900; color: #000000;
}
QProgressBar::chunk { background-color: #ff006e; border-radius: 0px; }
QFrame#Sep { background-color: #000000; max-height: 2px; border: none; }
QScrollArea { background-color: #ffffff; border: none; }
QScrollArea > QWidget > QWidget { background-color: transparent; }
QScrollBar:vertical { background: #ffffff; width: 14px; margin: 0; border: 2px solid #000000; }
QScrollBar::handle:vertical { background: #000000; min-height: 30px; border-radius: 0px; }
QScrollBar::handle:vertical:hover { background: #ff006e; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QMenu { background-color: #ffffff; border: 3px solid #000000; }
QMenu::item { padding: 6px 24px; color: #000000; }
QMenu::item:selected { background-color: #ffff00; color: #000000; }
"""


def fmt_int(n):
    return "{:,}".format(n)


def fmt_eta(seconds):
    """把秒数格式化为易读的剩余时间文本。"""
    if seconds is None:
        return "—"
    seconds = int(seconds + 0.5)
    if seconds < 1:
        return "即将完成"
    if seconds < 60:
        return "%d 秒" % seconds
    if seconds < 3600:
        return "%d 分 %02d 秒" % (seconds // 60, seconds % 60)
    if seconds < 86400:
        return "%d 小时 %d 分钟" % (seconds // 3600, (seconds % 3600) // 60)
    return "%d 天 %d 小时 %d 分钟" % (seconds // 86400, (seconds % 86400) // 3600,
                                     (seconds % 3600) // 60)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(680, 720)
        self.setMinimumSize(560, 480)

        self.controller = KeyController()
        self.controller.set_own_window_probe(self._own_window_rect)
        self.config = ConfigManager()

        self._build_ui()
        self._apply_config()

        # 统计刷新定时器（界面线程轮询，天然线程安全）
        self._poll = QTimer(self)
        self._poll.timeout.connect(self._refresh_stats)
        self._poll.start(100)
        self._refresh_stats()   # 首帧即显示正确状态

    # ---------------- 界面构建 ----------------

    def _build_ui(self):
        # 页面放进滚动区域：屏幕缩放较大、空间不足时可滚动，绝不重叠/裁切
        root = QWidget(objectName="Root")
        page = QVBoxLayout(root)
        page.setContentsMargins(22, 18, 22, 14)
        page.setSpacing(12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(root)
        self.setCentralWidget(scroll)

        # --- 标题行 ---
        head = QHBoxLayout()
        title_box = QVBoxLayout()
        t = QLabel("Wuwa Tappo", objectName="Title")
        s = QLabel("Windows 自动按键工具 · 独立发送指定按键，不动鼠标、不输入文字",
                   objectName="Subtitle")
        title_box.addWidget(t)
        title_box.addWidget(s)
        head.addLayout(title_box)
        head.addStretch(1)
        self.badge = QLabel("未开始")
        self.badge.setProperty("badge", True)
        head.addWidget(self.badge, 0, Qt.AlignTop)
        self._apply_hard_shadow(self.badge, 4)
        page.addLayout(head)

        # --- 参数设置区 ---
        g1 = QGroupBox("参数设置")
        form = QFormLayout(g1)
        form.setLabelAlignment(Qt.AlignRight)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)

        self.key_box = QComboBox()
        for name in MOUSE_TABLE:
            self.key_box.addItem(name)
        for name in KEY_TABLE:
            self.key_box.addItem(name)
        self.key_box.setCurrentText("F15")
        self.key_box.setFixedWidth(140)
        self.key_box.currentTextChanged.connect(lambda _: self._save_config())
        row_key = QHBoxLayout()
        row_key.setSpacing(12)
        row_key.addWidget(self.key_box)
        row_key.addWidget(QLabel("鼠标键在指针当前位置点击；指针停在本窗口上时不点击"))
        row_key.addStretch(1)
        form.addRow("目标按键：", row_key)

        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, MAX_COUNT)
        self.count_spin.setSingleStep(1000)
        self.count_spin.setGroupSeparatorShown(True)
        self.count_spin.setFixedWidth(160)
        self.count_spin.setAccelerated(True)
        row_cnt = QHBoxLayout()
        row_cnt.setSpacing(12)
        row_cnt.addWidget(self.count_spin)
        row_cnt.addWidget(QLabel("（1 ~ 100,000,000）"))
        row_cnt.addStretch(1)
        form.addRow("目标总次数：", row_cnt)

        self.rate_spin = QSpinBox()
        self.rate_spin.setRange(MIN_RATE, MAX_RATE)
        self.rate_spin.setSingleStep(50)
        self.rate_spin.setGroupSeparatorShown(True)
        self.rate_spin.setFixedWidth(160)
        row_rate = QHBoxLayout()
        row_rate.setSpacing(12)
        row_rate.addWidget(self.rate_spin)
        row_rate.addWidget(QLabel("次/秒（%d ~ %d，越高 CPU 占用越大）" % (MIN_RATE, MAX_RATE)))
        row_rate.addStretch(1)
        form.addRow("每秒按键数：", row_rate)

        btn_row = QHBoxLayout()
        reset_btn = QPushButton("恢复默认参数")
        reset_btn.clicked.connect(self._reset_defaults)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch(1)
        form.addRow("", btn_row)
        page.addWidget(g1)
        self._apply_hard_shadow(g1, 8)
        self._apply_hard_shadow(self.key_box, 4)
        self._apply_hard_shadow(self.count_spin, 4)
        self._apply_hard_shadow(self.rate_spin, 4)

        # --- 任务控制区 ---
        g2 = QGroupBox("任务控制")
        ctrl = QGridLayout(g2)
        ctrl.setHorizontalSpacing(10)
        ctrl.setVerticalSpacing(10)

        self.btn_start = QPushButton("▶  开始任务")
        self.btn_pause = QPushButton("⏸  暂停任务")
        self.btn_resume = QPushButton("⏵  继续任务")
        self.btn_stop = QPushButton("■  停止任务")
        self.btn_test = QPushButton("⚡  测试 100 次")
        self.btn_start.setObjectName("StartBtn")
        self.btn_pause.setObjectName("PauseBtn")
        self.btn_resume.setObjectName("PauseBtn")
        self.btn_stop.setObjectName("StopBtn")
        self.btn_test.setObjectName("TestBtn")
        self.btn_start.clicked.connect(self._on_start)
        self.btn_pause.clicked.connect(self.controller.pause)
        self.btn_resume.clicked.connect(self.controller.resume)
        self.btn_stop.clicked.connect(self.controller.stop)
        self.btn_test.clicked.connect(self._on_test)

        for i, b in enumerate((self.btn_start, self.btn_pause, self.btn_resume,
                               self.btn_stop, self.btn_test)):
            ctrl.addWidget(b, i // 3, i % 3)
            b.setMinimumHeight(40)
        ctrl.setColumnStretch(0, 1)
        ctrl.setColumnStretch(1, 1)
        ctrl.setColumnStretch(2, 1)
        hotkey_tip = QLabel("全局快捷键（软件不在前台也有效）：Ctrl+Alt+F8 暂停/继续　·　Ctrl+Alt+F9 停止")
        hotkey_tip.setWordWrap(True)
        hotkey_tip.setStyleSheet("color:#444444;")
        ctrl.addWidget(hotkey_tip, 2, 0, 1, 3)   # 第 2 行：避免与第 1 行按钮重叠
        page.addWidget(g2)
        self._apply_hard_shadow(g2, 8)
        for b in (self.btn_start, self.btn_pause, self.btn_resume,
                  self.btn_stop, self.btn_test):
            self._apply_hard_shadow(b, 6)
            b.installEventFilter(self)   # hover 阴影增大 / 按下压平

        # --- 实时统计区 ---
        g3 = QGroupBox("实时统计")
        stat = QVBoxLayout(g3)
        stat.setSpacing(10)

        counter = QHBoxLayout()
        self.sent_label = QLabel("0", objectName="SentCounter")
        slash = QLabel("/", objectName="TargetCounter")
        self.target_label = QLabel("—", objectName="TargetCounter")
        counter.addWidget(self.sent_label)
        counter.addWidget(slash)
        counter.addWidget(self.target_label)
        counter.addStretch(1)
        stat.addLayout(counter)

        self.progress = QProgressBar()
        self.progress.setRange(0, 10000)   # 万分比，减少大数值溢出与刷新抖动
        self.progress.setValue(0)
        stat.addWidget(self.progress)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(8)
        self.val_state = self._stat_cell(grid, 0, 0, "当前状态")
        self.val_percent = self._stat_cell(grid, 0, 1, "完成进度")
        self.val_speed = self._stat_cell(grid, 1, 0, "本轮平均速度")
        self.val_eta = self._stat_cell(grid, 1, 1, "预计剩余")
        self.val_key = self._stat_cell(grid, 2, 0, "目标按键")
        self.val_rate = self._stat_cell(grid, 2, 1, "设定频率")
        stat.addLayout(grid)
        page.addWidget(g3, 1)   # 统计区占据剩余空间
        self._apply_hard_shadow(g3, 8)

        # --- 底部提示 ---
        sep = QFrame(objectName="Sep")
        sep.setFrameShape(QFrame.HLine)
        page.addWidget(sep)
        self.msg_label = QLabel("就绪。设置参数后点击「开始任务」。")
        self.msg_label.setWordWrap(True)
        self.msg_label.setStyleSheet("color:#444444;")
        page.addWidget(self.msg_label)
        note = QLabel("统计数字为本程序实际调用系统按键接口的发送次数，"
                      "不一定等于目标应用实际接收的次数。本工具不绕过任何反作弊或安全限制，"
                      "请自行确认目标软件允许模拟按键。")
        note.setWordWrap(True)
        note.setStyleSheet("color:#444444; font-size:12px;")
        page.addWidget(note)

    @staticmethod
    def _stat_cell(grid, row, col, caption):
        # 单行横排：说明文字 + 数值并排，压缩纵向空间
        cell = QHBoxLayout()
        cell.setSpacing(8)
        cap = QLabel(caption)
        cap.setStyleSheet("color:#444444; font-size:12px;")
        val = QLabel("—", objectName="StatValue")
        cell.addWidget(cap, 0, Qt.AlignVCenter)
        cell.addWidget(val, 0, Qt.AlignVCenter)
        cell.addStretch(1)
        grid.addLayout(cell, row, col * 2, 1, 2)
        grid.setColumnStretch(col * 2, 1)
        return val

    # ---------------- Neo-Brutalist 硬边阴影 ----------------

    def _apply_hard_shadow(self, widget, offset=6):
        """硬边缘阴影（无模糊）：QSS 不支持 box-shadow，用 blur=0 的阴影特效模拟。"""
        eff = QGraphicsDropShadowEffect(widget)
        eff.setBlurRadius(0)
        eff.setOffset(offset, offset)
        eff.setColor(QColor("#000000"))
        widget.setGraphicsEffect(eff)

    def eventFilter(self, obj, event):
        # Physical Crushing：hover 阴影增大；按下完全压平（阴影消失 + QSS 位移）
        if isinstance(obj, QPushButton):
            eff = obj.graphicsEffect()
            if eff is not None:
                t = event.type()
                if t == QEvent.Enter and obj.isEnabled():
                    eff.setOffset(9, 9)
                elif t == QEvent.Leave:
                    eff.setOffset(6, 6)
                elif t == QEvent.MouseButtonPress:
                    eff.setEnabled(False)
                elif t == QEvent.MouseButtonRelease:
                    eff.setEnabled(True)
        return super().eventFilter(obj, event)

    # ---------------- 配置 ----------------

    def _apply_config(self):
        d = self.config.data
        if is_supported_key(d["key"]):
            self.key_box.setCurrentText(d["key"])
        self.count_spin.setValue(min(max(d["target_count"], 1), MAX_COUNT))
        self.rate_spin.setValue(min(max(d["rate"], MIN_RATE), MAX_RATE))

    def _save_config(self):
        self.config.save(self.key_box.currentText(),
                         self.count_spin.value(), self.rate_spin.value())

    def _reset_defaults(self):
        self.key_box.setCurrentText("F15")
        self.count_spin.setValue(100000)
        self.rate_spin.setValue(500)
        self._save_config()
        self.msg_label.setText("已恢复默认参数。")

    # ---------------- 任务操作 ----------------

    def _current_params(self):
        return (self.key_box.currentText(),
                self.count_spin.value(),
                self.rate_spin.value())

    def _set_params_enabled(self, enabled):
        self.key_box.setEnabled(enabled)
        self.count_spin.setEnabled(enabled)
        self.rate_spin.setEnabled(enabled)

    def _on_start(self):
        key, count, rate = self._current_params()
        try:
            ok = self.controller.start(key, count, rate)
        except ValueError as e:
            QMessageBox.warning(self, APP_TITLE, str(e))
            return
        if not ok:
            QMessageBox.information(self, APP_TITLE, "任务已在运行中，请勿重复启动。")
            return
        self.target_label.setText(fmt_int(count))
        self._save_config()
        self._set_params_enabled(False)

    def _on_test(self):
        key, _, rate = self._current_params()
        test_rate = min(rate, 25)
        try:
            ok = self.controller.start(key, 100, test_rate, is_test=True)
        except ValueError as e:
            QMessageBox.warning(self, APP_TITLE, str(e))
            return
        if not ok:
            QMessageBox.information(self, APP_TITLE, "有任务正在运行，请先停止后再测试。")
            return
        self.target_label.setText("100（测试）")
        self._set_params_enabled(False)

    # ---------------- 状态刷新 ----------------

    def _own_window_rect(self):
        """返回窗口在屏幕上的全局矩形，供控制器跳过自点击。"""
        g = self.frameGeometry()
        return (g.left(), g.top(), g.right(), g.bottom())

    def _refresh_stats(self):
        # 统计刷新绝不允许抛异常：定时器每 100ms 调一次，异常会反复中断界面
        try:
            self._do_refresh_stats()
        except Exception:
            import sys
            import traceback
            traceback.print_exc(file=sys.stderr)

    def _do_refresh_stats(self):
        snap = self.controller.snapshot()
        state = snap["state"]
        state_text = snap["state_text"]

        # 状态徽标
        self.badge.setText(state_text)
        self.badge.setStyleSheet('QLabel[badge="true"] '
                                 '{ background-color: %s; }' % STATE_COLORS[state])
        self.val_state.setText(state_text)
        self.val_state.setStyleSheet("color:%s;" % STATE_TEXT[state])

        # 计数与进度
        sent, target = snap["sent"], snap["target"]
        self.sent_label.setText(fmt_int(sent))
        if state == TaskState.IDLE or target <= 0:
            self.target_label.setText("—")
        else:
            base = "100（测试）" if snap["is_test"] else fmt_int(target)
            if self.target_label.text() != base:
                self.target_label.setText(base)
        percent = snap["percent"] if target > 0 else 0.0
        self.progress.setValue(int(percent * 100))
        self.val_percent.setText("%.2f%%" % percent)

        # 速度 / 剩余时间
        self.val_speed.setText("%.1f 次/秒" % snap["avg_rate"] if snap["avg_rate"] else "—")
        if state == TaskState.PAUSED:
            self.val_eta.setText("已暂停")
        elif state in (TaskState.IDLE, TaskState.STOPPED, TaskState.COMPLETED, TaskState.ERROR):
            self.val_eta.setText("—" if state != TaskState.COMPLETED else "已完成")
        else:
            self.val_eta.setText(fmt_eta(snap["eta_seconds"]))

        self.val_key.setText(snap["key"] if state != TaskState.IDLE
                             else self.key_box.currentText())
        self.val_rate.setText(("%d 次/秒" % snap["rate"]) if state != TaskState.IDLE
                              else ("%d 次/秒" % self.rate_spin.value()))

        # 按钮与参数可用性
        running = state == TaskState.RUNNING
        paused = state == TaskState.PAUSED
        busy = running or paused
        self.btn_start.setEnabled(not busy)
        self.btn_test.setEnabled(not busy)
        self.btn_pause.setEnabled(running)
        self.btn_resume.setEnabled(paused)
        self.btn_stop.setEnabled(busy)
        self._set_params_enabled(not busy)

        # 消息栏
        if state == TaskState.ERROR:
            self.msg_label.setText("运行异常：" + snap["last_error"])
            self.msg_label.setStyleSheet("color:#c4004f;")
        elif state == TaskState.COMPLETED:
            self.msg_label.setText("任务完成，共发送 %s 次。" % fmt_int(sent))
            self.msg_label.setStyleSheet("color:#00779e;")
        elif paused:
            self.msg_label.setText("任务已暂停，点击「继续任务」或按 Ctrl+Alt+F8 恢复。")
            self.msg_label.setStyleSheet("color:#a05000;")
        elif running:
            mode = "测试" if snap["is_test"] else "任务"
            self.msg_label.setText("%s运行中：正在以约 %d 次/秒发送「%s」。"
                                   % (mode, snap["rate"], snap["key"]))
            self.msg_label.setStyleSheet("color:#006600;")

    # ---------------- 退出清理 ----------------

    def closeEvent(self, event):
        self._poll.stop()
        self.controller.shutdown()
        if hasattr(self, "hotkeys"):
            self.hotkeys.stop()
        self._save_config()
        super().closeEvent(event)

    def set_hotkey_manager(self, manager):
        """由 main.py 注入，退出时统一释放。"""
        self.hotkeys = manager
        if not manager.hotkeys_ok and manager.failed_names:
            self.msg_label.setText("警告：全局快捷键 %s 注册失败（可能被其他软件占用），"
                                   "可仍用界面按钮控制任务。" % "、".join(manager.failed_names))
            self.msg_label.setStyleSheet("color:#fbbf24;")

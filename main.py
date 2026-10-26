# -*- coding: utf-8 -*-
"""Wuwa Tappo 自动按键 —— 程序入口。"""

import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from hotkey_manager import HotkeyManager
from ui import APP_TITLE, STYLE, MainWindow


def _excepthook(exc_type, exc_value, exc_tb):
    """未捕获异常：记录并弹出提示，避免静默崩溃。"""
    text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    sys.stderr.write(text)
    try:
        QMessageBox.critical(None, APP_TITLE + " - 发生错误",
                             "程序遇到未处理的异常：\n\n%s\n\n详细信息已输出到控制台。"
                             % (str(exc_value) or exc_type.__name__))
    except Exception:
        pass


def main():
    sys.excepthook = _excepthook
    app = QApplication(sys.argv)
    app.setApplicationName("WuwaTappoAutoKey")
    app.setOrganizationName("WuwaTappo")
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(STYLE)

    window = MainWindow()

    # 全局快捷键：回调直接调用线程安全的控制器，界面靠轮询自动同步
    hotkeys = HotkeyManager(on_toggle_pause=window.controller.toggle_pause,
                            on_stop=window.controller.stop)
    hotkeys.start()
    window.set_hotkey_manager(hotkeys)

    window.show()

    exit_code = app.exec()

    # 二次保险：正常退出路径之外也确保任务停止、热键注销
    window.controller.shutdown()
    hotkeys.stop()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

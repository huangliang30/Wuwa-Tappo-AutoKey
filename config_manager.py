# -*- coding: utf-8 -*-
"""配置保存和读取（JSON 格式）。

配置文件位置：优先 %APPDATA%/WuwaTappoAutoKey/config.json，
无法访问时回退到程序目录，保证只读环境下也能运行。
"""

import json
import os

from key_controller import DEFAULT_KEY, DEFAULT_COUNT, DEFAULT_RATE

APP_DIR_NAME = "WuwaTappoAutoKey"
CONFIG_NAME = "config.json"

DEFAULTS = {
    "key": DEFAULT_KEY,
    "target_count": DEFAULT_COUNT,
    "rate": DEFAULT_RATE,
}


def _config_path():
    appdata = os.environ.get("APPDATA")
    if appdata:
        try:
            path = os.path.join(appdata, APP_DIR_NAME)
            os.makedirs(path, exist_ok=True)
            return os.path.join(path, CONFIG_NAME)
        except OSError:
            pass
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_NAME)


class ConfigManager:
    def __init__(self):
        self.path = _config_path()
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                for k in DEFAULTS:
                    if k in stored:
                        self.data[k] = stored[k]
        except (OSError, ValueError):
            pass  # 文件不存在或损坏时使用默认值
        self.data["key"] = self.data["key"] if isinstance(self.data["key"], str) else DEFAULTS["key"]
        for num_key in ("target_count", "rate"):
            if not isinstance(self.data[num_key], int):
                self.data[num_key] = DEFAULTS[num_key]
        return self.data

    def save(self, key, target_count, rate):
        self.data = {"key": key, "target_count": int(target_count), "rate": int(rate)}
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            return True
        except OSError:
            return False

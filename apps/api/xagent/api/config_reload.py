"""配置热重载：运行时配置变更无需重启。

功能：
- 文件监听（polling）检测配置变更
- 变更回调通知
- 配置版本管理
- 线程安全读取

用法：
    from xagent.api.config_reload import config_manager

    config_manager.load("config.yaml")
    config_manager.on_change("database", lambda old, new: reconnect_db(new))
    value = config_manager.get("database.pool_size", default=10)
    await config_manager.start_watching(interval=5.0)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable

from xagent.infra.logging import get_logger

logger = get_logger("xagent.config")


class ConfigManager:
    """配置热重载管理器。"""

    def __init__(self):
        self._config: dict[str, Any] = {}
        self._file_path: Path | None = None
        self._file_hash: str = ""
        self._version: int = 0
        self._last_reload: float = 0.0
        self._watchers: dict[str, list[Callable[[Any, Any], None]]] = {}
        self._global_watchers: list[Callable[[dict, dict], None]] = []
        self._watching = False

    @property
    def version(self) -> int:
        return self._version

    @property
    def last_reload(self) -> float:
        return self._last_reload

    def load(self, file_path: str | Path) -> None:
        """加载配置文件。"""
        self._file_path = Path(file_path)
        self._reload()

    def load_dict(self, data: dict[str, Any]) -> None:
        """从字典加载配置。"""
        old = self._config
        self._config = data
        self._version += 1
        self._last_reload = time.time()
        self._notify_watchers(old, data)

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值（支持点号路径）。"""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        """运行时设置配置值。"""
        keys = key.split(".")
        target = self._config
        for k in keys[:-1]:
            if k not in target or not isinstance(target[k], dict):
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value

    def on_change(
        self,
        key: str | None,
        callback: Callable,
    ) -> None:
        """注册变更回调。key=None 表示全局。"""
        if key is None:
            self._global_watchers.append(callback)
        else:
            if key not in self._watchers:
                self._watchers[key] = []
            self._watchers[key].append(callback)

    async def start_watching(self, interval: float = 5.0) -> None:
        """启动文件监听。"""
        if not self._file_path:
            raise ValueError("No config file loaded")

        self._watching = True
        logger.info("config watching started: %s (interval=%.1fs)", self._file_path, interval)

        while self._watching:
            await asyncio.sleep(interval)
            if self._file_path and self._file_path.exists():
                content = self._file_path.read_bytes()
                new_hash = hashlib.md5(content).hexdigest()
                if new_hash != self._file_hash:
                    logger.info("config file changed, reloading...")
                    self._reload()

    def stop_watching(self) -> None:
        """停止文件监听。"""
        self._watching = False

    def _reload(self) -> None:
        """重新加载配置。"""
        if not self._file_path or not self._file_path.exists():
            return

        content = self._file_path.read_bytes()
        self._file_hash = hashlib.md5(content).hexdigest()

        old = self._config
        try:
            # 支持 JSON 格式
            if self._file_path.suffix == ".json":
                self._config = json.loads(content)
            else:
                # 简单 key=value 格式
                self._config = self._parse_simple(content.decode())

            self._version += 1
            self._last_reload = time.time()
            self._notify_watchers(old, self._config)
            logger.info("config reloaded (version=%d)", self._version)
        except Exception as exc:
            logger.error("config reload failed: %s", exc)

    def _parse_simple(self, content: str) -> dict[str, Any]:
        """解析简单 key=value 格式。"""
        result: dict[str, Any] = {}
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                result[key.strip()] = value.strip()
        return result

    def _notify_watchers(self, old: dict, new: dict) -> None:
        """通知变更回调。"""
        # 全局回调
        for cb in self._global_watchers:
            try:
                cb(old, new)
            except Exception as exc:
                logger.error("config watcher error: %s", exc)

        # 键级回调
        for key, callbacks in self._watchers.items():
            old_val = self._get_nested(old, key)
            new_val = self._get_nested(new, key)
            if old_val != new_val:
                for cb in callbacks:
                    try:
                        cb(old_val, new_val)
                    except Exception as exc:
                        logger.error("config watcher error (%s): %s", key, exc)

    @staticmethod
    def _get_nested(data: dict, key: str) -> Any:
        keys = key.split(".")
        value = data
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return None
        return value


# 全局单例
config_manager = ConfigManager()

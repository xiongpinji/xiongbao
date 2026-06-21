"""桌面 computer-use 适配层：UI-TARS（视觉 GUI agent）。

保留 X-Agent 独有的 IME/剪贴板/快捷键序列语义接口；Phase 2 提供 stub 降级，
真实 UI-TARS 模型接入（自部署或 API）在具备模型时启用。
"""

from xagent.adapters.desktop_auto.base import (
    DesktopAgent,
    DesktopResult,
    get_desktop_agent,
)

__all__ = ["DesktopAgent", "DesktopResult", "get_desktop_agent"]

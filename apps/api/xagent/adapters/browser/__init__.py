"""浏览器自动化适配层：browser-use（LLM 驱动）+ Playwright 执行层。

Phase 2：定义 BrowserAgent 协议 + 注册浏览器工具到 ToolRegistry。
真实 browser-use 依赖在 [browser] extras；未安装时降级为说明性 stub，
保证 lite/CI 可跑、编排循环不崩。
"""

from xagent.adapters.browser.base import BrowserAgent, BrowserResult, get_browser_agent
from xagent.adapters.browser.tools import browser_tools

__all__ = ["BrowserAgent", "BrowserResult", "get_browser_agent", "browser_tools"]

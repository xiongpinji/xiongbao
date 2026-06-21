"""编排：agent 状态机循环（observe → reason → act → reflect）。

Phase 1 提供**内置**循环（离线可跑、可测试）：通过提示工程让 LLM 在需要时
输出 JSON 动作 {"tool","args"}，编排执行工具并回灌结果，直至产出 final。

LangGraph 为目标后端：当安装 langgraph 时可切换为图执行（保留同样的 step 事件
语义），接口与内置一致，调用方无感。本模块对外只暴露 ``run_agent``。
"""

from xagent.core.orchestration.loop import run_agent
from xagent.core.orchestration.state import AgentRun, AgentState, StepEvent

__all__ = ["AgentRun", "AgentState", "StepEvent", "run_agent"]

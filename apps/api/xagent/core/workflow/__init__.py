"""工作流引擎：编排 / 补偿 / 审批 / 回放 + 结构化视图（★护城河）。

设计：
- 工作流 = 有序步骤 DAG；每步可声明补偿动作、审批门。
- 执行器逐步推进，失败触发补偿回滚，遇审批门暂停等待信号。
- 全程产出 StepEvent 事件流 -> 结构化 timeline 视图（X-Agent 卖点）。
- 事件采用 append-only + 哈希链，天然支持回放（replay）。
- 后端：lite 用进程内内存执行；full/enterprise 目标 Temporal（接口稳定，可切换）。
"""

from xagent.core.workflow.engine import WorkflowEngine, get_engine, reset_engine
from xagent.core.workflow.models import (
    ApprovalGate,
    WorkflowRun,
    WorkflowSpec,
    WorkflowStatus,
    WorkflowStep,
)

__all__ = [
    "WorkflowSpec",
    "WorkflowStep",
    "WorkflowStatus",
    "WorkflowRun",
    "ApprovalGate",
    "WorkflowEngine",
    "get_engine",
    "reset_engine",
]

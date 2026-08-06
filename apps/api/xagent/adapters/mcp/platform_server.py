"""X-Agent Platform MCP Server — 把平台能力暴露给外部 agent（V3-4）。

对标 Codex CLI 的 MCP 双向能力：Claude Code / Codex / Cursor 等外部 agent
可以把 X-Agent 作为 MCP 工具源直接调用。

工具面包括 Agent run/review、会话、统一 Runtime、审批、调度历史和完整
Skill Package。所有租户资源通过同一个进程配置 Principal、RBAC、tenant 过滤
和审计链，不允许工具参数覆盖 tenant。

传输：
- stdio（默认）：被宿主 agent 进程拉起，同机使用
- streamable HTTP：``--http --port 8100``，网络可达部署；非回环地址必须设置
  ``XAGENT_PLATFORM_MCP_TOKEN`` 并强制 Bearer 校验

安全边界：run/review 走平台既有权限与工具注册表（shell/python 默认禁用等
安全默认不变）；HTTP 模式默认仅绑 127.0.0.1。Principal 由
``XAGENT_PLATFORM_MCP_USER_ID/TENANT_ID/ROLES`` 配置，HTTP Bearer token 不会
成为工具参数或进入事件正文。
"""

from __future__ import annotations

import argparse
import os
import uuid
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from ipaddress import ip_address
from typing import Any

from mcp.server import MCPServer

from xagent.infra.logging import get_logger

logger = get_logger("xagent.mcp.platform_server")

server = MCPServer(name="xagent-platform")


def _system_principal():
    """从受信任的 MCP 进程配置构造调用主体，不接受工具参数覆盖 tenant。"""
    from xagent.enterprise.auth.principal import Principal

    roles = {
        role.strip()
        for role in os.environ.get("XAGENT_PLATFORM_MCP_ROLES", "admin").split(",")
        if role.strip()
    }
    return Principal(
        user_id=os.environ.get("XAGENT_PLATFORM_MCP_USER_ID", "platform-mcp"),
        tenant_id=os.environ.get("XAGENT_PLATFORM_MCP_TENANT_ID", "default"),
        roles=frozenset(roles),
        scopes=frozenset(),
        is_anonymous=False,
    )


def _is_allowed(principal: Any, resource: str, action: str) -> bool:
    from xagent.enterprise.authz.rbac import AccessRequest, authorize

    return authorize(principal, AccessRequest(resource=resource, action=action))


def _forbidden(resource: str, action: str) -> dict[str, Any]:
    return {"ok": False, "error": "forbidden", "resource": resource, "action": action}


def _safe_payload(value: Any) -> Any:
    """转成 MCP 可序列化值，同时移除本机路径并递归脱敏。"""
    from xagent.domains.checkpoints import redact_checkpoint_payload

    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        hidden = {"root_path", "worktree_path", "patch_path", "main_workspace"}
        normalized = {
            str(key): _safe_payload(item)
            for key, item in value.items()
            if str(key) not in hidden
        }
        return redact_checkpoint_payload(normalized)
    if isinstance(value, (list, tuple, set)):
        return [_safe_payload(item) for item in value]
    return redact_checkpoint_payload(value)


def _audit(
    principal: Any,
    action: str,
    resource: str,
    detail: dict[str, Any] | None = None,
) -> None:
    from xagent.enterprise.audit import get_audit_log

    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action=f"mcp.{action}",
        resource=resource,
        detail=_safe_payload(detail or {}),
    )


def _development_approval(record: Any) -> dict[str, Any]:
    return {
        "approval_id": f"development_task:{record.task_id}",
        "type": "development_task",
        "task_id": record.task_id,
        "run_id": record.parent_run_id,
        "goal": record.goal,
        "status": record.status.value,
        "owner_id": record.owner_id,
        "result_commit": record.result_commit,
        "diff_stat": record.diff_stat,
        "test_summary": record.test_summary,
        "created_at": record.created_at,
        "expires_at": record.expires_at,
    }


def _workflow_approvals(view: dict[str, Any]) -> list[dict[str, Any]]:
    run_id = str(view.get("run_id") or "")
    return [
        {
            "approval_id": f"workflow:{run_id}:{step.get('id', '')}",
            "type": "workflow",
            "run_id": run_id,
            "step_id": str(step.get("id") or ""),
            "name": str(step.get("name") or ""),
            "status": "awaiting_approval",
        }
        for step in view.get("steps") or []
        if str(step.get("status") or "") == "awaiting_approval"
    ]


def _skill_package_view(package: Any, *, detail: bool) -> dict[str, Any]:
    view = {
        "package_id": package.package_id,
        "skill_id": package.skill_id,
        "owner_id": package.owner_id,
        "name": package.name,
        "version": package.version,
        "content_hash": package.content_hash,
        "source": package.source,
        "file_count": package.file_count,
        "total_size": package.total_size,
        "imported_at": package.imported_at,
    }
    if detail:
        view.update(
            manifest=package.manifest,
            frontmatter=package.frontmatter,
            body=package.body,
        )
    return view


async def _execute_mcp_run(
    principal: Any,
    goal: str,
    *,
    role: str = "",
    conversation_id: str = "",
) -> dict[str, Any]:
    """执行并持久化 MCP run，使 run_get/events 能读取同一事实。"""
    from xagent.core.orchestration import run_agent
    from xagent.infra.db import get_sessionmaker
    from xagent.worker.celery_app import persist_agent_task_record_in_session

    run_id = uuid.uuid4().hex
    input_payload = _safe_payload(
        {"goal": goal, "role": role, "conversation_id": conversation_id}
    )
    try:
        run = await run_agent(
            goal,
            principal=principal,
            role_name=role or None,
            run_id=run_id,
            conversation_id=conversation_id or None,
        )
        result_payload = _safe_payload(run.to_dict())
        status = "succeeded"
        error = ""
    except Exception as exc:  # noqa: BLE001 — MCP 必须返回结构化失败并保留 run
        result_payload = {"run_id": run_id, "error": _safe_payload(str(exc))}
        status = "failed"
        error = str(result_payload["error"])
    delivery_summary: dict[str, Any] = {
        "status": "ready" if status == "succeeded" else "failed",
        "kind": "mcp.agent.run",
        "summary": (
            "MCP Agent run 已完成。" if status == "succeeded" else "MCP Agent run 失败。"
        ),
        "risks": [],
        "replay": {
            "mode": "task_detail",
            "run_id": run_id,
            "task_id": run_id,
            "api_path": f"/api/v1/runs/{run_id}",
            "console_path": f"/runs/{run_id}",
        },
    }
    async with get_sessionmaker()() as session:
        await persist_agent_task_record_in_session(
            session,
            task_id=run_id,
            run_id=run_id,
            tenant_id=principal.tenant_id,
            owner_id=principal.user_id,
            kind="agent.run",
            backend="mcp",
            status=status,
            input_payload=input_payload,
            result_payload=result_payload,
            error=error,
            validation_summary={"risks": []},
            delivery_summary=delivery_summary,
            preview_summary={
                "final_answer": str(result_payload.get("final_answer") or "")[:160],
                "error": error[:160],
            },
        )
        await session.commit()
    return {
        "ok": status == "succeeded",
        "run_id": run_id,
        "status": status,
        "result": result_payload,
        "error": error,
    }


async def xagent_run(goal: str, role: str = "") -> dict[str, Any]:
    """运行一次 X-Agent 任务（内置 observe→reason→act→reflect 编排），返回最终回答。"""
    principal = _system_principal()
    if not _is_allowed(principal, "agent", "execute"):
        return _forbidden("agent", "execute")
    goal = goal.strip()
    if not goal:
        return {"ok": False, "error": "missing_goal"}
    execution = await _execute_mcp_run(principal, goal, role=role)
    _audit(principal, "run.create", "run", {"run_id": execution["run_id"]})
    result = execution["result"]
    return {
        "ok": execution["ok"],
        "run_id": execution["run_id"],
        "answer": result.get("final_answer", ""),
        "steps": result.get("steps", 0),
        "error": execution["error"],
    }


async def xagent_code_review(
    diff: str = "", repo: str = "", base: str = "", head: str = "HEAD",
) -> dict[str, Any]:
    """代码评审：逻辑/安全/规范三维并行。传 diff 文本，或 repo+base..head。"""
    principal = _system_principal()
    if not _is_allowed(principal, "code_review", "execute"):
        return _forbidden("code_review", "execute")
    from xagent.domains.code_review.service import review_diff

    try:
        result = await review_diff(
            diff=diff or None, repo=repo or None, base=base or None, head=head,
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    _audit(principal, "code_review.run", "code_review")
    return {"ok": True, "result": result.to_dict()}


async def xagent_skill_match(goal: str) -> dict[str, Any]:
    """按任务目标匹配 X-Agent 技能库，返回命中技能与 prompt 注入文本。"""
    principal = _system_principal()
    if not _is_allowed(principal, "agent", "read"):
        return _forbidden("agent", "read")
    goal = goal.strip()
    if not goal:
        return {"ok": False, "error": "missing_goal"}
    from xagent.core.skills import get_skill_store

    store = get_skill_store()
    matched = store.match(goal, tenant_id=principal.tenant_id)
    _audit(principal, "skill.match", "skill", {"count": len(matched)})
    return {
        "ok": True,
        "matched": [s.to_dict() for s in matched],
        "prompt_injection": store.build_prompt_injection(
            goal, tenant_id=principal.tenant_id
        ),
    }


async def xagent_skill_import(content: str, origin: str = "mcp") -> dict[str, Any]:
    """导入 SKILL.md（agentskills.io 格式）到 X-Agent 技能库（强制质量门禁）。"""
    principal = _system_principal()
    if not _is_allowed(principal, "agent", "write"):
        return _forbidden("agent", "write")
    if not content.strip():
        return {"ok": False, "error": "missing_content"}
    from xagent.core.skills import get_skill_store
    from xagent.core.skills.importer import import_skillmd

    skill, reason = import_skillmd(
        get_skill_store(), content, origin, tenant_id=principal.tenant_id
    )
    if skill is None:
        return {"ok": False, "reason": reason}
    _audit(principal, "skill.import", "skill", {"skill_id": skill.skill_id})
    return {"ok": True, "skill_id": skill.skill_id, "name": skill.name}


async def xagent_conversation_list(limit: int = 50) -> dict[str, Any]:
    """列出当前 MCP Principal 租户内的持久会话。"""
    principal = _system_principal()
    if not _is_allowed(principal, "agent", "read"):
        return _forbidden("agent", "read")
    from xagent.core.orchestration.conversation import load_conversations_from_db
    from xagent.infra.db import get_sessionmaker

    async with get_sessionmaker()() as session:
        items = await load_conversations_from_db(
            session, principal.tenant_id, limit=max(1, min(limit, 200))
        )
    _audit(principal, "conversation.list", "conversation", {"count": len(items)})
    return {"ok": True, "items": _safe_payload(items)}


async def xagent_conversation_get(
    conversation_id: str, limit: int = 100
) -> dict[str, Any]:
    """读取当前租户的一条会话及消息。"""
    principal = _system_principal()
    if not _is_allowed(principal, "agent", "read"):
        return _forbidden("agent", "read")
    from xagent.core.orchestration.conversation import load_conversation_from_db
    from xagent.infra.db import get_sessionmaker

    async with get_sessionmaker()() as session:
        try:
            conversation = await load_conversation_from_db(
                session, principal.tenant_id, conversation_id
            )
        except LookupError:
            conversation = None
    if conversation is None:
        return {"ok": False, "error": "conversation_not_found"}
    messages = [
        {"role": message.role, "content": message.content}
        for message in conversation.messages[-max(1, min(limit, 200)) :]
    ]
    _audit(
        principal,
        "conversation.get",
        "conversation",
        {"conversation_id": conversation_id, "message_count": len(messages)},
    )
    return {
        "ok": True,
        "conversation": _safe_payload(
            {
                "conversation_id": conversation.conversation_id,
                "title": conversation.title,
                "created_at": conversation.created_at,
                "last_active": conversation.last_active,
                "messages": messages,
            }
        ),
    }


async def xagent_conversation_message(
    conversation_id: str, content: str, role: str = ""
) -> dict[str, Any]:
    """向现有租户会话发送消息，并以同一会话上下文运行 Agent。"""
    principal = _system_principal()
    if not _is_allowed(principal, "agent", "execute"):
        return _forbidden("agent", "execute")
    content = content.strip()
    if not content:
        return {"ok": False, "error": "missing_content"}
    from xagent.core.orchestration.conversation import load_conversation_from_db
    from xagent.infra.db import get_sessionmaker

    async with get_sessionmaker()() as session:
        try:
            conversation = await load_conversation_from_db(
                session, principal.tenant_id, conversation_id
            )
        except LookupError:
            conversation = None
    if conversation is None:
        return {"ok": False, "error": "conversation_not_found"}
    execution = await _execute_mcp_run(
        principal,
        content,
        role=role,
        conversation_id=conversation_id,
    )
    _audit(
        principal,
        "conversation.message",
        "conversation",
        {"conversation_id": conversation_id, "run_id": execution["run_id"]},
    )
    result = execution["result"]
    return {
        "ok": execution["ok"],
        "conversation_id": conversation_id,
        "run_id": execution["run_id"],
        "answer": result.get("final_answer", ""),
        "steps": result.get("steps", 0),
        "error": execution["error"],
    }


async def xagent_run_get(run_id: str) -> dict[str, Any]:
    """读取统一 Runtime run 视图。"""
    principal = _system_principal()
    if not _is_allowed(principal, "agent", "read"):
        return _forbidden("agent", "read")
    from xagent.core.runtime.service import get_runtime_run_detail
    from xagent.infra.db import get_sessionmaker

    async with get_sessionmaker()() as session:
        detail = await get_runtime_run_detail(
            session, run_id=run_id, tenant_id=principal.tenant_id
        )
    if detail is None:
        return {"ok": False, "error": "run_not_found"}
    _audit(principal, "run.get", "run", {"run_id": run_id})
    return {"ok": True, "run": _safe_payload(detail)}


async def xagent_run_cancel(
    run_id: str, confirm_run_id: str
) -> dict[str, Any]:
    """显式确认后取消当前租户内的可取消 run。"""
    principal = _system_principal()
    if not _is_allowed(principal, "agent", "execute"):
        return _forbidden("agent", "execute")
    if confirm_run_id != run_id:
        return {"ok": False, "error": "confirmation_mismatch"}
    from xagent.core.runtime.service import cancel_runtime_run
    from xagent.infra.db import get_sessionmaker

    async with get_sessionmaker()() as session:
        result = await cancel_runtime_run(
            session, run_id=run_id, tenant_id=principal.tenant_id
        )
        if result.get("cancelled"):
            await session.commit()
        else:
            await session.rollback()
    if result.get("error") == "run_not_found":
        return {"ok": False, **result}
    _audit(principal, "run.cancel", "run", {"run_id": run_id, **result})
    return {"ok": bool(result.get("cancelled")), **_safe_payload(result)}


async def xagent_run_events(run_id: str) -> dict[str, Any]:
    """读取统一 run 的 task/workflow/evidence 事件，并在出站前脱敏。"""
    result = await xagent_run_get(run_id)
    if not result.get("ok"):
        return result
    run = result["run"]
    task = run.get("task") or {}
    workflow = run.get("workflow") or {}
    task_result = task.get("result") or {}
    events: list[dict[str, Any]] = []
    for source, raw_items in (
        ("task", task_result.get("events") or []),
        ("workflow", workflow.get("timeline") or []),
        ("evidence", run.get("evidence") or []),
    ):
        for item in raw_items:
            event = dict(item) if isinstance(item, dict) else {"content": item}
            event["source"] = source
            events.append(event)
    principal = _system_principal()
    _audit(principal, "run.events", "run", {"run_id": run_id, "count": len(events)})
    return {"ok": True, "run_id": run_id, "events": _safe_payload(events)}


async def xagent_approval_list() -> dict[str, Any]:
    """列出开发任务和工作流中等待当前租户处理的审批。"""
    principal = _system_principal()
    if not _is_allowed(principal, "agent", "read"):
        return _forbidden("agent", "read")
    from xagent.core.workflow import get_engine
    from xagent.domains.development_tasks import (
        DevelopmentTaskStatus,
        list_development_tasks,
    )
    from xagent.infra.db import get_sessionmaker
    from xagent.infra.repos.workflow import load_workflow_runs

    async with get_sessionmaker()() as session:
        development = await list_development_tasks(session, principal.tenant_id)
        persisted_workflows = await load_workflow_runs(session, principal.tenant_id, 200)
    approvals = [
        _development_approval(record)
        for record in development
        if record.status == DevelopmentTaskStatus.awaiting_review
    ]
    workflow_views = {str(view.get("run_id") or ""): view for view in persisted_workflows}
    for run in get_engine().list_runs(principal.tenant_id):
        workflow_views[run.run_id] = run.to_view()
    for view in workflow_views.values():
        approvals.extend(_workflow_approvals(view))
    _audit(principal, "approval.list", "approval", {"count": len(approvals)})
    return {"ok": True, "items": _safe_payload(approvals)}


async def xagent_approval_resolve(
    approval_id: str, action: str, confirm_approval_id: str
) -> dict[str, Any]:
    """显式确认后批准/拒绝开发任务，或批准/拒绝工作流步骤。"""
    principal = _system_principal()
    if confirm_approval_id != approval_id:
        return {"ok": False, "error": "confirmation_mismatch"}
    action = action.strip().lower()
    from xagent.infra.db import get_sessionmaker

    if approval_id.startswith("development_task:"):
        if action not in {"approve", "reject"}:
            return {"ok": False, "error": "invalid_action"}
        resource, permission = (
            ("code_review", "execute") if action == "approve" else ("agent", "execute")
        )
        if not _is_allowed(principal, resource, permission):
            return _forbidden(resource, permission)
        task_id = approval_id.split(":", 1)[1]
        from xagent.domains.development_tasks import (
            DevelopmentTaskNotFoundError,
            DevelopmentTaskTransitionError,
            approve_development_task,
            reject_development_task,
        )

        try:
            async with get_sessionmaker()() as session:
                if action == "approve":
                    record = await approve_development_task(
                        session,
                        principal.tenant_id,
                        task_id,
                        reviewer_id=principal.user_id,
                    )
                else:
                    record = await reject_development_task(
                        session,
                        principal.tenant_id,
                        task_id,
                        actor_id=principal.user_id,
                    )
                await session.commit()
        except DevelopmentTaskNotFoundError:
            return {"ok": False, "error": "approval_not_found"}
        except DevelopmentTaskTransitionError as exc:
            return {"ok": False, "error": "invalid_transition", "detail": str(exc)}
        except (RuntimeError, ValueError) as exc:
            return {
                "ok": False,
                "error": "approval_resolve_failed",
                "detail": _safe_payload(str(exc)),
            }
        _audit(
            principal,
            f"approval.{action}",
            "development_task",
            {"approval_id": approval_id, "task_id": task_id},
        )
        return {"ok": True, "approval": _safe_payload(_development_approval(record))}

    if approval_id.startswith("workflow:"):
        if action not in {"approve", "deny"}:
            return {"ok": False, "error": "invalid_action"}
        if not _is_allowed(principal, "workflow", "execute"):
            return _forbidden("workflow", "execute")
        parts = approval_id.split(":", 2)
        if len(parts) != 3 or not parts[1] or not parts[2]:
            return {"ok": False, "error": "invalid_approval_id"}
        _, run_id, step_id = parts
        from xagent.core.workflow import get_engine
        from xagent.infra.repos.workflow import persist_workflow_run

        try:
            engine = get_engine()
            run = (
                await engine.approve(run_id, step_id, principal)
                if action == "approve"
                else await engine.deny(run_id, step_id, principal)
            )
        except (KeyError, RuntimeError):
            return {"ok": False, "error": "approval_not_active"}
        view = run.to_view()
        async with get_sessionmaker()() as session:
            await persist_workflow_run(session, view)
            await session.commit()
        _audit(
            principal,
            f"approval.{action}",
            "workflow",
            {"approval_id": approval_id, "run_id": run_id, "step_id": step_id},
        )
        return {"ok": True, "approval": _safe_payload(view)}
    return {"ok": False, "error": "invalid_approval_id"}


async def xagent_scheduler_job_read(job_id: str = "") -> dict[str, Any]:
    """读取当前租户的 scheduler job 列表或指定 job。"""
    principal = _system_principal()
    if not _is_allowed(principal, "agent", "read"):
        return _forbidden("agent", "read")
    from xagent.domains.scheduled_jobs import get_scheduled_job, list_scheduled_jobs
    from xagent.infra.db import get_sessionmaker

    async with get_sessionmaker()() as session:
        if job_id:
            job = await get_scheduled_job(session, principal.tenant_id, job_id)
            if job is None:
                return {"ok": False, "error": "job_not_found"}
            items = [job]
        else:
            items = await list_scheduled_jobs(session, principal.tenant_id)
    _audit(principal, "scheduler.job.read", "scheduler", {"job_id": job_id})
    return {"ok": True, "items": _safe_payload(items)}


async def xagent_scheduler_run_read(
    job_id: str = "", run_id: str = ""
) -> dict[str, Any]:
    """读取当前租户的 scheduler run 历史，可按 job/run 过滤。"""
    principal = _system_principal()
    if not _is_allowed(principal, "agent", "read"):
        return _forbidden("agent", "read")
    from xagent.domains.scheduled_jobs import list_scheduled_job_runs
    from xagent.infra.db import get_sessionmaker

    async with get_sessionmaker()() as session:
        items = await list_scheduled_job_runs(
            session, principal.tenant_id, job_id or None
        )
    if run_id:
        items = [item for item in items if item.run_id == run_id]
        if not items:
            return {"ok": False, "error": "scheduler_run_not_found"}
    _audit(
        principal,
        "scheduler.run.read",
        "scheduler",
        {"job_id": job_id, "run_id": run_id},
    )
    return {"ok": True, "items": _safe_payload(items)}


async def xagent_skill_package_read(package_id: str = "") -> dict[str, Any]:
    """读取当前租户 Skill Package；永不返回服务器 root_path。"""
    principal = _system_principal()
    if not _is_allowed(principal, "agent", "read"):
        return _forbidden("agent", "read")
    from xagent.domains.skill_packages import get_skill_package, list_skill_packages
    from xagent.infra.db import get_sessionmaker

    async with get_sessionmaker()() as session:
        if package_id:
            package = await get_skill_package(session, principal.tenant_id, package_id)
            if package is None:
                return {"ok": False, "error": "skill_package_not_found"}
            items = [package]
        else:
            items = await list_skill_packages(session, principal.tenant_id)
    _audit(
        principal,
        "skill_package.read",
        "skill_package",
        {"package_id": package_id},
    )
    return {
        "ok": True,
        "items": _safe_payload(
            [_skill_package_view(item, detail=bool(package_id)) for item in items]
        ),
    }


server.add_tool(xagent_run, description="运行一次 X-Agent 任务，返回最终回答")
server.add_tool(xagent_code_review, description="代码评审：逻辑/安全/规范三维并行")
server.add_tool(xagent_skill_match, description="按任务目标匹配技能库 + prompt 注入文本")
server.add_tool(xagent_skill_import, description="导入 SKILL.md（agentskills.io，强制质量门禁）")
server.add_tool(xagent_conversation_list, description="列出当前租户的持久会话")
server.add_tool(xagent_conversation_get, description="读取当前租户的会话与消息")
server.add_tool(xagent_conversation_message, description="向现有会话发送消息并运行 Agent")
server.add_tool(xagent_run_get, description="读取当前租户统一 Runtime run")
server.add_tool(xagent_run_cancel, description="显式确认后取消当前租户 run")
server.add_tool(xagent_run_events, description="读取并脱敏当前租户 run 事件")
server.add_tool(xagent_approval_list, description="列出当前租户待处理审批")
server.add_tool(xagent_approval_resolve, description="显式确认后处理开发任务或工作流审批")
server.add_tool(xagent_scheduler_job_read, description="读取当前租户 scheduler jobs")
server.add_tool(xagent_scheduler_run_read, description="读取当前租户 scheduler run 历史")
server.add_tool(xagent_skill_package_read, description="读取当前租户 Skill Package")


class _BearerAuthMiddleware:
    """纯 ASGI Bearer 校验（仅当 XAGENT_PLATFORM_MCP_TOKEN 设置时启用）。"""

    def __init__(self, app: Any, token: str) -> None:
        self._app = app
        self._token = token

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            auth = headers.get(b"authorization", b"").decode()
            if auth != f"Bearer {self._token}":
                body = b'{"error":"unauthorized"}'
                await send({
                    "type": "http.response.start", "status": 401,
                    "headers": [(b"content-type", b"application/json")],
                })
                await send({"type": "http.response.body", "body": body})
                return
        await self._app(scope, receive, send)


def build_http_app(token: str | None = None) -> Any:
    """构建 streamable HTTP ASGI 应用（无状态模式，每次调用独立）。"""
    app: Any = server.streamable_http_app(
        streamable_http_path="/mcp", stateless_http=True
    )
    token = token if token is not None else os.environ.get("XAGENT_PLATFORM_MCP_TOKEN", "")
    if token:
        app = _BearerAuthMiddleware(app, token)
    return app


def _http_token_required(host: str, token: str) -> bool:
    """非回环 HTTP 监听不允许在无 Bearer token 时启动。"""
    if token:
        return False
    normalized = host.strip().lower().strip("[]")
    if normalized == "localhost":
        return False
    try:
        return not ip_address(normalized).is_loopback
    except ValueError:
        return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--http", action="store_true", help="streamable HTTP 模式（默认 stdio）")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP 绑定地址（默认仅本机）")
    parser.add_argument("--port", type=int, default=8100)
    args = parser.parse_args()

    if args.http:
        import uvicorn

        token = os.environ.get("XAGENT_PLATFORM_MCP_TOKEN", "")
        if _http_token_required(args.host, token):
            logger.error("platform_mcp_http_token_required", host=args.host)
            return 2
        logger.info("platform_mcp_http_start", host=args.host, port=args.port)
        uvicorn.run(build_http_app(token=token), host=args.host, port=args.port)
        return 0

    # stdio：被宿主 agent 拉起
    import anyio

    anyio.run(server.run_stdio_async)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

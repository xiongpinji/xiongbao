"""内置 agent 循环。

策略：在 system prompt 中告知模型可用工具与「动作协议」——若需调用工具，
只输出一行 JSON：{"action":"tool","tool":"<name>","args":{...}}；
若已可作答，输出：{"action":"final","answer":"..."} 或直接自然语言。

解析鲁棒：能从混杂文本里提取 JSON；解析失败/无动作即视为 final（保证终止）。
mock LLM 返回普通文本 -> 第一步即 final，循环安全收敛。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from xagent.adapters.llm import Message, get_llm_client
from xagent.adapters.llm.litellm_client import LiteLLMClient, StreamChunk
from xagent.adapters.observability import get_tracer
from xagent.adapters.tools import get_tool_registry
from xagent.adapters.tools.base import ToolContext
from xagent.core.agents import get_role_registry
from xagent.core.orchestration.conversation import get_conversation_manager
from xagent.core.orchestration.state import AgentRun, AgentState, StepEvent, StepKind
from xagent.enterprise.auth.principal import Principal
from xagent.infra.logging import get_logger

logger = get_logger("xagent.loop")

MAX_STEPS = 40
_AGENT_RUN_TIMEOUT = 600  # 10 分钟
_WORKSPACE = Path(os.environ.get("XAGENT_WORKSPACE", Path.home() / "xagent_workspace"))

# ── LLM 调用重试配置（对标 Codex 的自动重试 + 指数退避） ──
_LLM_MAX_RETRIES = 3
_LLM_RETRY_BASE_DELAY = 2.0  # 秒
_LLM_RETRYABLE_ERRORS = ("rate_limit", "timeout", "connection", "server_error", "overloaded", "503", "429")

# ── 单工具执行超时（防止单个工具卡死整个循环） ──
_TOOL_TIMEOUT = 180  # 秒（shell_exec 自带 120s，这里做外层保护）

# ── Token 预算：超过此值触发主动压缩 ──
_TOKEN_BUDGET = 100_000  # 估算上下文 token 上限
_CHARS_PER_TOKEN = 4  # 粗略估算比例


async def _llm_call_with_retry(coro_factory, *, description: str = "llm_call"):
    """LLM 调用包装器：失败时指数退避重试。

    coro_factory: 无参函数，每次调用返回新的 coroutine。
    """
    last_exc = None
    for attempt in range(_LLM_MAX_RETRIES):
        try:
            return await coro_factory()
        except Exception as exc:
            last_exc = exc
            err_str = str(exc).lower()
            is_retryable = any(k in err_str for k in _LLM_RETRYABLE_ERRORS)
            if not is_retryable or attempt == _LLM_MAX_RETRIES - 1:
                raise
            delay = _LLM_RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                "llm_retry",
                attempt=attempt + 1,
                delay=delay,
                error=str(exc)[:200],
                description=description,
            )
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]

# ── 编辑类工具：触发验证闭环 ──
_EDIT_TOOLS = {"file_edit", "file_write"}
# ── 验证命令探测优先级 ──
_VERIFY_COMMANDS = [
    ("pyproject.toml", "python -m pytest --tb=short -q"),
    ("pytest.ini", "python -m pytest --tb=short -q"),
    ("package.json", "npx tsc --noEmit"),
    ("tsconfig.json", "npx tsc --noEmit"),
    ("Cargo.toml", "cargo check"),
    ("go.mod", "go build ./..."),
]


def _load_agents_md() -> str:
    """Load AGENTS.md project instructions (Codex-aligned).

    Searches workspace root and common locations for AGENTS.md,
    returns content to inject into system prompt.
    """
    candidates = [
        _WORKSPACE / "AGENTS.md",
        _WORKSPACE / "agents.md",
        _WORKSPACE / ".agents" / "AGENTS.md",
        Path.cwd() / "AGENTS.md",
    ]
    for p in candidates:
        try:
            if p.is_file():
                content = p.read_text(encoding="utf-8").strip()
                if content:
                    return content[:3000]  # cap at 3000 chars
        except OSError:
            continue
    return ""


async def _compress_context(messages: list[Message], llm, model: str | None) -> list[Message]:
    """Context compression: summarize old messages when conversation is too long.

    Codex-aligned: prevents context window overflow on long tasks.
    Keeps system + last N messages intact, compresses middle history.
    保护 tool_call_id 配对完整性：不会在 assistant+tool 消息对中间截断。
    """
    # Only compress if messages exceed threshold
    if len(messages) <= 20:
        return messages

    # Keep: system (first) + last 10 messages
    system_msg = messages[0] if messages[0].role == "system" else None
    keep_tail = 10
    start_idx = 1 if system_msg else 0
    end_idx = len(messages) - keep_tail

    if end_idx <= start_idx + 4:  # not enough to compress
        return messages

    # ── 保护 tool_call_id 完整性：调整截断点，不在 tool 消息中间截断 ──
    # 如果 end_idx 指向 tool role 消息，向前回退到对应的 assistant 消息之前
    while end_idx > start_idx and messages[end_idx].role == "tool":
        end_idx -= 1
    # 如果回退后指向 assistant 消息且其后紧跟 tool，再回退一步
    if end_idx > start_idx and messages[end_idx].role == "assistant":
        # 检查后面是否紧跟 tool 消息
        if end_idx + 1 < len(messages) and messages[end_idx + 1].role == "tool":
            end_idx -= 1

    if end_idx <= start_idx + 2:
        return messages

    # Build summary of middle section
    middle = messages[start_idx:end_idx]
    middle_text = "\n".join(
        f"{m.role}: {m.content[:200]}" for m in middle if m.content
    )[:4000]

    summary_prompt = (
        "Summarize the following conversation history into a concise context block. "
        "Focus on: what tools were called, what files were created/modified, "
        "what errors occurred, and current progress. Max 500 words.\n\n"
        + middle_text
    )

    try:
        resp = await llm.complete(
            [Message(role="user", content=summary_prompt)], model=model
        )
        summary = (resp.content or "").strip()
        if summary and len(summary) > 50:
            compressed = Message(
                role="user",
                content=f"[Context Summary - {len(middle)} messages compressed]\n{summary}",
            )
            result = []
            if system_msg:
                result.append(system_msg)
            result.append(compressed)
            result.extend(messages[end_idx:])
            return result
    except Exception:
        pass

    return messages


# ═══════════════════════════════════════════════════════════
#  项目结构感知（任务启动时自动探测）
# ═══════════════════════════════════════════════════════════


def _detect_project_context(workspace: Path) -> str:
    """探测项目结构 + 读取关键配置内容，返回注入 system prompt 的上下文摘要。

    Codex 对齐：进入 repo 先建立结构认知 + 读取关键文件，避免盲打。
    """
    lines: list[str] = []

    # 1. 探测项目类型
    markers = {
        "pyproject.toml": "Python (pyproject)",
        "setup.py": "Python (setup.py)",
        "package.json": "Node.js/TypeScript",
        "Cargo.toml": "Rust",
        "go.mod": "Go",
        "pom.xml": "Java (Maven)",
        "build.gradle": "Java (Gradle)",
    }
    project_type = "Unknown"
    for marker, label in markers.items():
        if (workspace / marker).is_file():
            project_type = label
            break
    lines.append(f"项目类型: {project_type}")
    lines.append(f"工作目录: {workspace}")

    # 2. 顶层目录结构（最多 2 层，排除噪音）
    _SKIP = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", ".next", ".ruff_cache", ".pytest_cache", ".worktrees", ".codegraph"}
    tree_lines: list[str] = []
    try:
        for item in sorted(workspace.iterdir()):
            if item.name in _SKIP or item.name.startswith("."):
                continue
            prefix = "📂" if item.is_dir() else "📄"
            tree_lines.append(f"  {prefix} {item.name}")
            if item.is_dir():
                try:
                    for sub in sorted(item.iterdir())[:8]:
                        if sub.name in _SKIP or sub.name.startswith("."):
                            continue
                        sub_prefix = "📂" if sub.is_dir() else "📄"
                        tree_lines.append(f"    {sub_prefix} {sub.name}")
                except OSError:
                    pass
            if len(tree_lines) > 40:
                tree_lines.append("  ... (截断)")
                break
    except OSError:
        pass
    if tree_lines:
        lines.append("项目结构:")
        lines.extend(tree_lines)

    # 3. 读取关键配置文件内容（让模型知道依赖/脚本/入口）
    _KEY_FILES = [
        "package.json", "pyproject.toml", "tsconfig.json",
        "Cargo.toml", "go.mod", "Makefile",
    ]
    for kf in _KEY_FILES:
        kf_path = workspace / kf
        if kf_path.is_file():
            try:
                content = kf_path.read_text(encoding="utf-8", errors="replace")
                # 只保留前 800 字符（避免注入过多）
                lines.append(f"\n--- {kf} (摘要) ---")
                lines.append(content[:800])
                if len(content) > 800:
                    lines.append("... (截断)")
            except OSError:
                pass
            break  # 只读第一个匹配的配置文件

    # 4. 探测验证命令
    verify_cmd = _detect_verify_command(workspace)
    if verify_cmd:
        lines.append(f"\n建议验证命令: {verify_cmd}")

    return "\n".join(lines)


def _detect_verify_command(workspace: Path) -> str | None:
    """探测项目可用的验证命令。"""
    for marker, cmd in _VERIFY_COMMANDS:
        if (workspace / marker).is_file():
            return cmd
    return None


# ═══════════════════════════════════════════════════════════
#  Git 事务隔离（多文件编辑保护）
# ═══════════════════════════════════════════════════════════


def _git_create_work_branch(workspace: Path, run_id: str) -> str | None:
    """创建临时工作分支，返回分支名。失败返回 None。"""
    import shutil as _shutil
    import subprocess as _sp

    git = _shutil.which("git")
    if not git:
        return None
    branch = f"xagent/run-{run_id[:8]}"
    try:
        # 确保在 git 仓库中
        rc = _sp.run([git, "rev-parse", "--is-inside-work-tree"],
                     cwd=str(workspace), capture_output=True, timeout=5)
        if rc.returncode != 0:
            return None
        _sp.run([git, "checkout", "-b", branch],
                cwd=str(workspace), capture_output=True, timeout=10)
        return branch
    except Exception:
        return None


def _git_rollback(workspace: Path, branch: str) -> None:
    """回滚到工作分支创建前的状态。"""
    import shutil as _shutil
    import subprocess as _sp

    git = _shutil.which("git")
    if not git:
        return
    try:
        _sp.run([git, "checkout", "--", "."],
                cwd=str(workspace), capture_output=True, timeout=10)
        _sp.run([git, "clean", "-fd"],
                cwd=str(workspace), capture_output=True, timeout=10)
    except Exception:
        pass


def _git_cleanup_branch(workspace: Path, branch: str) -> None:
    """任务成功后清理临时分支（切回原分支并删除）。"""
    import shutil as _shutil
    import subprocess as _sp

    git = _shutil.which("git")
    if not git:
        return
    try:
        # 获取之前的分支
        rc = _sp.run([git, "reflog", "show", "--format=%gs", "-1"],
                     cwd=str(workspace), capture_output=True, text=True, timeout=5)
        prev = "main"
        if rc.stdout.strip():
            # reflog 格式: "checkout: moving from X to Y"
            parts = rc.stdout.strip().split(" from ")
            if len(parts) == 2:
                prev = parts[1].split(" to ")[0]
        _sp.run([git, "checkout", prev],
                cwd=str(workspace), capture_output=True, timeout=10)
        _sp.run([git, "branch", "-D", branch],
                cwd=str(workspace), capture_output=True, timeout=5)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════
#  验证闭环（编辑后自动验证）
# ═══════════════════════════════════════════════════════════


async def _run_verification(workspace: Path, ctx, changed_files: list[str] | None = None) -> tuple[bool, str]:
    """执行项目验证命令，返回 (passed, output)。

    智能验证：如果有 changed_files，尝试只跑相关测试。
    """
    from xagent.adapters.tools import get_tool_registry

    # 智能验证：根据修改文件选择验证命令
    verify_cmd = _detect_verify_command(workspace)
    if not verify_cmd:
        return True, "(无可用验证命令，跳过)"

    # 如果修改了 Python 文件，尝试只跑相关测试
    if changed_files and "pytest" in verify_cmd:
        py_files = [f for f in changed_files if f.endswith(".py")]
        if py_files:
            # 尝试找对应的 test 文件
            test_targets = []
            for f in py_files[:3]:  # 最多 3 个
                p = Path(f)
                test_name = f"test_{p.name}"
                test_path = p.parent / test_name
                if test_path.exists():
                    test_targets.append(str(test_path))
                # 也尝试 tests/ 目录
                alt = workspace / "tests" / test_name
                if alt.exists():
                    test_targets.append(str(alt))
            if test_targets:
                verify_cmd = f"python -m pytest {' '.join(test_targets)} --tb=short -q"

    tools = get_tool_registry()
    result = await tools.call("shell_exec", {"command": verify_cmd, "timeout": 60}, ctx)
    output = result.output if result.ok else (result.error or "")
    passed = result.ok and "error" not in output.lower()[:200]
    return passed, output[:2000]


# ═══════════════════════════════════════════════════════════
#  工具结果智能截断
# ═══════════════════════════════════════════════════════════

_MAX_TOOL_OUTPUT = 4000  # 工具结果最大字符数


def _truncate_tool_output(text: str, tool_name: str) -> str:
    """智能截断工具输出：保留头尾，中间截断。

    不同工具不同策略：
    - code_search: 保留前 N 条结果
    - shell_exec: 保留头 + 尾（错误通常在尾部）
    - file_read: 保留前 N 行
    """
    if len(text) <= _MAX_TOOL_OUTPUT:
        return text

    if tool_name == "shell_exec":
        # 保留头部 1500 + 尾部 2000（错误信息通常在尾部）
        head = text[:1500]
        tail = text[-2000:]
        return f"{head}\n\n... [中间 {len(text) - 3500} 字符已截断] ...\n\n{tail}"
    elif tool_name == "code_search":
        # 保留前 N 条结果
        lines = text.split("\n")
        kept = lines[:60]
        return "\n".join(kept) + f"\n... [共 {len(lines)} 行，已截断]"
    else:
        # 通用：头部 + 尾部
        head = text[:2000]
        tail = text[-1500:]
        return f"{head}\n\n... [中间 {len(text) - 3500} 字符已截断] ...\n\n{tail}"


async def _retrieve_relevant_memories(goal: str, tenant_id: str) -> str:
    """检索与当前目标相关的记忆，返回拼接文本（空则无记忆）。"""
    try:
        from xagent.adapters.memory import get_vector_store

        hits = await get_vector_store().search(goal, top_k=3, tenant_id=tenant_id)
        if not hits:
            return ""
        lines = [f"- {h.text}" for h in hits if h.score > 0.3]
        return "\n".join(lines)
    except Exception:  # noqa: S110  记忆检索失败不影响主流程
        return ""


async def _save_to_memory(goal: str, answer: str, tenant_id: str) -> None:
    """将重要的 Q&A 对自动写入记忆库。"""
    try:
        import uuid as _uuid

        from xagent.adapters.memory import MemoryRecord, get_vector_store

        # 只保存有实质内容的回复（超过 20 字符）
        if len(answer) < 20:
            return
        record = MemoryRecord(
            id=f"conv_{_uuid.uuid4().hex[:12]}",
            text=f"用户: {goal[:200]}\n助手: {answer[:500]}",
            metadata={"tenant_id": tenant_id, "source": "auto_conversation"},
        )
        await get_vector_store().upsert([record])
    except Exception:  # noqa: S110
        pass


async def _auto_extract_skill(
    goal: str, answer: str, steps_count: int, events: list[StepEvent]
) -> None:
    """任务完成后自动提炼可复用技能（Skill 自进化核心）。

    触发条件：
    - 任务步数 >= 3（复杂任务）
    - 回答有实质内容
    - 无已有高效技能覆盖此场景
    """
    try:
        from xagent.core.skills import get_skill_store

        # 提取使用过的工具列表（工具名在 e.tool 字段）
        tools_used = [
            e.tool for e in events
            if e.kind == StepKind.tool_call and e.tool
        ]
        store = get_skill_store()
        await store.auto_extract(
            goal=goal,
            answer=answer,
            steps_count=steps_count,
            tools_used=tools_used or None,
        )
    except Exception as _sk_exc:  # noqa: S110  技能提炼失败不影响主流程
        from xagent.infra.logging import get_logger as _gl
        _gl("xagent.skills").debug("auto_extract_failed", error=str(_sk_exc))


def _build_system_prompt(role_system: str, tool_specs: list[dict[str, Any]]) -> str:
    lines = [role_system, "", "你可以使用以下工具："]
    for s in tool_specs:
        fn = s["function"]
        lines.append(f"- {fn['name']}: {fn['description']}")
    lines += [
        "",
        "动作协议（严格）：",
        '需要调用工具时，只输出一行 JSON：{"action":"tool","tool":"<名称>","args":{...}}',
        '已能作答时，输出：{"action":"final","answer":"<最终回答>"}',
        "不要输出多余文本。",
    ]
    return "\n".join(lines)


def _extract_action(text: str) -> dict[str, Any] | None:
    """从模型输出中尽力提取动作 JSON。失败返回 None。"""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    i, j = text.find("{"), text.rfind("}")
    if i == -1 or j == -1 or j <= i:
        return None
    try:
        obj = json.loads(text[i : j + 1])
        return obj if isinstance(obj, dict) and "action" in obj else None
    except Exception:
        return None


def _is_tool_echo(text: str) -> bool:
    """检测 LLM 输出是否为工具结果的原样复述。"""
    t = text.strip()
    if not t:
        return False
    if t.startswith("工具 ") and "结果：" in t[:80]:
        return True
    if t.startswith("[参考数据") or t.startswith("[错误]"):
        return True
    if t.startswith("{") and '"total_count"' in t[:200]:
        return True
    return False


def _detect_final_answer(content: str, state: AgentState) -> bool:
    """智能判断 LLM 输出是否为真正的最终回答。

    策略：综合多个信号判断，避免误判中间规划为最终回答。
    """
    text = content.strip()
    if not text:
        return True  # 空内容视为终止（由 _handle_empty_or_echo 处理）

    # ── 信号 1：包含询问用户的问句 → 中间态 ──
    _ASK_PATTERNS = (
        "要继续吗", "需要我继续", "你想从", "是否继续",
        "需要我进一步", "告诉我目标", "请确认",
        "哪一项", "哪个方向", "你希望",
    )
    if any(p in text for p in _ASK_PATTERNS):
        return False

    # ── 信号 2：包含“接下来/下一步”等继续信号且无测试结果 → 中间态 ──
    _CONTINUE_WORDS = (
        "接下来", "下一步", "现在并行", "然后我将", "准备创建",
        "开始写", "开始创建", "现在完成", "现在执行",
    )
    has_continue = any(w in text for w in _CONTINUE_WORDS)

    # ── 信号 3：包含测试结果/完成总结 → 最终态 ──
    _FINAL_EVIDENCE = (
        "passed", "failed", "测试通过", "测试失败",
        "全部完成", "所有测试通过", "所有子任务已完成",
        "项目完成总结", "开发完成", "✅ 全部",
        "exit code: 0", "RETURNCODE: 0",
    )
    has_final_evidence = any(e in text for e in _FINAL_EVIDENCE)

    # ── 信号 4：工具调用历史 — 如果之前有工具调用，纯文本更可能是中间态 ──
    recent_tool_results = sum(
        1 for m in state.messages[-10:]
        if m.role == "tool"
    )
    has_recent_tools = recent_tool_results > 0

    # ── 综合判断 ──
    # 规则 1：有明确完成证据 → 最终
    if has_final_evidence and not has_continue:
        return True
    # 规则 2：有继续信号 → 中间
    if has_continue:
        return False
    # 规则 3：有询问 → 中间
    # (已在上面处理)
    # 规则 4：之前有工具调用 + 文本较短(<800字) + 无完成证据 → 中间
    if has_recent_tools and len(text) < 800 and not has_final_evidence:
        return False
    # 规则 5：步数很少(<3)且无完成证据 → 可能是第一轮分析，允许终止
    #   但如果用户 goal 含多个子任务（数字列表），则不允许
    if state.step <= 2 and not has_final_evidence:
        # 检查 goal 是否含多步骤
        goal = ""
        for m in state.messages:
            if m.role == "user" and not m.content.startswith("["):
                goal = m.content
                break
        multi_step = bool(re.search(r'[1-9]\)', goal)) or goal.count("、") >= 2
        if multi_step:
            return False
    # 默认：允许终止
    return True


async def _handle_empty_or_echo(
    content_buf: str,
    state: AgentState,
    llm,
    target_model: str | None,
) -> str:
    """处理 LLM 返回空内容或回显工具结果的情况，返回修正后的内容。"""
    if _is_tool_echo(content_buf):
        state.messages.append(Message(role="assistant", content=content_buf))
        state.messages.append(Message(
            role="user",
            content=(
                "[指令] 你刚才只是复述了工具的原始返回数据，这不是合格的回答。"
                "请你现在基于这些数据，用你自己的语言写一份结构化的分析/总结/方案。"
                "要求：1)不要出现'工具xx结果'字样 2)提炼关键信息 3)给出结论或建议。"
            ),
        ))
        try:
            retry_resp = await llm.complete(state.messages, model=target_model)
            content_buf = retry_resp.content or ""
        except Exception:
            content_buf = ""
        if _is_tool_echo(content_buf):
            content_buf = ""

    if not content_buf.strip():
        state.messages.append(Message(
            role="user",
            content=(
                "[系统提示] 请基于已有的工具执行结果和你的知识，"
                "尽可能回答用户的问题。不要原样复述工具结果，要综合分析。"
            ),
        ))
        try:
            retry_resp = await llm.complete(state.messages, model=target_model)
            content_buf = retry_resp.content or ""
        except Exception:
            content_buf = ""
        if not content_buf.strip():
            content_buf = (
                "我已尝试获取相关信息，但受限于页面动态渲染或工具调用次数，"
                "未能获取完整内容。\n\n"
                "建议：\n"
                "1. 请告诉我该网站/项目的具体功能，我可以帮你分析\n"
                "2. 如果有 GitHub 仓库地址，我可以查看 README\n"
                "3. 如果有 API 文档链接，我可以获取更详细的信息"
            )
    return content_buf


def _tool_system_prompt_native(role_system: str, tool_specs: list[dict[str, Any]]) -> str:
    """原生 function-calling 模式下的 system prompt（工具由 API 注入，无需协议说明）。"""
    lines = [
        role_system,
        "",
        "## 核心行为准则（必须严格遵守）",
        "1. **行动优先**：当用户要求开发/创建/修复/执行时，直接调用工具执行，不要先写分析报告再问用户确认。",
        "2. **少说多做**：每轮回复中，工具调用应占主导。文字只用于简短说明你正在做什么（1-2句），不要写长篇分析。",
        "3. **绝对禁止中途停止**：在用户的所有子任务全部完成之前，绝对禁止：",
        "   - 问用户“要继续吗？”“需要我继续推进哪一项？”“你想从哪里开始？”",
        "   - 输出中间规划/待办列表然后等待用户指令",
        "   - 说“接下来我将...”然后不调用工具",
        "   你必须自己判断下一步并立即执行，直到全部完成。",
        "4. **连续执行**：完成一步后立即执行下一步，中间不要停顿。",
        "5. **文件操作**：创建/修改代码文件时，直接用 file_write 工具写入完整内容，不要把代码贴在回复里让用户复制。",
        "6. **命令执行**：需要安装依赖/启动服务/运行测试时，直接用 shell_exec 执行，不要给用户“手动操作指南”。",
        "7. **完成标准**：只有当用户要求的所有子任务都已执行完毕（文件已创建、测试已运行、结果已确认）后，才可以输出最终总结。最终总结必须包含“全部完成”或测试结果。",
        "",
        "## 工具使用规则",
        "1. 按需调用工具完成任务；已无更多工具可用时直接给出最终回答。",
        "2. **禁止原样复述工具返回的原始结果**。你必须对工具结果进行分析、总结、提炼，用你自己的语言回答用户。",
        "3. 如果工具未能获取有效信息，基于已有信息合理推断并给出建议。",
        "4. 最终回答应该是结构化的分析/方案/总结，而不是工具日志的复制粘贴。",
        "",
        "## 验证与自恢复（核心）",
        "1. **编辑后验证**：每次用 file_edit/file_write 修改代码后，必须用 shell_exec 运行验证（测试/类型检查/编译）确认修改正确。",
        "2. **错误自恢复**：工具调用失败时，读取错误信息→分析原因→修改方案→重试。不要直接放弃。",
        "3. **多文件编辑**：修改多个文件时，先用 file_list/code_search 确认文件存在，再逐个修改，最后统一验证。",
        "4. **项目感知**：开始任务前，先用 file_list 查看项目结构，用 file_read 读取关键文件（入口/配置），建立上下文后再动手。",
    ]
    return "\n".join(lines)


async def _handle_prompt_tool_action(
    action: dict[str, Any],
    role,
    tools,
    ctx,
    state: AgentState,
    events: list[StepEvent],
) -> None:
    """提示工程路径：处理 {"action":"tool",...} 动作。"""
    tool_name = action.get("tool", "")
    args = action.get("args", {}) or {}
    events.append(
        StepEvent(kind=StepKind.tool_call, tool=tool_name, content=args, step=state.step)
    )
    if not role.can_use(tool_name):
        result_text = f"[拒绝] 角色 {role.name} 无权使用工具 {tool_name}"
    else:
        result = await tools.call(tool_name, args, ctx)
        result_text = (
            (json.dumps(result.output, ensure_ascii=False) if not isinstance(result.output, str) else result.output)
            if result.ok
            else f"[错误] {result.error}"
        )
    events.append(
        StepEvent(
            kind=StepKind.tool_result,
            tool=tool_name,
            content=result_text,
            step=state.step,
        )
    )
    # 原生 tool role（提示工程路径无 tool_call_id，用合成 ID）
    tc_id = f"prompt_{state.step}_{tool_name}"
    state.messages.append(
        Message(role="tool", content=result_text, tool_call_id=tc_id, name=tool_name)
    )


async def run_agent(
    goal: str,
    *,
    principal: Principal,
    role_name: str | None = None,
    capabilities: set[str] | None = None,
    model: str | None = None,
    on_event: Any = None,
    session: Any = None,
    run_id: str | None = None,
    conversation_id: str | None = None,
    permission_mode: str = "full-auto",
) -> AgentRun:
    """运行一次 agent 任务，返回含事件序列的结果。

    on_event: 可选异步回调 (StepEvent) -> None，用于 SSE 实时推送。
    conversation_id: 会话 ID，传入则启用多轮对话。
    permission_mode: 权限模式 (suggest | auto-edit | full-auto)。
    """
    registry = get_role_registry()
    role = (
        registry.get(role_name)
        if role_name
        else registry.match(capabilities or {"general"})
    )
    if role is None:
        role = registry.match({"general"})

    tools = get_tool_registry()
    resolved_run_id = run_id or uuid.uuid4().hex
    # 仅暴露该角色允许的工具
    specs = [s for s in tools.specs() if role.can_use(s["function"]["name"])]

    # ── 多轮对话：加载历史 ──
    conv_mgr = get_conversation_manager()
    conv_session = conv_mgr.get_or_create(conversation_id, principal.tenant_id)
    history = conv_session.get_history(max_turns=8)

    # ── 自动记忆注入：检索相关记忆 ──
    memory_context = await _retrieve_relevant_memories(goal, principal.tenant_id)

    # 构建消息列表：system + 历史 + 当前 goal
    messages: list[Message] = []
    # 历史消息放在 goal 之前
    messages.extend(history)
    messages.append(Message(role="user", content=goal))

    state = AgentState(
        goal=goal,
        role_name=role.name,
        tenant_id=principal.tenant_id,
        messages=messages,
    )
    events: list[StepEvent] = []

    async def _emit(ev: StepEvent) -> None:
        events.append(ev)
        if on_event is not None:
            try:
                await on_event(ev)
            except Exception:  # noqa: S110  回调失败不影响编排
                pass

    llm = get_llm_client()
    tracer = get_tracer()
    ctx = ToolContext(principal=principal, session=session, run_id=resolved_run_id)
    target_model = model or role.preferred_model

    # 选择执行路径：支持原生 function-calling 走工具路径，否则提示工程降级
    use_native_tools = getattr(llm, "supports_tools", False) and bool(specs)
    if use_native_tools:
        system = _tool_system_prompt_native(role.system_prompt, specs)
    else:
        system = _build_system_prompt(role.system_prompt, specs)
    # 注入记忆上下文
    if memory_context:
        system += f"\n\n相关记忆（供参考）：\n{memory_context}"
    # 注入 AGENTS.md 项目指令（Codex 对齐）
    agents_md = _load_agents_md()
    if agents_md:
        system += f"\n\n## 项目指令 (AGENTS.md)\n{agents_md}"
    # 注入项目结构感知（Codex 对齐：先建立结构认知）
    project_ctx = _detect_project_context(_WORKSPACE)
    if project_ctx:
        system += f"\n\n## 项目环境\n{project_ctx}"
    # 注入权限模式说明（Codex 对齐）
    _MODE_DESC = {
        "suggest": "\n\n## 权限模式: suggest\n你只能建议代码修改，不能直接执行文件写入或 shell 命令。输出建议让用户确认。",
        "auto-edit": "\n\n## 权限模式: auto-edit\n你可以直接读写文件，但执行 shell 命令前应说明意图。",
        "full-auto": "",  # 默认模式，无额外限制
    }
    system += _MODE_DESC.get(permission_mode, "")
    # 注入匹配的技能（Skill 系统）
    try:
        from xagent.core.skills import get_skill_store
        skill_hint = get_skill_store().build_prompt_injection(goal)
        if skill_hint:
            system += f"\n\n{skill_hint}"
    except Exception:  # noqa: S110
        pass
    state.messages.insert(0, Message(role="system", content=system))

    # ── 任务规划阶段：复杂任务先分解再执行（Codex 对齐） ──
    _is_complex = (
        len(goal) > 100
        or goal.count("、") >= 2
        or bool(re.search(r'[1-9][)\.]', goal))
        or any(w in goal for w in ("并且", "同时", "然后", "接着", "分别"))
    )
    # ── 自适应步数：复杂任务动态提升 MAX_STEPS ──
    _effective_max_steps = MAX_STEPS
    if _is_complex:
        # 复杂任务：根据长度和子任务数动态调整
        _subtask_count = max(goal.count("、"), len(re.findall(r'[1-9][)\.]', goal)), 1)
        _effective_max_steps = min(MAX_STEPS + _subtask_count * 5, 80)  # 上限 80
    if _is_complex:
        state.messages.append(Message(
            role="user",
            content=(
                "[系统] 这是一个复杂多步骤任务。请先在内心规划执行步骤（不要输出给用户），"
                "然后立即开始执行第一步。每完成一步后立即执行下一步，直到全部完成。"
            ),
        ))

    async with tracer.trace("agent.run", role=role.name, tenant=principal.tenant_id) as span:
        span.set_input(goal)
        _run_start = time.perf_counter()
        # 判断是否支持流式
        can_stream = isinstance(llm, LiteLLMClient) and use_native_tools

        # ── Git 事务隔离：创建临时工作分支 ──
        _work_branch: str | None = None
        _edit_count = 0  # 跟踪编辑次数，首次编辑时创建分支

        # ── 文件变更追踪（任务结束时生成 diff 摘要） ──
        _changed_files: list[str] = []

        # ── 错误自恢复计数器 ──
        _consecutive_errors = 0
        _MAX_CONSECUTIVE_ERRORS = 3

        # ── 自反思标志（任务完成前质量检查，只触发一次） ──
        _did_reflect = False

        # ── 工具结果缓存：file_read 同文件不重复读取（编辑后失效） ──
        _file_read_cache: dict[str, str] = {}
        
        # ── 工具调用去重：同工具+同参数连续调用跳过 ──
        _recent_tool_calls: dict[str, str] = {}  # key -> last_result_text

        try:
            while not state.finished and state.step < _effective_max_steps:
              state.step += 1

              # 上下文压缩：每 10 步检查一次，或估算 token 超预算时触发
              _est_tokens = sum(len(m.content or "") for m in state.messages) // _CHARS_PER_TOKEN
              if (state.step % 10 == 0 and len(state.messages) > 20) or _est_tokens > _TOKEN_BUDGET:
                  state.messages = await _compress_context(
                      state.messages, llm, target_model
                  )

              # ── 断点续传：每 5 步保存 checkpoint ──
              try:
                  from xagent.core.orchestration.checkpoint import save_checkpoint, should_checkpoint
                  if should_checkpoint(state.step):
                      save_checkpoint(
                          conv_session.conversation_id, resolved_run_id, state.step,
                          [{"role": m.role, "content": m.content[:500]} for m in state.messages],
                          _changed_files, goal,
                      )
              except Exception:  # noqa: S110
                  pass

              if can_stream:
                  # ── 流式路径：逐 token 推送（带重试） ──
                  content_buf = ""
                  tool_calls_buf: dict[int, dict] = {}  # index -> {id, name, arguments}

                  # 流式重试：流失败时重建连接
                  _stream_ok = False
                  for _stream_attempt in range(_LLM_MAX_RETRIES):
                      try:
                          content_buf = ""
                          tool_calls_buf = {}
                          async for chunk in llm.stream_with_tools(
                              state.messages, specs, model=target_model
                          ):
                              if chunk.delta_content:
                                  content_buf += chunk.delta_content
                                  await _emit(
                                      StepEvent(kind=StepKind.token, content=chunk.delta_content, step=state.step)
                                  )
                              for tc_delta in chunk.tool_call_deltas:
                                  idx = tc_delta.get("index", 0)
                                  if idx not in tool_calls_buf:
                                      tool_calls_buf[idx] = {"id": "", "name": "", "arguments": ""}
                                  fn = tc_delta.get("function") or {}
                                  if tc_delta.get("id"):
                                      tool_calls_buf[idx]["id"] = tc_delta["id"]
                                  if fn.get("name"):
                                      tool_calls_buf[idx]["name"] += fn["name"]
                                  if fn.get("arguments"):
                                      tool_calls_buf[idx]["arguments"] += fn["arguments"]
                              if chunk.prompt_tokens:
                                  state.total_prompt_tokens += chunk.prompt_tokens
                              if chunk.completion_tokens:
                                  state.total_completion_tokens += chunk.completion_tokens
                          _stream_ok = True
                          break
                      except Exception as _stream_exc:
                          err_s = str(_stream_exc).lower()
                          _retryable = any(k in err_s for k in _LLM_RETRYABLE_ERRORS)
                          if not _retryable or _stream_attempt == _LLM_MAX_RETRIES - 1:
                              raise
                          _delay = _LLM_RETRY_BASE_DELAY * (2 ** _stream_attempt)
                          logger.warning("stream_retry", attempt=_stream_attempt + 1, delay=_delay, error=str(_stream_exc)[:150])
                          await asyncio.sleep(_delay)

                  if not _stream_ok:
                      continue

                  # 流结束：判断是工具调用还是最终回答
                  if tool_calls_buf:
                      state.messages.append(Message(role="assistant", content=content_buf or ""))
                      _had_edit = False

                      # ── 解析所有 tool_call ──
                      _parsed_calls: list[tuple[str, str, dict]] = []  # (name, id, args)
                      for _idx in sorted(tool_calls_buf.keys()):
                          tc_raw = tool_calls_buf[_idx]
                          tc_name = tc_raw["name"]
                          tc_id = tc_raw["id"] or f"call_{state.step}_{_idx}"
                          try:
                              tc_args = json.loads(tc_raw["arguments"] or "{}")
                          except Exception:
                              tc_args = {}
                          _parsed_calls.append((tc_name, tc_id, tc_args))

                      # ── 并行执行策略：多个只读工具并发，编辑工具顺序 ──
                      _has_edit_call = any(n in _EDIT_TOOLS for n, _, _ in _parsed_calls)
                      _use_parallel = len(_parsed_calls) > 1 and not _has_edit_call

                      if _use_parallel:
                          # ══ 并行路径：asyncio.gather 并发执行只读工具 ══

                          async def _exec_one(tc_name: str, tc_id: str, tc_args: dict) -> tuple[str, str, str]:
                              """Execute single tool, return (name, id, result_text)."""
                              if not role.can_use(tc_name):
                                  return (tc_name, tc_id, f"[拒绝] 角色 {role.name} 无权使用工具 {tc_name}")
                              # ── 工具调用去重：同工具+同参数跳过 ──
                              _dedup_key = f"{tc_name}:{json.dumps(tc_args, sort_keys=True, ensure_ascii=False)[:200]}"
                              if _dedup_key in _recent_tool_calls:
                                  return (tc_name, tc_id, _recent_tool_calls[_dedup_key])
                              # ── file_read 缓存：同文件不重复读取 ──
                              if tc_name == "file_read":
                                  _cache_key = tc_args.get("path", "")
                                  if _cache_key and _cache_key in _file_read_cache:
                                      return (tc_name, tc_id, _file_read_cache[_cache_key])
                              r = await asyncio.wait_for(tools.call(tc_name, tc_args, ctx), timeout=_TOOL_TIMEOUT)
                              if r.ok:
                                  txt = json.dumps(r.output, ensure_ascii=False) if not isinstance(r.output, str) else r.output
                                  # 缓存 file_read 结果
                                  if tc_name == "file_read":
                                      _ck = tc_args.get("path", "")
                                      if _ck:
                                          _file_read_cache[_ck] = txt
                              else:
                                  txt = f"[错误] {r.error}"
                              # 记录去重缓存
                              _recent_tool_calls[_dedup_key] = txt
                              return (tc_name, tc_id, txt)

                          # 先推送所有 tool_call 事件
                          for tc_name, tc_id, tc_args in _parsed_calls:
                              await _emit(StepEvent(kind=StepKind.tool_call, tool=tc_name, content=tc_args, step=state.step))

                          # 并发执行
                          _results = await asyncio.gather(
                              *[_exec_one(n, i, a) for n, i, a in _parsed_calls],
                              return_exceptions=True,
                          )
                          for (_p_name, _p_id, _p_args), _res in zip(_parsed_calls, _results):
                              if isinstance(_res, Exception):
                                  result_text = f"[错误] {type(_res).__name__}: {_res}"
                                  _consecutive_errors += 1
                              else:
                                  _, _, result_text = _res
                                  if result_text.startswith("[错误]") or result_text.startswith("[拒绝]"):
                                      _consecutive_errors += 1
                                  else:
                                      _consecutive_errors = 0
                              await _emit(StepEvent(kind=StepKind.tool_result, tool=_p_name, content=result_text, step=state.step))
                              _stored = _truncate_tool_output(result_text, _p_name)
                              state.messages.append(Message(role="tool", content=_stored, tool_call_id=_p_id, name=_p_name))
                      else:
                          # ══ 顺序路径：含编辑工具时逐个执行 ══
                          for tc_name, tc_id, tc_args in _parsed_calls:
                              await _emit(
                                  StepEvent(kind=StepKind.tool_call, tool=tc_name, content=tc_args, step=state.step)
                              )
                              # ── Git 隔离：首次编辑时创建分支 ──
                              if tc_name in _EDIT_TOOLS and _work_branch is None:
                                  _work_branch = _git_create_work_branch(_WORKSPACE, resolved_run_id)
                              # ── 编辑前上下文注入：文件未读过时自动补读 ──
                              if tc_name in _EDIT_TOOLS:
                                  _edit_path = tc_args.get("path", "")
                                  if _edit_path and _edit_path not in _file_read_cache:
                                      try:
                                          _pre_read = await tools.call("file_read", {"path": _edit_path}, ctx)
                                          if _pre_read.ok:
                                              _pre_txt = _pre_read.output if isinstance(_pre_read.output, str) else json.dumps(_pre_read.output, ensure_ascii=False)
                                              _file_read_cache[_edit_path] = _pre_txt
                                              # 注入文件内容到上下文（截断保护）
                                              state.messages.append(Message(
                                                  role="user",
                                                  content=f"[系统] 编辑前自动读取文件 {_edit_path}：\n{_pre_txt[:2000]}",
                                              ))
                                      except Exception:  # noqa: S110
                                          pass
                              if not role.can_use(tc_name):
                                  result_text = f"[拒绝] 角色 {role.name} 无权使用工具 {tc_name}"
                                  _consecutive_errors += 1
                              else:
                                  result = await asyncio.wait_for(tools.call(tc_name, tc_args, ctx), timeout=_TOOL_TIMEOUT)
                                  if result.ok:
                                      result_text = (
                                          json.dumps(result.output, ensure_ascii=False)
                                          if not isinstance(result.output, str)
                                          else result.output
                                      )
                                      _consecutive_errors = 0
                                  else:
                                      result_text = f"[错误] {result.error}"
                                      _consecutive_errors += 1
                              if tc_name in _EDIT_TOOLS:
                                  _had_edit = True
                                  _edit_count += 1
                                  _fp = tc_args.get("path", "")
                                  if _fp and _fp not in _changed_files:
                                      _changed_files.append(_fp)
                                  if _fp:
                                      _file_read_cache.pop(_fp, None)
                              await _emit(
                                  StepEvent(kind=StepKind.tool_result, tool=tc_name, content=result_text, step=state.step)
                              )
                              # ── 原生 tool role + 智能截断（Codex 对齐） ──
                              _stored = _truncate_tool_output(result_text, tc_name)
                              state.messages.append(
                                  Message(role="tool", content=_stored, tool_call_id=tc_id, name=tc_name)
                              )
                      # ── 验证闭环：编辑后自动跑验证 ──
                      if _had_edit and _edit_count % 2 == 0:  # 每 2 次编辑验证一次
                          v_passed, v_output = await _run_verification(_WORKSPACE, ctx, _changed_files)
                          if not v_passed:
                              state.messages.append(Message(
                                  role="user",
                                  content=(
                                      f"[验证失败] 你的修改未通过项目验证：\n{v_output[:1000]}\n"
                                      "请分析错误原因并修复。"
                                  ),
                              ))
                      # ── 错误自恢复：连续失败过多时注入分析指令 ──
                      if _consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                          state.messages.append(Message(
                              role="user",
                              content=(
                                  "[系统] 你已连续 " + str(_consecutive_errors) + " 次工具调用失败。"
                                  "请停下来分析失败原因，换一种方案重试。"
                                  "常见原因：路径错误、参数格式不对、文件不存在。"
                              ),
                          ))
                          _consecutive_errors = 0
                      continue
                  else:
                      # 纯内容 → 判断是最终回答还是中间规划
                      content_buf = await _handle_empty_or_echo(
                          content_buf, state, llm, target_model
                      )
                      await _emit(
                          StepEvent(kind=StepKind.reason, content=content_buf, step=state.step)
                      )
                      state.messages.append(Message(role="assistant", content=content_buf))

                      # ── 防过早终止：智能完成检测 ──
                      # 策略：综合判断是否为真正的最终回答
                      _is_final = _detect_final_answer(content_buf, state)
                      if not _is_final and state.step < _effective_max_steps - 2:
                          # 不是最终回答 → 注入继续指令
                          state.messages.append(Message(
                              role="user",
                              content=(
                                  "[系统指令] 你的任务尚未完成。禁止停下来询问用户或输出中间规划。"
                                  "立即调用工具执行下一步操作。"
                                  "只有当所有子任务全部执行完毕后，才输出包含测试结果或‘全部完成’的最终总结。"
                              ),
                          ))
                          continue

                      action = _extract_action(content_buf)
                      if not action or action.get("action") == "final":
                          state.final_answer = (
                              action.get("answer", content_buf) if action else content_buf
                          )
                      else:
                          state.final_answer = content_buf

                      # ── 自反思：有编辑操作时，完成前做一次质量检查 ──
                      if _edit_count > 0 and not _did_reflect and state.step < _effective_max_steps - 1:
                          _did_reflect = True
                          state.messages.append(Message(
                              role="user",
                              content=(
                                  "[系统自反思] 任务即将完成。请快速自检：\n"
                                  "1. 所有修改是否完整（无遗漏文件）\n"
                                  "2. 代码是否能正常运行（无语法错误）\n"
                                  "3. 是否满足了用户的原始需求\n"
                                  "如果发现问题，立即修复；否则输出最终总结。"
                              ),
                          ))
                          continue

                      state.finished = True
                      await _emit(
                          StepEvent(kind=StepKind.final, content=state.final_answer, step=state.step)
                      )
                      break

              elif use_native_tools:
                  # ── 非流式原生工具路径（回退） ──
                  resp = await _llm_call_with_retry(
                      lambda: llm.complete_with_tools(state.messages, specs, model=target_model),
                      description="complete_with_tools",
                  )
                  # Token 用量追踪
                  state.total_prompt_tokens += resp.prompt_tokens
                  state.total_completion_tokens += resp.completion_tokens
                  if resp.tool_calls:
                      state.messages.append(
                          Message(role="assistant", content=resp.content)
                      )
                      _had_edit_ns = False

                      # ── 并行执行策略（同流式路径） ──
                      _ns_has_edit = any(tc.name in _EDIT_TOOLS for tc in resp.tool_calls)
                      _ns_use_parallel = len(resp.tool_calls) > 1 and not _ns_has_edit

                      if _ns_use_parallel:
                          # 并行路径
                          async def _exec_one_ns(tc) -> tuple:
                              if not role.can_use(tc.name):
                                  return (tc.name, tc.id, f"[拒绝] 角色 {role.name} 无权使用工具 {tc.name}")
                              if tc.name == "file_read":
                                  _ck = tc.args.get("path", "")
                                  if _ck and _ck in _file_read_cache:
                                      return (tc.name, tc.id, _file_read_cache[_ck])
                              r = await asyncio.wait_for(tools.call(tc.name, tc.args, ctx), timeout=_TOOL_TIMEOUT)
                              if r.ok:
                                  txt = json.dumps(r.output, ensure_ascii=False) if not isinstance(r.output, str) else r.output
                                  if tc.name == "file_read":
                                      _ck2 = tc.args.get("path", "")
                                      if _ck2:
                                          _file_read_cache[_ck2] = txt
                              else:
                                  txt = f"[错误] {r.error}"
                              return (tc.name, tc.id, txt)

                          for tc in resp.tool_calls:
                              await _emit(StepEvent(kind=StepKind.tool_call, tool=tc.name, content=tc.args, step=state.step))
                          _ns_results = await asyncio.gather(
                              *[_exec_one_ns(tc) for tc in resp.tool_calls],
                              return_exceptions=True,
                          )
                          for tc, _res in zip(resp.tool_calls, _ns_results):
                              if isinstance(_res, Exception):
                                  result_text = f"[错误] {type(_res).__name__}: {_res}"
                                  _consecutive_errors += 1
                              else:
                                  _, _, result_text = _res
                                  if result_text.startswith("[错误]") or result_text.startswith("[拒绝]"):
                                      _consecutive_errors += 1
                                  else:
                                      _consecutive_errors = 0
                              await _emit(StepEvent(kind=StepKind.tool_result, tool=tc.name, content=result_text, step=state.step))
                              _stored = _truncate_tool_output(result_text, tc.name)
                              state.messages.append(Message(role="tool", content=_stored, tool_call_id=tc.id, name=tc.name))
                      else:
                          # 顺序路径（含编辑工具）
                          for tc in resp.tool_calls:
                              await _emit(
                                  StepEvent(kind=StepKind.tool_call, tool=tc.name, content=tc.args, step=state.step)
                              )
                              if tc.name in _EDIT_TOOLS and _work_branch is None:
                                  _work_branch = _git_create_work_branch(_WORKSPACE, resolved_run_id)
                              if not role.can_use(tc.name):
                                  result_text = f"[拒绝] 角色 {role.name} 无权使用工具 {tc.name}"
                                  _consecutive_errors += 1
                              else:
                                  result = await asyncio.wait_for(tools.call(tc.name, tc.args, ctx), timeout=_TOOL_TIMEOUT)
                                  if result.ok:
                                      result_text = (
                                          json.dumps(result.output, ensure_ascii=False)
                                          if not isinstance(result.output, str)
                                          else result.output
                                      )
                                      _consecutive_errors = 0
                                  else:
                                      result_text = f"[错误] {result.error}"
                                      _consecutive_errors += 1
                              if tc.name in _EDIT_TOOLS:
                                  _had_edit_ns = True
                                  _edit_count += 1
                                  _fp = tc.args.get("path", "")
                                  if _fp and _fp not in _changed_files:
                                      _changed_files.append(_fp)
                                  if _fp:
                                      _file_read_cache.pop(_fp, None)
                              await _emit(
                                  StepEvent(kind=StepKind.tool_result, tool=tc.name, content=result_text, step=state.step)
                              )
                              _stored = _truncate_tool_output(result_text, tc.name)
                              state.messages.append(
                                  Message(role="tool", content=_stored, tool_call_id=tc.id, name=tc.name)
                              )
                      # 验证闭环
                      if _had_edit_ns and _edit_count % 2 == 0:
                          v_passed, v_output = await _run_verification(_WORKSPACE, ctx, _changed_files)
                          if not v_passed:
                              state.messages.append(Message(
                                  role="user",
                                  content=(
                                      f"[验证失败] 你的修改未通过项目验证：\n{v_output[:1000]}\n"
                                      "请分析错误原因并修复。"
                                  ),
                              ))
                      # 错误自恢复
                      if _consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                          state.messages.append(Message(
                              role="user",
                              content=(
                                  "[系统] 你已连续 " + str(_consecutive_errors) + " 次工具调用失败。"
                                  "请停下来分析失败原因，换一种方案重试。"
                              ),
                          ))
                          _consecutive_errors = 0
                      continue

                  await _emit(
                      StepEvent(kind=StepKind.reason, content=resp.content, step=state.step)
                  )
                  state.messages.append(Message(role="assistant", content=resp.content))

                  # 防过早终止（非流式路径）— 智能完成检测
                  _is_final_ns = _detect_final_answer(resp.content, state)
                  if not _is_final_ns and state.step < _effective_max_steps - 2:
                      state.messages.append(Message(
                          role="user",
                          content=(
                              "[系统指令] 你的任务尚未完成。禁止停下来询问用户或输出中间规划。"
                              "立即调用工具执行下一步操作。"
                              "只有当所有子任务全部执行完毕后，才输出包含测试结果或‘全部完成’的最终总结。"
                          ),
                      ))
                      continue

                  action = _extract_action(resp.content)
                  if not action or action.get("action") == "final":
                      state.final_answer = (
                          action.get("answer", resp.content) if action else resp.content
                      )
                      state.finished = True
                      await _emit(
                          StepEvent(kind=StepKind.final, content=state.final_answer, step=state.step)
                      )
                      break
                  if action.get("action") == "tool":
                      await _handle_prompt_tool_action(action, role, tools, ctx, state, events)
                      continue
                  state.final_answer = resp.content
                  state.finished = True
                  await _emit(StepEvent(kind=StepKind.final, content=resp.content, step=state.step))

              else:
                  # ── 提示工程路径（mock / 不支持工具） ──
                  resp = await _llm_call_with_retry(
                      lambda: llm.complete(state.messages, model=target_model),
                      description="complete",
                  )
                  state.total_prompt_tokens += resp.prompt_tokens
                  state.total_completion_tokens += resp.completion_tokens
                  await _emit(
                      StepEvent(kind=StepKind.reason, content=resp.content, step=state.step)
                  )
                  state.messages.append(Message(role="assistant", content=resp.content))

                  action = _extract_action(resp.content)
                  if not action or action.get("action") == "final":
                      state.final_answer = (
                          action.get("answer", resp.content) if action else resp.content
                      )
                      state.finished = True
                      await _emit(
                          StepEvent(kind=StepKind.final, content=state.final_answer, step=state.step)
                      )
                      break

                  if action.get("action") == "tool":
                      await _handle_prompt_tool_action(action, role, tools, ctx, state, events)
                      continue

                  state.final_answer = resp.content
                  state.finished = True
                  await _emit(StepEvent(kind=StepKind.final, content=resp.content, step=state.step))

            if not state.finished:
                # MAX_STEPS 耗尽 — 让 LLM 做最终总结
                state.messages.append(Message(
                    role="user",
                    content=(
                        "[系统指令] 你已达到最大执行轮次。"
                        "请立即停止调用工具，基于你已完成的所有工作，"
                        "输出一份完整的总结报告，包括：已完成的子任务、未完成的部分、以及后续建议。"
                    ),
                ))
                try:
                    final_resp = await llm.complete(state.messages, model=target_model)
                    _fc = (final_resp.content or "").strip()
                    # 回显检测
                    if _fc and not (
                        _fc.startswith("工具 ") or _fc.startswith("[参考数据")
                        or (_fc.startswith("{") and '"total_count"' in _fc[:200])
                    ):
                        state.final_answer = _fc
                    else:
                        state.final_answer = ""
                except Exception:
                    state.final_answer = ""
                # 兆底
                if not state.final_answer:
                    state.final_answer = (
                        f"任务已执行 {state.step} 步，达到最大轮次限制。\n\n"
                        "已完成部分工作，但未能全部完成。\n"
                        "建议：可以继续对话让我完成剩余部分。"
                    )
                await _emit(
                    StepEvent(kind=StepKind.final, content=state.final_answer, step=state.step)
                )
        except asyncio.CancelledError:
            # ── Graceful 取消：用户中断时保存部分结果 + 清理 git ──
            if not state.final_answer:
                state.final_answer = (
                    f"任务被用户中断（已执行 {state.step} 步）。\n\n"
                    "已完成的工作已保存，可以继续对话让我完成剩余部分。"
                )
            # 保存 checkpoint 以便恢复
            try:
                from xagent.core.orchestration.checkpoint import save_checkpoint
                save_checkpoint(
                    conv_session.conversation_id, resolved_run_id, state.step,
                    [{"role": m.role, "content": m.content[:500]} for m in state.messages[-20:]],
                    _changed_files, goal,
                )
            except Exception:  # noqa: S110
                pass
            await _emit(StepEvent(kind=StepKind.final, content=state.final_answer, step=state.step))
        except Exception as loop_exc:
            # LLM 调用失败（超时/上下文过长等）——用已有工具结果兆底
            if not state.final_answer:
                # 从消息历史中提取最后的工具结果作为回答
                tool_results = [
                    m.content for m in state.messages
                    if m.role == "tool" and m.content and not m.content.startswith("[错误]")
                ]
                if tool_results:
                    state.final_answer = (
                        "工具已执行完成，但模型整合结果时出错。\n\n"
                        "以下是工具返回的原始结果：\n\n"
                        + "\n---\n".join(tool_results[-3:])[:3000]
                    )
                else:
                    state.final_answer = f"执行过程中出错：{loop_exc!s:.200}"
                await _emit(
                    StepEvent(kind=StepKind.final, content=state.final_answer, step=state.step)
                )
        span.set_output(state.final_answer)
        # ── Git 清理：任务完成后清理临时分支 ──
        if _work_branch:
            _git_cleanup_branch(_WORKSPACE, _work_branch)
        # ── 文件变更摘要：追加到最终回答 ──
        if _changed_files and state.final_answer:
            _summary_lines = ["\n\n---\n📝 **文件变更**:"]
            for _cf in _changed_files[:10]:
                _summary_lines.append(f"- `{_cf}`")
            if len(_changed_files) > 10:
                _summary_lines.append(f"- ... 及其他 {len(_changed_files) - 10} 个文件")
            state.final_answer += "\n".join(_summary_lines)
        # Prometheus 指标
        try:
            from xagent.adapters.observability.metrics import agent_run_seconds, agent_runs

            agent_runs.labels(role=role.name).inc()
            agent_run_seconds.labels(role=role.name).observe(time.perf_counter() - _run_start)
        except Exception:  # noqa: S110  指标失败不影响运行
            pass

    # ── 保存对话历史 ──
    conv_session.add_user(goal)
    conv_session.add_assistant(state.final_answer)
    # ── 清理 checkpoint（任务成功完成） ──
    try:
        from xagent.core.orchestration.checkpoint import clear_checkpoints
        clear_checkpoints(conv_session.conversation_id)
    except Exception:  # noqa: S110
        pass
    # ── 持久化到 DB ──
    try:
        from xagent.core.orchestration.conversation import persist_conversation, persist_message
        from xagent.infra.db import get_sessionmaker

        async with get_sessionmaker()() as db_sess:
            await persist_conversation(db_sess, conv_session)
            await persist_message(db_sess, conv_session.conversation_id, "user", goal)
            await persist_message(db_sess, conv_session.conversation_id, "assistant", state.final_answer)
            await db_sess.commit()
    except Exception:  # noqa: S110  持久化失败不影响主流程
        pass
    # ── 自动写入记忆库 ──
    await _save_to_memory(goal, state.final_answer, principal.tenant_id)
    # ── 自动技能提炼（Skill 自进化） ──
    await _auto_extract_skill(goal, state.final_answer, state.step, events)

    return AgentRun(
        run_id=resolved_run_id,
        goal=goal,
        role_name=role.name,
        tenant_id=principal.tenant_id,
        final_answer=state.final_answer,
        steps=state.step,
        events=events,
        conversation_id=conv_session.conversation_id,
        prompt_tokens=state.total_prompt_tokens,
        completion_tokens=state.total_completion_tokens,
    )

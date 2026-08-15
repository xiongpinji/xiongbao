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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from xagent.adapters.llm import LLMResponse, Message, get_llm_client
from xagent.adapters.llm.litellm_client import LiteLLMClient
from xagent.adapters.observability import get_tracer
from xagent.adapters.tools import get_tool_registry
from xagent.adapters.tools.base import ToolContext
from xagent.core.agents import get_role_registry
from xagent.core.orchestration.conversation import get_conversation_manager
from xagent.core.orchestration.state import (
    RUN_STATUS_CANCELLED,
    RUN_STATUS_FAILED,
    RUN_STATUS_SUCCEEDED,
    AgentRun,
    AgentState,
    StepEvent,
    StepKind,
)
from xagent.core.workspace import get_workspace  # V3-3: 每任务 contextvar 可覆盖
from xagent.enterprise.auth.principal import Principal
from xagent.infra.logging import get_logger

logger = get_logger("xagent.loop")

MAX_STEPS = 40
_AGENT_RUN_TIMEOUT = 600  # 10 分钟

# ── LLM 调用重试配置（对标 Codex 的自动重试 + 指数退避） ──
_LLM_MAX_RETRIES = 3
_LLM_RETRY_BASE_DELAY = 2.0  # 秒
_LLM_RETRYABLE_ERRORS = ("rate_limit", "timeout", "connection", "server_error", "overloaded", "503", "429")

# ── 单工具执行超时（防止单个工具卡死整个循环） ──
_TOOL_TIMEOUT = 180  # 秒（shell_exec 自带 120s，这里做外层保护）
_SLOW_TOOL_THRESHOLD = 30  # 秒：超过此值记录慢工具警告

# ── 按工具类型设置超时（秒） ──
_TOOL_TIMEOUTS = {
    "file_read": 30,
    "file_write": 30,
    "file_edit": 30,
    "file_list": 30,
    "code_search": 60,
    "shell_exec": 150,
    "web_fetch": 60,
    "git": 60,
}
_DEFAULT_TOOL_TIMEOUT = 60

# ── 并行执行限流：最大并发工具数 ──
_MAX_CONCURRENT_TOOLS = 5

# ── Token 预算：超过此值触发主动压缩 ──
_TOKEN_BUDGET = 100_000  # 估算上下文 token 上限
_CHARS_PER_TOKEN = 4  # 粗略估算比例

# ── 多模型降级：主模型连续失败 N 次后切换到备用模型 ──
_FALLBACK_MODEL = os.environ.get("XAGENT_FALLBACK_MODEL", "")  # 空=不降级
_MODEL_FALLBACK_THRESHOLD = 3  # 连续失败次数阈值


@dataclass(frozen=True)
class _ToolExecutionOutcome:
    """并发工具执行结果；统计由调用方在聚合阶段统一更新。"""

    name: str
    call_id: str
    text: str
    executed: bool = False
    succeeded: bool | None = None
    elapsed_seconds: float | None = None


def _checkpoint_message(message: Message) -> dict[str, Any]:
    item: dict[str, Any] = {"role": message.role, "content": message.content[:500]}
    if message.tool_calls:
        item["tool_calls"] = message.tool_calls
    if message.tool_call_id:
        item["tool_call_id"] = message.tool_call_id
    if message.name:
        item["name"] = message.name
    return item

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
            # 自适应重试：指数退避 + 随机抖动（防雷群效应）
            import random as _rnd_retry
            delay += _rnd_retry.uniform(0, delay * 0.3)  # noqa: S311 - 仅用于退避抖动
            logger.warning(
                "llm_retry",
                attempt=attempt + 1,
                delay=delay,
                error=str(exc)[:200],
                description=description,
            )
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


def _categorize_error(result_text: str, tool_name: str) -> str:
    """错误分类：根据错误内容和工具名返回分类恢复建议。"""
    text_lower = result_text.lower()
    if "not found" in text_lower or "no such file" in text_lower or "不存在" in text_lower:
        return (
            "[恢复策略] 文件/路径不存在。\n"
            "1. 用 file_list 确认目录结构\n"
            "2. 用 code_search 搜索文件名\n"
            "3. 检查路径是否使用了绝对路径"
        )
    if "permission" in text_lower or "拒绝" in result_text or "denied" in text_lower:
        return (
            "[恢复策略] 权限不足。\n"
            "1. 检查文件是否只读\n"
            "2. 尝试写入工作目录内的路径"
        )
    if "syntax" in text_lower or "parse" in text_lower or "unexpected" in text_lower:
        return (
            "[恢复策略] 语法错误。\n"
            "1. 先 file_read 查看文件当前内容\n"
            "2. 确认 old_text 与文件实际内容完全一致\n"
            "3. 注意缩进、空格、换行符差异"
        )
    if "timeout" in text_lower or "超时" in result_text:
        return (
            "[恢复策略] 执行超时。\n"
            "1. 简化命令或拆分任务\n"
            "2. 避免全量构建/测试，改用增量"
        )
    if tool_name in ("file_edit",) and "text not found" in text_lower:
        return (
            "[恢复策略] file_edit 匹配失败。\n"
            "1. 先 file_read 读取文件最新内容\n"
            "2. 从文件内容中复制精确的 old_text\n"
            "3. 注意行尾空白和换行符差异"
        )
    # ── 新增：更细粒度的错误分类 ──
    if "connection" in text_lower or "network" in text_lower or "网络" in result_text:
        return (
            "[恢复策略] 网络连接失败。\n"
            "1. 检查 URL 是否正确\n"
            "2. 稍后重试或换用本地工具"
        )
    if "encoding" in text_lower or "decode" in text_lower or "编码" in result_text:
        return (
            "[恢复策略] 编码错误。\n"
            "1. 尝试指定 encoding 参数\n"
            "2. 使用 errors='replace' 容错读取"
        )
    if "memory" in text_lower or "内存" in result_text or "killed" in text_lower:
        return (
            "[恢复策略] 内存不足。\n"
            "1. 减少单次处理的数据量\n"
            "2. 分批处理大文件"
        )
    if "import" in text_lower or "module" in text_lower or "依赖" in result_text:
        return (
            "[恢复策略] 依赖缺失。\n"
            "1. 用 shell_exec 安装缺失依赖\n"
            "2. 检查虚拟环境是否激活"
        )
    return (
        "[恢复策略] 工具调用失败。\n"
        "1. 检查参数格式是否正确\n"
        "2. 换一种工具或方法尝试\n"
        "3. 如果多次失败，考虑跳过此步骤"
    )


def _format_tool_result(tool_name: str, result_text: str, args: dict) -> str:
    """工具结果结构化：帮助模型更好理解输出。"""
    # 对于成功结果，添加元数据头
    if result_text.startswith("[错误]") or result_text.startswith("[拒绝]"):
        return result_text  # 错误结果不加工
    # file_read 结果：添加文件信息头
    if tool_name == "file_read" and len(result_text) > 100:
        path = args.get("path", "unknown")
        lines = result_text.count("\n") + 1
        return f"[文件: {path} | {lines} 行]\n{result_text}"
    # shell_exec 结果：提取关键信息
    if tool_name == "shell_exec":
        # 检测常见错误模式
        if "error" in result_text.lower()[:500] or "traceback" in result_text.lower()[:500]:
            # 提取错误摘要（最后几行通常包含关键信息）
            _lines = result_text.strip().split("\n")
            _err_summary = "\n".join(_lines[-5:]) if len(_lines) > 5 else result_text
            return f"[命令执行出错]\n{_err_summary}"
        return result_text
    # code_search 结果：添加匹配数 + 文件列表摘要
    if tool_name == "code_search":
        _lines = result_text.strip().split("\n")
        _match_count = len([line for line in _lines if line.strip()])
        # 提取涉及的文件（假设格式为 "file:line:content" 或类似）
        _files = set()
        for line in _lines[:50]:
            if ":" in line:
                _f = line.split(":")[0].strip()
                if _f and not _f.startswith(" "):
                    _files.add(_f)
        _file_list = ", ".join(list(_files)[:5])
        _header = f"[搜索结果: {_match_count} 条匹配]"
        if _file_list:
            _header += f" | 涉及文件: {_file_list}"
        return f"{_header}\n{result_text}"
    # JSON 结果：尝试提取摘要
    if result_text.strip().startswith("{") or result_text.strip().startswith("["):
        try:
            _data = json.loads(result_text)
            if isinstance(_data, dict):
                _keys = list(_data.keys())[:5]
                return f"[JSON 对象 | 字段: {', '.join(_keys)}]\n{result_text}"
            elif isinstance(_data, list):
                return f"[JSON 数组 | {len(_data)} 项]\n{result_text}"
        except json.JSONDecodeError:
            pass
    # 其他工具：添加成功标记
    if len(result_text) > 50:
        return f"[{tool_name} 执行成功]\n{result_text}"
    return result_text


def _validate_tool_args(tool_name: str, args: dict, specs: list[dict]) -> str | None:
    """工具参数预校验：检查必填参数。返回错误描述或 None(通过)。"""
    for spec in specs:
        fn = spec.get("function", {})
        if fn.get("name") != tool_name:
            continue
        params = fn.get("parameters", {})
        required = params.get("required", [])
        properties = params.get("properties", {})
        missing = [r for r in required if r not in args or args[r] is None or args[r] == ""]
        if missing:
            return f"缺少必填参数: {', '.join(missing)}"
        # 类型粗检：字符串参数不应是 dict/list
        for key, val in args.items():
            prop = properties.get(key, {})
            if prop.get("type") == "string" and isinstance(val, (dict, list)):
                return f"参数 {key} 应为字符串，实际为 {type(val).__name__}"
        return None
    return None  # 未找到 spec 不拦截

# ── 编辑类工具：触发验证闭环 ──
_EDIT_TOOLS = {"file_edit", "file_write"}

# ── 编辑回滚配置：连续验证失败 N 次后自动 git checkout 回滚 ──
_ROLLBACK_THRESHOLD = 2  # 连续验证失败次数阈值


async def _rollback_changed_files(workspace: Path, changed_files: list[str]) -> str:
    """回滚变更文件：git checkout -- <files>。返回操作结果描述。"""
    import subprocess as _sp
    if not changed_files:
        return "(无变更文件需要回滚)"
    try:
        # 只回滚工作区内的文件
        rel_files = []
        for f in changed_files:
            try:
                rel_files.append(str(Path(f).relative_to(workspace)))
            except ValueError:
                rel_files.append(f)
        cmd = ["git", "checkout", "--"] + rel_files
        proc = _sp.run(cmd, cwd=str(workspace), capture_output=True, text=True, timeout=30)
        if proc.returncode == 0:
            return f"已回滚 {len(rel_files)} 个文件: {', '.join(rel_files[:5])}"
        return f"回滚失败: {proc.stderr[:200]}"
    except Exception as exc:
        return f"回滚异常: {exc}"

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
        get_workspace() / "AGENTS.md",
        get_workspace() / "agents.md",
        get_workspace() / ".agents" / "AGENTS.md",
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
    优先级压缩：旧工具结果先截断 → 再 LLM 摘要。
    """
    # Only compress if messages exceed threshold
    if len(messages) <= 20:
        return messages

    # ── 第一阶段：优先级截断（无需 LLM 调用） ──
    # 对距离末尾 >15 条的 tool 消息，截断到 300 字符（保留摘要）
    _TRUNCATE_TAIL_KEEP = 15
    _OLD_TOOL_MAX_CHARS = 300
    _truncated_any = False
    for i in range(len(messages) - _TRUNCATE_TAIL_KEEP):
        m = messages[i]
        if m.role == "tool" and m.content and len(m.content) > _OLD_TOOL_MAX_CHARS:
            m.content = m.content[:_OLD_TOOL_MAX_CHARS] + f"\n... [截断: 原 {len(m.content)} 字符]"
            _truncated_any = True

    # 截断后重新估算 token，如果已低于预算则无需 LLM 压缩
    _est = sum(len(m.content or "") for m in messages) // 4
    if _truncated_any and _est < 80_000:
        return messages

    # ── 第二阶段：LLM 摘要压缩 ──
    # Keep: system (first) + last 10 messages
    system_msg = messages[0] if messages[0].role == "system" else None
    keep_tail = 10
    start_idx = 1 if system_msg else 0
    end_idx = len(messages) - keep_tail

    if end_idx <= start_idx + 4:  # not enough to compress
        return messages

    # ── 保护 tool_call_id 完整性：调整截断点，不在 tool 消息中间截断 ──
    while end_idx > start_idx and messages[end_idx].role == "tool":
        end_idx -= 1
    if end_idx > start_idx and messages[end_idx].role == "assistant":
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

    # 5. Git 状态感知：当前分支 + 最近提交
    try:
        import subprocess as _sp
        _git_br = _sp.run(["git", "branch", "--show-current"], cwd=str(workspace), capture_output=True, text=True, timeout=5)
        if _git_br.returncode == 0 and _git_br.stdout.strip():
            lines.append(f"\nGit 分支: {_git_br.stdout.strip()}")
        _git_log = _sp.run(["git", "log", "--oneline", "-3"], cwd=str(workspace), capture_output=True, text=True, timeout=5)
        if _git_log.returncode == 0 and _git_log.stdout.strip():
            lines.append(f"最近提交:\n{_git_log.stdout.strip()}")
    except Exception:  # noqa: S110
        pass

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

    # 如果修改了 TS/JS 文件且验证命令是 tsc，只检查变更文件所在包
    if changed_files and "tsc" in verify_cmd:
        ts_files = [f for f in changed_files if f.endswith((".ts", ".tsx"))]
        if ts_files:
            # 找到最近的 tsconfig.json 目录
            for tf in ts_files[:1]:
                tp = Path(tf)
                for parent in [tp.parent] + list(tp.parents):
                    if (parent / "tsconfig.json").exists():
                        verify_cmd = f"npx tsc --noEmit --project {parent / 'tsconfig.json'}"
                        break

    tools = get_tool_registry()
    result = await tools.call("shell_exec", {"command": verify_cmd, "timeout": 60}, ctx)
    output = result.output if result.ok else (result.error or "")
    # 改进通过判断：检查 exit code 和常见失败标记
    _fail_markers = ("error", "failed", "traceback", "Error:", "FAILED")
    _has_fail = any(m in output[:500] for m in _fail_markers)
    passed = result.ok and not _has_fail
    return passed, output[:2000]


# ═══════════════════════════════════════════════════════════
#  工具结果智能截断
# ═══════════════════════════════════════════════════════════

_MAX_TOOL_OUTPUT = 4000  # 工具结果最大字符数


def _truncate_tool_output(text: str, tool_name: str, goal: str = "") -> str:
    """智能截断工具输出：保留头尾，中间截断。

    不同工具不同策略：
    - code_search: 保留前 N 条结果
    - shell_exec: 提取关键行（错误/警告/成功）+ 头尾
    - file_read: 基于 goal 关键词保留相关行 + 头尾
    """
    if len(text) <= _MAX_TOOL_OUTPUT:
        return text

    if tool_name == "file_read" and goal:
        # 基于 goal 关键词智能压缩：保留包含关键词的行 + 头尾
        import re as _re_tr
        _keywords = [w.lower() for w in _re_tr.findall(r'[\w\u4e00-\u9fff]{2,}', goal)][:8]
        lines = text.split("\n")
        _relevant = []
        for i, line in enumerate(lines):
            _ll = line.lower()
            if any(k in _ll for k in _keywords):
                _relevant.append((i, line))
        if _relevant and len(_relevant) < len(lines) * 0.6:
            # 保留相关行 + 上下文各 2 行
            _keep_indices = set()
            for idx, _ in _relevant:
                for j in range(max(0, idx - 2), min(len(lines), idx + 3)):
                    _keep_indices.add(j)
            _kept: list[str | None] = [
                lines[i] if i in _keep_indices else None for i in range(len(lines))
            ]
            # 压缩连续 None
            _result_lines = []
            _gap = 0
            for _kept_line in _kept:
                if _kept_line is not None:
                    if _gap > 0:
                        _result_lines.append(f"  ... [{_gap} 行省略] ...")
                    _result_lines.append(_kept_line)
                    _gap = 0
                else:
                    _gap += 1
            _compressed = "\n".join(_result_lines)
            if len(_compressed) < len(text):
                return f"[智能压缩: 保留 {len(_keep_indices)}/{len(lines)} 行相关内容]\n{_compressed}"

    if tool_name == "shell_exec":
        # 提取关键行：错误/警告/成功指标
        lines = text.split("\n")
        _key_patterns = ("error", "warning", "failed", "success", "passed", "✓", "✗", "Traceback")
        _key_lines = [
            line for line in lines if any(pattern in line.lower() for pattern in _key_patterns)
        ][:10]
        _key_summary = "\n".join(_key_lines) if _key_lines else ""
        # 保留头部 1200 + 尾部 1800
        head = text[:1200]
        tail = text[-1800:]
        _result = f"{head}\n\n... [中间 {len(text) - 3000} 字符已截断] ...\n\n{tail}"
        if _key_summary:
            _result = f"[关键输出摘要]\n{_key_summary}\n\n{_result}"
        return _result
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
        # [工作流F·竞品对标Hermes] LLM提炼+质量门禁路径（auto_distill），无LLM/不过门禁静默跳过
        await store.auto_distill(
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
        "所有子任务执行完毕",
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
    """处理空内容或工具结果回显；恢复失败时抛出可诊断异常。"""
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
        except Exception as exc:
            raise RuntimeError(f"model_response_recovery_failed: {exc}") from exc
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
        except Exception as exc:
            raise RuntimeError(f"model_response_recovery_failed: {exc}") from exc
        if not content_buf.strip():
            raise RuntimeError("model_empty_response_after_retry")
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
    resume_messages: list[dict[str, Any]] | None = None,
    resume_step: int = 0,
    resume_changed_files: list[str] | None = None,
    resume_from_checkpoint_id: str = "",
    required_first_tool: str | None = None,
    tool_mode: str = "auto",
) -> AgentRun:
    """运行一次 agent 任务，返回含事件序列的结果。

    on_event: 可选异步回调 (StepEvent) -> None，用于 SSE 实时推送。
    conversation_id: 会话 ID，传入则启用多轮对话。
    permission_mode: 权限模式 (suggest | auto-edit | full-auto)。
    """
    if tool_mode not in {"auto", "none"}:
        raise ValueError(f"不支持的 tool_mode: {tool_mode}")
    no_tools_chat = tool_mode == "none"
    if no_tools_chat and required_first_tool:
        raise ValueError("tool_mode=none 不允许 required_first_tool")

    registry = get_role_registry()
    role = registry.get("general") if no_tools_chat else (
        registry.get(role_name) if role_name else registry.match(capabilities or {"general"})
    )
    if role is None:
        role = registry.match({"general"})

    tools = None if no_tools_chat else get_tool_registry()
    resolved_run_id = run_id or uuid.uuid4().hex
    # 仅暴露该角色允许的工具
    specs = (
        []
        if tools is None
        else [s for s in tools.specs() if role.can_use(s["function"]["name"])]
    )
    available_tool_names = {spec["function"]["name"] for spec in specs}
    if required_first_tool and required_first_tool not in available_tool_names:
        raise RuntimeError(
            f"必需工具 {required_first_tool} 未在当前角色的工具 schema 中"
        )
    if required_first_tool:
        specs = [
            spec
            for spec in specs
            if spec["function"]["name"] == required_first_tool
        ]

    # ── 多轮对话：加载历史 ──
    conv_mgr = get_conversation_manager()
    conv_session = (
        conv_mgr.get(conversation_id, principal.tenant_id) if conversation_id else None
    )
    if conversation_id and conv_session is None:
        from xagent.core.orchestration.conversation import load_conversation_from_db
        from xagent.infra.db import get_sessionmaker

        async with get_sessionmaker()() as conversation_db:
            conv_session = await load_conversation_from_db(
                conversation_db, principal.tenant_id, conversation_id
            )
        if conv_session is not None:
            conv_mgr.restore(conv_session)
    if conv_session is None:
        conv_session = conv_mgr.get_or_create(conversation_id, principal.tenant_id)
    history = conv_session.get_history(max_turns=8)

    # ── 自动记忆注入：检索相关记忆 ──
    memory_context = await _retrieve_relevant_memories(goal, principal.tenant_id)

    # 构建消息列表：system + 历史 + 当前 goal
    messages: list[Message] = []
    if resume_messages is not None:
        for item in resume_messages:
            messages.append(
                Message(
                    role=str(item.get("role") or "user"),
                    content=str(item.get("content") or ""),
                    tool_call_id=item.get("tool_call_id"),
                    name=item.get("name"),
                    tool_calls=item.get("tool_calls"),
                )
            )
    else:
        messages.extend(history)
    # ── 多轮对话上下文注入：历史较长时添加摘要提示 ──
    if resume_messages is None and len(history) >= 6:
        _hist_topics = []
        for m in history[-6:]:
            if m.role == "user" and m.content:
                _hist_topics.append(m.content[:60])
        if _hist_topics:
            messages.append(Message(
                role="user",
                content=(
                    f"[系统] 当前为多轮对话，之前讨论了: {'; '.join(_hist_topics[-3:])}。"
                    "请基于上下文继续，不要重复已完成的工作。"
                ),
            ))
    messages.append(Message(role="user", content=goal))

    state = AgentState(
        goal=goal,
        role_name=role.name,
        tenant_id=principal.tenant_id,
        messages=messages,
        step=max(0, resume_step),
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
    if required_first_tool and not use_native_tools:
        raise RuntimeError(
            f"必需工具 {required_first_tool} 需要支持原生工具调用的模型"
        )
    if no_tools_chat:
        system = role.system_prompt
    elif use_native_tools:
        system = _tool_system_prompt_native(role.system_prompt, specs)
    else:
        system = _build_system_prompt(role.system_prompt, specs)
    # 注入记忆上下文
    if memory_context:
        system += f"\n\n相关记忆（供参考）：\n{memory_context}"
    # 注入 AGENTS.md 项目指令（Codex 对齐）
    # [工作流F·竞品对标] 升级为三层分层指令（用户级<工作区根<子目录级），失败回退原单文件加载
    # [工作流S3-2] 识别任务涉及路径传入 task_paths（goal 显式路径优先、历史工具调用路径参数次之），
    #               无识别结果为 None 保持原仅两层行为；子目录层按就近优先合并
    if not no_tools_chat:
        try:
            from xagent.core.instructions import (
                extract_task_paths,
                get_layered_instructions,
            )

            _task_paths = extract_task_paths(get_workspace(), goal=goal, history=history)
            agents_md = (
                get_layered_instructions(get_workspace(), task_paths=_task_paths)
                or _load_agents_md()
            )
        except Exception:  # noqa: S110  指令加载失败不影响主流程
            agents_md = _load_agents_md()
        if agents_md:
            system += f"\n\n## 项目指令 (AGENTS.md)\n{agents_md}"
        # 注入项目结构感知（Codex 对齐：先建立结构认知）
        project_ctx = _detect_project_context(get_workspace())
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
        skill_hint = get_skill_store().build_prompt_injection(
            goal, tenant_id=principal.tenant_id
        )
        if skill_hint:
            system += f"\n\n{skill_hint}"
    except Exception:  # noqa: S110
        pass
    state.messages.insert(0, Message(role="system", content=system))

    # ── 任务规划阶段：复杂任务先分解再执行（Codex 对齐） ──
    # ── 任务类型检测：根据目标动态调整提示策略 ──
    _TASK_TYPE_HINTS = {
        "coding": "\n[任务类型: 代码开发] 优先使用 file_write/file_edit 直接写入代码，完成后运行验证。",
        "analysis": "\n[任务类型: 分析研究] 优先使用 file_read/code_search 收集信息，输出结构化分析报告。",
        "search": "\n[任务类型: 信息检索] 优先使用 code_search/web_fetch 查找信息，简洁汇总结果。",
        "debug": "\n[任务类型: 问题修复] 先复现问题，再定位根因，最后修复并验证。",
    }
    def _detect_task_type(g: str) -> str:
        g_lower = g.lower()
        if any(w in g_lower for w in ("修复", "bug", "错误", "报错", "异常", "fix")):
            return "debug"
        if any(w in g_lower for w in ("分析", "研究", "评估", "对比", "analyze")):
            return "analysis"
        if any(w in g_lower for w in ("查找", "搜索", "检索", "search", "find")):
            return "search"
        if any(w in g_lower for w in ("创建", "开发", "实现", "编写", "create", "build", "implement")):
            return "coding"
        return "coding"  # 默认
    _task_type = "chat" if no_tools_chat else _detect_task_type(goal)

    _is_complex = not no_tools_chat and (
        len(goal) > 100
        or goal.count("、") >= 2
        or bool(re.search(r"[1-9][)\.]", goal))
        or any(w in goal for w in ("并且", "同时", "然后", "接着", "分别"))
    )
    # ── 自适应步数：复杂任务动态提升 MAX_STEPS ──
    _effective_max_steps = 1 if no_tools_chat else MAX_STEPS
    if _is_complex:
        # 复杂任务：根据长度和子任务数动态调整
        _subtask_count = max(goal.count("、"), len(re.findall(r'[1-9][)\.]', goal)), 1)
        _effective_max_steps = min(MAX_STEPS + _subtask_count * 5, 80)  # 上限 80
    if _is_complex:
        # ── 任务分解建议：提取子任务列表 ──
        _subtasks = []
        # 从 goal 中提取编号子任务
        import re as _re
        _numbered = _re.findall(r'[1-9][)\.、]\s*([^\n、]+)', goal)
        if _numbered:
            _subtasks = _numbered[:5]
        # 从“、”分割提取
        elif "、" in goal:
            _parts = goal.split("、")
            _subtasks = [p.strip()[:30] for p in _parts[1:4]]
        
        _decompose_hint = (
            "[系统] 这是一个复杂多步骤任务。请先在内心规划执行步骤（不要输出给用户），"
            "然后立即开始执行第一步。每完成一步后立即执行下一步，直到全部完成。"
        )
        if _subtasks:
            _subtask_list = "; ".join(_subtasks)
            _decompose_hint += f"\n识别到的子任务: {_subtask_list}。请确保每个子任务都完成。"
        state.messages.append(Message(role="user", content=_decompose_hint))

    # ── 任务类型提示注入 ──
    _type_hint = _TASK_TYPE_HINTS.get(_task_type, "")
    if _type_hint:
        state.messages.append(Message(role="user", content=_type_hint))

    async def _complete_no_tools_chat(max_tokens: int = 512) -> LLMResponse:
        complete_chat = getattr(llm, "complete_chat", None)
        if callable(complete_chat):
            return await complete_chat(
                state.messages,
                model=target_model,
                max_tokens=max_tokens,
            )
        return await llm.complete(
            state.messages,
            model=target_model,
            temperature=0,
            max_tokens=max_tokens,
        )

    def _no_tools_chat_response_incomplete(
        response: LLMResponse, requested_max_tokens: int
    ) -> bool:
        choices = response.raw.get("choices")
        first_choice = choices[0] if isinstance(choices, list) and choices else {}
        finish_reason = (
            first_choice.get("finish_reason")
            if isinstance(first_choice, dict)
            else getattr(first_choice, "finish_reason", None)
        )
        return (
            finish_reason == "length"
            or response.completion_tokens >= requested_max_tokens
        )

    async with tracer.trace("agent.run", role=role.name, tenant=principal.tenant_id) as span:
        span.set_input(goal)
        _run_start = time.perf_counter()
        # ── 执行日志：任务开始 ──
        logger.info(
            "task_start",
            goal=goal[:100],
            role=role.name,
            task_type=_task_type,
            is_complex=_is_complex,
            max_steps=_effective_max_steps,
        )
        # 判断是否支持流式
        can_stream = isinstance(llm, LiteLLMClient) and use_native_tools

        # ── Git 事务隔离：创建临时工作分支 ──
        _work_branch: str | None = None
        _edit_count = 0  # 跟踪编辑次数，首次编辑时创建分支

        # ── 文件变更追踪（任务结束时生成 diff 摘要） ──
        _changed_files: list[str] = list(resume_changed_files or [])

        # ── 错误自恢复计数器 ──
        _consecutive_errors = 0
        _MAX_CONSECUTIVE_ERRORS = 3

        # ── 自反思标志（任务完成前质量检查，只触发一次） ──
        _did_reflect = False

        # ── 工具结果缓存：file_read 同文件不重复读取（编辑后失效） ──
        _file_read_cache: dict[str, str] = {}
        _file_read_cache_time: dict[str, float] = {}  # 缓存时间戳
        _CACHE_TTL = 300  # 缓存有效期 5 分钟

        # ── 缓存预热：预读关键配置文件（减少首次访问延迟） ──
        _PREWARM_FILES = (
            []
            if no_tools_chat
            else ["package.json", "pyproject.toml", "tsconfig.json", "README.md"]
        )
        for _pf in _PREWARM_FILES:
            _pf_path = get_workspace() / _pf
            if _pf_path.is_file():
                try:
                    _pf_content = _pf_path.read_text(encoding="utf-8", errors="ignore")[:5000]
                    _file_read_cache[str(_pf_path)] = _pf_content
                    _file_read_cache_time[str(_pf_path)] = time.time()
                except Exception:  # noqa: S110
                    pass

        # ── 工具调用去重：同工具+同参数连续调用跳过（带大小限制） ──
        _recent_tool_calls: dict[str, str] = {}  # key -> last_result_text
        _DEDUP_CACHE_MAX = 50  # 去重缓存最大条目数

        # ── 工具调用链优化：检测循环模式 ──
        _tool_call_history: list[str] = []  # 最近 10 次工具名
        _loop_detected: bool = False

        # ── 执行统计：工具调用次数/成功率 ──
        _tool_stats: dict[str, int] = {}  # tool_name -> call_count
        _tool_success: int = 0
        _tool_fail: int = 0
        _loop_error: str = ""  # 循环级异常信息（空 = 主循环未崩溃），供失败反思提炼
        _trace_seq: int = 0  # 链路追踪序号计数器
        _tool_success_by_type: dict[str, int] = {}  # tool_name -> success_count
        _tool_fail_by_type: dict[str, int] = {}  # tool_name -> fail_count
        _tool_time_by_type: dict[str, list[float]] = {}  # tool_name -> [elapsed_times]

        # ── 重复错误检测：同错误 3 次提前终止 ──
        _error_signatures: dict[str, int] = {}  # error_sig -> count
        _REPEAT_ERROR_LIMIT = 3

        # ── 错误分类恢复：追踪最后一次错误信息 ──
        _last_error_text: str = ""
        _last_error_tool: str = ""
        _recovery_attempts: dict[str, int] = {}  # error_type -> recovery_count

        # ── 会话级决策记忆：跨步骤记住关键决策 ──
        _session_decisions: list[str] = []  # 记录关键决策（最多 10 条）

        _last_checkpoint_step = 0
        _terminal_success = False
        _pending_final_event: StepEvent | None = None
        _run_status = RUN_STATUS_FAILED
        _run_error = ""
        _required_tool_seen = False
        _required_tool_attempts = 0
        _required_tool_choice = (
            {
                "type": "function",
                "function": {"name": required_first_tool},
            }
            if required_first_tool
            else None
        )

        # ── 编辑回滚：连续验证失败计数 ──
        _verify_fail_count: int = 0

        # ── 多模型降级：追踪 LLM 调用失败 ──
        _llm_fail_count: int = 0
        _model_degraded: bool = False

        try:
            while not state.finished and state.step < _effective_max_steps:
              state.step += 1

              # ── 执行进度估算：每步发射进度事件 ──
              _progress_pct = min(int(state.step / _effective_max_steps * 100), 95)
              await _emit(StepEvent(
                  kind=StepKind.progress,
                  content={"percent": _progress_pct, "step": state.step, "max_steps": _effective_max_steps},
                  step=state.step,
              ))

              # ── 动态步数延展：任务进展良好时自动延长 ──
              if state.step == _effective_max_steps - 3 and _effective_max_steps < 100:
                  _total_calls = _tool_success + _tool_fail
                  _success_rate = _tool_success / max(_total_calls, 1)
                  # 条件：成功率>70% 且有文件变更（任务在进展）
                  if _success_rate > 0.7 and len(_changed_files) > 0:
                      _extension = min(15, _effective_max_steps // 3)
                      _effective_max_steps += _extension
                      logger.info("step_extension", new_max=_effective_max_steps, success_rate=round(_success_rate, 2))
                      state.messages.append(Message(
                          role="user",
                          content=f"[系统] 任务进展良好，已自动延长执行限额至 {_effective_max_steps} 步。请继续完成剩余工作。",
                      ))

              # ── 动态上下文注入：每 5 步注入任务进度摘要（复杂任务才注入） ──
              if _is_complex and state.step % 5 == 0 and state.step > 0:
                  _ctx_parts = [f"[系统进度报告] 步骤 {state.step}/{_effective_max_steps} ({_progress_pct}%)"]
                  if _changed_files:
                      _ctx_parts.append(f"已修改文件: {', '.join(_changed_files[-8:])}")
                  if _session_decisions:
                      _ctx_parts.append(f"关键决策: {'; '.join(_session_decisions[-5:])}")
                  _ctx_parts.append("请继续执行任务，不要重复已完成的步骤。")
                  state.messages.append(Message(role="user", content="\n".join(_ctx_parts)))

              # 上下文压缩：每 10 步检查一次，或估算 token 超预算时触发
              _est_tokens = sum(len(m.content or "") for m in state.messages) // _CHARS_PER_TOKEN
              # ── 上下文预警：接近 80% 预算时通知模型精简输出 ──
              if (
                  not no_tools_chat
                  and _est_tokens > _TOKEN_BUDGET * 0.8
                  and not getattr(state, '_ctx_warned', False)
              ):
                  state.messages.append(Message(
                      role="user",
                      content=(
                          f"[系统] 上下文已使用 {_est_tokens // 1000}k/{_TOKEN_BUDGET // 1000}k tokens（{int(_est_tokens / _TOKEN_BUDGET * 100)}%）。"
                          "请精简后续输出，避免冗长解释，直接执行工具调用。"
                      ),
                  ))
                  state._ctx_warned = True  # type: ignore[attr-defined]
              if not no_tools_chat and (
                  (state.step % 10 == 0 and len(state.messages) > 20)
                  or _est_tokens > _TOKEN_BUDGET
              ):
                  state.messages = await _compress_context(
                      state.messages, llm, target_model
                  )
                  # ── 会话级决策记忆：压缩后注入决策摘要（防丢失） ──
                  if _session_decisions:
                      _dec_summary = "\n".join(_session_decisions[-10:])
                      state.messages.insert(1, Message(
                          role="user",
                          content=f"[系统] 历史决策记录（压缩后保留）：\n{_dec_summary}",
                      ))

              # ── 断点续传：每 5 步保存 checkpoint ──
              try:
                  from xagent.core.orchestration.checkpoint import (
                      save_checkpoint,
                      should_checkpoint,
                  )
                  if should_checkpoint(state.step):
                      await save_checkpoint(
                          conv_session.conversation_id, resolved_run_id, state.step,
                          [_checkpoint_message(m) for m in state.messages],
                          _changed_files, goal,
                          tenant_id=principal.tenant_id,
                          workspace=get_workspace(),
                          parent_checkpoint_id=resume_from_checkpoint_id,
                      )
                      _last_checkpoint_step = state.step
              except Exception:  # noqa: S110
                  pass

              if no_tools_chat:
                  chat_resp = await _llm_call_with_retry(
                      _complete_no_tools_chat,
                      description="chat_no_tools",
                  )
                  state.total_prompt_tokens += chat_resp.prompt_tokens
                  state.total_completion_tokens += chat_resp.completion_tokens
                  chat_content = (chat_resp.content or "").strip()
                  response_incomplete = _no_tools_chat_response_incomplete(
                      chat_resp, 512
                  )
                  if not chat_content or response_incomplete:
                      recovery_max_tokens = (
                          1024 if response_incomplete else 512
                      )
                      state.messages.append(Message(
                          role="user",
                          content=(
                              "[系统提示] 请直接回答用户的问题，"
                              "不要返回空内容。"
                          ),
                      ))
                      retry_resp = await _llm_call_with_retry(
                          lambda max_tokens=recovery_max_tokens: (
                              _complete_no_tools_chat(max_tokens)
                          ),
                          description="chat_no_tools_recovery",
                      )
                      state.total_prompt_tokens += retry_resp.prompt_tokens
                      state.total_completion_tokens += retry_resp.completion_tokens
                      chat_content = (retry_resp.content or "").strip()
                      if not chat_content:
                          raise RuntimeError("model_empty_response_after_retry")
                      if _no_tools_chat_response_incomplete(
                          retry_resp, recovery_max_tokens
                      ):
                          raise RuntimeError(
                              "model_incomplete_response_after_retry"
                          )
                  if not chat_content:
                      raise RuntimeError("model_empty_response_after_retry")
                  await _emit(
                      StepEvent(
                          kind=StepKind.reason,
                          content=chat_content,
                          step=state.step,
                      )
                  )
                  state.messages.append(
                      Message(role="assistant", content=chat_content)
                  )
                  state.final_answer = chat_content
                  _terminal_success = True
                  state.finished = True
                  _pending_final_event = StepEvent(
                      kind=StepKind.final,
                      content=chat_content,
                      step=state.step,
                  )
                  break

              assert tools is not None
              if can_stream:
                  # ── 流式路径：逐 token 推送（带重试 + 超时保护） ──
                  content_buf = ""
                  tool_calls_buf: dict[int, dict] = {}  # index -> {id, name, arguments}
                  _STREAM_FIRST_CHUNK_TIMEOUT = 60  # 首 chunk 超时
                  _STREAM_CHUNK_TIMEOUT = 30  # 后续 chunk 间隔超时

                  # 流式重试：流失败时重建连接
                  _stream_ok = False
                  _stream_tool_kwargs: dict[str, Any] = {}
                  if required_first_tool and not _required_tool_seen:
                      _required_tool_attempts += 1
                      _stream_tool_kwargs["tool_choice"] = _required_tool_choice
                  for _stream_attempt in range(_LLM_MAX_RETRIES):
                      try:
                          content_buf = ""
                          tool_calls_buf = {}
                          _last_chunk_time = time.perf_counter()
                          _first_chunk_received = False
                          stream_llm: Any = llm
                          async for chunk in stream_llm.stream_with_tools(
                              state.messages,
                              specs,
                              model=target_model,
                              **_stream_tool_kwargs,
                          ):
                              _now = time.perf_counter()
                              # 超时保护：首 chunk 60s，后续 30s
                              _timeout = _STREAM_FIRST_CHUNK_TIMEOUT if not _first_chunk_received else _STREAM_CHUNK_TIMEOUT
                              if _now - _last_chunk_time > _timeout:
                                  raise TimeoutError(f"Stream chunk timeout: {_timeout}s")
                              _last_chunk_time = _now
                              _first_chunk_received = True
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
                          _llm_fail_count = 0  # 成功后重置降级计数
                          break
                      except Exception as _stream_exc:
                          err_s = str(_stream_exc).lower()
                          _retryable = any(k in err_s for k in _LLM_RETRYABLE_ERRORS) or "timeout" in err_s
                          if not _retryable or _stream_attempt == _LLM_MAX_RETRIES - 1:
                              # ── 多模型降级：连续失败达阈值时切换备用模型 ──
                              _llm_fail_count += 1
                              if _llm_fail_count >= _MODEL_FALLBACK_THRESHOLD and _FALLBACK_MODEL and not _model_degraded:
                                  _model_degraded = True
                                  target_model = _FALLBACK_MODEL
                                  logger.warning("Model degraded to fallback: %s", _FALLBACK_MODEL)
                                  state.messages.append(Message(
                                      role="user",
                                      content=f"[系统] 主模型连续失败，已切换到备用模型 {_FALLBACK_MODEL}。请继续执行任务。",
                                  ))
                              raise
                          _delay = _LLM_RETRY_BASE_DELAY * (2 ** _stream_attempt)
                          # 自适应重试：指数退避 + 随机抖动
                          import random as _rnd_stream
                          _delay += _rnd_stream.uniform(  # noqa: S311 - 仅用于退避抖动
                              0, _delay * 0.3
                          )
                          logger.warning("stream_retry", attempt=_stream_attempt + 1, delay=_delay, error=str(_stream_exc)[:150])
                          await asyncio.sleep(_delay)

                  if not _stream_ok:
                      continue

                  # 流结束：判断是工具调用还是最终回答
                  if tool_calls_buf:
                      _stream_tool_names = {
                          item["name"] for item in tool_calls_buf.values()
                      }
                      if required_first_tool and not _required_tool_seen:
                          if required_first_tool in _stream_tool_names:
                              _required_tool_seen = True
                          elif _required_tool_attempts >= 2:
                              raise RuntimeError(
                                  f"隔离开发任务未调用必需工具 "
                                  f"{required_first_tool}（已纠偏重试 1 次）"
                              )
                          else:
                              state.messages.append(Message(
                                  role="user",
                                  content=(
                                      f"[必需工具纠偏] 这是隔离开发任务，"
                                      f"首轮必须调用 {required_first_tool} 产生真实文件变更。"
                                  ),
                              ))
                              continue
                      if required_first_tool:
                          _disallowed_stream_tools = (
                              _stream_tool_names - {required_first_tool}
                          )
                          if _disallowed_stream_tools:
                              raise RuntimeError(
                                  "strict_tool_policy_violation: "
                                  + ", ".join(sorted(_disallowed_stream_tools))
                              )
                      # 构建 OpenAI 格式 tool_calls（必须随 assistant 消息一起发送，否则 Deepseek 报错）
                      _tc_list = [
                          {"id": tool_calls_buf[_i]["id"] or f"call_{state.step}_{_i}", "type": "function",
                           "function": {"name": tool_calls_buf[_i]["name"], "arguments": tool_calls_buf[_i]["arguments"] or "{}"}}
                          for _i in sorted(tool_calls_buf.keys())
                      ]
                      state.messages.append(Message(role="assistant", content=content_buf or "", tool_calls=_tc_list))
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

                      # ── 并行执行策略：依赖感知排序（只读先并行，编辑后执行） ──
                      _edit_calls = [(n, a) for n, _, a in _parsed_calls if n in _EDIT_TOOLS]
                      _read_calls = [(n, i, a) for n, i, a in _parsed_calls if n not in _EDIT_TOOLS]
                      _edit_paths = [a.get("path", "") for _, a in _edit_calls]
                      # 只有当编辑工具目标文件都不同时才允许并行
                      _edits_safe = len(_edit_paths) == len(set(_edit_paths))  # 无重复文件
                      _use_parallel = len(_parsed_calls) > 1 and (not _edit_calls or _edits_safe)
                      # 依赖排序：有读+编辑混合时，读先执行
                      _has_dependency = len(_read_calls) > 0 and len(_edit_calls) > 0

                      if _use_parallel:
                          # ══ 并行路径：asyncio.gather 并发执行（带限流） ══
                          _semaphore = asyncio.Semaphore(_MAX_CONCURRENT_TOOLS)

                          async def _exec_one(
                              tc_name: str,
                              tc_id: str,
                              tc_args: dict,
                              semaphore: asyncio.Semaphore,
                          ) -> _ToolExecutionOutcome:
                              """Execute one tool under the supplied concurrency limit."""
                              async with semaphore:
                                  return await _exec_one_inner(tc_name, tc_id, tc_args)

                          async def _exec_one_inner(
                              tc_name: str, tc_id: str, tc_args: dict
                          ) -> _ToolExecutionOutcome:
                              """Execute one tool without mutating aggregate counters."""
                              if not role.can_use(tc_name):
                                  return _ToolExecutionOutcome(
                                      tc_name,
                                      tc_id,
                                      f"[拒绝] 角色 {role.name} 无权使用工具 {tc_name}",
                                  )
                              # ── 工具参数预校验：拦截无效调用 ──
                              _val_err = _validate_tool_args(tc_name, tc_args, specs)
                              if _val_err:
                                  return _ToolExecutionOutcome(
                                      tc_name, tc_id, f"[参数错误] {_val_err}"
                                  )
                              # ── 工具调用去重：同工具+同参数跳过 ──
                              _dedup_key = f"{tc_name}:{json.dumps(tc_args, sort_keys=True, ensure_ascii=False)[:200]}"
                              if _dedup_key in _recent_tool_calls:
                                  return _ToolExecutionOutcome(
                                      tc_name, tc_id, _recent_tool_calls[_dedup_key]
                                  )
                              # ── file_read 缓存：同文件不重复读取（带 TTL） ──
                              if tc_name == "file_read":
                                  _cache_key = tc_args.get("path", "")
                                  if _cache_key and _cache_key in _file_read_cache:
                                      # 检查 TTL
                                      _cache_age = time.time() - _file_read_cache_time.get(_cache_key, 0)
                                      if _cache_age < _CACHE_TTL:
                                          return _ToolExecutionOutcome(
                                              tc_name, tc_id, _file_read_cache[_cache_key]
                                          )
                                      else:
                                          # 缓存过期，删除
                                          _file_read_cache.pop(_cache_key, None)
                                          _file_read_cache_time.pop(_cache_key, None)
                              _t0 = time.perf_counter()
                              _tool_timeout = _TOOL_TIMEOUTS.get(tc_name, _DEFAULT_TOOL_TIMEOUT)
                              r = await asyncio.wait_for(tools.call(tc_name, tc_args, ctx), timeout=_tool_timeout)
                              _elapsed = time.perf_counter() - _t0
                              if _elapsed > _SLOW_TOOL_THRESHOLD:
                                  logger.warning("Slow tool: %s took %.1fs", tc_name, _elapsed)
                              if r.ok:
                                  txt = json.dumps(r.output, ensure_ascii=False) if not isinstance(r.output, str) else r.output
                                  # 缓存 file_read 结果
                                  if tc_name == "file_read":
                                      _ck = tc_args.get("path", "")
                                      if _ck:
                                          _file_read_cache[_ck] = txt
                                          _file_read_cache_time[_ck] = time.time()
                              else:
                                  txt = f"[错误] {r.error}"
                                  # 错误上下文增强：文件操作时提示工作目录
                                  if tc_name in ("file_read", "file_write", "file_edit") and "not found" in txt.lower():
                                      txt += f"\n[提示] 工作目录: {get_workspace()}"
                                  # ── 重复错误检测 ──
                                  _err_sig = f"{tc_name}:{str(r.error)[:80]}"
                                  _error_signatures[_err_sig] = _error_signatures.get(_err_sig, 0) + 1
                              # 记录去重缓存（带大小限制）
                              if len(_recent_tool_calls) >= _DEDUP_CACHE_MAX:
                                  # 淘汰最旧的条目
                                  _oldest_key = next(iter(_recent_tool_calls))
                                  _recent_tool_calls.pop(_oldest_key, None)
                              _recent_tool_calls[_dedup_key] = txt
                              return _ToolExecutionOutcome(
                                  tc_name,
                                  tc_id,
                                  txt,
                                  executed=True,
                                  succeeded=r.ok,
                                  elapsed_seconds=_elapsed,
                              )

                          # ── 工具调用链优化：检测循环模式 ──
                          _current_tools = [n for n, _, _ in _parsed_calls]
                          _tool_call_history.extend(_current_tools)
                          _tool_call_history = _tool_call_history[-10:]  # 保留最近 10 次
                          # 检测 A-B-A-B 循环
                          if len(_tool_call_history) >= 4:
                              _last4 = _tool_call_history[-4:]
                              if _last4[0] == _last4[2] and _last4[1] == _last4[3] and not _loop_detected:
                                  _loop_detected = True
                                  state.messages.append(Message(
                                      role="user",
                                      content=(
                                          f"[系统警告] 检测到工具调用循环: {_last4[0]} → {_last4[1]} → {_last4[0]} → {_last4[1]}\n"
                                          "请改变策略，尝试不同的方法解决问题。"
                                      ),
                                  ))
                          elif _loop_detected and len(set(_current_tools)) > 1:
                              _loop_detected = False  # 使用不同工具后重置
                          
                          # 先推送所有 tool_call 事件
                          for tc_name, _tc_id, tc_args in _parsed_calls:
                              _trace_seq += 1
                              await _emit(StepEvent(kind=StepKind.tool_call, tool=tc_name, content=tc_args, step=state.step, trace_id=f"s{state.step}-{_trace_seq}"))

                          # 并发执行（依赖感知：读工具先执行，编辑工具后执行）
                          if _has_dependency:
                              # 阶段1：只读工具并行
                              _read_results = await asyncio.gather(
                                  *[_exec_one(n, i, a, _semaphore) for n, i, a in _read_calls],
                                  return_exceptions=True,
                              )
                              # 阶段2：编辑工具并行（不同文件）或顺序
                              _edit_calls_full = [(n, i, a) for n, i, a in _parsed_calls if n in _EDIT_TOOLS]
                              _edit_results = await asyncio.gather(
                                  *[_exec_one(n, i, a, _semaphore) for n, i, a in _edit_calls_full],
                                  return_exceptions=True,
                              )
                              # 合并结果（按原始顺序）
                              _parallel_results = []
                              _read_idx, _edit_idx = 0, 0
                              for n, _call_id, _call_args in _parsed_calls:
                                  if n in _EDIT_TOOLS:
                                      _parallel_results.append(_edit_results[_edit_idx])
                                      _edit_idx += 1
                                  else:
                                      _parallel_results.append(_read_results[_read_idx])
                                      _read_idx += 1
                          else:
                              _parallel_results = await asyncio.gather(
                                  *[_exec_one(n, i, a, _semaphore) for n, i, a in _parsed_calls],
                                  return_exceptions=True,
                              )
                          for (_p_name, _p_id, _p_args), _parallel_result in zip(
                              _parsed_calls, _parallel_results, strict=True
                          ):
                              if isinstance(_parallel_result, BaseException):
                                  result_text = (
                                      f"[错误] {type(_parallel_result).__name__}: "
                                      f"{_parallel_result}"
                                  )
                                  _tool_fail += 1
                                  _tool_fail_by_type[_p_name] = _tool_fail_by_type.get(_p_name, 0) + 1
                                  _tool_stats[_p_name] = _tool_stats.get(_p_name, 0) + 1
                                  _consecutive_errors += 1
                              else:
                                  result_text = _parallel_result.text
                                  if _parallel_result.executed:
                                      _tool_stats[_p_name] = _tool_stats.get(_p_name, 0) + 1
                                      if _parallel_result.succeeded is True:
                                          _tool_success += 1
                                          _tool_success_by_type[_p_name] = _tool_success_by_type.get(_p_name, 0) + 1
                                      elif _parallel_result.succeeded is False:
                                          _tool_fail += 1
                                          _tool_fail_by_type[_p_name] = _tool_fail_by_type.get(_p_name, 0) + 1
                                  if _parallel_result.elapsed_seconds is not None:
                                      _tool_time_by_type.setdefault(_p_name, []).append(
                                          _parallel_result.elapsed_seconds
                                      )
                                  if result_text.startswith("[错误]") or result_text.startswith("[拒绝]"):
                                      _consecutive_errors += 1
                                  else:
                                      _consecutive_errors = 0
                              await _emit(StepEvent(kind=StepKind.tool_result, tool=_p_name, content=result_text, step=state.step))
                              _stored = _truncate_tool_output(_format_tool_result(_p_name, result_text, _p_args), _p_name, goal)
                              state.messages.append(Message(role="tool", content=_stored, tool_call_id=_p_id, name=_p_name))
                      else:
                          # ══ 顺序路径：含编辑工具时逐个执行 ══
                          for tc_name, tc_id, tc_args in _parsed_calls:
                              _edit_succeeded = False
                              _trace_seq += 1
                              await _emit(
                                  StepEvent(kind=StepKind.tool_call, tool=tc_name, content=tc_args, step=state.step, trace_id=f"s{state.step}-{_trace_seq}")
                              )
                              # ── Git 隔离：首次编辑时创建分支 ──
                              if tc_name in _EDIT_TOOLS and _work_branch is None:
                                  _work_branch = _git_create_work_branch(get_workspace(), resolved_run_id)
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
                                  # ── 工具参数预校验 ──
                                  _val_err = _validate_tool_args(tc_name, tc_args, specs)
                                  if _val_err:
                                      result_text = f"[参数错误] {_val_err}"
                                      _consecutive_errors += 1
                                      _last_error_text = result_text
                                      _last_error_tool = tc_name
                                  else:
                                      _t0 = time.perf_counter()
                                      _tool_timeout = _TOOL_TIMEOUTS.get(tc_name, _DEFAULT_TOOL_TIMEOUT)
                                      try:
                                          result = await asyncio.wait_for(
                                              tools.call(tc_name, tc_args, ctx),
                                              timeout=_tool_timeout,
                                          )
                                      except Exception as _tool_exc:
                                          # 工具超时/异常不炸穿循环：转为错误结果，回填 tool 消息，
                                          # 保证 tool_call_id 配对（否则 DeepSeek 400 / run 崩溃）
                                          result = None
                                          _exc_name = type(_tool_exc).__name__
                                          _tool_exc_info = f"{_exc_name}: {_tool_exc}"
                                      _elapsed = time.perf_counter() - _t0
                                      if _elapsed > _SLOW_TOOL_THRESHOLD:
                                          logger.warning("Slow tool: %s took %.1fs", tc_name, _elapsed)
                                      if result is None:
                                          result_text = f"[错误] 工具执行异常: {_tool_exc_info}"
                                          _consecutive_errors += 1
                                          _last_error_text = result_text
                                          _last_error_tool = tc_name
                                          _err_sig = f"{tc_name}:{result_text[:80]}"
                                          _error_signatures[_err_sig] = _error_signatures.get(_err_sig, 0) + 1
                                      elif result.ok:
                                          result_text = (
                                              json.dumps(result.output, ensure_ascii=False)
                                              if not isinstance(result.output, str)
                                              else result.output
                                          )
                                          _edit_succeeded = True
                                          _consecutive_errors = 0
                                      else:
                                          result_text = f"[错误] {result.error}"
                                          _consecutive_errors += 1
                                          _last_error_text = result_text
                                          _last_error_tool = tc_name
                                          # ── 重复错误检测 ──
                                          _err_sig = f"{tc_name}:{str(result.error)[:80]}"
                                          _error_signatures[_err_sig] = _error_signatures.get(_err_sig, 0) + 1
                                          # ── file_edit 失败智能重试：自动补读文件内容 ──
                                          if tc_name == "file_edit" and "text not found" in result_text.lower():
                                              _fail_path = tc_args.get("path", "")
                                              if _fail_path:
                                                  try:
                                                      _retry_read = await asyncio.wait_for(
                                                          tools.call("file_read", {"path": _fail_path}, ctx),
                                                          timeout=30,
                                                      )
                                                      if _retry_read.ok:
                                                          _retry_txt = _retry_read.output if isinstance(_retry_read.output, str) else json.dumps(_retry_read.output, ensure_ascii=False)
                                                          _file_read_cache[_fail_path] = _retry_txt
                                                          result_text += f"\n[系统已自动读取文件] 以下是 {_fail_path} 的当前内容，请从中复制精确的 old_text 重试：\n{_retry_txt[:2000]}"
                                                  except Exception:  # noqa: S110
                                                      pass
                              if tc_name in _EDIT_TOOLS and _edit_succeeded:
                                  _had_edit = True
                                  _edit_count += 1
                                  _fp = tc_args.get("path", "")
                                  if _fp and _fp not in _changed_files:
                                      _changed_files.append(_fp)
                                  if _fp:
                                      _file_read_cache.pop(_fp, None)
                                  # ── 会话级决策记忆：记录关键编辑决策 ──
                                  if _fp and len(_session_decisions) < 10:
                                      _session_decisions.append(f"step{state.step}: {tc_name} -> {_fp}")
                                  # ── 编辑差异摘要：计算变更行数 ──
                                  if tc_name == "file_edit" and result_text and not result_text.startswith("[错误]"):
                                      _old_lines = (tc_args.get("old_text", "") or "").count("\n") + 1
                                      _new_lines = (tc_args.get("new_text", "") or "").count("\n") + 1
                                      _diff_summary = f" [+{_new_lines}/-{_old_lines} 行]"
                                      result_text = result_text[:200] + _diff_summary
                              await _emit(
                                  StepEvent(kind=StepKind.tool_result, tool=tc_name, content=result_text, step=state.step)
                              )
                              # ── 原生 tool role + 智能截断（Codex 对齐） ──
                              _stored = _truncate_tool_output(_format_tool_result(tc_name, result_text, tc_args), tc_name, goal)
                              state.messages.append(
                                  Message(role="tool", content=_stored, tool_call_id=tc_id, name=tc_name)
                              )

                      # ── 重复错误提前终止：同错误达阈值时停止 ──
                      _repeat_errors = [sig for sig, cnt in _error_signatures.items() if cnt >= _REPEAT_ERROR_LIMIT]
                      if _repeat_errors:
                          _err_detail = _repeat_errors[0].split(":", 1)[-1]
                          state.final_answer = (
                              f"任务提前终止：同一错误重复出现 {_REPEAT_ERROR_LIMIT} 次。\n\n"
                              f"错误详情: {_err_detail}\n\n"
                              "建议：\n"
                              "1. 检查环境/依赖是否正确\n"
                              "2. 简化任务重试\n"
                              "3. 手动修复该错误后重新发起"
                          )
                          state.finished = True
                          logger.warning("early_termination", error=_repeat_errors[0], step=state.step)
                          await _emit(StepEvent(kind=StepKind.error, content=state.final_answer, step=state.step))
                          break

                      # ── 验证闭环：编辑后自动跑验证 + 回滚保护 ──
                      if _had_edit and _edit_count % 2 == 0:  # 每 2 次编辑验证一次
                          v_passed, v_output = await _run_verification(get_workspace(), ctx, _changed_files)
                          if not v_passed:
                              _verify_fail_count += 1
                              if _verify_fail_count >= _ROLLBACK_THRESHOLD:
                                  # 连续失败达阈值 → 自动回滚
                                  _rb_result = await _rollback_changed_files(get_workspace(), _changed_files)
                                  state.messages.append(Message(
                                      role="user",
                                      content=(
                                          f"[验证失败 + 自动回滚] 连续 {_verify_fail_count} 次验证未通过。\n"
                                          f"验证输出：{v_output[:500]}\n"
                                          f"{_rb_result}\n"
                                          "请重新分析需求，采用不同策略实现。"
                                      ),
                                  ))
                                  _verify_fail_count = 0
                                  _changed_files.clear()
                              else:
                                  state.messages.append(Message(
                                      role="user",
                                      content=(
                                          f"[验证失败] 你的修改未通过项目验证：\n{v_output[:1000]}\n"
                                          "请分析错误原因并修复。"
                                      ),
                                  ))
                          else:
                              _verify_fail_count = 0
                      # ── 错误分类恢复：连续失败过多时注入分类分析指令 ──
                      if _consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                          _recovery = _categorize_error(_last_error_text, _last_error_tool)
                          state.messages.append(Message(
                              role="user",
                              content=(
                                  f"[系统] 你已连续 {_consecutive_errors} 次工具调用失败。\n"
                                  f"最后错误：{_last_error_text[:300]}\n"
                                  f"{_recovery}"
                              ),
                          ))
                          _recovery_attempts[_last_error_text[:50]] = _recovery_attempts.get(_last_error_text[:50], 0) + 1
                          _consecutive_errors = 0
                      continue
                  else:
                      # 纯内容 → 判断是最终回答还是中间规划
                      if required_first_tool and not _required_tool_seen:
                          if _required_tool_attempts >= 2:
                              raise RuntimeError(
                                  f"隔离开发任务未调用必需工具 "
                                  f"{required_first_tool}（已纠偏重试 1 次）"
                              )
                          state.messages.append(
                              Message(role="assistant", content=content_buf)
                          )
                          state.messages.append(Message(
                              role="user",
                              content=(
                                  f"[必需工具纠偏] 不得用纯文本宣称完成。"
                                  f"立即调用 {required_first_tool} 产生真实文件变更。"
                              ),
                          ))
                          continue
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

                      # ── 最终回答质量门控：防空/过短/回显 ──
                      _fa = (state.final_answer or "").strip()
                      if len(_fa) < 10 and state.step > 1:
                          # 回答过短，要求模型补充
                          state.messages.append(Message(
                              role="user",
                              content="[系统] 你的回答过短，请补充完整的任务总结（包括做了什么、修改了哪些文件、结果如何）。",
                          ))
                          state.final_answer = ""
                          continue

                      _terminal_success = True
                      state.finished = True
                      _pending_final_event = StepEvent(
                          kind=StepKind.final, content=_fa, step=state.step
                      )
                      break

              elif use_native_tools:
                  # ── 非流式原生工具路径（回退） ──
                  _native_tool_kwargs: dict[str, Any] = {}
                  if required_first_tool and not _required_tool_seen:
                      _required_tool_attempts += 1
                      _native_tool_kwargs["tool_choice"] = _required_tool_choice
                  resp = await _llm_call_with_retry(
                      lambda selected_model=target_model,
                      tool_kwargs=_native_tool_kwargs: llm.complete_with_tools(
                          state.messages,
                          specs,
                          model=selected_model,
                          **tool_kwargs,
                      ),
                      description="complete_with_tools",
                  )
                  # Token 用量追踪
                  state.total_prompt_tokens += resp.prompt_tokens
                  state.total_completion_tokens += resp.completion_tokens
                  if resp.tool_calls:
                      _native_tool_names = {tc.name for tc in resp.tool_calls}
                      if required_first_tool and not _required_tool_seen:
                          if required_first_tool in _native_tool_names:
                              _required_tool_seen = True
                          elif _required_tool_attempts >= 2:
                              raise RuntimeError(
                                  f"隔离开发任务未调用必需工具 "
                                  f"{required_first_tool}（已纠偏重试 1 次）"
                              )
                          else:
                              state.messages.append(Message(
                                  role="user",
                                  content=(
                                      f"[必需工具纠偏] 这是隔离开发任务，"
                                      f"首轮必须调用 {required_first_tool} 产生真实文件变更。"
                                  ),
                              ))
                              continue
                      if required_first_tool:
                          _disallowed_native_tools = (
                              _native_tool_names - {required_first_tool}
                          )
                          if _disallowed_native_tools:
                              raise RuntimeError(
                                  "strict_tool_policy_violation: "
                                  + ", ".join(sorted(_disallowed_native_tools))
                              )
                      # 构建 OpenAI 格式 tool_calls（必须随 assistant 消息一起发送）
                      _tc_list_ns = [
                          {"id": tc.id, "type": "function",
                           "function": {"name": tc.name, "arguments": json.dumps(tc.args, ensure_ascii=False)}}
                          for tc in resp.tool_calls
                      ]
                      state.messages.append(
                          Message(role="assistant", content=resp.content, tool_calls=_tc_list_ns)
                      )
                      _had_edit_ns = False

                      # ── 并行执行策略（同流式路径：编辑不同文件可并行） ──
                      _ns_edit_calls = [tc for tc in resp.tool_calls if tc.name in _EDIT_TOOLS]
                      _ns_edit_paths = [tc.args.get("path", "") for tc in _ns_edit_calls]
                      _ns_edits_safe = len(_ns_edit_paths) == len(set(_ns_edit_paths))
                      _ns_use_parallel = len(resp.tool_calls) > 1 and (not _ns_edit_calls or _ns_edits_safe)

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
                          for tc, _res in zip(resp.tool_calls, _ns_results, strict=True):
                              if isinstance(_res, BaseException):
                                  result_text = f"[错误] {type(_res).__name__}: {_res}"
                                  _consecutive_errors += 1
                              else:
                                  _, _, result_text = _res
                                  if result_text.startswith("[错误]") or result_text.startswith("[拒绝]"):
                                      _consecutive_errors += 1
                                  else:
                                      _consecutive_errors = 0
                              await _emit(StepEvent(kind=StepKind.tool_result, tool=tc.name, content=result_text, step=state.step))
                              _stored = _truncate_tool_output(_format_tool_result(tc.name, result_text, tc.args), tc.name, goal)
                              state.messages.append(Message(role="tool", content=_stored, tool_call_id=tc.id, name=tc.name))
                      else:
                          # 顺序路径（含编辑工具）
                          for tc in resp.tool_calls:
                              _edit_succeeded = False
                              await _emit(
                                  StepEvent(kind=StepKind.tool_call, tool=tc.name, content=tc.args, step=state.step)
                              )
                              if tc.name in _EDIT_TOOLS and _work_branch is None:
                                  _work_branch = _git_create_work_branch(get_workspace(), resolved_run_id)
                              if not role.can_use(tc.name):
                                  result_text = f"[拒绝] 角色 {role.name} 无权使用工具 {tc.name}"
                                  _consecutive_errors += 1
                              else:
                                  try:
                                      result = await asyncio.wait_for(
                                          tools.call(tc.name, tc.args, ctx),
                                          timeout=_TOOL_TIMEOUT,
                                      )
                                  except Exception as _tool_exc:
                                      # 工具超时/异常不炸穿循环：转为错误结果，回填 tool 消息
                                      result = None
                                      _exc_name = type(_tool_exc).__name__
                                      _tool_exc_info = f"{_exc_name}: {_tool_exc}"
                                  if result is None:
                                      result_text = f"[错误] 工具执行异常: {_tool_exc_info}"
                                      _consecutive_errors += 1
                                      _last_error_text = result_text
                                      _last_error_tool = tc.name
                                      _err_sig = f"{tc.name}:{result_text[:80]}"
                                      _error_signatures[_err_sig] = _error_signatures.get(_err_sig, 0) + 1
                                  elif result.ok:
                                      result_text = (
                                          json.dumps(result.output, ensure_ascii=False)
                                          if not isinstance(result.output, str)
                                          else result.output
                                      )
                                      _edit_succeeded = True
                                      _consecutive_errors = 0
                                  else:
                                      result_text = f"[错误] {result.error}"
                                      _consecutive_errors += 1
                                      _last_error_text = result_text
                                      _last_error_tool = tc.name
                                      # ── 重复错误检测 ──
                                      _err_sig = f"{tc.name}:{str(result.error)[:80]}"
                                      _error_signatures[_err_sig] = _error_signatures.get(_err_sig, 0) + 1
                              if tc.name in _EDIT_TOOLS and _edit_succeeded:
                                  _had_edit_ns = True
                                  _edit_count += 1
                                  _fp = tc.args.get("path", "")
                                  if _fp and _fp not in _changed_files:
                                      _changed_files.append(_fp)
                                  if _fp:
                                      _file_read_cache.pop(_fp, None)
                                  # ── 会话级决策记忆：记录关键编辑决策 ──
                                  if _fp and len(_session_decisions) < 10:
                                      _session_decisions.append(f"step{state.step}: {tc.name} -> {_fp}")
                              await _emit(
                                  StepEvent(kind=StepKind.tool_result, tool=tc.name, content=result_text, step=state.step)
                              )
                              _stored = _truncate_tool_output(_format_tool_result(tc.name, result_text, tc.args), tc.name, goal)
                              state.messages.append(
                                  Message(role="tool", content=_stored, tool_call_id=tc.id, name=tc.name)
                              )

                      # ── 重复错误提前终止 ──
                      _repeat_errors = [sig for sig, cnt in _error_signatures.items() if cnt >= _REPEAT_ERROR_LIMIT]
                      if _repeat_errors:
                          _err_detail = _repeat_errors[0].split(":", 1)[-1]
                          state.final_answer = (
                              f"任务提前终止：同一错误重复出现 {_REPEAT_ERROR_LIMIT} 次。\n\n"
                              f"错误详情: {_err_detail}\n\n"
                              "建议：\n1. 检查环境/依赖\n2. 简化任务重试\n3. 手动修复后重新发起"
                          )
                          state.finished = True
                          logger.warning("early_termination", error=_repeat_errors[0], step=state.step)
                          await _emit(StepEvent(kind=StepKind.error, content=state.final_answer, step=state.step))
                          break

                      # 验证闭环 + 回滚保护
                      if _had_edit_ns and _edit_count % 2 == 0:
                          v_passed, v_output = await _run_verification(get_workspace(), ctx, _changed_files)
                          if not v_passed:
                              _verify_fail_count += 1
                              if _verify_fail_count >= _ROLLBACK_THRESHOLD:
                                  _rb_result = await _rollback_changed_files(get_workspace(), _changed_files)
                                  state.messages.append(Message(
                                      role="user",
                                      content=(
                                          f"[验证失败 + 自动回滚] 连续 {_verify_fail_count} 次验证未通过。\n"
                                          f"验证输出：{v_output[:500]}\n"
                                          f"{_rb_result}\n"
                                          "请重新分析需求，采用不同策略实现。"
                                      ),
                                  ))
                                  _verify_fail_count = 0
                                  _changed_files.clear()
                              else:
                                  state.messages.append(Message(
                                      role="user",
                                      content=(
                                          f"[验证失败] 你的修改未通过项目验证：\n{v_output[:1000]}\n"
                                          "请分析错误原因并修复。"
                                      ),
                                  ))
                          else:
                              _verify_fail_count = 0
                      # 错误分类恢复
                      if _consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                          _recovery = _categorize_error(_last_error_text, _last_error_tool)
                          state.messages.append(Message(
                              role="user",
                              content=(
                                  f"[系统] 你已连续 {_consecutive_errors} 次工具调用失败。\n"
                                  f"最后错误：{_last_error_text[:300]}\n"
                                  f"{_recovery}"
                              ),
                          ))
                          _consecutive_errors = 0
                      continue

                  if required_first_tool and not _required_tool_seen:
                      if _required_tool_attempts >= 2:
                          raise RuntimeError(
                              f"隔离开发任务未调用必需工具 "
                              f"{required_first_tool}（已纠偏重试 1 次）"
                          )
                      state.messages.append(
                          Message(role="assistant", content=resp.content)
                      )
                      state.messages.append(Message(
                          role="user",
                          content=(
                              f"[必需工具纠偏] 不得用纯文本宣称完成。"
                              f"立即调用 {required_first_tool} 产生真实文件变更。"
                          ),
                      ))
                      continue

                  content_buf_ns = await _handle_empty_or_echo(
                      resp.content, state, llm, target_model
                  )
                  await _emit(
                      StepEvent(kind=StepKind.reason, content=content_buf_ns, step=state.step)
                  )
                  state.messages.append(Message(role="assistant", content=content_buf_ns))

                  # 防过早终止（非流式路径）— 智能完成检测
                  _is_final_ns = _detect_final_answer(content_buf_ns, state)
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

                  action = _extract_action(content_buf_ns)
                  if not action or action.get("action") == "final":
                      state.final_answer = (
                          action.get("answer", content_buf_ns) if action else content_buf_ns
                      )
                      _terminal_success = True
                      state.finished = True
                      _pending_final_event = StepEvent(
                          kind=StepKind.final,
                          content=state.final_answer,
                          step=state.step,
                      )
                      break
                  if action.get("action") == "tool":
                      await _handle_prompt_tool_action(action, role, tools, ctx, state, events)
                      continue
                  state.final_answer = content_buf_ns
                  _terminal_success = True
                  state.finished = True
                  _pending_final_event = StepEvent(
                      kind=StepKind.final, content=content_buf_ns, step=state.step
                  )

              else:
                  # ── 提示工程路径（mock / 不支持工具） ──
                  resp = await _llm_call_with_retry(
                      lambda selected_model=target_model: llm.complete(
                          state.messages, model=selected_model
                      ),
                      description="complete",
                  )
                  state.total_prompt_tokens += resp.prompt_tokens
                  state.total_completion_tokens += resp.completion_tokens
                  content_buf_plain = await _handle_empty_or_echo(
                      resp.content, state, llm, target_model
                  )
                  await _emit(
                      StepEvent(kind=StepKind.reason, content=content_buf_plain, step=state.step)
                  )
                  state.messages.append(Message(role="assistant", content=content_buf_plain))

                  action = _extract_action(content_buf_plain)
                  if not action or action.get("action") == "final":
                      state.final_answer = (
                          action.get("answer", content_buf_plain) if action else content_buf_plain
                      )
                      _terminal_success = True
                      state.finished = True
                      _pending_final_event = StepEvent(
                          kind=StepKind.final,
                          content=state.final_answer,
                          step=state.step,
                      )
                      break

                  if action.get("action") == "tool":
                      await _handle_prompt_tool_action(action, role, tools, ctx, state, events)
                      continue

                  state.final_answer = content_buf_plain
                  _terminal_success = True
                  state.finished = True
                  _pending_final_event = StepEvent(
                      kind=StepKind.final, content=content_buf_plain, step=state.step
                  )

            if not state.finished:
                # MAX_STEPS 耗尽 — 让 LLM 做最终总结
                _run_error = "max_steps_exceeded"
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
                    StepEvent(kind=StepKind.error, content=state.final_answer, step=state.step)
                )
        except asyncio.CancelledError:
            # ── Graceful 取消：用户中断时保存部分结果 + Git Diff 摘要 ──
            _cancel_parts = [f"任务被用户中断（已执行 {state.step} 步）。"]
            # 添加 Git Diff 摘要
            if _changed_files:
                try:
                    import subprocess as _sp
                    _diff = _sp.run(
                        ["git", "diff", "--stat", "HEAD"],
                        cwd=str(get_workspace()), capture_output=True, text=True, timeout=10
                    )
                    if _diff.returncode == 0 and _diff.stdout.strip():
                        _cancel_parts.append(f"\n已修改文件：\n{_diff.stdout.strip()}")
                except Exception:  # noqa: S110
                    _cancel_parts.append(f"\n已修改文件: {', '.join(_changed_files[:10])}")
            _cancel_parts.append("\n已完成的工作已保存，可以继续对话让我完成剩余部分。")
            if not state.final_answer:
                state.final_answer = "\n".join(_cancel_parts)
            # 保存 checkpoint 以便恢复
            try:
                from xagent.core.orchestration.checkpoint import save_checkpoint
                await save_checkpoint(
                    conv_session.conversation_id, resolved_run_id, state.step,
                    [_checkpoint_message(m) for m in state.messages[-20:]],
                    _changed_files, goal,
                    tenant_id=principal.tenant_id,
                    workspace=get_workspace(),
                    parent_checkpoint_id=resume_from_checkpoint_id,
                )
            except Exception:  # noqa: S110
                pass
            _run_status = RUN_STATUS_CANCELLED
            _run_error = "cancelled_by_user"
            if required_first_tool:
                if _work_branch:
                    _git_cleanup_branch(get_workspace(), _work_branch)
                    _work_branch = None
                raise
            await _emit(StepEvent(kind=StepKind.error, content=state.final_answer, step=state.step))
        except MemoryError as memory_exc:
            # ── 优雅降级：内存不足时清理缓存并继续 ──
            logger.warning("memory_pressure", step=state.step)
            _file_read_cache.clear()
            _recent_tool_calls.clear()
            _run_error = f"memory_pressure: {memory_exc!s:.200}"
            if not state.final_answer:
                state.final_answer = (
                    "任务执行过程中遇到内存压力，已清理缓存。\n\n"
                    f"已完成 {state.step} 步，建议简化任务或分批执行。"
                )
            await _emit(StepEvent(kind=StepKind.error, content=state.final_answer, step=state.step))
        except Exception as loop_exc:
            _loop_error = str(loop_exc)[:300]
            _run_error = _loop_error or type(loop_exc).__name__
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
                    StepEvent(kind=StepKind.error, content=state.final_answer, step=state.step)
                )
        span.set_output(state.final_answer)
        # ── Git 清理：任务完成后清理临时分支 ──
        if _work_branch:
            _git_cleanup_branch(get_workspace(), _work_branch)
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

    # ── 任务完成摘要增强：添加 diff 统计 + 执行统计 ──
    if state.final_answer:
        _summary_parts = []
        # 执行统计
        _total_calls = _tool_success + _tool_fail
        if _total_calls > 0:
            _success_rate = int(_tool_success / _total_calls * 100)
            _top_tools = sorted(_tool_stats.items(), key=lambda x: -x[1])[:3]
            _tools_str = ", ".join(f"{t}({c})" for t, c in _top_tools)
            _summary_parts.append(f"📈 执行统计: {_total_calls} 次工具调用, 成功率 {_success_rate}%, 常用: {_tools_str}")
            # 按工具类型成功率（只显示有失败的）
            _fail_tools = [(t, _tool_fail_by_type.get(t, 0)) for t in _tool_stats if _tool_fail_by_type.get(t, 0) > 0]
            if _fail_tools:
                _fail_str = ", ".join(f"{t}({f}次失败)" for t, f in _fail_tools[:3])
                _summary_parts.append(f"⚠️ 失败分布: {_fail_str}")
            # 工具耗时统计（显示平均耗时最高的）
            _avg_times = []
            for _tn, _times in _tool_time_by_type.items():
                if _times:
                    _avg = sum(_times) / len(_times)
                    _avg_times.append((_tn, _avg, len(_times)))
            if _avg_times:
                _avg_times.sort(key=lambda x: -x[1])
                _time_str = ", ".join(f"{t}(平均{a:.1f}s×{c})" for t, a, c in _avg_times[:3])
                _summary_parts.append(f"⏱️ 耗时分析: {_time_str}")
        # diff 统计
        if _changed_files:
            try:
                import subprocess as _sp
                _diff_stat = _sp.run(
                    ["git", "diff", "--stat", "HEAD"],
                    cwd=str(get_workspace()), capture_output=True, text=True, timeout=10
                )
                if _diff_stat.returncode == 0 and _diff_stat.stdout.strip():
                    _stat_line = _diff_stat.stdout.strip().split("\n")[-1]
                    _summary_parts.append(f"📊 变更统计: {_stat_line}")
            except Exception:  # noqa: S110
                pass
        if _summary_parts:
            state.final_answer += "\n\n---\n" + "\n".join(_summary_parts)

    if _terminal_success and not _run_error:
        _run_status = RUN_STATUS_SUCCEEDED
    elif _run_status != RUN_STATUS_CANCELLED and not _run_error:
        _run_error = "incomplete_run"

    terminal_messages = [_checkpoint_message(m) for m in conv_session.messages]
    terminal_messages.extend(
        [
            {"role": "user", "content": goal},
            {"role": "assistant", "content": state.final_answer},
        ]
    )
    if _terminal_success and state.step > 0:
        try:
            from xagent.core.orchestration.checkpoint import save_checkpoint_snapshot

            await save_checkpoint_snapshot(
                conv_session.conversation_id,
                resolved_run_id,
                state.step,
                terminal_messages,
                _changed_files,
                goal,
                tenant_id=principal.tenant_id,
                workspace=get_workspace(),
                parent_checkpoint_id=resume_from_checkpoint_id,
            )
        except Exception as exc:
            logger.warning(
                "terminal_checkpoint_save_failed",
                run_id=resolved_run_id,
                step=state.step,
                error_type=type(exc).__name__,
            )
            raise RuntimeError("terminal_checkpoint_save_failed") from exc
    # ── 保存对话历史 ──
    conv_session.add_user(goal)
    conv_session.add_assistant(state.final_answer)
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
    if _loop_error:
        # 失败反思提炼（V3-2c）：循环级异常 → 从失败学习，提炼避坑技能
        try:
            from xagent.core.skills import get_skill_store as _get_skills

            _tools_tried = [e.tool for e in events if isinstance(e.tool, str) and e.tool]
            await _get_skills().distill_from_failure(goal, _loop_error, tools_used=_tools_tried)
        except Exception:  # noqa: S110  失败反思失败不影响主流程
            pass
    else:
        await _auto_extract_skill(goal, state.final_answer, state.step, events)

    if _pending_final_event is not None:
        await _emit(
            StepEvent(
                kind=StepKind.final,
                content=state.final_answer,
                step=_pending_final_event.step,
            )
        )

    # ── 执行日志：任务完成 ──
    _run_elapsed = time.perf_counter() - _run_start
    logger.info(
        "task_complete",
        run_id=resolved_run_id,
        steps=state.step,
        elapsed_sec=round(_run_elapsed, 1),
        tool_calls=_tool_success + _tool_fail,
        success_rate=round(_tool_success / max(_tool_success + _tool_fail, 1) * 100),
        files_changed=len(_changed_files),
        model_degraded=_model_degraded,
    )

    # ── 资源清理：释放缓存内存 ──
    _file_read_cache.clear()
    _recent_tool_calls.clear()
    _tool_call_history.clear()

    return AgentRun(
        run_id=resolved_run_id,
        goal=goal,
        role_name=role.name,
        tenant_id=principal.tenant_id,
        final_answer=state.final_answer,
        steps=state.step,
        status=_run_status,
        error=_run_error,
        events=events,
        conversation_id=conv_session.conversation_id,
        prompt_tokens=state.total_prompt_tokens,
        completion_tokens=state.total_completion_tokens,
    )

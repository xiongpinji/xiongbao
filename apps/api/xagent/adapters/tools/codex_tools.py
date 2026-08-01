"""Codex 对齐工具集：git 操作 + 代码搜索 + 文件编辑。

- git：执行 git 命令（status/diff/log/branch/commit/add）
- code_search：ripgrep 风格全文搜索（正则 + 文件类型过滤）
- file_edit：精确搜索替换编辑文件（对标 Codex 的 auto-edit 模式）
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from xagent.adapters.tools.base import Tool, ToolContext, ToolResult, ToolSpec

_WORKSPACE = Path(os.environ.get("XAGENT_WORKSPACE", Path.home() / "xagent_workspace"))
_MAX_OUTPUT = 6000
_MAX_SEARCH_RESULTS = 50


def _truncate(text: str, limit: int = _MAX_OUTPUT) -> str:
    if len(text) > limit:
        return text[:limit] + f"\n... [truncated, total {len(text)} chars]"
    return text


def _run_git(args: list[str], cwd: str, timeout: int = 30) -> tuple[str, str, int]:
    """Execute git command."""
    git_path = shutil.which("git")
    if not git_path:
        return "", "git not installed or not in PATH", -1
    cmd = [git_path] + args
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = ""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=cwd, encoding="utf-8", errors="replace", env=env,
        )
        return proc.stdout or "", proc.stderr or "", proc.returncode
    except subprocess.TimeoutExpired:
        return "", f"git timeout ({timeout}s)", -1
    except Exception as e:
        return "", f"git failed: {e}", -1


# --- Git Tool ---


class GitTool:
    """Codex-aligned git integration."""

    spec = ToolSpec(
        name="git",
        description=(
            "Execute Git operations. Supported: status, diff, log, branch, checkout, "
            "add, commit, stash, remote, init, clone. "
            "Use for viewing changes, creating branches, committing code."
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "git subcommand+args, e.g. 'status', 'diff --staged', 'log --oneline -10', 'add .', 'commit -m \"fix: xxx\"'",
                },
                "working_dir": {
                    "type": "string",
                    "description": "repo path (defaults to workspace)",
                },
            },
            "required": ["command"],
        },
    )

    _BLOCKED = ("push --force", "reset --hard", "clean -fd", "branch -D main", "branch -D master")

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        command = args.get("command", "").strip()
        if not command:
            return ToolResult(ok=False, error="command cannot be empty")
        cmd_lower = command.lower()
        for blocked in self._BLOCKED:
            if blocked in cmd_lower:
                return ToolResult(ok=False, error=f"Security: '{blocked}' is blocked")
        cwd = args.get("working_dir") or str(_WORKSPACE)
        git_args = command.split()
        out, err, rc = await asyncio.to_thread(_run_git, git_args, cwd)
        output = _truncate((out + ("\n[stderr] " + err if err.strip() else "")).strip())
        if rc == 0:
            return ToolResult(ok=True, output=output or "(no output)")
        return ToolResult(ok=False, error=output or f"git exit code: {rc}")


# --- Code Search Tool ---


class CodeSearchTool:
    """Codex-aligned code search: regex full-text search."""

    spec = ToolSpec(
        name="code_search",
        description=(
            "Search codebase with regex (like ripgrep/grep). "
            "Returns matching lines with file:line format. "
            "Supports file extension filtering (e.g. *.py, *.ts)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "regex or text to search"},
                "path": {"type": "string", "description": "search directory (defaults to workspace)"},
                "file_pattern": {"type": "string", "description": "glob filter e.g. '*.py'"},
                "max_results": {"type": "integer", "description": "max results (default 50)"},
            },
            "required": ["pattern"],
        },
    )

    _SKIP_DIRS = {
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        ".ruff_cache", ".pytest_cache", "dist", "build", ".next",
        ".worktrees", ".codegraph",
    }
    _SKIP_EXTS = {
        ".pyc", ".pyo", ".so", ".dll", ".exe", ".bin",
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
        ".mp4", ".mp3", ".wav", ".zip", ".tar", ".gz",
        ".db", ".sqlite", ".lock",
    }

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        pattern = args.get("pattern", "")
        if not pattern:
            return ToolResult(ok=False, error="pattern cannot be empty")
        search_path = Path(args.get("path") or ".")
        if not search_path.is_absolute():
            search_path = _WORKSPACE / search_path
        if not search_path.exists():
            return ToolResult(ok=False, error=f"path not found: {search_path}")
        file_pattern = args.get("file_pattern", "")
        max_results = min(int(args.get("max_results") or _MAX_SEARCH_RESULTS), 100)
        rg_path = shutil.which("rg")
        if rg_path:
            return await self._search_rg(rg_path, pattern, search_path, file_pattern, max_results)
        return await asyncio.to_thread(self._search_py, pattern, search_path, file_pattern, max_results)

    async def _search_rg(self, rg: str, pattern: str, path: Path, file_pat: str, max_results: int) -> ToolResult:
        cmd = [rg, "--line-number", "--no-heading", "--color=never", "-m", str(max_results)]
        if file_pat:
            cmd += ["--glob", file_pat]
        for d in self._SKIP_DIRS:
            cmd += ["--glob", f"!{d}"]
        cmd += [pattern, str(path)]
        try:
            proc = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True,
                timeout=30, encoding="utf-8", errors="replace",
            )
            output = proc.stdout.strip()
            if not output and proc.returncode == 1:
                return ToolResult(ok=True, output="(no matches)")
            if proc.returncode > 1:
                return ToolResult(ok=False, error=proc.stderr[:500])
            return ToolResult(ok=True, output=_truncate(output))
        except Exception as e:
            return ToolResult(ok=False, error=f"ripgrep failed: {e}")

    def _search_py(self, pattern: str, path: Path, file_pat: str, max_results: int) -> ToolResult:
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return ToolResult(ok=False, error=f"invalid regex: {e}")
        results: list[str] = []
        files_searched = 0
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in self._SKIP_DIRS]
            for fname in files:
                fpath = Path(root) / fname
                if fpath.suffix.lower() in self._SKIP_EXTS:
                    continue
                if file_pat and not fpath.match(file_pat):
                    continue
                try:
                    if fpath.stat().st_size > 1_000_000:
                        continue
                except OSError:
                    continue
                files_searched += 1
                try:
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for i, line in enumerate(content.splitlines(), 1):
                    if regex.search(line):
                        rel = fpath.relative_to(path)
                        results.append(f"{rel}:{i}: {line.rstrip()[:200]}")
                        if len(results) >= max_results:
                            break
                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break
        if not results:
            return ToolResult(ok=True, output=f"(no matches, searched {files_searched} files)")
        header = f"Found {len(results)} matches ({files_searched} files searched):\n"
        return ToolResult(ok=True, output=_truncate(header + "\n".join(results)))


# --- File Edit Tool (search & replace) ---


class FileEditTool:
    """Codex auto-edit: precise search-replace file editing."""

    spec = ToolSpec(
        name="file_edit",
        description=(
            "Edit file by searching and replacing text. "
            "More precise than file_write - only modifies target section. "
            "Use for modifying functions, updating configs, fixing bugs."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "file path"},
                "old_text": {"type": "string", "description": "text to find (must match exactly)"},
                "new_text": {"type": "string", "description": "replacement text"},
                "replace_all": {"type": "boolean", "description": "replace all occurrences (default false)"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = Path(args.get("path", ""))
        if not path.is_absolute():
            path = _WORKSPACE / path
        if not path.exists():
            return ToolResult(ok=False, error=f"file not found: {path}")
        old_text = args.get("old_text", "")
        new_text = args.get("new_text", "")
        replace_all = args.get("replace_all", False)
        if not old_text:
            return ToolResult(ok=False, error="old_text cannot be empty")
        if old_text == new_text:
            return ToolResult(ok=False, error="old_text and new_text are identical")
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            return ToolResult(ok=False, error=f"read failed: {e}")
        count = content.count(old_text)
        if count == 0:
            lines = content.splitlines()
            hint = ""
            old_first = old_text.splitlines()[0].strip() if old_text else ""
            if old_first:
                for i, line in enumerate(lines, 1):
                    if old_first in line:
                        hint = f"\nHint: line {i} has similar: {line.strip()[:100]}"
                        break
            return ToolResult(ok=False, error=f"text not found ({len(lines)} lines){hint}")
        if replace_all:
            new_content = content.replace(old_text, new_text)
        else:
            new_content = content.replace(old_text, new_text, 1)
        try:
            path.write_text(new_content, encoding="utf-8")
        except Exception as e:
            return ToolResult(ok=False, error=f"write failed: {e}")
        replaced = count if replace_all else 1
        return ToolResult(ok=True, output=f"Replaced {replaced} occurrence(s) in {path.name}")


# --- Skill Tools ---


class SkillExecTool:
    """Execute a stored skill by name/ID (tool call sequence replay)."""

    spec = ToolSpec(
        name="skill_exec",
        description=(
            "Execute a stored skill. Skills are reusable task templates "
            "learned from previous successful tasks. "
            "Use skill_list to see available skills."
        ),
        parameters={
            "type": "object",
            "properties": {
                "skill_id": {"type": "string", "description": "skill ID to execute"},
                "params": {"type": "object", "description": "optional parameters for the skill"},
            },
            "required": ["skill_id"],
        },
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        skill_id = args.get("skill_id", "")
        if not skill_id:
            return ToolResult(ok=False, error="skill_id cannot be empty")
        try:
            from xagent.core.skills import get_skill_store
            store = get_skill_store()
            skill = store.get(skill_id)
            if not skill:
                return ToolResult(ok=False, error=f"skill '{skill_id}' not found")
            # Record usage
            store.record_usage(skill_id, success=True)
            # Return skill info for the agent to follow
            steps_desc = ""
            if skill.steps:
                steps_desc = "\nSteps:\n" + "\n".join(
                    f"  {i+1}. {s.get('tool', '?')}({s.get('args', {})})"
                    for i, s in enumerate(skill.steps)
                )
            output = (
                f"Skill: {skill.name}\n"
                f"Description: {skill.description}\n"
                f"Hint: {skill.system_prompt_hint or 'none'}"
                f"{steps_desc}"
            )
            return ToolResult(ok=True, output=output)
        except Exception as e:
            return ToolResult(ok=False, error=f"skill exec failed: {e}")


class SkillListTool:
    """List available skills."""

    spec = ToolSpec(
        name="skill_list",
        description=(
            "List all available skills. Skills are reusable task templates "
            "that can be executed with skill_exec."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "optional search query to filter skills"},
            },
            "required": [],
        },
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            from xagent.core.skills import get_skill_store
            store = get_skill_store()
            query = args.get("query", "")
            if query:
                skills = store.match(query)
            else:
                skills = store.list_all()
            if not skills:
                return ToolResult(ok=True, output="(no skills found)")
            lines = []
            for s in skills[:20]:
                lines.append(
                    f"- [{s.skill_id}] {s.name}: {s.description} "
                    f"(used {s.use_count}x, success {s.success_rate:.0%})"
                )
            return ToolResult(ok=True, output="\n".join(lines))
        except Exception as e:
            return ToolResult(ok=False, error=f"skill list failed: {e}")


class SkillCreateTool:
    """Create a new skill from current task experience."""

    spec = ToolSpec(
        name="skill_create",
        description=(
            "Create a new reusable skill from current task experience. "
            "Call this after successfully completing a complex task to save "
            "the approach for future reuse."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "skill name"},
                "description": {"type": "string", "description": "what this skill does"},
                "trigger_pattern": {"type": "string", "description": "keywords to trigger (pipe-separated)"},
                "system_prompt_hint": {"type": "string", "description": "hint to inject when skill matches"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "tags"},
            },
            "required": ["name", "description", "trigger_pattern"],
        },
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        name = args.get("name", "")
        if not name:
            return ToolResult(ok=False, error="name cannot be empty")
        try:
            from xagent.core.skills import get_skill_store
            store = get_skill_store()
            skill = store.create_skill(
                name=name,
                description=args.get("description", ""),
                trigger_pattern=args.get("trigger_pattern", ""),
                system_prompt_hint=args.get("system_prompt_hint", ""),
                tags=args.get("tags", []),
            )
            return ToolResult(ok=True, output=f"Skill created: [{skill.skill_id}] {skill.name}")
        except Exception as e:
            return ToolResult(ok=False, error=f"skill create failed: {e}")


# --- Registration ---


def codex_tools() -> list[Tool]:
    """Return all Codex-aligned tool instances."""
    _WORKSPACE.mkdir(parents=True, exist_ok=True)
    return [
        GitTool(), CodeSearchTool(), FileEditTool(),
        SkillExecTool(), SkillListTool(), SkillCreateTool(),
    ]

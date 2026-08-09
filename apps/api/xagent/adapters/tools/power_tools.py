"""实用工具集：让智能体真正具备执行能力。

- python_exec：执行 Python 代码片段，返回 stdout/stderr/结果
- shell_exec：执行系统命令（有超时保护）
- web_fetch：抓取网页正文内容
- file_read：读取文件内容
- file_write：写入/创建文件
- file_list：列出目录结构
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from xagent.adapters.tools.base import Tool, ToolContext, ToolResult, ToolSpec

# 安全工作目录（文件操作限制在此目录下）
from xagent.core.workspace import get_workspace as _ws_resolve  # V3-3: 每任务可覆盖

_MAX_OUTPUT = 4000  # 输出截断长度（工具结果给 LLM 看的上限）
_TIMEOUT = 30  # python_exec 命令超时秒数
_SHELL_TIMEOUT = 120  # shell_exec 超时（安装依赖等耗时操作）

# ── 沙箱安全：危险命令黑名单（对标 Codex 沙箱隔离） ──
_DANGEROUS_PATTERNS = (
    "rm -rf /", "rm -rf ~", "del /s /q c:\\", "format c:",
    "rd /s /q c:\\", "shutdown", "reboot", "mkfs",
    "dd if=", "> /dev/sda", "chmod -R 777 /",
    "Remove-Item -Recurse -Force C:\\", "Remove-Item -Recurse -Force ~",
    "curl | sh", "wget | sh", "iwr | iex",
)


def _is_dangerous_command(cmd: str) -> str | None:
    """检测危险命令，返回拦截原因或 None。"""
    cmd_lower = cmd.lower().strip()
    for pattern in _DANGEROUS_PATTERNS:
        if pattern in cmd_lower:
            return f"安全拦截：检测到危险操作 '{pattern}'"
    return None


def _truncate(text: str) -> str:
    if len(text) > _MAX_OUTPUT:
        return text[:_MAX_OUTPUT] + f"\n... [截断，共 {len(text)} 字符]"
    return text


def _run_subprocess(
    cmd: list[str] | str, *, cwd: str, shell: bool = False, timeout: int = _TIMEOUT
) -> tuple[str, str, int]:
    """同步子进程（在线程池中调用，规避 Windows asyncio 子进程 bug）。"""
    env = os.environ.copy()
    # 确保当前 Python 解释器所在目录在 PATH 中（shell 中可用 python）
    python_dir = str(Path(sys.executable).parent)
    env["PATH"] = python_dir + os.pathsep + env.get("PATH", "")

    # Windows shell=True 默认用 cmd.exe，但 LLM 可能生成 PowerShell 或 Linux 语法
    # 必须显式用 pwsh/powershell 执行，否则 if/Test-Path/Get-ChildItem 等全部失败
    actual_cmd: list[str] | str = cmd
    if shell and sys.platform == "win32" and isinstance(cmd, str):
        # 用 shutil.which 可靠定位 PowerShell 可执行文件
        pwsh_path = shutil.which("pwsh") or shutil.which("powershell")
        if pwsh_path:
            actual_cmd = [pwsh_path, "-NoProfile", "-NonInteractive", "-Command", cmd]
            shell = False  # 已手动指定解释器，不再需要 shell=True

    try:
        proc = subprocess.run(
            actual_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            shell=shell,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        return proc.stdout or "", proc.stderr or "", proc.returncode
    except subprocess.TimeoutExpired:
        return "", f"执行超时（{timeout}s）", -1
    except Exception as e:
        return "", f"启动进程失败: {e}", -1


# ─── Python 代码执行 ───────────────────────────────────────────────


class PythonExecTool:
    spec = ToolSpec(
        name="python_exec",
        description=(
            "执行一段 Python 代码并返回输出。代码在独立子进程中运行，"
            "print() 的内容会作为 stdout 返回。适合计算、数据处理、算法验证等。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "要执行的 Python 代码"},
            },
            "required": ["code"],
        },
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        # 安全门禁：默认禁用（XAGENT_TOOLS__ENABLE_PYTHON_EXEC=false），即使被直接
        # 注册/调用也拒绝执行，对编排循环透明。
        from xagent.infra.settings import get_settings

        if not get_settings().tools.enable_python_exec:
            return ToolResult(
                ok=False,
                error=(
                    "python_exec 已被配置禁用：请显式设置 "
                    "XAGENT_TOOLS__ENABLE_PYTHON_EXEC=true 后重启以启用 Python 代码执行"
                    "（执行需配合沙箱后端，见 XAGENT_SANDBOX__BACKEND）"
                ),
            )

        code = args.get("code", "")
        if not code.strip():
            return ToolResult(ok=False, error="code 不能为空")

        # 沙箱路由（RFC-001）：backend=docker/e2b 时隔离执行，且**不降级到宿主机**
        # （沙箱失败说明隔离边界不可用，静默落到宿主机等于绕过安全边界）。
        # backend=disabled（L0）同样 fail-closed：拒绝执行并明确报错，不做宿主机
        # 子进程回退——与 docs/deployment/sandbox.md「默认 disabled：不执行任何
        # 不可信代码，绝不在宿主机裸跑」的安全姿态一致。
        from xagent.adapters.sandbox.base import get_sandbox

        sandbox = get_sandbox()
        if sandbox.backend == "disabled":
            return ToolResult(
                ok=False,
                error=(
                    "python_exec 拒绝执行：沙箱后端为 disabled（L0），按 RFC-001 安全姿态"
                    "不在宿主机执行不可信代码。请配置 XAGENT_SANDBOX__BACKEND=docker（或 e2b）"
                    "后在隔离环境中执行。"
                ),
            )
        sr = await sandbox.run_code("python", code, timeout=_TIMEOUT)
        if sr.ok:
            return ToolResult(ok=True, output=_truncate(sr.stdout or "(无输出)"))
        return ToolResult(
            ok=False,
            error=f"沙箱执行失败（backend={sandbox.backend}）: {sr.error or sr.stderr}",
        )


# ─── Shell 命令执行 ───────────────────────────────────────────────


class ShellExecTool:
    spec = ToolSpec(
        name="shell_exec",
        description=(
            "在系统 Shell 中执行命令。当前系统为 Windows，必须使用 PowerShell 语法！"
            "禁止使用 Linux/bash 命令（如 mkdir -p, ls -la, cat, pwd）。"
            "正确示例：New-Item -ItemType Directory -Path mydir -Force; "
            "Get-ChildItem; Get-Content file.txt; python script.py。"
            "适合安装依赖、运行脚本、创建目录、查看系统信息等。默认 120 秒超时。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的命令"},
                "working_dir": {"type": "string", "description": "工作目录（可选）"},
                "timeout": {"type": "integer", "description": "超时秒数（默认120，最大300）"},
            },
            "required": ["command"],
        },
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        # 安全门禁：默认禁用（XAGENT_TOOLS__ENABLE_SHELL=false），即使被直接
        # 注册/调用也拒绝执行，对编排循环透明。
        from xagent.infra.settings import get_settings

        if not get_settings().tools.enable_shell:
            return ToolResult(
                ok=False,
                error=(
                    "shell_exec 已被配置禁用：请显式设置 "
                    "XAGENT_TOOLS__ENABLE_SHELL=true 后重启以启用宿主机命令执行"
                ),
            )

        command = args.get("command", "")
        if not command.strip():
            return ToolResult(ok=False, error="command 不能为空")

        # ── 沙箱安全：危险命令拦截 ──
        danger = _is_dangerous_command(command)
        if danger:
            return ToolResult(ok=False, error=danger)

        timeout = min(int(args.get("timeout") or _SHELL_TIMEOUT), 300)

        # 沙箱路由（RFC-001 L1）：backend=docker 时命令在一次性隔离容器内执行，
        # 绝不落到宿主机；沙箱不可用直接报错，不做宿主机降级。
        from xagent.adapters.sandbox.base import get_sandbox

        sandbox = get_sandbox()
        if sandbox.backend != "disabled":
            sr = await sandbox.run_code("shell", command, timeout=timeout)
            parts = []
            if sr.stdout.strip():
                parts.append(sr.stdout)
            if sr.stderr.strip():
                parts.append(f"[stderr] {sr.stderr}")
            parts.append(f"[exit: {sr.exit_code}]")
            output = _truncate("\n".join(parts))
            if sr.ok:
                return ToolResult(ok=True, output=output)
            return ToolResult(
                ok=False,
                error=(
                    f"沙箱执行失败（backend={sandbox.backend}）: {sr.error}"
                    if sr.error and not sr.stdout
                    else output
                ),
            )

        cwd = args.get("working_dir") or str(_ws_resolve())

        try:
            out, err, rc = await asyncio.to_thread(
                _run_subprocess, command, cwd=cwd, shell=True, timeout=timeout
            )
            parts = []
            if out.strip():
                parts.append(out)
            if err.strip():
                parts.append(f"[stderr] {err}")
            parts.append(f"[exit: {rc}]")
            output = _truncate("\n".join(parts))

            if rc == 0:
                return ToolResult(ok=True, output=output)
            else:
                # 失败时把完整输出放入 error，避免前端显示 "[错误] None"
                return ToolResult(ok=False, error=output)
        except Exception as e:
            return ToolResult(ok=False, error=f"执行失败: {e}")


# ─── 网页抓取 ───────────────────────────────────────────────


class WebFetchTool:
    spec = ToolSpec(
        name="web_fetch",
        description=(
            "获取指定 URL 网页的文本内容（去除 HTML 标签）。"
            "适合查阅文档、获取 API 信息、阅读文章等。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "要抓取的网页 URL"},
            },
            "required": ["url"],
        },
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        url = args.get("url", "")
        if not url.startswith(("http://", "https://")):
            return ToolResult(ok=False, error="URL 必须以 http:// 或 https:// 开头")

        # GitHub 仓库页面智能路由：转为 API 调用获取结构化数据
        import re as _re
        gh_match = _re.match(
            r"https?://github\.com/([^/]+)/([^/]+)/?$", url
        )
        if gh_match:
            owner, repo = gh_match.group(1), gh_match.group(2)
            api_url = f"https://api.github.com/repos/{owner}/{repo}"
            try:
                import httpx
                resp = await asyncio.to_thread(
                    httpx.get, api_url,
                    headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "X-Agent"},
                    timeout=15,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    summary = (
                        f"仓库: {data.get('full_name', url)}\n"
                        f"描述: {data.get('description', '无')}\n"
                        f"语言: {data.get('language', '未知')}\n"
                        f"Stars: {data.get('stargazers_count', 0)}\n"
                        f"Topics: {', '.join(data.get('topics', []))}\n"
                        f"README URL: {data.get('html_url', '')}#readme"
                    )
                    return ToolResult(ok=True, output=summary)
            except Exception:
                pass  # API 失败则回退到普通抓取

        try:
            import httpx

            resp = await asyncio.to_thread(
                httpx.get,
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) X-Agent"},
                timeout=20,
                follow_redirects=True,
            )
            if resp.status_code >= 400:
                return ToolResult(
                    ok=False,
                    error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )

            content_type = resp.headers.get("content-type", "")
            if "json" in content_type:
                return ToolResult(ok=True, output=_truncate(resp.text))

            # HTML → 提取正文
            text = self._extract_text(resp.text, url)
            # 如果正文提取太少，尝试从 meta 标签获取有用信息
            if len(text.strip()) < 80:
                meta_info = self._extract_meta(resp.text, url)
                if meta_info:
                    text = meta_info
                else:
                    text = f"[该页面为 SPA/JS 渲染应用，无法提取正文内容。URL: {url}。建议：请用户提供页面功能描述，或尝试访问其 API 文档/README 页面。]"
            return ToolResult(ok=True, output=_truncate(text))
        except Exception as e:
            return ToolResult(ok=False, error=f"抓取失败: {type(e).__name__}: {e}")

    @staticmethod
    def _extract_meta(html: str, url: str) -> str:
        """从 HTML 的 <head> 中提取 meta 信息（title/description/og tags），即使 SPA 也有。"""
        import re
        parts = []
        # title
        title_m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
        if title_m:
            parts.append(f"页面标题: {title_m.group(1).strip()}")
        # meta description
        desc_m = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', html, re.I
        )
        if not desc_m:
            desc_m = re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']', html, re.I
            )
        if desc_m:
            parts.append(f"页面描述: {desc_m.group(1).strip()}")
        # og:title
        og_title = re.search(
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', html, re.I
        )
        if og_title and og_title.group(1).strip() not in (title_m.group(1).strip() if title_m else ""):
            parts.append(f"OG标题: {og_title.group(1).strip()}")
        # og:description
        og_desc = re.search(
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)', html, re.I
        )
        if og_desc and og_desc.group(1).strip() not in (desc_m.group(1).strip() if desc_m else ""):
            parts.append(f"OG描述: {og_desc.group(1).strip()}")
        # og:type / og:site_name
        og_site = re.search(
            r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']+)', html, re.I
        )
        if og_site:
            parts.append(f"站点名: {og_site.group(1).strip()}")
        # keywords
        kw_m = re.search(
            r'<meta[^>]+name=["\']keywords["\'][^>]+content=["\']([^"\']+)', html, re.I
        )
        if kw_m:
            parts.append(f"关键词: {kw_m.group(1).strip()}")
        if not parts:
            return ""
        header = f"[以下为从 {url} 的 HTML meta 标签提取的信息（页面主体为 JS 渲染，无法获取完整正文）：]\n"
        return header + "\n".join(parts)

    @staticmethod
    def _extract_text(html: str, url: str = "") -> str:
        """HTML 正文提取：去 script/style/nav/header/footer，保留主体文本。"""
        import re

        # GitHub 特判：搜索页/导航页几乎无有用内容，直接提示
        if "github.com" in url and ("/search" in url or "/topics" in url or "/explore" in url):
            og = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)', html, re.I)
            if og:
                return f"[GitHub 页面，JS 渲染内容无法完整提取。页面描述: {og.group(1)}]"
            return f"[GitHub 搜索/导航页面，内容需 JS 渲染，无法提取。URL: {url}]"

        # 去除无用区块
        html = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.I)
        html = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", html, flags=re.I)
        html = re.sub(r"<nav[^>]*>[\s\S]*?</nav>", "", html, flags=re.I)
        html = re.sub(r"<header[^>]*>[\s\S]*?</header>", "", html, flags=re.I)
        html = re.sub(r"<footer[^>]*>[\s\S]*?</footer>", "", html, flags=re.I)
        html = re.sub(r"<aside[^>]*>[\s\S]*?</aside>", "", html, flags=re.I)
        # 去除 form / svg / noscript
        html = re.sub(r"<form[^>]*>[\s\S]*?</form>", "", html, flags=re.I)
        html = re.sub(r"<svg[^>]*>[\s\S]*?</svg>", "", html, flags=re.I)
        html = re.sub(r"<noscript[^>]*>[\s\S]*?</noscript>", "", html, flags=re.I)
        # 优先提取 main / article 内容
        main_match = re.search(r"<(?:main|article)[^>]*>([\s\S]*?)</(?:main|article)>", html, re.I)
        if main_match:
            html = main_match.group(1)
        # 去标签
        html = re.sub(r"<[^>]+>", " ", html)
        html = re.sub(r"&[a-z]+;", " ", html)  # HTML entities
        html = re.sub(r"&#\d+;", " ", html)
        html = re.sub(r"\s+", " ", html)
        text = html.strip()
        # 去除常见导航噪音
        noise_patterns = [
            "skip to content", "sign in", "sign up", "toggle navigation",
            "navigation menu", "search syntax", "cookie", "privacy policy",
            "terms of service", "appearance settings", "platform ai",
            "code creation", "copilot", "actions agents", "mcp registry",
            "new integrate", "external tools", "developer workflows",
            "codespaces", "instant dev", "plan and track", "code review",
            "manage code changes", "enforce quality", "security",
            "secret protection", "stop leaks", "explore by topic",
            "customer stories", "events & webinars", "ebooks & reports",
            "business insights", "skills", "support & services",
            "documentation customer", "support community forum",
            "trust center", "partners", "view all resources",
            "open source", "sponsors fund", "accelerator", "stars archive",
            "trending collections", "enterprise solutions",
            "you can't perform that action",
        ]
        # 按句子分割过滤
        sentences = re.split(r'(?<=[.!?])\s+', text)
        cleaned = [
            s for s in sentences
            if len(s.strip()) > 10 and not any(p in s.lower() for p in noise_patterns)
        ]
        result = " ".join(cleaned).strip()
        # 如果过滤后内容太少，返回原始截断版
        if len(result) < 100:
            result = text[:2000]
        return result


# ─── 文件操作 ───────────────────────────────────────────────


class FileReadTool:
    spec = ToolSpec(
        name="file_read",
        description="读取指定路径文件的内容。支持文本文件。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
            },
            "required": ["path"],
        },
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = Path(args.get("path", ""))
        if not path.is_absolute():
            path = _ws_resolve() / path
        if not path.exists():
            return ToolResult(ok=False, error=f"文件不存在: {path}")
        if not path.is_file():
            return ToolResult(ok=False, error=f"不是文件: {path}")
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            return ToolResult(ok=True, output=_truncate(content))
        except Exception as e:
            return ToolResult(ok=False, error=f"读取失败: {e}")


def _resolve_workspace_write_path(raw_path: Any) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("写入路径不能为空")
    requested = Path(raw_path)
    if any(part == ".." for part in requested.parts):
        raise ValueError("写入路径不得包含 ../ 穿越")
    if any(part.casefold() == ".git" for part in requested.parts):
        raise ValueError("禁止写入 Git 元数据路径")

    workspace = _ws_resolve().resolve()
    candidate = requested if requested.is_absolute() else workspace / requested
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(workspace):
        raise ValueError(f"写入路径必须位于 workspace 内: {workspace}")
    relative = resolved.relative_to(workspace)
    if any(part.casefold() == ".git" for part in relative.parts):
        raise ValueError("禁止写入 Git 元数据路径")
    return resolved


class FileWriteTool:
    spec = ToolSpec(
        name="file_write",
        description="将内容写入指定路径（自动创建父目录）。适合生成代码文件、配置文件等。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "要写入的内容"},
            },
            "required": ["path", "content"],
        },
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        content = args.get("content", "")
        try:
            path = _resolve_workspace_write_path(args.get("path", ""))
        except (OSError, ValueError) as exc:
            return ToolResult(ok=False, error=str(exc))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # ── 原子写入：先写临时文件再 rename（防止崩溃时文件损坏） ──
            import tempfile as _tf
            _tmp_fd, _tmp_path = _tf.mkstemp(
                dir=str(path.parent), suffix=".tmp", prefix=f".{path.name}."
            )
            try:
                with os.fdopen(_tmp_fd, "w", encoding="utf-8") as _f:
                    _f.write(content)
                os.replace(_tmp_path, path)
            except Exception:
                # 清理临时文件
                try:
                    os.unlink(_tmp_path)
                except OSError:
                    pass
                raise
            return ToolResult(ok=True, output=f"已写入 {path}（{len(content)} 字符）")
        except Exception as e:
            return ToolResult(ok=False, error=f"写入失败: {e}")


class FileListTool:
    spec = ToolSpec(
        name="file_list",
        description="列出指定目录下的文件和子目录。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径（默认为工作目录）"},
            },
            "required": [],
        },
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = Path(args.get("path", "") or ".")
        if not path.is_absolute():
            path = _ws_resolve() / path
        if not path.exists():
            return ToolResult(ok=False, error=f"目录不存在: {path}")
        if not path.is_dir():
            return ToolResult(ok=False, error=f"不是目录: {path}")
        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
            lines = []
            for e in entries[:100]:
                prefix = "📁 " if e.is_dir() else "   "
                size = f" ({e.stat().st_size}B)" if e.is_file() else ""
                lines.append(f"{prefix}{e.name}{size}")
            return ToolResult(ok=True, output="\n".join(lines) or "(空目录)")
        except Exception as e:
            return ToolResult(ok=False, error=f"列目录失败: {e}")


# ─── 注册入口 ───────────────────────────────────────────────


def power_tools() -> list[Tool]:
    """返回所有实用工具实例。

    安全门禁：``shell_exec`` / ``python_exec`` 默认不注册
    （XAGENT_TOOLS__ENABLE_SHELL / XAGENT_TOOLS__ENABLE_PYTHON_EXEC=false），
    工具列表喂给 LLM 时直接不可见；仅显式开启时才注册。
    """
    _ws_resolve().mkdir(parents=True, exist_ok=True)
    from xagent.infra.logging import get_logger
    from xagent.infra.settings import get_settings

    settings = get_settings()
    log = get_logger("xagent.tools")
    tools: list[Tool] = []
    if settings.tools.enable_python_exec:
        tools.append(PythonExecTool())
    else:
        log.info(
            "python_exec_disabled",
            message="python_exec 工具未注册（XAGENT_TOOLS__ENABLE_PYTHON_EXEC=false）",
        )
    tools.extend(
        [
            WebFetchTool(),
            FileReadTool(),
            FileWriteTool(),
            FileListTool(),
        ]
    )
    if settings.tools.enable_shell:
        tools.append(ShellExecTool())
    else:
        log.info(
            "shell_exec_disabled",
            message="shell_exec 工具未注册（XAGENT_TOOLS__ENABLE_SHELL=false）",
        )
    return tools

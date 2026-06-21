"""智能体剪辑工具：注册到 ToolRegistry，让 agent 通过 function-calling 操作剪辑。

工具集：创建时间线 / 添加片段 / 添加转场 / 添加字幕 / 添加配乐 / 剪切 / 渲染 / 导出草稿。
agent 可自主调用这些工具完成完整剪辑流程。
"""

from __future__ import annotations

from typing import Any

from xagent.adapters.tools.base import Tool, ToolContext, ToolResult, ToolSpec
from xagent.domains.creative_studio.editor.models import (
    Clip,
    Timeline,
    TrackType,
    Transition,
    TransitionType,
)
from xagent.domains.creative_studio.editor.video_editor import get_video_editor

# 进程内时间线存储（按 tenant 隔离在路由层；工具层共享）
_timelines: dict[str, Timeline] = {}


def get_timeline(timeline_id: str) -> Timeline | None:
    return _timelines.get(timeline_id)


class CreateTimelineTool:
    spec = ToolSpec(
        name="editor_create_timeline",
        description="创建视频剪辑时间线（宽高/帧率），返回 timeline_id。",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "default": "未命名"},
                "width": {"type": "integer", "default": 1080},
                "height": {"type": "integer", "default": 1920},
                "fps": {"type": "integer", "default": 30},
            },
        },
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        tl = Timeline(
            name=args.get("name", "未命名"),
            width=args.get("width", 1080),
            height=args.get("height", 1920),
            fps=args.get("fps", 30),
        )
        _timelines[tl.id] = tl
        return ToolResult(ok=True, output={"timeline_id": tl.id})


class AddClipTool:
    spec = ToolSpec(
        name="editor_add_clip",
        description="添加视频/音频/文本片段到时间线。",
        parameters={
            "type": "object",
            "properties": {
                "timeline_id": {"type": "string"},
                "track_type": {"type": "string", "enum": ["video", "audio", "text"]},
                "source_url": {"type": "string", "description": "素材URL(视频/音频)"},
                "timeline_start": {"type": "number", "default": 0},
                "timeline_end": {"type": "number", "default": 4},
                "text": {"type": "string", "description": "文本内容(text类型)"},
            },
            "required": ["timeline_id", "track_type"],
        },
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        tl = _timelines.get(args["timeline_id"])
        if tl is None:
            return ToolResult(ok=False, error="时间线不存在")
        clip = Clip(
            track_type=TrackType(args.get("track_type", "video")),
            source_url=args.get("source_url", ""),
            timeline_start=args.get("timeline_start", 0),
            timeline_end=args.get("timeline_end", 4),
            text=args.get("text", ""),
        )
        tl.add_clip(clip)
        return ToolResult(ok=True, output={"clip_id": clip.id, "timeline": tl.to_dict()})


class AddTransitionTool:
    spec = ToolSpec(
        name="editor_add_transition",
        description="添加片段间转场(dissolve/fade/wipe/slide/zoom)。",
        parameters={
            "type": "object",
            "properties": {
                "timeline_id": {"type": "string"},
                "clip_id": {"type": "string"},
                "type": {"type": "string", "enum": ["dissolve", "fade", "wipe", "slide", "zoom"]},
                "duration": {"type": "number", "default": 0.5},
            },
            "required": ["timeline_id", "clip_id"],
        },
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        tl = _timelines.get(args["timeline_id"])
        if tl is None:
            return ToolResult(ok=False, error="时间线不存在")
        tr = Transition(
            clip_id=args["clip_id"],
            type=TransitionType(args.get("type", "dissolve")),
            duration=args.get("duration", 0.5),
        )
        tl.add_transition(tr)
        return ToolResult(ok=True, output={"transition_id": tr.id})


class RenderVideoTool:
    spec = ToolSpec(
        name="editor_render",
        description="渲染时间线导出视频文件(MoviePy)。",
        parameters={
            "type": "object",
            "properties": {"timeline_id": {"type": "string"}},
            "required": ["timeline_id"],
        },
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        tl = _timelines.get(args["timeline_id"])
        if tl is None:
            return ToolResult(ok=False, error="时间线不存在")
        result = await get_video_editor().render(tl)
        return ToolResult(ok=result["ok"], output=result, error=result.get("error"))


class ExportDraftTool:
    spec = ToolSpec(
        name="editor_export_draft",
        description="导出剪映草稿(可在剪映中打开精修)。",
        parameters={
            "type": "object",
            "properties": {"timeline_id": {"type": "string"}},
            "required": ["timeline_id"],
        },
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        tl = _timelines.get(args["timeline_id"])
        if tl is None:
            return ToolResult(ok=False, error="时间线不存在")
        result = get_video_editor().export_jianying_draft(tl)
        return ToolResult(ok=result["ok"], output=result, error=result.get("error"))


def editor_tools() -> list[Tool]:
    return [
        CreateTimelineTool(),
        AddClipTool(),
        AddTransitionTool(),
        RenderVideoTool(),
        ExportDraftTool(),
    ]

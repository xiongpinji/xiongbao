"""VideoEditor 引擎：MoviePy 渲染 + pyJianYingDraft 草稿导出。

MoviePy（MIT）：服务端无 GUI 渲染导出视频（剪切/拼接/字幕/配乐/合成）。
pyJianYingDraft（Apache）：生成剪映草稿 JSON（用户可打开精修）。
两者未安装时降级为纯数据操作（时间线 CRUD 仍可用，渲染返回占位）。
"""

from __future__ import annotations

import json
import os
from typing import Any

from xagent.domains.creative_studio.editor.models import (
    Timeline,
    TrackType,
)
from xagent.infra.logging import get_logger

logger = get_logger("xagent.editor")


class VideoEditor:
    """视频剪辑引擎。"""

    def __init__(self, output_dir: str = "./data/renders") -> None:
        self._output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def has_moviepy(self) -> bool:
        try:
            import moviepy  # noqa: F401

            return True
        except ImportError:
            return False

    def has_jianying(self) -> bool:
        try:
            import pyJianYingDraft  # noqa: F401

            return True
        except ImportError:
            return False

    def preview(self, timeline: Timeline) -> dict[str, Any]:
        """返回时间线结构化预览（前端渲染用）。"""
        return timeline.to_dict()

    async def render(self, timeline: Timeline, output_name: str | None = None) -> dict[str, Any]:
        """用 MoviePy 渲染导出视频。未装 MoviePy 返回占位。"""
        if not self.has_moviepy():
            logger.warning("moviepy_not_installed", detail="渲染降级为占位")
            return {
                "ok": False,
                "error": "未安装 MoviePy。pip install moviepy 后重试。",
                "timeline_id": timeline.id,
            }

        from moviepy import CompositeVideoClip, TextClip, VideoFileClip, concatenate_videoclips

        output_name = output_name or f"render_{timeline.id[:8]}.mp4"
        output_path = os.path.join(self._output_dir, output_name)

        try:
            # 按轨道类型分组处理
            video_clips = []
            text_clips = []

            for clip in timeline.clips:
                if clip.track_type == TrackType.video and clip.source_url:
                    vc = VideoFileClip(clip.source_url)
                    # 截取
                    if clip.source_start is not None or clip.source_end is not None:
                        vc = vc.subclipped(
                            clip.source_start or 0,
                            clip.source_end or vc.duration,
                        )
                    vc = vc.with_duration(clip.duration)
                    if clip.volume != 1.0:
                        vc = vc.with_volume_scaled(clip.volume)
                    video_clips.append(vc)

                elif clip.track_type == TrackType.text and clip.text:
                    tc = TextClip(
                        text=clip.text, font_size=clip.font_size,
                        color=clip.color, size=(timeline.width, None),
                    )
                    tc = tc.with_duration(clip.duration)
                    tc = tc.with_position(clip.position)
                    tc = tc.with_start(clip.timeline_start)
                    text_clips.append(tc)

            # 拼接视频片段
            if video_clips:
                base = (
                    concatenate_videoclips(video_clips)
                    if len(video_clips) > 1
                    else video_clips[0]
                )
            else:
                # 纯文本/无视频 -> 创建黑色底
                from moviepy import ColorClip

                base = ColorClip(
                    size=(timeline.width, timeline.height),
                    color=(0, 0, 0),
                    duration=timeline.total_duration or 5,
                )

            # 叠加文本
            if text_clips:
                base = CompositeVideoClip(
                    [base] + text_clips,
                    size=(timeline.width, timeline.height),
                )

            base = base.with_fps(timeline.fps)
            base.write_videofile(
                output_path, codec="libx264", audio_codec="aac", logger=None
            )

            logger.info("render_done", path=output_path, duration=timeline.total_duration)
            return {
                "ok": True,
                "output_path": output_path,
                "output_url": f"local://renders/{output_name}",
                "timeline_id": timeline.id,
                "duration": round(timeline.total_duration, 2),
            }
        except Exception as exc:
            logger.error("render_failed", error=str(exc))
            return {"ok": False, "error": str(exc), "timeline_id": timeline.id}

    def export_jianying_draft(
        self, timeline: Timeline, draft_name: str | None = None
    ) -> dict[str, Any]:
        """用 pyJianYingDraft 生成剪映草稿 JSON。未装返回占位。"""
        if not self.has_jianying():
            logger.warning("pyJianYingDraft_not_installed", detail="草稿导出降级为占位 JSON")
            # 降级：导出时间线 JSON（用户可手动导入或将来用）
            draft_name = draft_name or f"draft_{timeline.id[:8]}"
            path = os.path.join(self._output_dir, f"{draft_name}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(timeline.to_dict(), f, ensure_ascii=False, indent=2)
            return {
                "ok": True,
                "draft_path": path,
                "note": "pyJianYingDraft 未安装，已导出时间线 JSON（可手动转换）",
                "timeline_id": timeline.id,
            }

        import pyJianYingDraft as draft

        script = draft.ScriptFile(timeline.width, timeline.height)

        # 添加轨道
        script.add_track(draft.TrackType.video, "main")
        script.add_track(draft.TrackType.text, "subtitles")
        script.add_track(draft.TrackType.audio, "bgm")

        # 添加片段
        for clip in timeline.clips:
            tr = draft.trange(
                f"{clip.timeline_start}s",
                f"{clip.duration}s",
            )
            if clip.track_type == TrackType.video and clip.source_url:
                seg = draft.VideoSegment(clip.source_url, tr)
                script.add_segment(seg, "main")
            elif clip.track_type == TrackType.text and clip.text:
                seg = draft.TextSegment(clip.text, tr)
                script.add_segment(seg, "subtitles")
            elif clip.track_type == TrackType.audio and clip.source_url:
                seg = draft.AudioSegment(clip.source_url, tr)
                if clip.fade_in or clip.fade_out:
                    seg.add_fade(
                        f"{clip.fade_in}s" if clip.fade_in else None,
                        f"{clip.fade_out}s" if clip.fade_out else None,
                    )
                script.add_segment(seg, "bgm")

        draft_name = draft_name or f"draft_{timeline.id[:8]}"
        path = os.path.join(self._output_dir, f"{draft_name}_draft_content.json")
        script.dump(path)

        logger.info("jianying_draft_exported", path=path)
        return {
            "ok": True,
            "draft_path": path,
            "note": "剪映草稿已生成，可在剪映中打开精修",
            "timeline_id": timeline.id,
        }


# 单例
_editor: VideoEditor | None = None


def get_video_editor() -> VideoEditor:
    global _editor
    if _editor is None:
        _editor = VideoEditor()
    return _editor

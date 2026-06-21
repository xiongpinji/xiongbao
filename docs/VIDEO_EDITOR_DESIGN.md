# 短剧工厂 · 视频剪辑引擎设计（类剪映）

> 目标：短剧工厂具备**专业视频剪辑完整功能**，智能体可完全操作整个剪辑流程。
> 选型：**MoviePy v2**（MIT，服务端渲染导出）+ **pyJianYingDraft**（Apache，剪映草稿导出）。

## 一、选型理由

| 引擎 | 用途 | 许可 | 服务端无GUI | 核心能力 |
|---|---|---|---|---|
| MoviePy v2 | 服务端视频渲染导出 | MIT | ✅ | 剪切/拼接/字幕/配乐/合成/转场/导出 |
| pyJianYingDraft | 剪映草稿生成 | Apache | ✅ | 时间线/轨道/片段/转场/字幕/配乐/特效/滤镜/关键帧 |

两者互补：MoviePy 做自动化渲染（智能体可全程操作），pyJianYingDraft 做剪映草稿（用户可打开精修）。

## 二、架构

```
domains/creative_studio/
  editor/
    models.py        时间线/轨道/片段/特效 数据模型（与剪辑引擎无关的中间表示）
    video_editor.py  VideoEditor 引擎（MoviePy 渲染 + pyJianYingDraft 草稿导出）
    tools.py         智能体剪辑工具（注册到 ToolRegistry）
```

### 数据模型（中间表示，引擎无关）

```python
class TrackType(Enum): video / audio / text / effect
class Clip:
    id, track_id, source_url, start, end,       # 时间线位置
    source_start, source_end,                    # 素材截取范围
    text, font_size, color, position,            # 文本属性
    volume, fade_in, fade_out                    # 音频属性
class Transition:
    id, clip_id, type(dissolve/fade/wipe...), duration
class Timeline:
    id, width, height, fps, clips[], transitions[]
```

### VideoEditor 引擎

```python
class VideoEditor:
    async def render(timeline: Timeline, output_path: str) -> str
        # MoviePy: 加载素材 → 剪切 → 拼接 → 加字幕 → 加配乐 → 合成 → 导出
    def export_jianying_draft(timeline: Timeline, draft_path: str) -> str
        # pyJianYingDraft: 生成剪映草稿 JSON
    def preview_timeline(timeline: Timeline) -> dict
        # 返回时间线结构化预览（前端渲染用）
```

### 智能体剪辑工具（注册到 ToolRegistry）

| 工具 | 说明 |
|---|---|
| `editor_create_timeline` | 创建时间线（宽高/帧率） |
| `editor_add_clip` | 添加片段到轨道（素材/时间范围/文本） |
| `editor_add_transition` | 添加转场 |
| `editor_add_subtitle` | 添加字幕（文本/时间/样式） |
| `editor_add_audio` | 添加配乐（音频素材/淡入淡出） |
| `editor_trim_clip` | 剪切片段（调整起止时间） |
| `editor_render` | 渲染导出视频（MoviePy） |
| `editor_export_draft` | 导出剪映草稿 |

智能体可通过 function-calling 自主调用这些工具完成完整剪辑流程。

## 三、API 路由

| 端点 | 说明 |
|---|---|
| `POST /creative-studio/editor/timelines` | 创建时间线 |
| `GET /creative-studio/editor/timelines` | 列出时间线 |
| `POST /creative-studio/editor/timelines/{id}/clips` | 添加片段 |
| `POST /creative-studio/editor/timelines/{id}/transitions` | 添加转场 |
| `POST /creative-studio/editor/timelines/{id}/render` | 渲染导出视频 |
| `POST /creative-studio/editor/timelines/{id}/export-draft` | 导出剪映草稿 |
| `POST /creative-studio/editor/agent-clip` | 智能体自主剪辑（一句话指令→完整剪辑） |

## 四、与短剧全链路衔接

produce_short_drama 产出的逐镜头视频 → 自动创建 Timeline → 添加到轨道 → 智能体可进一步操作（加转场/字幕/配乐）→ 渲染导出成片。

## 五、许可证

- MoviePy: MIT ✅
- pyJianYingDraft: Apache-2.0 ✅
- 均无 GPL/AGPL 风险，CI license-check 通过。

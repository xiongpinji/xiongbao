# 短剧工厂 · 媒体生成设计（多模型可插拔）

> 决策：媒体（图像 / 视频）生成采用**多模型可插拔 provider 架构**，不绑定单一平台 key。
> 预留通用接口对接：图像 = gpt-image-2 / DALL·E（OpenAI 兼容）；视频 = 可灵 Kling / 即梦 Jimeng / 通用任务式 HTTP。
> 未配 key 时 NullProvider 占位，流程不中断（lite/CI 零配置可跑）。

## 一、能力矩阵

| 能力 | 模式（GenerationMode） | provider |
|---|---|---|
| 文生图 | text_to_image | OpenAI(gpt-image-2/dall-e-3)、Null |
| 图生图 | image_to_image | OpenAI(images/edits)、Null |
| 文生视频 | text_to_video | Kling、Jimeng、Generic、Null |
| 图生视频 | image_to_video | Kling、Jimeng、Generic、Null |

## 二、抽象接口（`media/base.py`）

```python
class MediaKind(Enum): image / video / audio
class GenerationMode(Enum): text_to_image / image_to_image / text_to_video / image_to_video / text_to_speech

@dataclass
class GenerationRequest:
    kind, prompt, mode, model_id, negative_prompt,
    loras, reference_images,           # 图生图/图生视频输入
    duration_seconds, fps, resolution, seed, params

@dataclass
class GenerationTask:
    task_id, provider, status, outputs, error, raw

class MediaProvider(Protocol):
    async def submit(req) -> GenerationTask      # 提交任务
    async def poll(task_id) -> GenerationTask    # 轮询状态
    def list_models(kind) -> list[ModelCard]     # 可用模型
```

## 三、provider 实现

| Provider | 文件 | 能力 | 说明 |
|---|---|---|---|
| `OpenAIImageProvider` | image_providers.py | 文生图/图生图 | gpt-image-2 / dall-e-3，OpenAI 兼容端点（可指向官方或代理），同步返回 |
| `KlingProvider` | video_providers.py | 文/图生视频 | 可灵 Kling（预留，任务式 submit+poll） |
| `JimengProvider` | video_providers.py | 文/图生视频 | 即梦 Jimeng（预留） |
| `GenericVideoProvider` | video_providers.py | 文/图生视频 | 通用任务式，配 submit_url/poll_url 即可对接任意视频 API（Runway/Pika 等） |
| `NullProvider` | base.py | 全部 | 占位降级，无需 key |

## 四、配置（settings `MediaSettings`，环境变量前缀 `XAGENT_MEDIA__`）

```bash
# provider 选择
XAGENT_MEDIA__DEFAULT_IMAGE_PROVIDER=openai     # null | openai
XAGENT_MEDIA__DEFAULT_VIDEO_PROVIDER=kling      # null | kling | jimeng | generic

# 图像（OpenAI 兼容：gpt-image-2 / dall-e-3）
XAGENT_MEDIA__OPENAI_IMAGE_API_KEY=...
XAGENT_MEDIA__OPENAI_IMAGE_BASE_URL=https://api.openai.com/v1
XAGENT_MEDIA__OPENAI_IMAGE_MODEL=gpt-image-2

# 视频（可灵）
XAGENT_MEDIA__KLING_API_KEY=...
XAGENT_MEDIA__KLING_SUBMIT_URL=...
XAGENT_MEDIA__KLING_POLL_URL=.../{task_id}

# 视频（即梦）
XAGENT_MEDIA__JIMENG_API_KEY=...
XAGENT_MEDIA__JIMENG_SUBMIT_URL=...
XAGENT_MEDIA__JIMENG_POLL_URL=.../{task_id}

# 视频（通用任务式，对接任意 API）
XAGENT_MEDIA__GENERIC_VIDEO_SUBMIT_URL=...
XAGENT_MEDIA__GENERIC_VIDEO_POLL_URL=.../{task_id}
XAGENT_MEDIA__GENERIC_VIDEO_API_KEY=...
XAGENT_MEDIA__GENERIC_VIDEO_MODEL=...

XAGENT_MEDIA__POLL_INTERVAL_SECONDS=3
XAGENT_MEDIA__TASK_TIMEOUT_SECONDS=600
```

## 五、API 端点

| 端点 | 说明 |
|---|---|
| `GET /api/v1/creative-studio/media/models?kind=image\|video` | 列出可用媒体模型 |
| `POST /api/v1/creative-studio/media/generate` | 媒体生成（kind/prompt/mode/model_id/reference_images/wait） |

强鉴权 + RBAC（read 列模型 / execute 生成）+ 审计。

## 六、与短剧工作流衔接

节点链：需求解析 → 钩子结构 → 分镜 → 角色一致性 → 关键帧(image provider) → 视频(video provider) → 人工审核导出。

- 关键帧节点：`MediaKind.image` + `text_to_image` / `image_to_image`（角色一致性用 reference_images + 固定 seed）
- 视频节点：`MediaKind.video` + `text_to_video` / `image_to_video`（关键帧图驱动）
- 异步任务进度回写 workflow timeline（Temporal 事件桥接）

> lite 默认 NullProvider，无需任何 key 即可走完短剧工作流草稿（产物为占位）。

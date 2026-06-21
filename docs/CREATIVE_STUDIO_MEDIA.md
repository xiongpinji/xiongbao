# 短剧工厂 · 媒体生成设计（参考 LibLib / LibTV）

> 决策：媒体（图像 / 视频 / 音频）生成**不自托管 ComfyUI**，改为参考 **LibLib（liblib.art）/ LibTV（liblib.tv）** 的云端 AI 创作平台模式，通过**可插拔的云生成 API provider** 实现。这样既消除 GPL-3.0 许可风险，又对齐国内主流 AI 视频/绘画平台的产品形态。

## 一、LibLib / LibTV 模式要点（对标参考）

| 维度 | 平台做法 | X-Agent 借鉴 |
|---|---|---|
| 生成形态 | 云端在线生成，不需本地 GPU | provider 走 HTTP API，提交任务 + 轮询/回调取结果 |
| 模型选择 | Checkpoint + LoRA 组合，模型市场按 versionUuid 引用 | provider 支持 `model_id` / `lora` 参数，内置模型目录 |
| 能力类型 | 文生图 / 图生图 / 文生视频 / 图生视频 / 在线工作流 | 抽象为 `image` / `video` / `audio` 能力，统一任务接口 |
| 视频模型 | 接入 Seedance 等视频大模型 | provider 可声明支持的 `media_kind` 与时长/分辨率上限 |
| 异步性 | 生成任务排队，需轮询状态 | 统一 `submit() -> task_id` + `poll(task_id) -> status/result` |
| 开发者接入 | 开放平台 API（鉴权 + 签名） | provider 持有自己的 key/签名逻辑，配置在 settings |

## 二、抽象接口（`domains/creative_studio/media/base.py`，Phase 3 落地）

沿用旧仓 `MediaProviderRegistry` 的依赖注入思路，但 provider 协议改为「云任务」语义：

```python
class MediaKind(str, Enum):
    image = "image"
    video = "video"
    audio = "audio"

@dataclass
class GenerationRequest:
    kind: MediaKind
    prompt: str
    model_id: str | None = None          # 选用的模型（checkpoint / 视频模型）
    loras: list[str] = field(default_factory=list)
    reference_images: list[str] = field(default_factory=list)  # 图生图/角色一致性
    params: dict[str, Any] = field(default_factory=dict)        # 尺寸/时长/帧率/种子...

@dataclass
class GenerationTask:
    task_id: str
    status: str              # queued | running | succeeded | failed
    outputs: list[str] = field(default_factory=list)  # 产物 URL / 路径
    error: str | None = None

class MediaProvider(Protocol):
    name: str
    supported_kinds: set[MediaKind]
    async def submit(self, req: GenerationRequest) -> GenerationTask: ...
    async def poll(self, task_id: str) -> GenerationTask: ...
    def list_models(self, kind: MediaKind) -> list[ModelCard]: ...
```

## 三、Provider 实现（可插拔）

| Provider | 能力 | 说明 |
|---|---|---|
| `LiblibProvider` | image / video | 对接 LibLib 开放平台 API（文生图 / 图生图 / 视频），按 versionUuid 选模型 + LoRA |
| `GenericVideoProvider` | video | 通用视频生成 API 适配（Seedance / 可灵 / 即梦等，按需配置 endpoint） |
| `OpenAIImageProvider` | image | DALL·E / gpt-image 等（海外场景） |
| `LocalTTSProvider` | audio | faster-whisper(STT) + Piper(TTS)，本地，无版权风险 |
| `NullProvider` | all | lite / 测试：返回占位产物，保证流程不中断（沿用旧仓「确定性回退」思想） |

Provider 由 `MediaProviderRegistry` 据 settings 注册；短剧工厂 `producer` 通过注入的 registry 调度，不感知具体平台。

## 四、与短剧工厂工作流的衔接

旧仓节点链保留：需求解析 → 钩子结构 → 分镜 → 角色一致性 → 关键帧(image provider) → 视频(video provider) → 人工审核导出。

- 关键帧节点调用 `MediaProvider(kind=image)`；视频节点调用 `MediaProvider(kind=video)`。
- 角色一致性通过 `reference_images` + 固定 `loras` / seed 传递。
- 异步任务进度回写到工作流 timeline（与 Temporal 事件桥接，Phase 2/3 衔接）。

## 五、配置（settings 草案，Phase 3 补全）

```
XAGENT_MEDIA__DEFAULT_IMAGE_PROVIDER=liblib
XAGENT_MEDIA__DEFAULT_VIDEO_PROVIDER=liblib
XAGENT_MEDIA__LIBLIB_BASE_URL=...
XAGENT_MEDIA__LIBLIB_ACCESS_KEY=...
XAGENT_MEDIA__LIBLIB_SECRET_KEY=...
XAGENT_MEDIA__POLL_INTERVAL_SECONDS=3
XAGENT_MEDIA__TASK_TIMEOUT_SECONDS=600
```

> lite 模式默认 `NullProvider`，无需任何外部 key 即可走完短剧工作流草稿（仅产物为占位），与 README 单机演示一致。

# X-Agent 短剧商用交付门实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 让短剧测试默认完全离线、状态与产物一致，并生成可下载、可重新打开、可校验摘要且明确标注 provider 等级的本地 ZIP 交付包。

**架构：** `null`、`pollinations` 和 `openai` 三种图像 provider 语义分离，只有显式选择公共/付费 provider 才允许网络路径。生产文档持久化完整时间线快照；交付包构建器只打包生产 JSON、时间线 JSON 和允许根目录内的本地媒体，placeholder/外部 URI 只作为引用记录。API 下载前先做租户校验，ZIP manifest 对每个成员记录 SHA-256。

**技术栈：** FastAPI、pytest-asyncio、SQLAlchemy、Python `zipfile`/`hashlib`、Playwright

---

## 文件结构

- 修改：`apps/api/xagent/infra/settings.py` —— 明确 `null | pollinations | openai` provider 语义。
- 修改：`apps/api/xagent/domains/creative_studio/media/registry.py` —— 默认 null，不隐式访问 Pollinations。
- 修改：`apps/api/tests/test_creative_studio.py`、`apps/api/tests/test_pipeline.py`、`apps/api/tests/test_audio_providers.py` —— 离线 provider、task id、配音、时间线与状态回归。
- 修改：`apps/api/xagent/api/v1/creative_studio.py` —— 持久化时间线快照并提供 tenant-safe bundle 下载。
- 创建：`apps/api/xagent/domains/creative_studio/delivery_bundle.py` —— 安全生成 ZIP 与 manifest。
- 创建：`apps/api/tests/test_creative_delivery_bundle.py` —— ZIP、摘要、路径边界、placeholder 分类、租户隔离和重启恢复测试。
- 创建：`tests/e2e/specs/short-drama-delivery.spec.ts` —— 浏览器上下文中的产出、重开、下载与摘要验证。
- 创建：`scripts/run_short_drama_commercial_gate.ps1`、`tests/release/test_short_drama_gate_script.py` —— 同一 SHA 短剧门。
- 修改：`.github/workflows/ci.yml` —— 短剧门独立命名并上传非敏感测试证据。

### 任务 1：修复默认图像 provider 的隐式联网

**文件：**
- 修改：`apps/api/tests/test_creative_studio.py`
- 修改：`apps/api/xagent/domains/creative_studio/media/registry.py`
- 修改：`apps/api/xagent/infra/settings.py`

- [ ] **步骤 1：编写默认 null 与显式 Pollinations 测试**

```python
def test_registry_image_defaults_to_null(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings.media, "default_image_provider", "null")
    reset_media_registry()
    registry = get_media_registry()
    assert registry.get(MediaKind.image) is registry.null


def test_registry_pollinations_requires_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings.media, "default_image_provider", "pollinations")
    reset_media_registry()
    assert get_media_registry().get(MediaKind.image).name == "pollinations"


def test_openai_without_key_falls_back_to_null(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings.media, "default_image_provider", "openai")
    monkeypatch.setattr(settings.media, "openai_image_api_key", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    reset_media_registry()
    assert get_media_registry().get(MediaKind.image) is get_media_registry().null
```

- [ ] **步骤 2：运行测试确认默认错误注册 Pollinations**

运行：`python -m pytest apps/api/tests/test_creative_studio.py -q`

预期：至少 `test_registry_image_defaults_to_null` FAIL，实际 provider 为 `pollinations`。

- [ ] **步骤 3：实现显式 provider 分支**

```python
image_provider = cfg.default_image_provider
if image_provider == "openai" and (
    cfg.openai_image_api_key or os.environ.get("OPENAI_API_KEY")
):
    registry.register(
        MediaKind.image,
        OpenAIImageProvider(
            api_key=cfg.openai_image_api_key or os.environ.get("OPENAI_API_KEY", ""),
            base_url=cfg.openai_image_base_url,
            default_model=cfg.openai_image_model,
        ),
    )
elif image_provider == "pollinations":
    registry.register(MediaKind.image, PollinationsProvider())
```

`null` 和 openai 缺 key 均不注册图像 provider，由 `registry.get()` 返回 `NullProvider`。把 `MediaSettings.default_image_provider` 注释改为 `null | pollinations | openai`；不改变默认值 `null`。

- [ ] **步骤 4：验证短剧关键回归**

运行：

```powershell
python -m pytest apps/api/tests/test_creative_studio.py apps/api/tests/test_creative_persistence.py apps/api/tests/test_pipeline.py apps/api/tests/test_audio_providers.py -q
```

预期：此前 `pollinations-err`、常量 task id、`partial`、零 artifacts 和持久化失败全部消失；配音本地时间线测试得到两条 audio clip。

- [ ] **步骤 5：提交 provider 修复**

```bash
git add apps/api/xagent/infra/settings.py apps/api/xagent/domains/creative_studio/media/registry.py apps/api/tests/test_creative_studio.py apps/api/tests/test_pipeline.py apps/api/tests/test_audio_providers.py
git commit -m "fix: keep short drama defaults offline"
```

### 任务 2：持久化完整时间线快照

**文件：**
- 修改：`apps/api/tests/test_creative_studio.py`
- 修改：`apps/api/xagent/api/v1/creative_studio.py`

- [ ] **步骤 1：编写产出与重启恢复测试**

```python
@pytest.mark.asyncio
async def test_production_persists_openable_timeline_after_memory_clear(client: AsyncClient) -> None:
    token = create_access_token(user_id="u", tenant_id="timeline-tenant", roles=["member"])
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.post(
        "/api/v1/creative-studio/produce",
        headers=headers,
        json={"brief": "离线交付测试", "with_video": False},
    )
    assert response.status_code == 200
    produced = response.json()
    assert produced["status"] == "produced"
    assert produced["timeline"]["id"] == produced["timeline_id"]
    assert produced["timeline"]["clips"]

    creative_api._productions.clear()
    creative_persistence.reset_creative_table_cache()
    reopened = await client.get(
        f"/api/v1/creative-studio/productions/{produced['storyboard_id']}",
        headers=headers,
    )
    assert reopened.status_code == 200
    assert reopened.json()["timeline"] == produced["timeline"]
```

- [ ] **步骤 2：运行失败测试**

运行：`python -m pytest apps/api/tests/test_creative_studio.py::test_production_persists_openable_timeline_after_memory_clear -q`

预期：FAIL，产出文档只有 `timeline_id`，没有 `timeline`。

- [ ] **步骤 3：在保存前附加时间线快照**

```python
from xagent.domains.creative_studio.editor.tools import get_timeline


def _attach_timeline_snapshot(doc: dict[str, Any]) -> dict[str, Any]:
    timeline_id = str(doc.get("timeline_id") or "")
    timeline = get_timeline(timeline_id) if timeline_id else None
    doc["timeline"] = timeline.to_dict() if timeline is not None else None
    return doc
```

`produce()` 在加入 `tenant_id`/`owner` 后、写 `_productions` 与 DB 前调用该函数。若 `timeline_id` 存在而 timeline 缺失，把结果状态改为 `partial` 并在顶层 `failures` 追加 `timeline_snapshot_missing`，不返回伪 `produced`。

- [ ] **步骤 4：验证持久化回归**

运行：`python -m pytest apps/api/tests/test_creative_studio.py apps/api/tests/test_creative_persistence.py -q`

预期：全部 PASS；内存清空后仍能取回相同时间线。

- [ ] **步骤 5：提交时间线持久化**

```bash
git add apps/api/xagent/api/v1/creative_studio.py apps/api/tests/test_creative_studio.py
git commit -m "feat: persist short drama timeline snapshots"
```

### 任务 3：实现安全、可校验的短剧 ZIP 交付包

**文件：**
- 创建：`apps/api/xagent/domains/creative_studio/delivery_bundle.py`
- 创建：`apps/api/tests/test_creative_delivery_bundle.py`

- [ ] **步骤 1：编写 ZIP 内容与路径边界测试**

```python
def sample_production(
    *,
    image_outputs: list[str] | None = None,
    audio_outputs: list[str] | None = None,
) -> dict[str, object]:
    return {
        "storyboard_id": "storyboard-test",
        "status": "produced",
        "timeline_id": "timeline-test",
        "timeline": {"id": "timeline-test", "clips": []},
        "shots": [{
            "shot_id": "shot-1",
            "image_outputs": image_outputs or [],
            "video_outputs": [],
            "audio_outputs": audio_outputs or [],
        }],
        "failures": [],
    }


def test_build_bundle_contains_manifest_timeline_and_allowed_media(tmp_path: Path) -> None:
    media = tmp_path / "media" / "voice.wav"
    media.parent.mkdir()
    media.write_bytes(b"RIFF-test-audio")
    production = sample_production(audio_outputs=[str(media)])
    payload = build_delivery_bundle(production, allowed_roots=(tmp_path,))
    with ZipFile(BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert {"manifest.json", "production.json", "timeline.json", "assets/voice.wav"} <= names
        manifest = json.loads(archive.read("manifest.json"))
        entry = next(item for item in manifest["files"] if item["path"] == "assets/voice.wav")
        assert entry["sha256"] == hashlib.sha256(b"RIFF-test-audio").hexdigest()
        assert entry["size_bytes"] == len(b"RIFF-test-audio")


def test_build_bundle_never_reads_outside_allowed_roots(tmp_path: Path) -> None:
    outside = tmp_path.parent / "private.txt"
    outside.write_text("must-not-leak", encoding="utf-8")
    payload = build_delivery_bundle(sample_production(audio_outputs=[str(outside)]), allowed_roots=(tmp_path,))
    with ZipFile(BytesIO(payload)) as archive:
        assert "must-not-leak" not in b"".join(archive.read(name) for name in archive.namelist()).decode("utf-8")
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["references"][0]["classification"] == "outside_allowed_roots"


def test_placeholder_is_declared_as_fixture_not_real_media() -> None:
    payload = build_delivery_bundle(
        sample_production(image_outputs=["placeholder://image/task-1"]),
        allowed_roots=(),
    )
    with ZipFile(BytesIO(payload)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["provider_classification"] == "fixture_local"
        assert manifest["external_provider_acceptance"] == "not_authorized"
```

- [ ] **步骤 2：运行测试确认模块不存在**

运行：`python -m pytest apps/api/tests/test_creative_delivery_bundle.py -q`

预期：FAIL，不能导入 `delivery_bundle`。

- [ ] **步骤 3：实现规范 JSON、摘要和 ZIP**

```python
from collections.abc import Sequence


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _file_entry(path: str, payload: bytes) -> dict[str, object]:
    return {
        "path": path,
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _is_within(path: Path, roots: Sequence[Path]) -> bool:
    resolved = path.resolve(strict=True)
    return any(resolved == root.resolve() or root.resolve() in resolved.parents for root in roots)
```

`build_delivery_bundle(production, allowed_roots)` 先写 `production.json` 和 `timeline.json`；遍历每个 shot 的 `image_outputs`、`video_outputs`、`audio_outputs`。本地普通路径仅在 `_is_within` 为真且是常规文件时写到 `assets/{sha256前12位}-{安全basename}`；HTTP、placeholder、缺失和越界路径只进入 `references`。`manifest.json` 固定包含：

```python
manifest = {
    "schema_version": "1.0",
    "storyboard_id": str(production["storyboard_id"]),
    "production_status": str(production["status"]),
    "provider_classification": "fixture_local" if placeholder_seen else "local_files",
    "external_provider_acceptance": "not_authorized",
    "files": sorted(file_entries, key=lambda item: str(item["path"])),
    "references": references,
    "failures": production.get("failures", []),
}
```

ZIP 每个成员使用固定时间戳 `(1980, 1, 1, 0, 0, 0)`，保证相同输入得到相同摘要。禁止 `../`、绝对 ZIP member 和同名覆盖。

- [ ] **步骤 4：验证 ZIP 可打开且可重复**

运行：`python -m pytest apps/api/tests/test_creative_delivery_bundle.py -q`

预期：全部 PASS；相同输入两次返回完全相同 bytes；越界文件内容不进入 ZIP。

- [ ] **步骤 5：提交 bundle 构建器**

```bash
git add apps/api/xagent/domains/creative_studio/delivery_bundle.py apps/api/tests/test_creative_delivery_bundle.py
git commit -m "feat: build verifiable short drama delivery bundles"
```

### 任务 4：提供租户隔离的下载端点

**文件：**
- 修改：`apps/api/xagent/api/v1/creative_studio.py`
- 修改：`apps/api/tests/test_creative_delivery_bundle.py`

- [ ] **步骤 1：编写 API 下载与隔离测试**

```python
@pytest.mark.asyncio
async def test_bundle_download_reopens_and_is_tenant_isolated(client: AsyncClient) -> None:
    token_a = create_access_token(user_id="a", tenant_id="bundle-a", roles=["member"])
    token_b = create_access_token(user_id="b", tenant_id="bundle-b", roles=["member"])
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    create_response = await client.post(
        "/api/v1/creative-studio/produce",
        headers=headers_a,
        json={"brief": "交付包租户测试", "with_video": False},
    )
    assert create_response.status_code == 200
    produced = create_response.json()
    storyboard_id = produced["storyboard_id"]
    response = await client.get(
        f"/api/v1/creative-studio/productions/{storyboard_id}/bundle",
        headers=headers_a,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    assert f'filename="short-drama-{storyboard_id}.zip"' in response.headers["content-disposition"]
    with ZipFile(BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        assert json.loads(archive.read("production.json"))["storyboard_id"] == storyboard_id

    forbidden = await client.get(
        f"/api/v1/creative-studio/productions/{storyboard_id}/bundle",
        headers=headers_b,
    )
    assert forbidden.status_code == 404
```

- [ ] **步骤 2：运行失败测试**

运行：`python -m pytest apps/api/tests/test_creative_delivery_bundle.py -q`

预期：FAIL，下载路由返回 404。

- [ ] **步骤 3：实现下载端点**

```python
@router.get("/productions/{storyboard_id}/bundle", summary="下载短剧交付包")
async def download_production_bundle(
    storyboard_id: str,
    principal: Principal = Depends(require_permission("creative", "read")),
) -> Response:
    doc = await creative_persistence.load_production(storyboard_id, principal.tenant_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "产物不存在或无权访问")
    payload = build_delivery_bundle(doc, allowed_roots=_creative_delivery_roots())
    return Response(
        payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="short-drama-{storyboard_id}.zip"'},
    )
```

`_creative_delivery_roots()` 只返回 `Path(get_settings().media.tts_output_dir).resolve()` 和 `FS_ALLOWED_ROOTS` 中的非空绝对路径。不得使用用户请求参数扩展 allowlist。

- [ ] **步骤 4：验证下载、重启与租户隔离**

运行：`python -m pytest apps/api/tests/test_creative_delivery_bundle.py apps/api/tests/test_creative_persistence.py apps/api/tests/test_creative_studio.py -q`

预期：全部 PASS；越权返回 404；清空内存后仍能从 DB 下载相同逻辑内容。

- [ ] **步骤 5：提交下载端点**

```bash
git add apps/api/xagent/api/v1/creative_studio.py apps/api/tests/test_creative_delivery_bundle.py
git commit -m "feat: expose tenant safe short drama bundles"
```

### 任务 5：浏览器验证产出、重开、下载和摘要

**文件：**
- 创建：`tests/e2e/specs/short-drama-delivery.spec.ts`

- [ ] **步骤 1：编写 Playwright 端到端测试**

```typescript
const API_BASE = process.env.E2E_API_URL || "http://127.0.0.1:8000";

async function register(
  request: APIRequestContext,
  username: string,
  password: string,
  tenantId: string,
): Promise<string> {
  const response = await request.post(`${API_BASE}/api/v1/auth/register`, {
    data: { username, password, tenant_id: tenantId },
  });
  expect(response.status()).toBe(200);
  return (await response.json()).access_token;
}


test("短剧本地产出可重开并下载校验包", async ({ request }) => {
  const token = await register(request, `short-drama-${Date.now()}`, "pass123456", `tenant-${Date.now()}`);
  const headers = { Authorization: `Bearer ${token}` };
  const produced = await request.post(`${API_BASE}/api/v1/creative-studio/produce`, {
    headers,
    data: { brief: "本地离线交付验收", with_video: false },
    timeout: 180_000,
  });
  expect(produced.status()).toBe(200);
  const doc = await produced.json();
  expect(doc.status).toBe("produced");
  expect(doc.timeline.id).toBe(doc.timeline_id);

  const reopened = await request.get(`${API_BASE}/api/v1/creative-studio/productions/${doc.storyboard_id}`, { headers });
  expect((await reopened.json()).timeline).toEqual(doc.timeline);
  const bundle = await request.get(`${API_BASE}/api/v1/creative-studio/productions/${doc.storyboard_id}/bundle`, { headers });
  expect(bundle.status()).toBe(200);
  const bytes = await bundle.body();
  expect(bytes.subarray(0, 2).toString()).toBe("PK");
  await writeFile(resolve(process.env.E2E_EVIDENCE_DIR!, "short-drama.zip"), bytes);
});
```

同一测试随后用 `adm-zip` 打开下载文件，验证 `manifest.json`、`production.json`、`timeline.json`，逐个重新计算 `manifest.files` 的 SHA-256。把 `adm-zip` 固定到 `tests/e2e/package.json` 并更新 lock。

- [ ] **步骤 2：运行单一短剧浏览器门**

运行：

```powershell
$sha = (git rev-parse HEAD).Trim()
$env:E2E_EVIDENCE_DIR = (Resolve-Path .).Path + "\output\commercial-delivery\$sha\short-drama\browser"
npm --prefix tests/e2e ci
npm --prefix tests/e2e exec -- playwright test specs/short-drama-delivery.spec.ts --reporter=list
```

预期：`1 passed`、零 retry；证据目录含可由 `Expand-Archive` 打开的 `short-drama.zip`。

- [ ] **步骤 3：提交浏览器验收**

```bash
git add tests/e2e/specs/short-drama-delivery.spec.ts tests/e2e/package.json tests/e2e/package-lock.json
git commit -m "test: verify short drama delivery download in browser"
```

### 任务 6：建立短剧独立门与证据

**文件：**
- 创建：`scripts/run_short_drama_commercial_gate.ps1`
- 创建：`tests/release/test_short_drama_gate_script.py`
- 修改：`.github/workflows/ci.yml`

- [ ] **步骤 1：编写门脚本合同**

```python
def test_short_drama_gate_is_offline_by_default() -> None:
    text = (ROOT / "scripts/run_short_drama_commercial_gate.ps1").read_text(encoding="utf-8")
    assert "XAGENT_MEDIA__DEFAULT_IMAGE_PROVIDER='null'" in text
    assert "XAGENT_MEDIA__DEFAULT_VIDEO_PROVIDER='null'" in text
    assert "short-drama-delivery.spec.ts" in text
    assert '"external_provider_acceptance": "not_authorized"' in text
    assert "pollinations.ai" not in text
```

- [ ] **步骤 2：实现并解析门脚本**

脚本从干净工作树读取 `source_sha`，设置三个 media provider 为 null，运行短剧相关单元/集成测试、整仓后端 runner、Compose API、短剧 Playwright 和 ZIP 摘要复核；成功时写 `output/commercial-delivery/$sourceSha/short-drama/gate.json`：

```json
{
  "gate": "short_drama",
  "source_sha": "由脚本读取的四十位 Git SHA",
  "status": "passed",
  "provider_classification": "fixture_local",
  "external_provider_acceptance": "not_authorized",
  "paid_submission_attempted": false
}
```

任何外部 provider 路径出现、ZIP 摘要不一致、`partial`/`blocked`、pytest failed 或 Playwright retry 都使脚本退出 `1`。

- [ ] **步骤 3：验证脚本与 CI YAML**

运行：

```powershell
python -m pytest tests/release/test_short_drama_gate_script.py -q
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml', encoding='utf-8')); print('ci yaml ok')"
```

预期：PASS。CI 新增 `short-drama` job，运行离线测试与 bundle 单元测试；不在 CI 调用 Pollinations/OpenAI/Kling/即梦/火山等外部生成服务。

- [ ] **步骤 4：提交独立门**

```bash
git add scripts/run_short_drama_commercial_gate.ps1 tests/release/test_short_drama_gate_script.py .github/workflows/ci.yml
git commit -m "ci: add independent short drama delivery gate"
```

- [ ] **步骤 5：运行实际短剧门**

运行：`pwsh -NoProfile -File scripts/run_short_drama_commercial_gate.ps1`

预期：退出码 `0`；同一 SHA 的短剧 `gate.json` 为 `passed`，ZIP 可打开且摘要全部一致。结果只能标记 `fixture_local`；在获得付费价格、余额和一次提交授权前，不执行真实外部图像/视频调用。

## 本计划完成判定

默认测试无公共网络请求；短剧相关测试及整仓测试通过；状态为 `produced/ready`；产物重启后可重开；ZIP 含 production、timeline、引用、失败记录、审计元数据和文件摘要；浏览器实际下载并复核 ZIP；付费 provider 保持 `not_authorized` 且没有提交记录。

# X-Agent 同一 SHA 证据与回滚实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 用机器可验证清单证明五个门都来自同一干净 SHA，并在两个独立 Compose 项目中实际完成备份、恢复、升级、应用回滚和数据完整性复核。

**架构：** 每个门写相同最小 schema 的 `gate.json`，聚合器重新计算制品摘要并拒绝缺门、dirty、SHA 漂移、命令失败或授权越界。备份脚本输出带 SHA/project/collection 的 manifest；恢复永远写入新的 `xagent-restore-*` 项目和不存在的 collection，不删除已有 collection。应用回滚仅切换带本轮 Compose project label 的 API/worker/web 候选，不触碰现有项目或生产。

**技术栈：** Python 3.11、pytest、Docker Compose、Postgres pg_dump/pg_restore、Qdrant snapshots、Git worktree、PowerShell、JSON/SHA-256

---

## 文件结构

- 创建：`scripts/commercial_delivery_gate.py`、`tests/release/test_commercial_delivery_gate.py` —— 五门同 SHA 聚合和最终分类。
- 创建：`scripts/gate_evidence.py`、`tests/release/test_gate_evidence.py` —— gate schema、命令记录与 artifact 摘要共享函数。
- 修改：`scripts/backup.py`、`scripts/restore.py` —— 显式 project/collection/scope、安全 manifest、无隐式删除。
- 创建：`tests/release/test_backup_restore_safety.py` —— 备份恢复安全边界。
- 创建：`scripts/run_rollback_drill.ps1`、`tests/release/test_rollback_drill_script.py` —— 隔离备份恢复与候选回滚演练。
- 创建：`docs/release/commercial-delivery-evidence.md` —— 本地候选人类可读报告格式和三层证据边界。
- 修改：`scripts/run_commercial_kernel_gate.ps1`、`scripts/run_webapi_commercial_gate.ps1`、`scripts/run_short_drama_commercial_gate.ps1`、`scripts/run_desktop_commercial_gate.ps1` —— 统一 schema。
- 修改：`.github/workflows/ci.yml` —— 下载各 job 证据并在同一 `github.sha` 聚合，正式发布仍需独立授权。

### 任务 1：定义统一 gate 证据 schema

**文件：**
- 创建：`scripts/gate_evidence.py`
- 创建：`tests/release/test_gate_evidence.py`

- [ ] **步骤 1：编写 schema 与摘要测试**

```python
def test_build_gate_evidence_records_source_and_commands(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.zip"
    artifact.write_bytes(b"delivery")
    evidence = build_gate_evidence(
        gate="webapi",
        repository="xagent",
        branch="codex/commercial-delivery-20260815",
        source_sha="a" * 40,
        dirty=False,
        started_at="2026-08-15T00:00:00Z",
        finished_at="2026-08-15T00:10:00Z",
        tools={"python": "3.11.9"},
        commands=[CommandEvidence(command="python -m pytest", exit_code=0, passed=10, failed=0, skipped=0)],
        artifacts=[artifact],
        evidence_root=tmp_path,
        classification="candidate_local",
    )
    assert evidence["source_sha"] == "a" * 40
    assert evidence["commands"][0]["exit_code"] == 0
    assert evidence["artifacts"][0]["sha256"] == hashlib.sha256(b"delivery").hexdigest()


def test_invalid_gate_or_sha_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="source_sha"):
        build_gate_evidence(
            gate="unknown", repository="xagent", branch="main", source_sha="short",
            dirty=False, started_at="2026-08-15T00:00:00Z", finished_at="2026-08-15T00:01:00Z",
            tools={}, commands=[], artifacts=[], evidence_root=tmp_path,
            classification="candidate_local",
        )
```

- [ ] **步骤 2：运行测试确认模块不存在**

运行：`python -m pytest tests/release/test_gate_evidence.py -q`

预期：FAIL，`scripts.gate_evidence` 不存在。

- [ ] **步骤 3：实现固定 schema**

```python
ALLOWED_GATES = frozenset({"commercial_kernel", "webapi", "short_drama", "desktop", "rollback"})
SHA_PATTERN = re.compile(r"^[a-f0-9]{40}$")


@dataclass(frozen=True)
class CommandEvidence:
    command: str
    exit_code: int
    passed: int = 0
    failed: int = 0
    skipped: int = 0


def artifact_evidence(path: Path, evidence_root: Path) -> dict[str, object]:
    resolved = path.resolve(strict=True)
    root = evidence_root.resolve(strict=True)
    if root not in resolved.parents:
        raise ValueError("artifact must be inside evidence root")
    payload = resolved.read_bytes()
    return {
        "path": resolved.relative_to(root).as_posix(),
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
```

`build_gate_evidence` 拒绝未知 gate、非 40 位 SHA、dirty、空 commands、任一非零 exit code/failed、结束早于开始。输出字段固定为：`schema_version`、`gate`、`repository`、`branch`、`source_sha`、`dirty`、`started_at`、`finished_at`、`tools`、`environment`、`commands`、`artifacts`、`status`、`classification`、`authorizations`。`authorizations` 默认四项均为 `not_authorized`。

- [ ] **步骤 4：验证 schema**

运行：`python -m pytest tests/release/test_gate_evidence.py -q`

预期：PASS；生成 JSON 中无环境变量值、token、URL credential 或 secret。

- [ ] **步骤 5：提交证据 schema**

```bash
git add scripts/gate_evidence.py tests/release/test_gate_evidence.py
git commit -m "feat: define commercial gate evidence schema"
```

### 任务 2：统一五门脚本输出

**文件：**
- 创建：`scripts/run_commercial_kernel_gate.ps1`
- 修改：`scripts/run_webapi_commercial_gate.ps1`
- 修改：`scripts/run_short_drama_commercial_gate.ps1`
- 修改：`scripts/run_desktop_commercial_gate.ps1`
- 创建：`tests/release/test_gate_script_schema.py`

- [ ] **步骤 1：编写五门脚本合同测试**

```python
@pytest.mark.parametrize("script,gate", [
    ("run_commercial_kernel_gate.ps1", "commercial_kernel"),
    ("run_webapi_commercial_gate.ps1", "webapi"),
    ("run_short_drama_commercial_gate.ps1", "short_drama"),
    ("run_desktop_commercial_gate.ps1", "desktop"),
])
def test_gate_script_writes_shared_schema(script: str, gate: str) -> None:
    text = (ROOT / "scripts" / script).read_text(encoding="utf-8")
    assert "gate_evidence.py" in text
    assert gate in text
    assert "source_sha" in text
    assert "commands" in text
    assert "artifacts" in text
    assert "not_authorized" in text
```

- [ ] **步骤 2：实现共享 JSON 输入约定**

每个 PowerShell 门把自身命令记录写入 `commands.raw.json`，格式：

```json
[
  {
    "command": "python scripts/verify_release_versions.py --tag v1.1.3",
    "exit_code": 0,
    "passed": 1,
    "failed": 0,
    "skipped": 0
  }
]
```

脚本成功末尾调用：

```powershell
python "$RepoRoot\scripts\gate_evidence.py" build `
  --gate $gate `
  --repo-root $RepoRoot `
  --source-sha $sourceSha `
  --started-at $startedAt `
  --commands "$evidence\commands.raw.json" `
  --artifacts-root $evidence `
  --output "$evidence\gate.json"
```

kernel 门顺序执行版本、Windows preflight、secret、security、dependency audit、container/Helm tests；任何失败不写 `passed` gate。门脚本只允许清洗后的工具版本和运行环境摘要，不序列化完整 environment。

- [ ] **步骤 3：验证四门脚本可解析**

运行：

```powershell
python -m pytest tests/release/test_gate_script_schema.py -q
Get-ChildItem scripts\run_*commercial_gate.ps1 | ForEach-Object {
  $tokens = $null; $errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$errors) > $null
  if ($errors) { throw ($errors | Out-String) }
}
```

预期：测试 PASS，四个脚本无语法错误。

- [ ] **步骤 4：提交统一门输出**

```bash
git add scripts/run_commercial_kernel_gate.ps1 scripts/run_webapi_commercial_gate.ps1 scripts/run_short_drama_commercial_gate.ps1 scripts/run_desktop_commercial_gate.ps1 tests/release/test_gate_script_schema.py
git commit -m "test: standardize commercial gate evidence"
```

### 任务 3：修复备份脚本的范围和可验证性

**文件：**
- 修改：`scripts/backup.py`
- 创建：`tests/release/test_backup_restore_safety.py`

- [ ] **步骤 1：编写备份范围与 manifest 测试**

```python
def test_backup_manifest_binds_project_collection_and_sha(tmp_path: Path) -> None:
    artifact = tmp_path / "postgres.dump"
    artifact.write_bytes(b"pg")
    manifest = build_backup_manifest(
        output_root=tmp_path,
        compose_project="xagent-commercial-a1b2c3d4",
        source_sha="a" * 40,
        qdrant_collection="xagent_memory_a1b2c3d4",
        artifacts=[artifact],
    )
    assert manifest["compose_project"] == "xagent-commercial-a1b2c3d4"
    assert manifest["qdrant_collection"] == "xagent_memory_a1b2c3d4"
    assert manifest["artifacts"][0]["sha256"] == hashlib.sha256(b"pg").hexdigest()


def test_backup_rejects_generic_project_and_collection(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        validate_scope("xagent-r2", "xagent_memory", "a" * 40, tmp_path)
```

- [ ] **步骤 2：运行测试确认现有脚本无 scope**

运行：`python -m pytest tests/release/test_backup_restore_safety.py -q`

预期：FAIL，`build_backup_manifest` 和 `validate_scope` 不存在。

- [ ] **步骤 3：实现显式 scope 和 hash manifest**

`backup.py` 新增必填参数：`--compose-project` 必须匹配 `^xagent-commercial-[a-f0-9]{8}$`，`--source-sha` 必须为 40 位，`--qdrant-collection` 必须等于 `f"xagent_memory_{source_sha[:8]}"`，`--output` resolve 后必须位于 `repo / "output" / "commercial-delivery" / source_sha / "rollback"` 下。Postgres 改用：

```python
subprocess.run(
    ["pg_dump", "--format=custom", "--no-owner", "--no-privileges", pg_url, "--file", str(path)],
    check=True,
    capture_output=True,
)
```

Qdrant 所有 URL 使用显式 collection。删除 `_cleanup_old_backups` 调用；该门不替用户执行留存删除。完成后写 `backup-manifest.json`，对 Postgres dump、Qdrant snapshot、audit export和短剧 ZIP逐个记录相对路径、大小、SHA-256。

- [ ] **步骤 4：验证备份单元测试**

运行：`python -m pytest tests/release/test_backup_restore_safety.py -q`

预期：PASS；输出目录越界、generic collection 或 project 名不匹配均在任何 subprocess/HTTP 调用前失败。

- [ ] **步骤 5：提交安全备份**

```bash
git add scripts/backup.py tests/release/test_backup_restore_safety.py
git commit -m "fix: scope backup artifacts to commercial drill"
```

### 任务 4：把恢复限制到新的空目标

**文件：**
- 修改：`scripts/restore.py`
- 修改：`tests/release/test_backup_restore_safety.py`

- [ ] **步骤 1：编写禁止删除与新目标测试**

```python
def test_restore_requires_new_restore_project_and_collection() -> None:
    scope = validate_restore_scope(
        compose_project="xagent-restore-a1b2c3d4",
        qdrant_collection="xagent_restore_a1b2c3d4",
        source_sha="a" * 40,
    )
    assert scope.compose_project == "xagent-restore-a1b2c3d4"
    assert scope.qdrant_collection == "xagent_restore_a1b2c3d4"


def test_restore_source_has_no_qdrant_delete_call() -> None:
    source = (ROOT / "scripts/restore.py").read_text(encoding="utf-8")
    assert "httpx.delete" not in source
    assert "DELETE" not in source
```

- [ ] **步骤 2：运行测试确认现有恢复会删除 collection**

运行：`python -m pytest tests/release/test_backup_restore_safety.py -q`

预期：FAIL，当前 `restore.py` 包含 `httpx.delete` 且没有 scope 验证。

- [ ] **步骤 3：实现新项目/新 collection 恢复**

CLI 只接受 `--manifest backup-manifest.json`、`--target-project "xagent-restore-$sha8"`、`--target-pg-url`、`--target-qdrant-url`、`--target-qdrant-collection "xagent_restore_$sha8"`，其中 `$sha8 = $sourceSha.Substring(0, 8)`。先重新计算 manifest 内所有 hash；再确认：

1. `docker compose -p $targetProject -f deploy/compose/docker-compose.yml ps` 返回的所有容器 label `com.docker.compose.project` 都等于 `$targetProject`；
2. target Postgres 除系统 schema 外没有业务表；
3. target Qdrant collection 不存在。

Postgres 使用参数数组 `pg_restore --exit-on-error --no-owner --no-privileges --dbname $targetPgUrl $dumpPath`。Qdrant只对新 collection执行 create 和 snapshot upload；如果 collection 已存在立即失败，不删除、不覆盖。恢复后写 `restore-manifest.json`，记录 source backup hash、target project/collection、命令退出码和完成时间。

- [ ] **步骤 4：验证恢复单元测试**

运行：`python -m pytest tests/release/test_backup_restore_safety.py -q`

预期：PASS；source 不包含任何 Qdrant DELETE；已有表/collection、hash 不一致、label 不一致都 fail-closed。

- [ ] **步骤 5：提交安全恢复**

```bash
git add scripts/restore.py tests/release/test_backup_restore_safety.py
git commit -m "fix: restore only into isolated empty targets"
```

### 任务 5：实现隔离升级与应用回滚演练

**文件：**
- 创建：`scripts/run_rollback_drill.ps1`
- 创建：`tests/release/test_rollback_drill_script.py`

- [ ] **步骤 1：编写危险操作与范围合同**

```python
def test_rollback_drill_uses_only_audited_projects() -> None:
    text = (ROOT / "scripts/run_rollback_drill.ps1").read_text(encoding="utf-8")
    assert "xagent-commercial-" in text
    assert "xagent-restore-" in text
    assert "com.docker.compose.project" in text
    assert "backup-manifest.json" in text
    assert "restore-manifest.json" in text
    assert "docker volume rm" not in text
    assert "docker system prune" not in text
    assert "Remove-Item -Recurse" not in text
    assert "production" not in text.lower()
```

- [ ] **步骤 2：实现 preflight 和 test data**

脚本先要求 Windows 本地、干净工作树、40 位 source SHA、Docker engine healthy。设置 `$sha8 = $sourceSha.Substring(0, 8)`、`$candidateProject = "xagent-commercial-$sha8"`、`$restoreProject = "xagent-restore-$sha8"`；对每个已运行容器执行 `docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}'` 并精确匹配。候选 collection 设置为 `"xagent_memory_$sha8"`，恢复 collection 设置为 `"xagent_restore_$sha8"`。

通过 API 创建两个租户，各写带 nonce 的 memory、调度任务和短剧 production；下载短剧 ZIP并记录 SHA。查询 `/api/v1/audit/verify` 确认链通过。所有测试 ID 都以 PowerShell 字符串 `"rollback-$sha8-"` 开头。

- [ ] **步骤 3：实际备份并恢复到第二项目**

调用新版 `backup.py` 生成 manifest；启动空 restore Compose 项目（使用独立 ports override 和独立 volumes），再调用 `restore.py`。restore API 启动后验证：两个租户仍只能看到各自数据；memory nonce、scheduler、短剧 production 和 ZIP摘要一致；`/api/v1/audit/verify` 通过；Postgres 行数、Qdrant points count 和 artifact hash 与备份清单一致。

- [ ] **步骤 4：构建基线和当前候选并执行应用回滚**

基线 commit 固定为本计划开始基线 `c87aab2b706c443bc4b92fb00aba8d65c986bd0f`。脚本设置 `$baseWorktree = Join-Path $RepoRoot ".worktrees\rollback-base-$sha8"`，运行参数数组 `git -C $RepoRoot worktree add --detach $baseWorktree c87aab2b706c443bc4b92fb00aba8d65c986bd0f`，构建 `"xagent-api:rollback-base-$sha8"` 与 `"xagent-web:rollback-base-$sha8"`；当前 SHA 构建 `"xagent-api:rollback-current-$sha8"` 与 `"xagent-web:rollback-current-$sha8"`。所有镜像读取并记录 immutable digest。

在 restore 项目先以 baseline images 健康启动并读取已恢复数据，再用 override 切到 current digests、运行 `alembic upgrade head`、验证核心链；最后用 override 切回 baseline digests，不回退数据库破坏性迁移，验证健康、租户隔离、ZIP和审计连续。仅对 label 匹配 restore 项目的 `api`、`worker`、`web` 执行 `up -d --no-deps --no-build`。

临时 worktree 用 `git -C $RepoRoot worktree remove $baseWorktree` 清理前，先 resolve 并确认 `$baseWorktree` 的父目录精确等于 repo `.worktrees`；不使用递归文件删除。

- [ ] **步骤 5：生成 rollback gate**

成功时通过 `gate_evidence.py` 写 PowerShell 路径 `output/commercial-delivery/$sourceSha/rollback/gate.json`，classification `candidate_local`，artifacts 包含 backup/restore manifests、两个短剧 ZIP、镜像 digest 清单、升级和回滚健康日志。任一数据摘要或租户隔离不一致则 status 为 failed 且脚本退出 `1`。

- [ ] **步骤 6：验证脚本与提交**

运行：

```powershell
python -m pytest tests/release/test_rollback_drill_script.py tests/release/test_backup_restore_safety.py -q
pwsh -NoProfile -Command '$errors=$null; [System.Management.Automation.Language.Parser]::ParseFile("scripts/run_rollback_drill.ps1", [ref]$null, [ref]$errors) > $null; if ($errors) { $errors | Out-String | Write-Error }'
```

预期：PASS。

```bash
git add scripts/run_rollback_drill.ps1 tests/release/test_rollback_drill_script.py
git commit -m "test: add isolated backup restore and rollback drill"
```

### 任务 6：实现同一 SHA 聚合器

**文件：**
- 创建：`scripts/commercial_delivery_gate.py`
- 创建：`tests/release/test_commercial_delivery_gate.py`

- [ ] **步骤 1：编写缺门、SHA 漂移和 hash 漂移测试**

```python
def test_verify_requires_all_five_gates(tmp_path: Path) -> None:
    write_gate(tmp_path, "commercial_kernel", "a" * 40)
    with pytest.raises(GateError, match="missing gates"):
        verify_evidence(tmp_path, "a" * 40)


def test_verify_rejects_sha_and_artifact_drift(tmp_path: Path) -> None:
    write_all_gates(tmp_path, "a" * 40)
    gate_path = tmp_path / "desktop" / "gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    gate["source_sha"] = "b" * 40
    gate_path.write_text(json.dumps(gate), encoding="utf-8")
    with pytest.raises(GateError, match="source_sha"):
        verify_evidence(tmp_path, "a" * 40)

    write_all_gates(tmp_path, "a" * 40)
    (tmp_path / "desktop" / "installer.exe").write_bytes(b"tampered")
    with pytest.raises(GateError, match="sha256"):
        verify_evidence(tmp_path, "a" * 40)


def test_verified_local_candidate_does_not_claim_external_release(tmp_path: Path) -> None:
    write_all_gates(tmp_path, "a" * 40)
    result = verify_evidence(tmp_path, "a" * 40)
    assert result["classification"] == "candidate_local"
    assert result["remote_release"] == "not_authorized"
    assert result["production_deployment"] == "not_authorized"
    assert result["customer_production_acceptance"] == "not_authorized"
```

- [ ] **步骤 2：运行测试确认聚合器不存在**

运行：`python -m pytest tests/release/test_commercial_delivery_gate.py -q`

预期：FAIL，模块不存在。

- [ ] **步骤 3：实现五门验证和最终 manifest**

```python
GATE_DIRECTORIES = {
    "commercial_kernel": "kernel",
    "webapi": "webapi",
    "short_drama": "short-drama",
    "desktop": "desktop",
    "rollback": "rollback",
}


def verify_artifact(root: Path, item: Mapping[str, object]) -> None:
    path = (root / str(item["path"])).resolve(strict=True)
    if root.resolve() not in path.parents:
        raise GateError("artifact path escaped evidence root")
    payload = path.read_bytes()
    if len(payload) != int(item["size_bytes"]):
        raise GateError(f"artifact size mismatch: {path.name}")
    if hashlib.sha256(payload).hexdigest() != str(item["sha256"]):
        raise GateError(f"artifact sha256 mismatch: {path.name}")
```

`verify_evidence(root, source_sha)` 读取五个固定目录的 `gate.json`，要求 schema `1.0`、gate 名、repository `xagent`、同一 branch/SHA、dirty false、status passed、非空 commands 且全零失败、artifact 重算一致、授权状态不超界。生成：

```python
{
    "schema_version": "1.0",
    "repository": "xagent",
    "source_sha": source_sha,
    "classification": "candidate_local",
    "gates": {name: "passed" for name in GATE_DIRECTORIES},
    "remote_release": "not_authorized",
    "production_deployment": "not_authorized",
    "paid_provider_acceptance": "not_authorized",
    "customer_production_acceptance": "not_authorized",
}
```

CLI `verify --evidence-root --source-sha --require-clean` 在 `--require-clean` 下同时检查当前 repo HEAD 和 porcelain 为空；成功写 `commercial-delivery-manifest.json` 和 `commercial-delivery-report.md`，任何异常退出 `1`。

- [ ] **步骤 4：验证聚合器**

运行：`python -m pytest tests/release/test_commercial_delivery_gate.py tests/release/test_gate_evidence.py -q`

预期：PASS。

- [ ] **步骤 5：提交聚合器**

```bash
git add scripts/commercial_delivery_gate.py tests/release/test_commercial_delivery_gate.py
git commit -m "feat: verify same SHA commercial delivery evidence"
```

### 任务 7：CI 聚合和人类可读报告边界

**文件：**
- 修改：`.github/workflows/ci.yml`
- 创建：`docs/release/commercial-delivery-evidence.md`

- [ ] **步骤 1：新增 CI 聚合 job**

新增 `commercial-evidence` job，`needs` 为 kernel、backend-commercial、frontend、short-drama、desktop、supply-chain。各 job 的 gate artifact 必须含 `source_sha: ${{ github.sha }}`；聚合 job 下载到固定目录并运行 `commercial_delivery_gate.py verify`。CI 没有本地 installer lifecycle、真实 Ollama 和回滚 drill 时，不创建完整 `candidate_local`，只输出 `ci_component_evidence`；完整本地清单必须来自本轮本地五门。

- [ ] **步骤 2：编写报告模板**

`docs/release/commercial-delivery-evidence.md` 固定包含：候选路径/分支/SHA/dirty、五门结果、命令统计、artifact hash、skip 分类、真实本地模型、浏览器 retry、短剧 provider classification、desktop signature、backup/restore/rollback、四项外部授权。模板明确三层：本地候选、正式发布、客户生产，不允许从前一层推断后一层。

- [ ] **步骤 3：验证 CI YAML 和占位符扫描**

运行：

```powershell
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml', encoding='utf-8')); print('ci yaml ok')"
rg -n '待[定]|TO[D]O|TB[D]|以后[补]|假定已[通过]' docs/release/commercial-delivery-evidence.md
```

预期：YAML 可解析；扫描无匹配。

- [ ] **步骤 4：提交 CI 与报告**

```bash
git add .github/workflows/ci.yml docs/release/commercial-delivery-evidence.md
git commit -m "ci: aggregate commercial evidence without release overclaim"
```

### 任务 8：实际运行备份恢复、回滚和最终聚合

- [ ] **步骤 1：在干净最终 SHA 重跑前四门**

运行：

```powershell
pwsh -NoProfile -File scripts/run_commercial_kernel_gate.ps1
pwsh -NoProfile -File scripts/run_webapi_commercial_gate.ps1
pwsh -NoProfile -File scripts/run_short_drama_commercial_gate.ps1
pwsh -NoProfile -File scripts/run_desktop_commercial_gate.ps1
```

预期：四个 gate.json 同 SHA、dirty false、status passed。

- [ ] **步骤 2：运行隔离回滚演练**

运行：`pwsh -NoProfile -File scripts/run_rollback_drill.ps1`

预期：候选与恢复项目 label 精确匹配；备份、恢复、baseline→current→baseline、租户隔离、短剧 ZIP、Qdrant、audit 全部通过；不删除 volumes 或已有 collection。

- [ ] **步骤 3：最终聚合**

运行：

```powershell
$sha = (git rev-parse HEAD).Trim()
python scripts/commercial_delivery_gate.py verify `
  --evidence-root "output/commercial-delivery/$sha" `
  --source-sha $sha `
  --require-clean
```

预期：退出码 `0`，输出 `commercial delivery candidate: candidate_local`；manifest 五门全 passed，四项外部授权仍为 `not_authorized`。

- [ ] **步骤 4：最终泄密、dirty 与证据审计**

运行：

```powershell
git status --porcelain
git diff --check
$sha = (git rev-parse HEAD).Trim()
$manifest = Get-Content -Raw -LiteralPath "output/commercial-delivery/$sha/commercial-delivery-manifest.json" | ConvertFrom-Json
if ($manifest.source_sha -ne $sha -or $manifest.classification -ne 'candidate_local') { throw 'final manifest mismatch' }
rg -n --hidden --glob '!.git/**' --glob '!output/**' '(sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----)' .
```

预期：工作树为空、diff check 通过、manifest 匹配当前 SHA、泄密扫描无匹配。

## 本计划完成判定

五门 schema 与 artifact hash 全部复核通过且同一 SHA；备份恢复和应用回滚在两个带明确 Compose label 的隔离项目中实际执行；测试数据、租户隔离、短剧 ZIP、Qdrant 和 audit 连续；最终只生成 `candidate_local`，没有把远端 Release、签名、生产部署、付费 provider 或客户验收标成已完成。

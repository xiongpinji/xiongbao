# X-Agent Web/API R2 本机隔离 Full Compose 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 把 R1 Web/API 候选放入隔离的单机 Full Compose，在本地真实 Ollama、PostgreSQL、Redis、Qdrant、worker、Web、MCP 和观测链上完成试用、重启、故障、备份与恢复验收。

**架构：** `deploy/compose/docker-compose.yml` 是唯一 R2 编排事实源，默认只启动六个核心服务，扩展服务通过 profile 分层。API 与 worker 共用 `/data` 持久卷，浏览器只访问 `127.0.0.1:18080`，API 只暴露 `127.0.0.1:18000`，真实推理走宿主机 `qwen3:4b`。

**技术栈：** Docker Compose 5、FastAPI/Python 3.11、PostgreSQL 16、Redis 7、Qdrant、Celery、React/Vite/Nginx、Ollama、Playwright、Prometheus、Grafana、Platform MCP。

---

## 文件结构

### 创建

- `apps/api/tests/test_runtime_data_paths.py`：锁定 Skill Store 与完整 Skill Package 的可配置持久化根目录。
- `tests/release/test_r2_compose_contract.py`：不依赖运行中 Docker 的 R2 Compose 静态合同门禁。
- `tests/release/test_r2_preflight.py`：本机环境初始化、秘密校验和无泄漏输出的单元测试。
- `scripts/r2_preflight.py`：跨平台的 env 初始化、配置安全、端口、Docker、Git、Ollama 和 Compose config 预检。
- `scripts/r2-preflight.ps1`：Windows 用户入口，只负责可靠转发参数与退出码。
- `deploy/compose/r2.env.example`：可提交、无真实 secret 的 R2 配置模板。
- `deploy/grafana/provisioning/datasources/prometheus.yml`：自动创建 UID 为 `prometheus` 的同栈数据源。
- `deploy/grafana/provisioning/dashboards/xagent.yml`：自动加载现有 X-Agent dashboard JSON。
- `tests/e2e/specs/webapi-r2-full-compose.spec.ts`：排除短剧的 Full Compose 浏览器/API 同链验收。
- `tests/e2e/fixtures/r2-skill/SKILL.md`：R2 完整技能包主文件。
- `tests/e2e/fixtures/r2-skill/references/checklist.md`：技能包 reference 持久化探针。
- `tests/e2e/fixtures/r2-skill/scripts/verify.py`：技能包脚本文件持久化探针，不在 R2 中执行。
- `tests/e2e/fixtures/r2-skill/assets/badge.txt`：技能包 asset 持久化探针。
- `tests/e2e/fixtures/r2-workspace/README.md`：容器内隔离 Git 验收仓库的种子文件。
- `docs/coordination/reports/WEB_API_R2_STAGING_TRIAL_EVIDENCE.md`：R2 新鲜证据、恢复实例和剩余边界报告。

### 修改

- `apps/api/xagent/core/skills/__init__.py`：让 Skill Store 尊重 `XAGENT_SKILLS_ROOT`。
- `apps/api/xagent/domains/skill_packages/service.py`：让技能包文件尊重 `XAGENT_SKILL_PACKAGES_ROOT`。
- `apps/api/xagent/api/v1/skill_packages.py`：调用运行时解析的技能包根目录，避免模块导入时固定旧路径。
- `deploy/compose/docker-compose.yml`：端口、project、profiles、持久卷、健康依赖和 loopback 绑定。
- `docker-compose.yml`：明确根编排仅供开发兼容，R2 不使用它。
- `.github/workflows/ci.yml`：加入不启动容器的 R2 配置合同门禁。
- `docs/DEPLOYMENT_RUNBOOK.md`：增加 R2 单一入口、预检、启动、停止、恢复与证据命令。
- `docs/coordination/WEB_API_RELEASE_TASK_BOARD.md`：记录 R2-A 至 R2-D 的 CLAIMED/REVIEW/DONE 与证据。
- `.gitignore`：忽略 R2 原始运行日志和本机验收输出，保留显式选取的脱敏截图/报告。

### 不修改

- 短剧、Tauri、E2B、多机 HA 和付费 provider 代码。
- `scripts/backup.py` / `scripts/restore.py`：R2 使用 provider-native 快照和只读 volume 归档，不扩大通用脚本的危险恢复语义。

---

### 任务 1：让技能与技能包文件进入共享持久卷

**文件：**
- 创建：`apps/api/tests/test_runtime_data_paths.py`
- 修改：`apps/api/xagent/core/skills/__init__.py:15-24,145-155`
- 修改：`apps/api/xagent/domains/skill_packages/service.py:13-30`
- 修改：`apps/api/xagent/api/v1/skill_packages.py:13-29,61-91`

- [ ] **步骤 1：编写失败的路径测试**

```python
from pathlib import Path

from xagent.core.skills import SkillStore
from xagent.domains.skill_packages.service import default_packages_root


def test_skill_store_uses_configured_root(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "skills"
    monkeypatch.setenv("XAGENT_SKILLS_ROOT", str(root))
    store = SkillStore()
    assert store._dir == root


def test_skill_package_root_uses_configured_root(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "skill-packages"
    monkeypatch.setenv("XAGENT_SKILL_PACKAGES_ROOT", str(root))
    assert default_packages_root() == root
```

- [ ] **步骤 2：运行测试并确认旧代码失败**

运行：`cd apps/api; pytest tests/test_runtime_data_paths.py -q`

预期：两个测试失败；一个仍使用项目 `data/skills`，另一个无法导入 `default_packages_root`。

- [ ] **步骤 3：实现最小的环境路径解析**

在 `core/skills/__init__.py` 增加：

```python
import os


def default_skills_root() -> Path:
    configured = os.environ.get("XAGENT_SKILLS_ROOT", "").strip()
    return Path(configured).expanduser() if configured else _PROJECT_ROOT / "data" / "skills"
```

并把 `SkillStore.__init__` 的第一行改为：

```python
base = storage_dir or default_skills_root()
```

在 `domains/skill_packages/service.py` 增加：

```python
import os


def default_packages_root() -> Path:
    configured = os.environ.get("XAGENT_SKILL_PACKAGES_ROOT", "").strip()
    return (
        Path(configured).expanduser()
        if configured
        else _PROJECT_ROOT / "data" / "skill-packages"
    )
```

删除模块级 `DEFAULT_PACKAGES_ROOT`；所有函数的 `packages_root` 默认值改为 `None`，函数入口用 `packages_root = packages_root or default_packages_root()`。API 导入端点直接传 `default_packages_root()`，避免环境变量在测试/进程初始化后失效。

- [ ] **步骤 4：运行定向与既有技能包测试**

运行：

```powershell
cd apps/api
pytest tests/test_runtime_data_paths.py tests/test_skill_packages.py tests/test_skill_packages_api.py -q
```

预期：全部 PASS，且临时目录外没有新增技能文件。

- [ ] **步骤 5：提交持久化路径改动**

```powershell
git add apps/api/xagent/core/skills/__init__.py apps/api/xagent/domains/skill_packages/service.py apps/api/xagent/api/v1/skill_packages.py apps/api/tests/test_runtime_data_paths.py
git commit -m "fix(存储): 持久化 Full 模式技能文件"
```

---

### 任务 2：用失败合同锁定 R2 Compose 结构

**文件：**
- 创建：`tests/release/test_r2_compose_contract.py`
- 修改：`deploy/compose/docker-compose.yml:1-280`
- 创建：`deploy/compose/r2.env.example`
- 修改：`docker-compose.yml:1-12`

- [ ] **步骤 1：创建静态 Compose 合同测试**

```python
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = (ROOT / "deploy/compose/docker-compose.yml").read_text(encoding="utf-8")
ENV = (ROOT / "deploy/compose/r2.env.example").read_text(encoding="utf-8")


class R2ComposeContractTest(unittest.TestCase):
    def test_project_and_ports_are_isolated(self) -> None:
        self.assertIn("name: ${COMPOSE_PROJECT_NAME:-xagent-r2}", COMPOSE)
        for name in (
            "XAGENT_POSTGRES_PORT", "XAGENT_REDIS_PORT", "XAGENT_QDRANT_HTTP_PORT",
            "XAGENT_QDRANT_GRPC_PORT", "XAGENT_API_PORT", "XAGENT_WEB_PORT",
            "XAGENT_CONTEXTFORGE_PORT", "XAGENT_OPENFGA_PORT", "XAGENT_LITELLM_PORT",
            "XAGENT_LANGFUSE_PORT", "XAGENT_MCP_PORT", "XAGENT_PROMETHEUS_PORT",
            "XAGENT_GRAFANA_PORT",
        ):
            self.assertIn(name, COMPOSE)
        self.assertNotIn('"8000:8000"', COMPOSE)
        self.assertNotIn('"3000:80"', COMPOSE)

    def test_default_core_and_optional_profiles(self) -> None:
        self.assertIn('profiles: ["gateway"]', COMPOSE)
        self.assertIn('profiles: ["tracing"]', COMPOSE)
        self.assertGreaterEqual(COMPOSE.count('profiles: ["federation"]'), 2)
        self.assertGreaterEqual(COMPOSE.count('profiles: ["observability"]'), 2)
        self.assertIn('profiles: ["mcp"]', COMPOSE)

    def test_shared_runtime_data_is_explicit(self) -> None:
        self.assertGreaterEqual(COMPOSE.count("xagentdata:/data"), 2)
        for setting in (
            "XAGENT_WORKSPACE=/data/workspace",
            "XAGENT_STORAGE__LOCAL_ROOT=/data/storage",
            "XAGENT_SKILLS_ROOT=/data/skills",
            "XAGENT_SKILL_PACKAGES_ROOT=/data/skill-packages",
        ):
            self.assertGreaterEqual(COMPOSE.count(setting), 2)
        self.assertNotIn("docker.sock", COMPOSE)

    def test_health_dependencies_cover_deep_health_and_worker(self) -> None:
        self.assertIn("/health/deep", COMPOSE)
        self.assertIn("inspect ping", COMPOSE)
        self.assertIn("condition: service_healthy", COMPOSE)

    def test_r2_template_contains_no_real_secret(self) -> None:
        self.assertIn("POSTGRES_PASSWORD=__GENERATE__", ENV)
        self.assertIn("XAGENT_SECURITY__JWT_SECRET=__GENERATE__", ENV)
        self.assertIn('XAGENT_CORS_ORIGINS=["http://127.0.0.1:18080"]', ENV)
        self.assertNotIn("admin/admin", ENV)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **步骤 2：运行合同并确认失败**

运行：`python -m unittest discover -s tests/release -p "test_r2_compose_contract.py" -v`

预期：FAIL，至少报告 `r2.env.example` 不存在、固定端口或缺少 profile/volume。

- [ ] **步骤 3：参数化 project、端口和核心数据库名**

把 Compose 顶层和端口改成以下合同：

```yaml
name: ${COMPOSE_PROJECT_NAME:-xagent-r2}

services:
  postgres:
    ports:
      - "${XAGENT_BIND_ADDRESS:-127.0.0.1}:${XAGENT_POSTGRES_PORT:-15432}:5432"
  redis:
    ports:
      - "${XAGENT_BIND_ADDRESS:-127.0.0.1}:${XAGENT_REDIS_PORT:-16379}:6379"
  qdrant:
    ports:
      - "${XAGENT_BIND_ADDRESS:-127.0.0.1}:${XAGENT_QDRANT_HTTP_PORT:-16333}:6333"
      - "${XAGENT_BIND_ADDRESS:-127.0.0.1}:${XAGENT_QDRANT_GRPC_PORT:-16334}:6334"
  api:
    ports:
      - "${XAGENT_BIND_ADDRESS:-127.0.0.1}:${XAGENT_API_PORT:-18000}:8000"
  web:
    ports:
      - "${XAGENT_BIND_ADDRESS:-127.0.0.1}:${XAGENT_WEB_PORT:-18080}:80"
```

所有 API/worker/Postgres URL 使用 `${POSTGRES_DB:-xagent}`，不再硬编码数据库名。

可选服务也只能绑定 loopback，并使用下列宿主端口变量：ContextForge `XAGENT_CONTEXTFORGE_PORT`、OpenFGA `XAGENT_OPENFGA_PORT`、LiteLLM `XAGENT_LITELLM_PORT`、Langfuse `XAGENT_LANGFUSE_PORT`、Platform MCP `XAGENT_MCP_PORT`、Prometheus `XAGENT_PROMETHEUS_PORT`、Grafana `XAGENT_GRAFANA_PORT`。

因为 Compose 会在 profile 筛选前插值整份文件，Langfuse 的三个 profile-only secret 改为 `${LANGFUSE_NEXTAUTH_SECRET:-}`、`${LANGFUSE_SALT:-}`、`${LANGFUSE_INIT_USER_PASSWORD:-}`；R2 不启用 tracing，不能让未启用服务阻断核心 config。JWT 与 PostgreSQL secret 仍保持核心必填。

- [ ] **步骤 4：分层扩展服务并加入共享卷**

为服务增加：

```yaml
contextforge:
  profiles: ["federation"]
openfga:
  profiles: ["federation"]
litellm:
  profiles: ["gateway"]
langfuse:
  profiles: ["tracing"]
platform-mcp:
  profiles: ["mcp"]
prometheus:
  profiles: ["observability"]
grafana:
  profiles: ["observability"]
```

API 与 worker 同时增加：

```yaml
environment:
  - XAGENT_WORKSPACE=/data/workspace
  - XAGENT_STORAGE__LOCAL_ROOT=/data/storage
  - XAGENT_SKILLS_ROOT=/data/skills
  - XAGENT_SKILL_PACKAGES_ROOT=/data/skill-packages
volumes:
  - xagentdata:/data
```

底部增加 `xagentdata:`；不得挂载 Docker Socket。

- [ ] **步骤 5：收紧健康依赖**

API 健康检查解析 deep health：

```yaml
healthcheck:
  test:
    - CMD
    - python
    - -c
    - "import httpx; r=httpx.get('http://localhost:8000/health/deep', timeout=5); raise SystemExit(0 if r.status_code == 200 and r.json().get('status') == 'healthy' else 1)"
```

worker 健康检查：

```yaml
healthcheck:
  test: ["CMD-SHELL", "celery -A xagent.worker.celery_app inspect ping --timeout=5 | grep -q pong"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

Qdrant 改为 `condition: service_healthy`；worker 和 web 对 API 使用 `condition: service_healthy`。

- [ ] **步骤 6：创建无 secret 模板并标记根 Compose 用途**

`deploy/compose/r2.env.example` 必须包含：

```dotenv
COMPOSE_PROJECT_NAME=xagent-r2
XAGENT_BIND_ADDRESS=127.0.0.1
XAGENT_POSTGRES_PORT=15432
XAGENT_REDIS_PORT=16379
XAGENT_QDRANT_HTTP_PORT=16333
XAGENT_QDRANT_GRPC_PORT=16334
XAGENT_API_PORT=18000
XAGENT_WEB_PORT=18080
XAGENT_MCP_PORT=18100
XAGENT_PROMETHEUS_PORT=19090
XAGENT_GRAFANA_PORT=13002
XAGENT_CONTEXTFORGE_PORT=18081
XAGENT_OPENFGA_PORT=18082
XAGENT_LITELLM_PORT=14000
XAGENT_LANGFUSE_PORT=13001
POSTGRES_USER=xagent
POSTGRES_PASSWORD=__GENERATE__
POSTGRES_DB=xagent
XAGENT_MODE=full
XAGENT_DEBUG=false
XAGENT_CORS_ORIGINS=["http://127.0.0.1:18080"]
XAGENT_SECURITY__JWT_SECRET=__GENERATE__
XAGENT_SECURITY__REQUIRE_AUTH=true
XAGENT_LLM__OLLAMA_BASE_URL=http://host.docker.internal:11434
XAGENT_LLM__OLLAMA_MODEL=qwen3:4b
XAGENT_LLM__DEFAULT_MODEL=qwen3:4b
XAGENT_TOOLS__ENABLE_SHELL=false
XAGENT_TOOLS__ENABLE_PYTHON_EXEC=false
XAGENT_SANDBOX__BACKEND=disabled
XAGENT_PLATFORM_MCP_TOKEN=__GENERATE__
GRAFANA_ADMIN_PASSWORD=__GENERATE__
```

根 `docker-compose.yml` 文件头增加“开发兼容入口；R2/发布等价运行使用 `deploy/compose/docker-compose.yml`”，不改其服务行为。

- [ ] **步骤 7：运行合同和 Compose 渲染**

运行：

```powershell
python -m unittest discover -s tests/release -p "test_r2_compose_contract.py" -v
$env:POSTGRES_PASSWORD='config-only-postgres-strong-value'
$env:XAGENT_SECURITY__JWT_SECRET='config-only-jwt-secret-at-least-32-characters'
$env:GRAFANA_ADMIN_PASSWORD='config-only-grafana-strong-value'
docker compose -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.example config --quiet
docker compose -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.example config --services
```

预期：合同全部 PASS，Compose config 退出码 0；`config --services` 只列出 `postgres redis qdrant api worker web`。

- [ ] **步骤 8：提交 Compose 合同和实现**

```powershell
git add tests/release/test_r2_compose_contract.py deploy/compose/docker-compose.yml deploy/compose/r2.env.example docker-compose.yml
git commit -m "feat(部署): 隔离 R2 Full Compose 核心栈"
```

---

### 任务 3：生成强 secret 并执行可测试预检

**文件：**
- 创建：`tests/release/test_r2_preflight.py`
- 创建：`scripts/r2_preflight.py`
- 创建：`scripts/r2-preflight.ps1`
- 修改：`.gitignore`

- [ ] **步骤 1：编写 env 初始化和校验失败测试**

```python
from pathlib import Path
import tempfile
import unittest

from scripts.r2_preflight import init_env, load_env, validate_env


class R2PreflightTest(unittest.TestCase):
    def test_init_env_generates_secrets_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "r2.env.example"
            target = root / "r2.env.local"
            template.write_text(
                "POSTGRES_PASSWORD=__GENERATE__\n"
                "XAGENT_SECURITY__JWT_SECRET=__GENERATE__\n"
                "GRAFANA_ADMIN_PASSWORD=__GENERATE__\n",
                encoding="utf-8",
            )
            init_env(template, target)
            values = load_env(target)
            self.assertGreaterEqual(len(values["POSTGRES_PASSWORD"]), 32)
            self.assertGreaterEqual(len(values["XAGENT_SECURITY__JWT_SECRET"]), 32)
            with self.assertRaises(FileExistsError):
                init_env(template, target)

    def test_validate_env_rejects_weak_values(self) -> None:
        errors = validate_env({
            "POSTGRES_PASSWORD": "xagent",
            "XAGENT_SECURITY__JWT_SECRET": "short",
            "XAGENT_PLATFORM_MCP_TOKEN": "",
            "GRAFANA_ADMIN_PASSWORD": "admin",
            "XAGENT_SECURITY__REQUIRE_AUTH": "false",
            "XAGENT_CORS_ORIGINS": "*",
            "XAGENT_LLM__OLLAMA_MODEL": "",
        })
        self.assertEqual(
            {item["code"] for item in errors},
            {
                "weak_postgres_password", "weak_jwt_secret", "weak_mcp_token",
                "weak_grafana_password", "auth_disabled", "wildcard_cors",
                "missing_ollama_model",
            },
        )

    def test_validation_result_never_contains_secret_value(self) -> None:
        secret = "visible-secret-must-not-leak"
        errors = validate_env({
            "POSTGRES_PASSWORD": secret,
            "XAGENT_SECURITY__JWT_SECRET": "short",
            "XAGENT_PLATFORM_MCP_TOKEN": "mcp-token-value-at-least-32-characters",
            "GRAFANA_ADMIN_PASSWORD": "grafana-password-value-at-least-16",
            "XAGENT_SECURITY__REQUIRE_AUTH": "true",
            "XAGENT_CORS_ORIGINS": '["http://127.0.0.1:18080"]',
            "XAGENT_LLM__OLLAMA_MODEL": "qwen3:4b",
        })
        self.assertNotIn(secret, repr(errors))
```

- [ ] **步骤 2：运行测试并确认模块不存在**

运行：`python -m unittest discover -s tests/release -p "test_r2_preflight.py" -v`

预期：FAIL，报 `No module named scripts.r2_preflight`。

- [ ] **步骤 3：实现 env 初始化和纯校验函数**

`scripts/r2_preflight.py` 必须暴露：

```python
GENERATED_KEYS = (
    "POSTGRES_PASSWORD",
    "XAGENT_SECURITY__JWT_SECRET",
    "XAGENT_PLATFORM_MCP_TOKEN",
    "GRAFANA_ADMIN_PASSWORD",
)


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def init_env(template: Path, target: Path) -> None:
    if target.exists():
        raise FileExistsError(f"refusing to overwrite {target}")
    text = template.read_text(encoding="utf-8")
    for key in GENERATED_KEYS:
        text = text.replace(f"{key}=__GENERATE__", f"{key}={secrets.token_urlsafe(36)}")
    target.write_text(text, encoding="utf-8", newline="\n")


def validate_env(values: dict[str, str]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if values.get("POSTGRES_PASSWORD", "").lower() in {"", "xagent", "password", "__generate__"}:
        errors.append({"code": "weak_postgres_password", "message": "PostgreSQL password is not strong"})
    if len(values.get("XAGENT_SECURITY__JWT_SECRET", "")) < 32:
        errors.append({"code": "weak_jwt_secret", "message": "JWT secret must contain at least 32 characters"})
    if len(values.get("XAGENT_PLATFORM_MCP_TOKEN", "")) < 32:
        errors.append({"code": "weak_mcp_token", "message": "Platform MCP token must contain at least 32 characters"})
    if len(values.get("GRAFANA_ADMIN_PASSWORD", "")) < 16:
        errors.append({"code": "weak_grafana_password", "message": "Grafana password must contain at least 16 characters"})
    if values.get("XAGENT_SECURITY__REQUIRE_AUTH", "").lower() != "true":
        errors.append({"code": "auth_disabled", "message": "Full mode requires authentication"})
    if "*" in values.get("XAGENT_CORS_ORIGINS", ""):
        errors.append({"code": "wildcard_cors", "message": "Wildcard CORS is forbidden"})
    if not values.get("XAGENT_LLM__OLLAMA_MODEL", "").strip():
        errors.append({"code": "missing_ollama_model", "message": "Ollama model is required"})
    return errors
```

- [ ] **步骤 4：实现只读系统预检 CLI**

CLI 参数固定为：

```text
--env-file deploy/compose/r2.env.local
--compose-file deploy/compose/docker-compose.yml
--project-name xagent-r2
--expected-branch feature/webapi-r2-staging-readiness
--output output/r2-runtime/preflight.json
--init-env deploy/compose/r2.env.local
--validate-env-only
--allow-running-project
```

`--init-env` 生成文件并完成纯 env 校验后退出，不要求当时 Git clean。正常预检依次执行：加载/校验 env；验证 Git 分支和 clean status；调用 `docker version`、`docker compose version`；逐个 bind 候选端口；请求 `http://127.0.0.1:11434/api/tags` 并确认模型；运行目标 Compose 文件的 `config --quiet`。`--allow-running-project` 只在目标 project 已运行时使用：每个被占端口都必须与 `docker compose port` 返回的同 project 服务映射相同，否则仍失败。输出 JSON 只包含检查名、`ok`、非敏感 detail、commit、branch 和时间，不输出任何 env value。

- [ ] **步骤 5：实现 PowerShell 薄入口**

```powershell
param(
    [string]$EnvFile = "deploy/compose/r2.env.local",
    [string]$ProjectName = "xagent-r2",
    [switch]$Init,
    [switch]$ValidateEnvOnly,
    [switch]$AllowRunningProject
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python -ErrorAction Stop).Source
$arguments = @(
    (Join-Path $repoRoot "scripts/r2_preflight.py"),
    "--env-file", (Join-Path $repoRoot $EnvFile),
    "--compose-file", (Join-Path $repoRoot "deploy/compose/docker-compose.yml"),
    "--project-name", $ProjectName,
    "--expected-branch", "feature/webapi-r2-staging-readiness",
    "--output", (Join-Path $repoRoot "output/r2-runtime/preflight.json")
)
if ($Init) {
    $arguments += @("--init-env", (Join-Path $repoRoot $EnvFile))
}
if ($ValidateEnvOnly) {
    $arguments += "--validate-env-only"
}
if ($AllowRunningProject) {
    $arguments += "--allow-running-project"
}
& $python @arguments
exit $LASTEXITCODE
```

- [ ] **步骤 6：运行测试、生成本机 env 并执行预检**

运行：

```powershell
python -m unittest discover -s tests/release -p "test_r2_preflight.py" -v
pwsh -File scripts/r2-preflight.ps1 -Init
pwsh -File scripts/r2-preflight.ps1 -ValidateEnvOnly
```

预期：测试 PASS；`deploy/compose/r2.env.local` 创建且被 Git 忽略；纯 env 预检 `ok=true`；输出中找不到任何生成的 secret。

- [ ] **步骤 7：提交预检工具**

先在 `.gitignore` 增加：

```gitignore
output/r2-runtime/
output/r2-backups/
```

```powershell
git add scripts/r2_preflight.py scripts/r2-preflight.ps1 tests/release/test_r2_preflight.py .gitignore
git commit -m "feat(运维): 增加 R2 安全预检入口"
```

- [ ] **步骤 8：在 clean commit 上执行完整预检**

运行：`pwsh -File scripts/r2-preflight.ps1`

预期：Git、Docker、端口、Ollama、目标模型和 Compose config 全部 `ok=true`。

---

### 任务 4：接入配置门禁并更新单机 Runbook

**文件：**
- 修改：`.github/workflows/ci.yml:90-117`
- 修改：`docs/DEPLOYMENT_RUNBOOK.md:1-220`
- 修改：`docs/coordination/WEB_API_RELEASE_TASK_BOARD.md`

- [ ] **步骤 1：先让 CI 合同断言失败**

在 `R2ComposeContractTest` 类中增加：

```python
    def test_ci_runs_r2_release_contract(self) -> None:
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("test_r2_*.py", ci)
        self.assertIn("docker compose", ci)
        self.assertIn("deploy/compose/r2.env.example", ci)
```

运行：`python -m unittest discover -s tests/release -p "test_r2_*.py" -v`

预期：新增断言 FAIL，因为 CI 尚未执行 R2 门禁。

- [ ] **步骤 2：在 config-governance job 加入门禁**

```yaml
- name: R2 compose contract
  run: python -m unittest discover -s tests/release -p "test_r2_*.py" -v

- name: R2 compose render
  env:
    POSTGRES_PASSWORD: config-only-postgres-strong-value
    XAGENT_SECURITY__JWT_SECRET: config-only-jwt-secret-at-least-32-characters
    GRAFANA_ADMIN_PASSWORD: config-only-grafana-strong-value
  run: docker compose -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.example config --quiet
```

- [ ] **步骤 3：把 R2 单一路径写入 Runbook**

新增明确命令：

```powershell
pwsh -File scripts/r2-preflight.ps1 -Init
pwsh -File scripts/r2-preflight.ps1
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local up -d --build postgres redis qdrant api worker web
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local --profile mcp --profile observability up -d platform-mcp prometheus grafana
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local down
```

文档同时声明：不运行 `down -v`；根 Compose 非 R2 入口；本阶段不启用 `gateway/tracing/federation`；所有浏览器验收使用 `127.0.0.1:18080`。

- [ ] **步骤 4：建立 R2 任务板条目**

加入 R2-A、R2-B、R2-C、R2-D 四行，初始状态分别为 `CLAIMED/PENDING/PENDING/PENDING`。脱敏后需要提交的截图放在 `output/playwright/`，不使用原始证据目录。

- [ ] **步骤 5：验证并提交 Runbook/CI**

运行：

```powershell
python -m unittest discover -s tests/release -p "test_r2_*.py" -v
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml', encoding='utf-8'))"
git diff --check
```

预期：合同 PASS、CI YAML 可解析、diff check 无输出。

提交：

```powershell
git add .github/workflows/ci.yml docs/DEPLOYMENT_RUNBOOK.md docs/coordination/WEB_API_RELEASE_TASK_BOARD.md tests/release/test_r2_compose_contract.py
git commit -m "docs(部署): 固化 R2 运行与配置门禁"
```

---

### 任务 5：从 fresh volumes 启动核心栈并证明真实 Ollama

**文件：**
- 修改：`docs/coordination/WEB_API_RELEASE_TASK_BOARD.md`
- 后续引用：`docs/coordination/reports/WEB_API_R2_STAGING_TRIAL_EVIDENCE.md`

- [ ] **步骤 1：冻结本次候选身份**

运行并保存非 secret 输出：

```powershell
git status --short --branch
git rev-parse HEAD
docker version --format 'client={{.Client.Version}} server={{.Server.Version}}'
docker compose version
ollama list
```

预期：工作树 clean；分支为 `feature/webapi-r2-staging-readiness`；`qwen3:4b` 存在。

- [ ] **步骤 2：执行预检并检查隔离资源不存在**

```powershell
pwsh -File scripts/r2-preflight.ps1
docker ps -a --filter name=xagent-r2
docker volume ls --filter name=xagent-r2
```

预期：预检通过；没有旧 R2 容器或 volume。若存在，只能先调查来源；不得直接删除。

- [ ] **步骤 3：构建 Web 和核心镜像**

```powershell
cd apps/web
npm ci
npm run build
cd ../..
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local build api worker web
```

预期：三个镜像成功；构建日志不包含 secret。

- [ ] **步骤 4：启动六个核心服务**

```powershell
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local up -d postgres redis qdrant api worker web
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local ps
```

预期：六个服务 running；有 healthcheck 的服务最终 healthy。

- [ ] **步骤 5：核对 migration、深度健康和 worker**

```powershell
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local exec -T api python -m alembic current
Invoke-RestMethod http://127.0.0.1:18000/health
Invoke-RestMethod http://127.0.0.1:18000/health/ready
Invoke-RestMethod http://127.0.0.1:18000/health/deep
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local exec -T worker celery -A xagent.worker.celery_app inspect ping --timeout=5
```

预期：migration 为 `20260807_checkpoints` 或实施时新 head；deep health 的 DB/Redis/Qdrant 都是 healthy；worker 返回 pong。

- [ ] **步骤 6：创建隔离账号并发送真实模型请求**

运行：

```powershell
$randomBytes = New-Object byte[] 36
[Security.Cryptography.RandomNumberGenerator]::Fill($randomBytes)
$trialPassword = [Convert]::ToBase64String($randomBytes)
$registerBody = @{
  username = 'r2-reviewer'
  password = $trialPassword
  tenant_id = 'r2-trial'
} | ConvertTo-Json
$registration = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:18000/api/v1/auth/register' -ContentType 'application/json' -Body $registerBody
$headers = @{ Authorization = "Bearer $($registration.access_token)" }
$runBody = @{ goal = '请只回复：R2-OLLAMA-OK' } | ConvertTo-Json
$ollamaRun = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:18000/api/v1/agents/run' -Headers $headers -ContentType 'application/json' -Body $runBody
$env:E2E_USERNAME = 'r2-reviewer'
$env:E2E_PASSWORD = $trialPassword
```

预期：HTTP 200、存在 `run_id` 和非空 final answer；API 日志包含 `ollama_warmup_succeeded` 或真实 Ollama route；不得出现 MockLLM 标识。

- [ ] **步骤 7：把 R2-A 转 REVIEW 并提交运行事实**

任务板只写镜像 ID、commit、migration、健康结果和 run ID，不写 token/密码。运行：`git diff --check` 后提交：

```powershell
git add docs/coordination/WEB_API_RELEASE_TASK_BOARD.md
git commit -m "docs(证据): 记录 R2 核心栈启动"
```

---

### 任务 6：增加并运行排除短剧的 R2 Playwright 验收

**文件：**
- 创建：`tests/e2e/specs/webapi-r2-full-compose.spec.ts`
- 创建：`tests/e2e/fixtures/r2-skill/SKILL.md`
- 创建：`tests/e2e/fixtures/r2-skill/references/checklist.md`
- 创建：`tests/e2e/fixtures/r2-skill/scripts/verify.py`
- 创建：`tests/e2e/fixtures/r2-skill/assets/badge.txt`
- 创建：`tests/e2e/fixtures/r2-workspace/README.md`
- 修改：`docs/coordination/WEB_API_RELEASE_TASK_BOARD.md`

- [ ] **步骤 1：创建只覆盖 Web/API 发布面的测试骨架**

```typescript
import { expect, test, type Page } from "@playwright/test";

const API_BASE = process.env.E2E_API_URL ?? "http://127.0.0.1:18000";
const USERNAME = process.env.E2E_USERNAME;
const PASSWORD = process.env.E2E_PASSWORD;

test.describe.configure({ mode: "serial" });

async function login(page: Page) {
  if (!USERNAME || !PASSWORD) throw new Error("R2 full-mode credentials are required");
  await page.goto("/");
  const response = await page.request.post("/api/v1/auth/login", {
    data: { username: USERNAME, password: PASSWORD, tenant_id: "r2-trial" },
  });
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  await page.evaluate((token) => localStorage.setItem("xagent_token", token), body.access_token);
}

test.beforeEach(async ({ page }) => login(page));
```

- [ ] **步骤 2：加入健康、真实对话、Run Console 和刷新恢复用例**

```typescript
test("deep health 覆盖 PostgreSQL Redis Qdrant", async ({ request }) => {
  const response = await request.get(`${API_BASE}/health/deep`);
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  expect(body.status).toBe("healthy");
  expect(body.checks.database.status).toBe("healthy");
  expect(body.checks.redis.status).toBe("healthy");
  expect(body.checks.qdrant.status).toBe("healthy");
});

test("真实 Ollama 对话进入 Run Console 并可刷新恢复", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/chat");
  await page.getByPlaceholder(/描述一个任务/).fill("请只回复：R2-WEB-OLLAMA-OK");
  await page.getByRole("button", { name: "发送" }).click();
  const runLink = page.getByText("运行详情", { exact: true }).last();
  await expect(runLink).toBeVisible({ timeout: 160_000 });
  await runLink.click();
  await expect(page.getByText("Run Console", { exact: true })).toBeVisible();
  await expect(page.getByText(/checkpoint/i).first()).toBeVisible();
  const runId = new URL(page.url()).pathname.split("/").at(-1);
  const token = await page.evaluate(() => localStorage.getItem("xagent_token"));
  const checkpoints = await page.request.get(
    `/api/v1/checkpoints?run_id=${encodeURIComponent(runId ?? "")}`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  expect(checkpoints.ok()).toBeTruthy();
  process.env.E2E_CHECKPOINT_ID = (await checkpoints.json()).checkpoints[0].checkpoint_id;
  const runUrl = page.url();
  await page.reload({ waitUntil: "networkidle" });
  await expect(page).toHaveURL(runUrl);
  await expect(page.getByText("Run Console", { exact: true })).toBeVisible();
});
```

- [ ] **步骤 3：加入调度器和技能包持久化用例**

```typescript
test("调度任务运行 暂停并刷新后保持", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/scheduler");
  await page.getByPlaceholder("任务名称").fill("R2 restart probe");
  await page.getByPlaceholder("Agent 目标").fill("请只回复 R2-SCHEDULER-OK");
  await page.getByRole("button", { name: "创建" }).click();
  await expect(page.getByText("调度任务已创建")).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "立即运行" }).click();
  await expect(page.getByText(/attempt 1/)).toBeVisible({ timeout: 160_000 });
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "暂停" }).click();
  await page.reload({ waitUntil: "networkidle" });
  await expect(page.getByText("已暂停").first()).toBeVisible();
});

test("完整技能包导入后在 Web 可见", async ({ page }) => {
  const archive = process.env.E2E_SKILL_PACKAGE;
  if (!archive) throw new Error("E2E_SKILL_PACKAGE is required");
  await page.goto("/settings?section=skills");
  const imported = page.waitForResponse((response) =>
    response.url().includes("/api/v1/skill-packages/import") && response.status() === 201,
  );
  await page.locator('input[type="file"]').setInputFiles(archive);
  const importedBody = await (await imported).json();
  process.env.E2E_SKILL_PACKAGE_ID = importedBody.package.package_id;
  await expect(page.getByText("R2 持久化验收技能")).toBeVisible();
  await expect(page.getByText("完整技能包", { exact: true })).toBeVisible();
});
```

- [ ] **步骤 4：加入开发任务与租户边界用例**

```typescript
test("开发任务产物可审查和下载", async ({ page }) => {
  const taskId = process.env.E2E_DEVELOPMENT_TASK_ID;
  if (!taskId) throw new Error("E2E_DEVELOPMENT_TASK_ID is required");
  await page.goto("/development-tasks");
  await page.getByText(taskId, { exact: false }).first().click();
  await expect(page.getByText(/awaiting_review|approved|applied/).first()).toBeVisible();
  await expect(page.getByRole("link", { name: /下载|Patch/i })).toBeVisible();
});

test("第二租户不能读取第一租户资源", async ({ request }) => {
  const packageId = process.env.E2E_SKILL_PACKAGE_ID;
  const checkpointId = process.env.E2E_CHECKPOINT_ID;
  const taskId = process.env.E2E_DEVELOPMENT_TASK_ID;
  if (!packageId || !checkpointId || !taskId) throw new Error("R2 tenant-bound ids are required");
  const username = `r2-isolation-${Date.now()}`;
  const register = await request.post(`${API_BASE}/api/v1/auth/register`, {
    data: { username, password: "R2-isolation-password-2026", tenant_id: "r2-other" },
  });
  expect(register.ok()).toBeTruthy();
  const token = (await register.json()).access_token;
  const headers = { Authorization: `Bearer ${token}` };
  for (const path of [
    `/api/v1/skill-packages/${packageId}`,
    `/api/v1/checkpoints/${checkpointId}`,
    `/api/v1/development-tasks/${taskId}`,
  ]) {
    const response = await request.get(`${API_BASE}${path}`, { headers });
    expect([403, 404]).toContain(response.status());
  }
});
```

- [ ] **步骤 5：先做测试发现与旧环境失败检查**

```powershell
cd tests/e2e
npm ci
npx playwright test specs/webapi-r2-full-compose.spec.ts --list
$env:E2E_BASE_URL='http://127.0.0.1:18080'
$env:E2E_API_URL='http://127.0.0.1:18000'
npx playwright test specs/webapi-r2-full-compose.spec.ts --project=chromium --reporter=list
```

预期：测试可被发现；若 fixture/预置数据尚未创建，对应测试明确失败，不得通过 skip 隐藏。

- [ ] **步骤 6：准备只存在于 R2 volume 的验收 fixture**

技能 fixture 内容固定为：

```markdown
---
name: r2-persistence-probe
description: R2 Full Compose 技能包持久化验收
version: 1.0.0
triggers:
  - R2 持久化验收技能
---

# R2 持久化验收技能

读取 references/checklist.md；scripts 和 assets 只验证保存，不执行。
```

`references/checklist.md` 内容为 `R2 skill package reference preserved.`；`scripts/verify.py` 内容为 `print("R2 skill package script preserved")`；`assets/badge.txt` 内容为 `R2-SKILL-ASSET`。

`tests/e2e/fixtures/r2-workspace/README.md` 内容为 `R2 isolated workspace`。把它复制到 `/data/workspace`，初始化临时 Git 仓库并提交：

```powershell
$apiContainer = docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local ps -q api
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local exec -T api mkdir -p /data/workspace
docker cp tests/e2e/fixtures/r2-workspace/README.md "${apiContainer}:/data/workspace/README.md"
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local exec -T api git -C /data/workspace init -b main
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local exec -T api git -C /data/workspace config user.name 'R2 Trial'
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local exec -T api git -C /data/workspace config user.email 'r2@xagent.local'
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local exec -T api git -C /data/workspace add README.md
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local exec -T api git -C /data/workspace commit -m 'chore: seed R2 workspace'
$parallelBody = @{
  tasks = @(@{ goal = '在当前工作区创建 R2_AGENT_RESULT.md，内容必须是 R2-DEVELOPMENT-TASK-OK'; capabilities = @('file_write') })
  coordinator_goal = '验证隔离开发任务结果'
  use_worktrees = $true
} | ConvertTo-Json -Depth 6
$parallel = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:18000/api/v1/agents/parallel-run' -Headers $headers -ContentType 'application/json' -Body $parallelBody
$env:E2E_DEVELOPMENT_TASK_ID = $parallel.sub_results[0].development_task_id
$skillArchive = Join-Path $env:TEMP 'xagent-r2-skill.zip'
Compress-Archive -Path 'tests/e2e/fixtures/r2-skill/*' -DestinationPath $skillArchive
$env:E2E_SKILL_PACKAGE = $skillArchive
```

预期：development task 状态为 `awaiting_review`，且任务路径位于 `/data/.xagent-worktrees`。不得把真实项目工作树当作 apply 目标。

- [ ] **步骤 7：运行完整 R2 Playwright 并采集截图**

使用本次随机账号变量运行 headed Chromium；保存 chat、Run Console、scheduler、skill、development task、reload 六张截图到 `output/playwright/r2-*.png`。同时注册 `page.on("console")` 和 `page.on("pageerror")`，最终断言无 error。

预期：所有 R2 spec PASS；短剧路由和媒体 API没有被调用。

- [ ] **步骤 8：提交 E2E 规格与脱敏截图**

```powershell
git add tests/e2e/specs/webapi-r2-full-compose.spec.ts tests/e2e/fixtures/r2-skill tests/e2e/fixtures/r2-workspace output/playwright/r2-*.png docs/coordination/WEB_API_RELEASE_TASK_BOARD.md
git commit -m "test(Web): 覆盖 R2 Full Compose 试用主链"
```

---

### 任务 7：验证重启和非破坏性故障恢复

**文件：**
- 修改：`docs/coordination/WEB_API_RELEASE_TASK_BOARD.md`

- [ ] **步骤 1：记录故障前业务锚点**

保存 tenant、user、conversation ID、run ID、scheduler job ID、skill package ID、checkpoint ID、development task ID 和 patch SHA-256；不保存 token。

- [ ] **步骤 2：重启 API 和 worker**

```powershell
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local restart api worker
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local ps
```

重新登录并读取全部锚点。预期：数据库状态和 `/data` 文件都可用，worker pong。

- [ ] **步骤 3：暂停 worker 并观察任务状态**

运行：

```powershell
$workerContainer = docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local ps -q worker
docker pause $workerContainer
$queued = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:18000/api/v1/tasks' -Headers $headers -ContentType 'application/json' -Body (@{ goal = 'R2 worker pause probe' } | ConvertTo-Json)
$pausedState = Invoke-RestMethod -Uri "http://127.0.0.1:18000/api/v1/tasks/$($queued.task_id)" -Headers $headers
docker unpause $workerContainer
```

断言 `$pausedState.status` 不是 `succeeded`；恢复后轮询到 succeeded，并确认最终记录只有一个终态。

- [ ] **步骤 4：暂停 Redis 并检查受控失败**

```powershell
$redisContainer = docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local ps -q redis
docker pause $redisContainer
$degradedHealth = Invoke-RestMethod 'http://127.0.0.1:18000/health/deep'
docker unpause $redisContainer
```

预期：暂停时 Redis 为 degraded 且整体不是全成功；恢复后轮询 deep health 重回 healthy，scheduler 不产生重复终态记录。

- [ ] **步骤 5：重启整个核心栈但保留 volumes**

```powershell
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local down
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local up -d postgres redis qdrant api worker web
```

重复读取全部锚点并打开浏览器。预期：账号、会话、run、job、skill package、checkpoint、patch 全部存在。

- [ ] **步骤 6：检查错误和重复记录**

运行：

```powershell
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local logs --since 30m api worker redis | Select-String -Pattern 'Traceback|Unhandled|duplicate|MockLLM|password|JWT_SECRET'
```

每个命中必须分类为预期故障、已知非阻断或需要修复；无法解释的错误阻止 R2-C。

- [ ] **步骤 7：提交故障恢复摘要**

任务板记录故障窗口、预期响应、恢复时间和锚点复核结果；`git diff --check` 后提交：

```powershell
git add docs/coordination/WEB_API_RELEASE_TASK_BOARD.md
git commit -m "docs(证据): 记录 R2 重启与故障恢复"
```

---

### 任务 8：启用 Platform MCP 和观测 profile

**文件：**
- 创建：`deploy/grafana/provisioning/datasources/prometheus.yml`
- 创建：`deploy/grafana/provisioning/dashboards/xagent.yml`
- 修改：`deploy/compose/docker-compose.yml`
- 修改：`tests/release/test_r2_compose_contract.py`
- 修改：`docs/coordination/WEB_API_RELEASE_TASK_BOARD.md`

- [ ] **步骤 1：先用合同证明 Grafana provisioning 缺失**

在 `test_r2_compose_contract.py` 增加：

```python
    def test_grafana_is_provisioned_from_same_stack(self) -> None:
        datasource = ROOT / "deploy/grafana/provisioning/datasources/prometheus.yml"
        dashboards = ROOT / "deploy/grafana/provisioning/dashboards/xagent.yml"
        self.assertTrue(datasource.exists())
        self.assertTrue(dashboards.exists())
        self.assertIn("http://prometheus:9090", datasource.read_text(encoding="utf-8"))
        self.assertIn("uid: prometheus", datasource.read_text(encoding="utf-8"))
        self.assertIn("/etc/grafana/provisioning", COMPOSE)
```

运行合同并确认 FAIL，因为 provisioning 文件和挂载尚不存在。

- [ ] **步骤 2：创建 Grafana datasource/dashboard provisioning**

`datasources/prometheus.yml`：

```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    uid: prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
```

`dashboards/xagent.yml`：

```yaml
apiVersion: 1
providers:
  - name: X-Agent
    orgId: 1
    folder: X-Agent
    type: file
    disableDeletion: true
    editable: false
    options:
      path: /var/lib/grafana/dashboards
```

Grafana 服务增加两个只读 provisioning mount；保留现有 dashboard JSON mount。

- [ ] **步骤 3：重跑合同并启用 mcp 与 observability**

```powershell
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local --profile mcp --profile observability up -d platform-mcp prometheus grafana
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local --profile mcp --profile observability ps
```

预期：三项扩展服务 running；Grafana 密码来自本地 env。

- [ ] **步骤 4：验证 Platform MCP 当前真实状态**

使用 `XAGENT_PLATFORM_MCP_TOKEN` 调用 `http://127.0.0.1:18100/mcp`：初始化、列出工具、读取同 tenant 会话/run/审批/事件；用无 token 和第二 tenant token复测拒绝。

预期：工具数与当前实现一致；同 tenant 读取成功；无凭证 401；跨租户不返回第一 tenant 数据。

- [ ] **步骤 5：验证 Prometheus target 与指标**

请求 `http://127.0.0.1:19090/api/v1/targets`，断言 `xagent` target 的 discovered URL 指向 `api:8000/metrics` 且 health=`up`。请求 API 指标，确认 HTTP、run 或 scheduler 指标有样本。

- [ ] **步骤 6：验证 Grafana 数据源和面板**

使用本地 Grafana 管理凭据调用 `/api/datasources` 和 `/api/search`；断言 Prometheus 数据源可查询，X-Agent dashboard 存在并能返回非空 panel 数据。

- [ ] **步骤 7：仅在仍失败时做最小配置修复**

如果 target 或 datasource 漂移，先增加能复现该错误的 `test_r2_compose_contract.py` 断言，再只改对应的 Prometheus/Grafana provision 文件。不得趁机加入 Langfuse、ContextForge 或 OpenFGA。

- [ ] **步骤 8：提交观测/MCP 证据和 provisioning**

```powershell
git add deploy/grafana/provisioning/datasources/prometheus.yml deploy/grafana/provisioning/dashboards/xagent.yml deploy/compose/docker-compose.yml tests/release/test_r2_compose_contract.py docs/coordination/WEB_API_RELEASE_TASK_BOARD.md
git commit -m "test(运维): 验证 R2 MCP 与观测链"
```

---

### 任务 9：备份并恢复到全新隔离 project

**文件：**
- 修改：`docs/coordination/WEB_API_RELEASE_TASK_BOARD.md`
- 后续引用：`docs/coordination/reports/WEB_API_R2_STAGING_TRIAL_EVIDENCE.md`

- [ ] **步骤 1：创建仓库外备份目录和 manifest**

使用 `$env:TEMP\xagent-r2-backup-<UTC timestamp>`，记录 commit、migration、镜像 ID、project name、volume name和业务锚点。manifest 只写 secret key 名称，不写值。

- [ ] **步骤 2：暂停写入面并保持数据服务在线**

```powershell
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local stop web api worker
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local ps
```

预期：Web/API/worker stopped；PostgreSQL/Redis/Qdrant 仍 healthy。源数据 volume 不删除。

- [ ] **步骤 3：创建 PostgreSQL 与 Qdrant 一致性备份**

在 Postgres 容器内运行 `pg_dump -Fc` 后用 `docker cp` 复制。若 `xagent_memory` collection 尚不存在，先创建维度 1536 的验收 collection 并写入固定 marker point；调用 Qdrant snapshot API并下载 snapshot。分别计算 SHA-256 和字节数。

- [ ] **步骤 4：备份 Redis 与 xagentdata volume**

在 Redis 容器内运行 `redis-cli --rdb /tmp/r2.rdb` 并用 `docker cp` 复制该 RDB。使用只读 source mount 的 `alpine:3.20` 将 `xagent-r2_xagentdata` 归档到备份目录。不得停止或修改其他 project volume。

- [ ] **步骤 5：恢复源实例并确认仍可用**

重新启动源 Web/API/worker，核对 deep health 和全部业务锚点；源实例失败时停止恢复演练并先修复源实例。

- [ ] **步骤 6：为恢复实例生成独立 env**

复制本机 R2 env 到仓库外临时文件，仅修改：project=`xagent-r2-restore`，端口=`25432/26379/26333/26334/28000/28080/28100/29090/23002`。重新生成 JWT、PostgreSQL、Grafana secret；恢复实例不能复用源 secret。

- [ ] **步骤 7：创建全新 volumes 并恢复文件数据**

只在确认 `xagent-r2-restore_*` volumes 不存在后创建它们。把 RDB 复制为新 Redis volume 的 `/data/dump.rdb`，把 xagentdata archive 解压到新 volume，再启动 Postgres/Redis/Qdrant；使用 `pg_restore` 恢复 fresh PostgreSQL，使用 Qdrant snapshot upload 恢复 collection。

- [ ] **步骤 8：启动恢复 API/worker/Web**

```powershell
docker compose -p xagent-r2-restore -f deploy/compose/docker-compose.yml --env-file $restoreEnv up -d api worker web
docker compose -p xagent-r2-restore -f deploy/compose/docker-compose.yml --env-file $restoreEnv ps
```

预期：恢复实例独立 healthy，源实例仍在且未被修改。

- [ ] **步骤 9：重复恢复验收**

在 `http://127.0.0.1:28080` 重新登录，读取全部业务锚点；对 PostgreSQL 行数、Qdrant collection、skill package文件、patch SHA-256 做源/恢复实例对比。恢复实例再发起一次新的真实 Ollama run，证明不是只读快照。

- [ ] **步骤 10：停止恢复实例但保留证据**

执行：

```powershell
docker compose -p xagent-r2-restore -f deploy/compose/docker-compose.yml --env-file $restoreEnv down
```

命令不带 `-v`。在用户未要求清理前保留恢复 volumes；任务板写明恢复 project、端口、hash 和验证结果。

- [ ] **步骤 11：提交恢复演练摘要**

```powershell
git add docs/coordination/WEB_API_RELEASE_TASK_BOARD.md
git commit -m "docs(证据): 完成 R2 备份恢复演练"
```

---

### 任务 10：全量回归、证据审计与 R2 交付判定

**文件：**
- 创建：`docs/coordination/reports/WEB_API_R2_STAGING_TRIAL_EVIDENCE.md`
- 修改：`docs/coordination/WEB_API_RELEASE_TASK_BOARD.md`

- [ ] **步骤 1：运行后端全量和发布静态门禁**

在最终 API 镜像内运行 `pytest -q`；在宿主机运行关键 Ruff、完整静态基线、mypy/许可证/版本门禁。记录 passed/skipped/warnings 的精确数量和原因。

- [ ] **步骤 2：运行 Web 全量门禁**

```powershell
cd apps/web
npm test
npm run typecheck
npm run lint
npm run lint:release
npm run build
npm run audit:release
```

预期：测试/typecheck/build/audit 通过；lint error 为 0；任何 warnings 必须与精确豁免一致。

- [ ] **步骤 3：运行 R2 配置、E2E 和镜像复验**

```powershell
python -m unittest discover -s tests/release -p "test_r2_*.py" -v
pwsh -File scripts/r2-preflight.ps1 -AllowRunningProject
docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml --env-file deploy/compose/r2.env.local config --quiet
cd tests/e2e
npx playwright test specs/webapi-r2-full-compose.spec.ts --project=chromium --reporter=list
```

运行中端口必须通过“已属于目标 project”映射校验；不得把占用直接忽略。

- [ ] **步骤 4：审计日志、浏览器和 secret 泄漏**

检查 API/worker/Web/MCP/Prometheus/Grafana 最近日志；浏览器 console/pageerror；`git grep` 与证据目录中不得出现本机随机密码、JWT、token。检查 `git status`、`git diff --check` 和未跟踪文件。

- [ ] **步骤 5：撰写证据报告**

报告必须分开列出：源码/测试、镜像/Compose、真实 Ollama、浏览器、重启、故障、MCP、观测、备份恢复、未验证/排除项。不能用 R1 历史结论替代 R2 新鲜结果；不能把“容器 running”写成 E2E 成功。

- [ ] **步骤 6：把 R2-A 至 R2-D 转 DONE 或准确降级**

只有 10 项完成标准全部满足才写 DONE。任一真实模型、浏览器、deep health、worker、恢复实例或租户边界失败，任务板和报告必须写 PARTIAL/BLOCKED 及具体缺口。

- [ ] **步骤 7：提交最终证据**

```powershell
git add docs/coordination/reports/WEB_API_R2_STAGING_TRIAL_EVIDENCE.md docs/coordination/WEB_API_RELEASE_TASK_BOARD.md output/playwright/r2-*.png
git commit -m "docs(证据): 完成 Web API R2 试运行审计"
git status --short --branch
git log --oneline 0627747..HEAD
```

预期：工作树 clean；没有 push、tag 或生产部署。

---

## 最终执行纪律

- 每个任务必须先形成失败证据，再做最小修复，再运行定向和相邻回归。
- 当前 linked worktree 已是专用隔离环境，不创建嵌套 worktree。
- 原始备份、token、密码、环境文件和完整运行日志不进入 Git。
- 不使用 `docker compose down -v`，不删除来源不明的容器或 volume。
- 不启用短剧、Tauri、E2B、付费 provider、HA、gateway、tracing 或 federation。
- 任何需要 Docker Socket、生产凭据、远程部署或外部写入的动作都暂停并重新获取 Owner 授权。

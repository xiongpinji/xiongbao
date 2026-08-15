import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CI_PATH = ROOT / ".github" / "workflows" / "ci.yml"
RUNBOOK_PATH = ROOT / "docs" / "DEPLOYMENT_RUNBOOK.md"
COMPOSE_PATH = ROOT / "deploy" / "compose" / "docker-compose.yml"
ENV_PATH = ROOT / "deploy" / "compose" / "r2.env.example"
ROOT_COMPOSE_PATH = ROOT / "docker-compose.yml"
API_DOCKERFILE_PATH = ROOT / "apps" / "api" / "Dockerfile"
GRAFANA_DATASOURCE_PATH = (
    ROOT / "deploy" / "grafana" / "provisioning" / "datasources" / "prometheus.yml"
)
GRAFANA_DASHBOARD_PROVIDER_PATH = (
    ROOT / "deploy" / "grafana" / "provisioning" / "dashboards" / "xagent.yml"
)


def _docker_compose_argv() -> list:
    """Prefer the docker compose plugin, fall back to standalone docker-compose."""
    import shutil

    if shutil.which("docker-compose"):
        probe = subprocess.run(
            ("docker-compose", "version"), capture_output=True, check=False, timeout=20
        )
        if probe.returncode == 0:
            return ["docker-compose"]
    return ["docker", "compose"]

def read_or_empty(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


class R2ComposeContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ci = yaml.safe_load(CI_PATH.read_text(encoding="utf-8"))
        cls.runbook = read_or_empty(RUNBOOK_PATH)
        cls.compose = read_or_empty(COMPOSE_PATH)
        cls.env_example = read_or_empty(ENV_PATH)
        cls.root_compose = read_or_empty(ROOT_COMPOSE_PATH)

    def service_block(self, service: str) -> str:
        marker = f"  {service}:\n"
        start = self.compose.find(marker)
        self.assertNotEqual(start, -1, f"missing service: {service}")
        block_lines = []
        for line in self.compose[start + len(marker) :].splitlines():
            if line.startswith("  ") and not line.startswith("   ") and line.endswith(":"):
                break
            block_lines.append(line)
        return "\n".join(block_lines)

    def test_ci_runs_r2_release_contract(self) -> None:
        job = self.ci["jobs"]["config-governance"]
        steps = {step.get("name"): step for step in job["steps"] if "name" in step}

        self.assertIn("R2 compose contract", steps)
        contract = steps["R2 compose contract"]
        self.assertEqual(
            'python -m unittest discover -s tests/release -p "test_r2_*.py" -v',
            contract["run"],
        )

        self.assertIn("R2 compose render", steps)
        render = steps["R2 compose render"]
        self.assertEqual(
            render["env"]["POSTGRES_PASSWORD"],
            "config-only-postgres-strong-value",
        )
        self.assertEqual(
            render["env"]["XAGENT_SECURITY__JWT_SECRET"],
            "config-only-jwt-secret-at-least-32-characters",
        )
        self.assertEqual(
            render["env"]["GRAFANA_ADMIN_PASSWORD"],
            "config-only-grafana-strong-value",
        )
        self.assertEqual(
            "docker compose -f deploy/compose/docker-compose.yml --env-file "
            "deploy/compose/r2.env.example config --quiet",
            render["run"],
        )

    def test_api_image_contains_operational_scripts(self) -> None:
        dockerfile = API_DOCKERFILE_PATH.read_text(encoding="utf-8")

        for script in (
            "post_deploy_summary.py",
            "collect_ops_evidence.py",
            "auto_archive_evidence.py",
        ):
            with self.subTest(script=script):
                self.assertIn(
                    f"COPY scripts/{script} ./scripts/{script}",
                    dockerfile,
                )

    def test_runbook_host_debug_uses_r2_core_dependency_command(self) -> None:
        expected_command = (
            "docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml "
            "--env-file deploy/compose/r2.env.local up -d postgres redis qdrant"
        )
        self.assertIn(expected_command, self.runbook)
        self.assertIn("根目录 `docker-compose.yml` 只是开发兼容入口，不是 R2 入口", self.runbook)

        forbidden_commands = [
            line
            for line in self.runbook.splitlines()
            if line.startswith("docker compose")
            and any(service in line for service in ("litellm", "langfuse"))
        ]
        self.assertEqual([], forbidden_commands)

    def test_runbook_operations_use_current_r2_env_and_project_commands(self) -> None:
        expected_logs_command = (
            "docker compose -p xagent-r2 -f deploy/compose/docker-compose.yml "
            "--env-file deploy/compose/r2.env.local logs api worker --since=10m"
        )
        self.assertIn(
            expected_logs_command + ' | grep -E "ollama_warmup_(succeeded|failed)"',
            self.runbook,
        )
        self.assertNotIn(
            'docker compose logs api worker --since=10m | grep -E "ollama_warmup_(succeeded|failed)"',
            self.runbook,
        )
        self.assertIn(
            "`deploy/compose/r2.env.example` 与 `pwsh -File scripts/r2-preflight.ps1 -Init`",
            self.runbook,
        )
        self.assertIn("`XAGENT_LLM__WARMUP_WAIT_TIMEOUT_SECONDS=120`", self.runbook)
        self.assertNotIn("复制到 `.env` 后应保留这组基线", self.runbook)
        self.assertIn("模型名是否与 `deploy/compose/r2.env.local` 一致", self.runbook)
        self.assertIn("重跑 4.1 的冷启动验证", self.runbook)
        self.assertNotIn("重跑 3.1 的冷启动验证", self.runbook)

    def test_project_and_host_ports_are_isolated(self) -> None:
        self.assertIn("name: ${COMPOSE_PROJECT_NAME:-xagent-r2}", self.compose)
        port_variables = (
            "XAGENT_POSTGRES_PORT",
            "XAGENT_REDIS_PORT",
            "XAGENT_QDRANT_HTTP_PORT",
            "XAGENT_QDRANT_GRPC_PORT",
            "XAGENT_API_PORT",
            "XAGENT_WEB_PORT",
            "XAGENT_CONTEXTFORGE_PORT",
            "XAGENT_OPENFGA_PORT",
            "XAGENT_LITELLM_PORT",
            "XAGENT_LANGFUSE_PORT",
            "XAGENT_MCP_PORT",
            "XAGENT_PROMETHEUS_PORT",
            "XAGENT_GRAFANA_PORT",
        )
        for variable in port_variables:
            with self.subTest(variable=variable):
                self.assertIn(
                    f"${{XAGENT_BIND_ADDRESS:-127.0.0.1}}:${{{variable}:-",
                    self.compose,
                )
        self.assertNotIn('"8000:8000"', self.compose)
        self.assertNotIn('"3000:80"', self.compose)

    def test_optional_services_use_profiles(self) -> None:
        expected_profiles = {
            "litellm": '["gateway"]',
            "langfuse": '["tracing"]',
            "contextforge": '["federation"]',
            "openfga": '["federation"]',
            "prometheus": '["observability"]',
            "grafana": '["observability"]',
            "platform-mcp": '["mcp"]',
        }
        for service, profile in expected_profiles.items():
            with self.subTest(service=service):
                self.assertIn(f"profiles: {profile}", self.service_block(service))
        for service in ("postgres", "redis", "qdrant", "api", "worker", "web"):
            with self.subTest(core_service=service):
                self.assertNotIn("profiles:", self.service_block(service))

    def test_platform_mcp_overrides_api_image_healthcheck(self) -> None:
        environment = os.environ.copy()
        for variable in ("COMPOSE_ENV_FILES", "COMPOSE_PROFILES"):
            environment.pop(variable, None)
        environment.update(
            {
                "COMPOSE_DISABLE_ENV_FILE": "1",
                "POSTGRES_PASSWORD": "contract-only-postgres-strong-value",
                "XAGENT_SECURITY__JWT_SECRET": (
                    "contract-only-jwt-secret-at-least-32-characters"
                ),
            }
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            empty_env = Path(temporary_directory) / "empty.env"
            empty_env.write_text("", encoding="utf-8")
            result = subprocess.run(
                (
                    *_docker_compose_argv(),
                    "-f",
                    str(COMPOSE_PATH),
                    "--env-file",
                    str(empty_env),
                    "--profile",
                    "mcp",
                    "config",
                    "--format",
                    "json",
                ),
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        healthcheck = yaml.safe_load(result.stdout)["services"]["platform-mcp"][
            "healthcheck"
        ]["test"]
        self.assertEqual(healthcheck[0], "CMD-SHELL")
        command = healthcheck[1]
        self.assertIn("--max-time 4", command)
        self.assertIn("--write-out '%{http_code}'", command)
        self.assertIn("--request POST http://localhost:8100/mcp", command)
        whitelist = re.search(r'case "\$\$http_code" in ([0-9|]+)\)', command)
        self.assertIsNotNone(whitelist, command)
        accepted = set(whitelist.group(1).split("|"))
        self.assertEqual(accepted, {"200", "400", "401", "406"})
        for rejected in ("404", "405", "500", "502", "503"):
            with self.subTest(rejected=rejected):
                self.assertNotIn(rejected, accepted)
        self.assertIn(") exit 0 ;; *) exit 1 ;; esac", command)

    def test_platform_mcp_principal_defaults_match_server_contract(self) -> None:
        platform_mcp = yaml.safe_load(self.compose)["services"]["platform-mcp"]
        for setting in (
            "XAGENT_PLATFORM_MCP_USER_ID=${XAGENT_PLATFORM_MCP_USER_ID:-platform-mcp}",
            "XAGENT_PLATFORM_MCP_TENANT_ID=${XAGENT_PLATFORM_MCP_TENANT_ID:-default}",
            "XAGENT_PLATFORM_MCP_ROLES=${XAGENT_PLATFORM_MCP_ROLES:-admin}",
        ):
            with self.subTest(setting=setting):
                self.assertIn(setting, platform_mcp["environment"])

    def test_platform_mcp_principal_accepts_shell_environment_overrides(self) -> None:
        environment = os.environ.copy()
        for variable in (
            "COMPOSE_ENV_FILES",
            "COMPOSE_PROFILES",
            "XAGENT_PLATFORM_MCP_TOKEN",
        ):
            environment.pop(variable, None)
        environment.update(
            {
                "COMPOSE_DISABLE_ENV_FILE": "1",
                "POSTGRES_PASSWORD": "contract-only-postgres-strong-value",
                "XAGENT_SECURITY__JWT_SECRET": (
                    "contract-only-jwt-secret-at-least-32-characters"
                ),
                "XAGENT_PLATFORM_MCP_USER_ID": "contract-mcp-user",
                "XAGENT_PLATFORM_MCP_TENANT_ID": "contract-mcp-tenant",
                "XAGENT_PLATFORM_MCP_ROLES": "viewer,admin",
            }
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            empty_env = Path(temporary_directory) / "empty.env"
            empty_env.write_text("", encoding="utf-8")
            result = subprocess.run(
                (
                    *_docker_compose_argv(),
                    "-f",
                    str(COMPOSE_PATH),
                    "--env-file",
                    str(empty_env),
                    "--profile",
                    "mcp",
                    "config",
                    "--format",
                    "json",
                ),
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        rendered = yaml.safe_load(result.stdout)["services"]["platform-mcp"][
            "environment"
        ]
        self.assertEqual(rendered.get("XAGENT_PLATFORM_MCP_USER_ID"), "contract-mcp-user")
        self.assertEqual(rendered.get("XAGENT_PLATFORM_MCP_TENANT_ID"), "contract-mcp-tenant")
        self.assertEqual(rendered.get("XAGENT_PLATFORM_MCP_ROLES"), "viewer,admin")

    def test_grafana_provisioning_and_dashboard_mounts_are_read_only(self) -> None:
        grafana = yaml.safe_load(self.compose)["services"]["grafana"]
        self.assertCountEqual(
            grafana["volumes"],
            (
                "../grafana/provisioning/datasources/prometheus.yml:"
                "/etc/grafana/provisioning/datasources/prometheus.yml:ro",
                "../grafana/provisioning/dashboards/xagent.yml:"
                "/etc/grafana/provisioning/dashboards/xagent.yml:ro",
                "../grafana/xagent-dashboard.json:"
                "/var/lib/grafana/dashboards/xagent-overview.json:ro",
                "grafanadata:/var/lib/grafana",
            ),
        )

    def test_grafana_prometheus_datasource_is_internal_and_stable(self) -> None:
        self.assertTrue(GRAFANA_DATASOURCE_PATH.is_file())
        provisioning = yaml.safe_load(GRAFANA_DATASOURCE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(provisioning["apiVersion"], 1)
        self.assertEqual(len(provisioning["datasources"]), 1)
        datasource = provisioning["datasources"][0]
        self.assertEqual(datasource["name"], "Prometheus")
        self.assertEqual(datasource["type"], "prometheus")
        self.assertEqual(datasource["uid"], "prometheus")
        self.assertEqual(datasource["url"], "http://prometheus:9090")
        self.assertEqual(datasource["access"], "proxy")
        self.assertTrue(datasource["isDefault"])
        self.assertFalse(datasource["editable"])

    def test_grafana_dashboard_provider_loads_existing_dashboard(self) -> None:
        self.assertTrue(GRAFANA_DASHBOARD_PROVIDER_PATH.is_file())
        provisioning = yaml.safe_load(GRAFANA_DASHBOARD_PROVIDER_PATH.read_text(encoding="utf-8"))
        self.assertEqual(provisioning["apiVersion"], 1)
        self.assertEqual(len(provisioning["providers"]), 1)
        provider = provisioning["providers"][0]
        self.assertEqual(provider["name"], "X-Agent")
        self.assertEqual(provider["type"], "file")
        self.assertEqual(provider["orgId"], 1)
        self.assertEqual(provider["folder"], "X-Agent")
        self.assertTrue(provider["disableDeletion"])
        self.assertFalse(provider["editable"])
        self.assertEqual(provider["options"]["path"], "/var/lib/grafana/dashboards")

    def test_default_config_does_not_require_optional_profile_secrets(self) -> None:
        environment = os.environ.copy()
        for variable in (
            "GRAFANA_ADMIN_PASSWORD",
            "XAGENT_PLATFORM_MCP_TOKEN",
            "XAGENT_PLATFORM_MCP_USER_ID",
            "XAGENT_PLATFORM_MCP_TENANT_ID",
            "XAGENT_PLATFORM_MCP_ROLES",
            "COMPOSE_ENV_FILES",
            "COMPOSE_PROFILES",
        ):
            environment.pop(variable, None)
        environment["COMPOSE_DISABLE_ENV_FILE"] = "1"
        environment["POSTGRES_PASSWORD"] = "contract-only-postgres-strong-value"
        environment["XAGENT_SECURITY__JWT_SECRET"] = (
            "contract-only-jwt-secret-at-least-32-characters"
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            empty_env = Path(temporary_directory) / "empty.env"
            empty_env.write_text("", encoding="utf-8")
            result = subprocess.run(
                (
                    *_docker_compose_argv(),
                    "-f",
                    str(COMPOSE_PATH),
                    "--env-file",
                    str(empty_env),
                    "config",
                    "--services",
                ),
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertCountEqual(
            result.stdout.splitlines(),
            ("postgres", "redis", "qdrant", "api", "worker", "web"),
        )

    def test_api_and_worker_share_persistent_data_paths(self) -> None:
        self.assertGreaterEqual(self.compose.count("xagentdata:/data"), 2)
        required_environment = (
            "XAGENT_WORKSPACE=/data/workspace",
            "XAGENT_STORAGE__LOCAL_ROOT=/data/storage",
            "XAGENT_SKILLS_ROOT=/data/skills",
            "XAGENT_SKILL_PACKAGES_ROOT=/data/skill-packages",
        )
        for service in ("api", "worker"):
            block = self.service_block(service)
            for setting in required_environment:
                with self.subTest(service=service, setting=setting):
                    self.assertIn(setting, block)
            self.assertIn("xagentdata:/data", block)
        self.assertIn("xagentdata:", self.compose)
        self.assertNotIn("docker.sock", self.compose)

    def test_healthchecks_gate_dependent_services(self) -> None:
        api = self.service_block("api")
        worker = self.service_block("worker")
        web = self.service_block("web")
        self.assertIn("/health/deep", api)
        self.assertIn("status_code", api)
        self.assertIn("healthy", api)
        self.assertIn("inspect ping", worker)
        self.assertIn("--timeout=5", worker)
        self.assertIn("grep -q pong", worker)
        self.assertIn("interval: 30s", worker)
        self.assertIn("timeout: 10s", worker)
        self.assertIn("retries: 3", worker)
        self.assertIn("start_period: 60s", worker)
        self.assertGreaterEqual(self.compose.count("condition: service_healthy"), 5)
        self.assertIn("condition: service_healthy", web)

    def test_api_and_worker_warmup_failures_gate_startup(self) -> None:
        parsed = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
        services = parsed["services"]
        forbidden_fragments = (
            "warmup || true",
            "warmup||true",
            "warmup; true",
            "warmup && true",
        )
        for service in ("api", "worker"):
            with self.subTest(service=service):
                command = services[service]["command"]
                self.assertIn("python -m xagent.cli warmup", command)
                for fragment in forbidden_fragments:
                    self.assertNotIn(fragment, command)

    def test_database_urls_use_configured_database_name(self) -> None:
        self.assertIn("${POSTGRES_DB:-xagent}", self.compose)
        self.assertNotIn("@postgres:5432/xagent", self.compose)

    def test_profile_only_langfuse_secrets_do_not_block_core_config(self) -> None:
        langfuse = self.service_block("langfuse")
        self.assertIn("${LANGFUSE_NEXTAUTH_SECRET:-}", langfuse)
        self.assertIn("${LANGFUSE_SALT:-}", langfuse)
        self.assertIn("${LANGFUSE_INIT_USER_PASSWORD:-}", langfuse)
        self.assertIn("NEXTAUTH_URL=http://127.0.0.1:${XAGENT_LANGFUSE_PORT:-13001}", langfuse)

    def test_release_compose_points_to_the_r2_env_template(self) -> None:
        header = "\n".join(self.compose.splitlines()[:8])
        self.assertIn("cp r2.env.example .env", header)

    def test_r2_env_example_contains_safe_required_defaults(self) -> None:
        required_lines = (
            "COMPOSE_PROJECT_NAME=xagent-r2",
            "XAGENT_BIND_ADDRESS=127.0.0.1",
            "XAGENT_POSTGRES_PORT=15432",
            "XAGENT_REDIS_PORT=16379",
            "XAGENT_QDRANT_HTTP_PORT=16333",
            "XAGENT_QDRANT_GRPC_PORT=16334",
            "XAGENT_API_PORT=18000",
            "XAGENT_WEB_PORT=18080",
            "XAGENT_CONTEXTFORGE_PORT=18081",
            "XAGENT_OPENFGA_PORT=18082",
            "XAGENT_LITELLM_PORT=14000",
            "XAGENT_LANGFUSE_PORT=13001",
            "XAGENT_MCP_PORT=18100",
            "XAGENT_PROMETHEUS_PORT=19090",
            "XAGENT_GRAFANA_PORT=13002",
            "POSTGRES_USER=xagent",
            "POSTGRES_DB=xagent",
            "XAGENT_MODE=full",
            "XAGENT_DEBUG=false",
            'XAGENT_CORS_ORIGINS=["http://127.0.0.1:18080",'
            '"http://tauri.localhost","tauri://localhost"]',
            "XAGENT_SECURITY__REQUIRE_AUTH=true",
            "XAGENT_LLM__OLLAMA_BASE_URL=http://host.docker.internal:11434",
            "XAGENT_LLM__OLLAMA_MODEL=xagent-qwen3",
            "XAGENT_LLM__DEFAULT_MODEL=xagent-qwen3",
            "XAGENT_TOOLS__ENABLE_SHELL=false",
            "XAGENT_TOOLS__ENABLE_PYTHON_EXEC=false",
            "XAGENT_SANDBOX__BACKEND=disabled",
        )
        for line in required_lines:
            with self.subTest(line=line):
                self.assertIn(line, self.env_example.splitlines())

        generated_secrets = (
            "POSTGRES_PASSWORD=__GENERATE__",
            "XAGENT_SECURITY__JWT_SECRET=__GENERATE__",
            "XAGENT_PLATFORM_MCP_TOKEN=__GENERATE__",
            "GRAFANA_ADMIN_PASSWORD=__GENERATE__",
        )
        for line in generated_secrets:
            with self.subTest(secret=line):
                self.assertIn(line, self.env_example.splitlines())
        self.assertNotIn("admin/admin", self.env_example.lower())

    def test_root_compose_identifies_the_release_equivalent_entrypoint(self) -> None:
        header = "\n".join(self.root_compose.splitlines()[:5])
        self.assertIn("开发兼容入口", header)
        self.assertIn("deploy/compose/docker-compose.yml", header)


if __name__ == "__main__":
    unittest.main()

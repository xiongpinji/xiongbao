import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = ROOT / "deploy" / "compose" / "docker-compose.yml"
ENV_PATH = ROOT / "deploy" / "compose" / "r2.env.example"
ROOT_COMPOSE_PATH = ROOT / "docker-compose.yml"


def read_or_empty(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


class R2ComposeContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
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

    def test_default_config_does_not_require_optional_profile_secrets(self) -> None:
        environment = os.environ.copy()
        for variable in (
            "GRAFANA_ADMIN_PASSWORD",
            "XAGENT_PLATFORM_MCP_TOKEN",
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
                    "docker",
                    "compose",
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
            'XAGENT_CORS_ORIGINS=["http://127.0.0.1:18080"]',
            "XAGENT_SECURITY__REQUIRE_AUTH=true",
            "XAGENT_LLM__OLLAMA_BASE_URL=http://host.docker.internal:11434",
            "XAGENT_LLM__OLLAMA_MODEL=qwen3:4b",
            "XAGENT_LLM__DEFAULT_MODEL=qwen3:4b",
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

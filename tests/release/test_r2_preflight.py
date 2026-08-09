import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.r2_preflight import check_ports, init_env, load_env, main, validate_env


class R2PreflightTest(unittest.TestCase):
    def test_init_env_generates_secrets_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "r2.env.example"
            target = root / "r2.env.local"
            template.write_text(
                "POSTGRES_PASSWORD=__GENERATE__\n"
                "XAGENT_SECURITY__JWT_SECRET=__GENERATE__\n"
                "XAGENT_PLATFORM_MCP_TOKEN=__GENERATE__\n"
                "GRAFANA_ADMIN_PASSWORD=__GENERATE__\n",
                encoding="utf-8",
            )

            init_env(template, target)
            values = load_env(target)

            self.assertEqual(set(values), {
                "POSTGRES_PASSWORD",
                "XAGENT_SECURITY__JWT_SECRET",
                "XAGENT_PLATFORM_MCP_TOKEN",
                "GRAFANA_ADMIN_PASSWORD",
            })
            for value in values.values():
                self.assertGreaterEqual(len(value), 32)
                self.assertNotEqual(value, "__GENERATE__")
            with self.assertRaises(FileExistsError):
                init_env(template, target)

    def test_load_env_parses_only_simple_key_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / "r2.env.local"
            env_file.write_text(
                "# comment\n"
                "\n"
                "POSTGRES_PASSWORD = strong-postgres-password\n"
                "MALFORMED\n"
                "XAGENT_CORS_ORIGINS=[\"http://127.0.0.1:18080\"]\n",
                encoding="utf-8",
            )

            values = load_env(env_file)

            self.assertEqual(values["POSTGRES_PASSWORD"], "strong-postgres-password")
            self.assertEqual(values["XAGENT_CORS_ORIGINS"], "[\"http://127.0.0.1:18080\"]")
            self.assertNotIn("MALFORMED", values)

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
                "weak_postgres_password",
                "weak_jwt_secret",
                "weak_mcp_token",
                "weak_grafana_password",
                "auth_disabled",
                "wildcard_cors",
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
        self.assertIn("weak_jwt_secret", {item["code"] for item in errors})

    def test_init_env_cli_writes_safe_json_without_git_clean_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            compose_dir = root / "deploy" / "compose"
            compose_dir.mkdir(parents=True)
            template = compose_dir / "r2.env.example"
            env_file = compose_dir / "r2.env.local"
            output = root / "output" / "r2-runtime" / "preflight.json"
            template.write_text(
                "POSTGRES_PASSWORD=__GENERATE__\n"
                "XAGENT_SECURITY__JWT_SECRET=__GENERATE__\n"
                "XAGENT_PLATFORM_MCP_TOKEN=__GENERATE__\n"
                "GRAFANA_ADMIN_PASSWORD=__GENERATE__\n"
                "XAGENT_SECURITY__REQUIRE_AUTH=true\n"
                "XAGENT_CORS_ORIGINS=[\"http://127.0.0.1:18080\"]\n"
                "XAGENT_LLM__OLLAMA_MODEL=qwen3:4b\n",
                encoding="utf-8",
            )

            exit_code = main([
                "--env-file", str(env_file),
                "--compose-file", str(compose_dir / "docker-compose.yml"),
                "--project-name", "xagent-r2",
                "--expected-branch", "dirty-branch-should-not-be-checked",
                "--output", str(output),
                "--init-env", str(env_file),
            ])

            values = load_env(env_file)
            report_text = output.read_text(encoding="utf-8")
            report = json.loads(report_text)
            self.assertEqual(exit_code, 0)
            self.assertTrue(report["ok"])
            self.assertEqual([check["name"] for check in report["checks"]], ["env"])
            for key in (
                "POSTGRES_PASSWORD",
                "XAGENT_SECURITY__JWT_SECRET",
                "XAGENT_PLATFORM_MCP_TOKEN",
                "GRAFANA_ADMIN_PASSWORD",
            ):
                value = values[key]
                self.assertNotIn(value, report_text)

    def test_full_preflight_runs_checks_in_order_with_non_secret_details(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env_file = root / "r2.env.local"
            compose_file = root / "docker-compose.yml"
            output = root / "preflight.json"
            env_file.write_text(
                "POSTGRES_PASSWORD=secret-postgres-value\n"
                "XAGENT_SECURITY__JWT_SECRET=jwt-secret-value-at-least-32-characters\n"
                "XAGENT_PLATFORM_MCP_TOKEN=mcp-token-value-at-least-32-characters\n"
                "GRAFANA_ADMIN_PASSWORD=grafana-password-value\n"
                "XAGENT_SECURITY__REQUIRE_AUTH=true\n"
                "XAGENT_CORS_ORIGINS=[\"http://127.0.0.1:18080\"]\n"
                "XAGENT_LLM__OLLAMA_MODEL=qwen3:4b\n"
                "XAGENT_POSTGRES_PORT=25432\n"
                "XAGENT_REDIS_PORT=26379\n"
                "XAGENT_QDRANT_HTTP_PORT=26333\n"
                "XAGENT_QDRANT_GRPC_PORT=26334\n"
                "XAGENT_API_PORT=28000\n"
                "XAGENT_WEB_PORT=28080\n"
                "XAGENT_MCP_PORT=28100\n"
                "XAGENT_PROMETHEUS_PORT=29090\n"
                "XAGENT_GRAFANA_PORT=23002\n",
                encoding="utf-8",
            )
            compose_file.write_text("services: {}\n", encoding="utf-8")

            command_results = [
                mock.Mock(returncode=0, stdout="feature/webapi-r2-staging-readiness\n", stderr=""),
                mock.Mock(returncode=0, stdout="", stderr=""),
                mock.Mock(returncode=0, stdout="abc123\n", stderr=""),
                mock.Mock(returncode=0, stdout="Docker version\n", stderr=""),
                mock.Mock(returncode=0, stdout="Docker Compose version\n", stderr=""),
                mock.Mock(returncode=0, stdout="", stderr=""),
            ]
            with mock.patch("scripts.r2_preflight.run_command", side_effect=command_results) as run_command, \
                    mock.patch("scripts.r2_preflight.check_port_available", return_value=True), \
                    mock.patch("scripts.r2_preflight.fetch_ollama_models", return_value={"qwen3:4b"}):
                exit_code = main([
                    "--env-file", str(env_file),
                    "--compose-file", str(compose_file),
                    "--project-name", "xagent-r2",
                    "--expected-branch", "feature/webapi-r2-staging-readiness",
                    "--output", str(output),
                ])

            report_text = output.read_text(encoding="utf-8")
            report = json.loads(report_text)
            self.assertEqual(exit_code, 0)
            self.assertTrue(report["ok"])
            self.assertEqual(
                [check["name"] for check in report["checks"]],
                ["env", "git", "docker", "docker_compose", "ports", "ollama", "compose_config"],
            )
            self.assertEqual(
                [call.args[0] for call in run_command.call_args_list],
                [
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    ["git", "status", "--porcelain"],
                    ["git", "rev-parse", "HEAD"],
                    ["docker", "version"],
                    ["docker", "compose", "version"],
                    [
                        "docker", "compose", "--env-file", str(env_file),
                        "-f", str(compose_file), "-p", "xagent-r2", "config", "--quiet",
                    ],
                ],
            )
            for secret in (
                "secret-postgres-value",
                "jwt-secret-value-at-least-32-characters",
                "mcp-token-value-at-least-32-characters",
                "grafana-password-value",
            ):
                self.assertNotIn(secret, report_text)

    def test_allow_running_project_accepts_only_same_project_port_mapping(self) -> None:
        values = {"XAGENT_BIND_ADDRESS": "127.0.0.1", "XAGENT_API_PORT": "28000"}
        with mock.patch("scripts.r2_preflight.check_port_available", return_value=False), \
                mock.patch("scripts.r2_preflight.run_command") as run_command:
            run_command.return_value = mock.Mock(returncode=0, stdout="127.0.0.1:28000\n", stderr="")
            checks: list[dict[str, object]] = []

            ok = check_ports(
                checks,
                values,
                Path("r2.env.local"),
                Path("docker-compose.yml"),
                "xagent-r2",
                allow_running_project=True,
            )

            self.assertTrue(ok)
            self.assertEqual(checks, [{"name": "ports", "ok": True, "detail": "1 candidate ports available"}])

        with mock.patch("scripts.r2_preflight.check_port_available", return_value=False), \
                mock.patch("scripts.r2_preflight.run_command") as run_command:
            run_command.return_value = mock.Mock(returncode=1, stdout="", stderr="not found")
            checks = []

            ok = check_ports(
                checks,
                values,
                Path("r2.env.local"),
                Path("docker-compose.yml"),
                "xagent-r2",
                allow_running_project=True,
            )

            self.assertFalse(ok)
            self.assertIn("XAGENT_API_PORT:28000", checks[0]["detail"])


if __name__ == "__main__":
    unittest.main()

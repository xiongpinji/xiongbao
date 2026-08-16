from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
CI_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PROMPTFOO_CONFIG_PATH = REPO_ROOT / ".promptfoo" / "config.yaml"
RESULT_CHECKER_PATH = REPO_ROOT / "scripts" / "check_promptfoo_results.py"


class R3PromptfooContractTests(unittest.TestCase):
    def test_ci_uses_an_authenticated_fail_closed_promptfoo_gate(self) -> None:
        workflow = yaml.load(
            CI_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader
        )
        job = workflow["jobs"]["promptfoo-eval"]
        steps = {step.get("name"): step for step in job["steps"] if step.get("name")}

        self.assertIn(
            "vars.XAGENT_PAID_EVAL_AUTHORIZED == 'true'",
            job.get("if", ""),
        )
        self.assertIn("github.event_name == 'workflow_dispatch'", job.get("if", ""))
        self.assertIn("inputs.paid_eval_source_sha == github.sha", job.get("if", ""))
        self.assertIn(
            "inputs.paid_eval_authorization == 'one_batch_8_calls'",
            job.get("if", ""),
        )
        self.assertIn(
            "inputs.paid_eval_authorization",
            job["env"].get("XAGENT_PAID_EVAL_AUTHORIZATION", ""),
        )
        self.assertEqual(
            job["env"].get("XAGENT_LLM__DEFAULT_MODEL"),
            "deepseek-chat",
        )
        self.assertEqual(
            job["env"].get("XAGENT_LLM__MAX_ATTEMPTS"),
            "1",
        )
        self.assertIn(
            "secrets.XAGENT_LLM_DEEPSEEK_API_KEY",
            job["env"].get("XAGENT_LLM__DEEPSEEK_API_KEY", ""),
        )
        self.assertEqual(job["env"]["XAGENT_SECURITY__REQUIRE_AUTH"], "true")
        self.assertEqual(steps["Configure CI JWT secret"]["run"].count("GITHUB_ENV"), 1)

        preflight = steps["Verify paid-model authorization"]
        self.assertIn("scripts/paid_model_eval_gate.py preflight", preflight["run"])
        self.assertIn("--expected-calls 8", preflight["run"])
        self.assertIn("--source-sha \"${GITHUB_SHA}\"", preflight["run"])

        registration = steps["Create Promptfoo member token"]["run"]
        self.assertIn("/api/v1/auth/register", registration)
        self.assertIn("PROMPTFOO_API_TOKEN", registration)
        self.assertIn("PROMPTFOO_TENANT_ID", registration)
        self.assertIn("::add-mask::", registration)
        self.assertIn("GITHUB_ENV", registration)

        self.assertEqual(
            steps["Install promptfoo"]["run"], "npm install -g promptfoo@0.122.0"
        )
        setup_node = next(
            step for step in job["steps"] if step.get("uses") == "actions/setup-node@v4"
        )
        self.assertEqual(setup_node["with"]["node-version"], "24")

        eval_command = steps["Run eval"]["run"]
        self.assertIn("--max-concurrency 1", eval_command)
        self.assertIn("--output /tmp/promptfoo-results.json", eval_command)
        self.assertNotIn("scripts/check_promptfoo_results.py", eval_command)

        finalize = steps["Finalize paid-model evidence"]["run"]
        self.assertIn("scripts/paid_model_eval_gate.py verify", finalize)
        self.assertIn("/tmp/promptfoo-results.json", finalize)
        self.assertIn("/tmp/paid-model-preflight.json", finalize)

        artifact = steps["Upload paid-model evidence"]
        self.assertIn("actions/upload-artifact@", artifact["uses"])
        self.assertIn("paid-model-evidence.json", artifact["with"]["path"])

    def test_ci_discovers_the_promptfoo_contract(self) -> None:
        workflow = yaml.safe_load(CI_PATH.read_text(encoding="utf-8"))
        steps = workflow["jobs"]["config-governance"]["steps"]
        contract = next(
            step for step in steps if step.get("name") == "R3 Promptfoo contract"
        )

        self.assertEqual(
            contract["run"],
            "python -m unittest discover -s tests/release "
            '-p "test_r3_promptfoo_contract.py" -v',
        )

    def test_promptfoo_target_uses_runtime_bearer_and_product_result_contract(
        self,
    ) -> None:
        source = PROMPTFOO_CONFIG_PATH.read_text(encoding="utf-8")
        config = yaml.safe_load(source)
        target = config["targets"][0]["config"]

        self.assertEqual(
            target["auth"],
            {"type": "bearer", "token": "{{env.PROMPTFOO_API_TOKEN}}"},
        )
        self.assertEqual(target["body"]["tool_mode"], "none")
        self.assertEqual(target["transformResponse"], "JSON.stringify(json)")
        self.assertEqual(target["maxRetries"], 0)
        self.assertIn("status >= 200", target["validateStatus"])
        self.assertNotIn("[mock] 收到", source)
        self.assertNotIn("最后一条用户内容：", source)

        assertions = config["defaultTest"]["assert"]
        javascript = "\n".join(
            assertion.get("value", "")
            for assertion in assertions
            if assertion.get("type") == "javascript"
        )
        for required in (
            "status",
            "succeeded",
            "run_id",
            "final_answer",
            "tenant_id",
            "PROMPTFOO_TENANT_ID",
            "context.vars.query",
            "result.goal.includes(query)",
            "result.final_answer.trim().length > 0",
        ):
            self.assertIn(required, javascript)
        self.assertNotIn("result.final_answer.includes(query)", javascript)
        self.assertIn("Traceback", source)
        self.assertIn("Internal Server Error", source)
        self.assertTrue(
            any(
                item.get("type") == "not-contains" and item.get("value") == "[mock]"
                for item in assertions
            )
        )

    def test_result_checker_accepts_only_the_complete_expected_matrix(self) -> None:
        result = self._run_checker(successes=8, failures=0, errors=0, expected=8)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("8/8", result.stdout)

    def test_result_checker_rejects_zero_executed_evaluations(self) -> None:
        result = self._run_checker(successes=0, failures=0, errors=0, expected=8)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected 8 evaluations, got 0", result.stderr)

    def test_result_checker_rejects_failed_or_error_evaluations(self) -> None:
        for stats in (
            {"successes": 7, "failures": 1, "errors": 0},
            {"successes": 7, "failures": 0, "errors": 1},
        ):
            with self.subTest(stats=stats):
                result = self._run_checker(expected=8, **stats)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("promptfoo quality gate failed", result.stderr)

    def test_result_checker_rejects_non_integer_stats(self) -> None:
        for successes, expected in (("8", 8), (8.9, 8), (True, 1)):
            with self.subTest(successes=successes):
                result = self._run_checker(
                    successes=successes,
                    failures=0,
                    errors=0,
                    expected=expected,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid promptfoo result", result.stderr)

    def _run_checker(
        self, *, successes: object, failures: object, errors: object, expected: int
    ) -> subprocess.CompletedProcess[str]:
        payload = {
            "results": {
                "stats": {
                    "successes": successes,
                    "failures": failures,
                    "errors": errors,
                }
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            result_path = Path(directory) / "promptfoo-results.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")
            return subprocess.run(
                [
                    sys.executable,
                    str(RESULT_CHECKER_PATH),
                    str(result_path),
                    "--expected",
                    str(expected),
                ],
                check=False,
                capture_output=True,
                text=True,
            )


if __name__ == "__main__":
    unittest.main()

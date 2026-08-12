from __future__ import annotations

import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
LOAD_SCRIPT_PATH = REPO_ROOT / "tests" / "load" / "k6-load.js"
CI_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


class R3LoadContractTests(unittest.TestCase):
    def test_metrics_uses_a_realistic_dedicated_scrape_scenario(self) -> None:
        source = LOAD_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("api_traffic:", source)
        self.assertIn('exec: "apiTraffic"', source)
        self.assertIn("metrics_scrape:", source)
        self.assertIn('exec: "metricsScrape"', source)
        self.assertIn("rate: 1", source)
        self.assertIn('timeUnit: "15s"', source)
        self.assertIn("http_req_duration{scenario:api_traffic}", source)
        self.assertIn('"checks{scenario:metrics_scrape}": ["rate>0.999"]', source)
        self.assertIn('"errors{scenario:metrics_scrape}": ["rate<0.001"]', source)
        api_traffic = source.split("export function apiTraffic()", 1)[1].split(
            "export function metricsScrape()", 1
        )[0]
        self.assertNotIn("/metrics", api_traffic)

    def test_load_checks_cover_the_expected_security_responses(self) -> None:
        source = LOAD_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn('"checks{scenario:api_traffic}": ["rate>0.99"]', source)
        self.assertIn("[401, 404, 422, 429].includes(r.status)", source)

    def test_summary_collects_the_p99_value_it_reports(self) -> None:
        source = LOAD_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn(
            'summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"]',
            source,
        )
        self.assertIn(
            'const apiDuration = metrics["http_req_duration{scenario:api_traffic}"]',
            source,
        )
        self.assertIn('const p99 = apiDuration?.values?.["p(99)"] || 0', source)

    def test_ci_disables_the_global_rate_limiter_for_the_load_job(self) -> None:
        workflow = yaml.load(
            CI_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader
        )

        self.assertEqual(
            workflow["jobs"]["load-test"]["env"]["XAGENT_SECURITY__RATE_LIMIT_ENABLED"],
            "false",
        )

    def test_ci_discovers_the_r3_load_contract(self) -> None:
        workflow = yaml.safe_load(CI_PATH.read_text(encoding="utf-8"))
        steps = workflow["jobs"]["config-governance"]["steps"]
        contract = next(
            step for step in steps if step.get("name") == "R3 load contract"
        )

        self.assertEqual(
            contract["run"],
            "python -m unittest discover -s tests/release "
            '-p "test_r3_load_contract.py" -v',
        )


if __name__ == "__main__":
    unittest.main()

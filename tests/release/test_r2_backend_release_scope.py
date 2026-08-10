from __future__ import annotations

import ast
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPO_ROOT / "scripts" / "run_webapi_release_tests.py"
CI_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"

EXPECTED_EXCLUDED_MODULES = {
    "tests/test_audio_providers.py",
    "tests/test_canvas_extras.py",
    "tests/test_canvas_workflow.py",
    "tests/test_creative_persistence.py",
    "tests/test_creative_studio.py",
    "tests/test_e2e_drama_canvas.py",
    "tests/test_editor.py",
    "tests/test_media.py",
    "tests/test_media_task.py",
    "tests/test_pipeline.py",
    "tests/test_producer.py",
    "tests/test_sandbox_e2b.py",
}
EXPECTED_EXCLUDED_NODES = {
    "tests/test_runtime_runs.py::test_runs_api_normalizes_creative_production_status",
}


def _literal_assignment(source: str, name: str) -> set[str]:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            return set(value)
    raise AssertionError(f"missing literal assignment: {name}")


class R2BackendReleaseScopeTests(unittest.TestCase):
    def test_runner_declares_the_complete_product_exclusion_boundary(self) -> None:
        self.assertTrue(RUNNER_PATH.is_file(), "Web/API release test runner is missing")
        source = RUNNER_PATH.read_text(encoding="utf-8")

        self.assertEqual(
            _literal_assignment(source, "EXCLUDED_TEST_MODULES"),
            EXPECTED_EXCLUDED_MODULES,
        )
        self.assertEqual(
            _literal_assignment(source, "EXCLUDED_TEST_NODES"),
            EXPECTED_EXCLUDED_NODES,
        )
        self.assertIn("sys.path.insert(0, str(API_ROOT))", source)
        self.assertIn("pytest.main", source)

    def test_backend_ci_uses_the_reproducible_webapi_scope(self) -> None:
        workflow = CI_PATH.read_text(encoding="utf-8")

        self.assertIn(
            "name: Test (Web/API release scope)\n        run: python ../../scripts/run_webapi_release_tests.py",
            workflow,
        )
        self.assertNotIn("name: Test (pytest)\n        run: pytest -q", workflow)


if __name__ == "__main__":
    unittest.main()

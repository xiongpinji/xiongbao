from scripts import run_backend_commercial_tests as runner


def test_commercial_runner_has_no_exclusions() -> None:
    assert runner.pytest_args() == ["-ra", "-q", "tests"]


def test_commercial_runner_targets_api_root() -> None:
    assert runner.API_ROOT.name == "api"
    assert (runner.API_ROOT / "tests").is_dir()

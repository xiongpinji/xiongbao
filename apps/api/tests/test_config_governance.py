"""P0 平台级配置治理与差异控制 — 门禁脚本回归测试。

覆盖对象（仓库根 scripts/，按文件路径动态加载，与被测脚本自定位 REPO_ROOT 兼容）：

- ``scripts/validate_helm_values.py``：四环境生产就绪校验
- ``scripts/render_env_diff.py``：环境 values 结构化 diff

同时把"环境差异策略"固化为机器校验：
``REQUIRED_DIFF_KEYS`` 在 dev 与 prod/enterprise 之间必须全部不同，
``REQUIRED_SAME_KEYS`` 在四个环境之间必须一致。
策略文档见 docs/CONFIG_GOVERNANCE_V1.md。
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from itertools import combinations
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"

ENVS = ("dev", "staging", "prod", "enterprise")

# prod/enterprise 相对 dev 必须全部不同的键（安全与可用性分级红线）
REQUIRED_DIFF_KEYS = (
    "config.debug",
    "config.corsOrigins",
    "secrets.eso.enabled",
    "networkPolicy.enabled",
    "pdb.enabled",
    "alerting.enabled",
    "replicaCount",
)

# 四个环境必须保持一致的键（平台统一安全基线）
REQUIRED_SAME_KEYS = (
    "security.requireAuth",
    "serviceAccount.automountServiceAccountToken",
)


def _load_script(name: str):
    path = SCRIPTS_DIR / f"{name}.py"
    assert path.exists(), f"missing script: {path}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


validate_mod = _load_script("validate_helm_values")
diff_mod = _load_script("render_env_diff")


def _criticals(errors: list[str]) -> list[str]:
    return [e for e in errors if "[CRITICAL]" in e]


# ---------------------------------------------------------------------------
# validate_helm_values：真实环境全量通过
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("env", ENVS)
def test_real_env_values_pass_validation(env: str) -> None:
    values = validate_mod.load_values(env)
    errors = validate_mod.validate(env, values)
    assert _criticals(errors) == [], f"{env} has CRITICAL errors: {errors}"


# ---------------------------------------------------------------------------
# validate_helm_values：篡改用例必须产生对应 CRITICAL
# ---------------------------------------------------------------------------


def _prod_values() -> dict:
    return validate_mod.load_values("prod")


def _set(d: dict, dotted_key: str, value) -> None:
    keys = dotted_key.split(".")
    cur = d
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    cur[keys[-1]] = value


@pytest.mark.parametrize(
    ("dotted_key", "bad_value", "expected_fragment"),
    [
        ("config.debug", True, "config.debug"),
        ("security.jwtSecret", "real-looking-prod-secret-123", "plaintext security.jwtSecret"),
        ("networkPolicy.enabled", False, "networkPolicy.enabled"),
        ("pdb.enabled", False, "pdb.enabled"),
        ("alerting.enabled", False, "alerting.enabled"),
        ("config.corsOrigins", "*", "wildcard CORS"),
        ("security.requireAuth", False, "authentication"),
    ],
)
def test_prod_tampering_triggers_critical(
    dotted_key: str, bad_value, expected_fragment: str
) -> None:
    values = _prod_values()
    _set(values, dotted_key, bad_value)
    errors = _criticals(validate_mod.validate("prod", values))
    assert any(
        expected_fragment in e for e in errors
    ), f"tampering {dotted_key}={bad_value!r} did not raise expected CRITICAL: {errors}"


def test_prod_without_eso_and_without_secret_ref_fails() -> None:
    values = _prod_values()
    _set(values, "secrets.eso.enabled", False)
    errors = _criticals(validate_mod.validate("prod", values))
    assert any("secrets.eso.enabled" in e for e in errors)


def test_staging_insecure_jwt_without_eso_warns() -> None:
    values = validate_mod.load_values("staging")
    _set(values, "secrets.eso.enabled", False)
    _set(values, "security.existingJwtSecretRef.name", "")
    _set(values, "security.jwtSecret", "change-me")
    errors = validate_mod.validate("staging", values)
    assert any("[WARNING]" in e and "jwtSecret" in e for e in errors)
    assert _criticals(errors) == []


# ---------------------------------------------------------------------------
# render_env_diff：合并 / 扁平化 / diff 行为
# ---------------------------------------------------------------------------


def test_deep_merge_overlay_wins_and_preserves_siblings() -> None:
    base = {"a": {"x": 1, "y": 2}, "b": 3}
    overlay = {"a": {"y": 20, "z": 30}}
    merged = diff_mod._deep_merge(base, overlay)
    assert merged == {"a": {"x": 1, "y": 20, "z": 30}, "b": 3}


def test_flatten_produces_dotted_keys() -> None:
    flat = diff_mod.flatten({"a": {"b": {"c": 1}}, "d": "x"})
    assert flat == {"a.b.c": "1", "d": "'x'"}


def test_dev_to_prod_diff_contains_governance_keys() -> None:
    diffs = diff_mod.compute_diff(
        diff_mod.load_values("dev"), diff_mod.load_values("prod")
    )
    changed = {d["key"] for d in diffs}
    assert diffs, "dev->prod diff must not be empty"
    for key in REQUIRED_DIFF_KEYS:
        assert key in changed, f"expected dev->prod diff to include {key}"


def test_render_json_structure() -> None:
    diffs = [{"key": "a.b", "from": "1", "to": "2"}]
    payload = json.loads(diff_mod.render_json(diffs, "dev", "prod"))
    assert payload["from"] == "dev"
    assert payload["to"] == "prod"
    assert payload["total_diffs"] == 1
    assert payload["changes"] == diffs


def test_render_markdown_table() -> None:
    out = diff_mod.render_markdown([{"key": "a.b", "from": "1", "to": "2"}], "dev", "prod")
    assert "# Values Diff: dev -> prod" in out
    assert "`a.b`" in out


# ---------------------------------------------------------------------------
# 环境差异策略（差异控制的机器校验核心）
# ---------------------------------------------------------------------------


def _flat(env: str) -> dict[str, str]:
    return diff_mod.flatten(diff_mod.load_values(env))


def test_required_diff_keys_differ_between_dev_and_strict_envs() -> None:
    dev = _flat("dev")
    for env in ("prod", "enterprise"):
        other = _flat(env)
        for key in REQUIRED_DIFF_KEYS:
            assert dev.get(key) != other.get(key), (
                f"{key} must differ between dev and {env}: "
                f"dev={dev.get(key)} {env}={other.get(key)}"
            )


def test_no_two_envs_are_identical_on_governance_keys() -> None:
    for env_a, env_b in combinations(ENVS, 2):
        flat_a, flat_b = _flat(env_a), _flat(env_b)
        differing = [
            k for k in REQUIRED_DIFF_KEYS if flat_a.get(k) != flat_b.get(k)
        ]
        assert differing, (
            f"{env_a} and {env_b} are identical on all REQUIRED_DIFF_KEYS"
        )


def test_required_same_keys_consistent_across_envs() -> None:
    flats = {env: _flat(env) for env in ENVS}
    for key in REQUIRED_SAME_KEYS:
        values = {env: flats[env].get(key) for env in ENVS}
        assert len(set(values.values())) == 1, (
            f"{key} must be identical across envs, got {values}"
        )


def test_loaded_values_are_deepcopiable() -> None:
    # validate() 的篡改用例依赖 values 可安全深拷贝/就地修改而不影响后续加载
    values = copy.deepcopy(_prod_values())
    _set(values, "config.debug", True)
    assert validate_mod.load_values("prod")["config"]["debug"] is False

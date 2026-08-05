#!/usr/bin/env python3
"""Validate Helm values for production readiness.

Checks that production/enterprise environments enforce:
- ESO or existingSecretRef (no plaintext secrets)
- NetworkPolicy enabled
- PDB enabled
- Alerting enabled
- No debug mode

Usage:
  python scripts/validate_helm_values.py --env prod
  python scripts/validate_helm_values.py --env enterprise
  python scripts/validate_helm_values.py --env staging
  python scripts/validate_helm_values.py --env dev  # relaxed checks
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    raise SystemExit(1)


REPO_ROOT = Path(__file__).resolve().parents[1]
HELM_DIR = REPO_ROOT / "deploy" / "helm"
ENVIRONMENTS_DIR = HELM_DIR / "environments"

INSECURE_JWT_SECRETS = {
    "",
    "dev-insecure-lite-jwt-secret-for-local-only",
    "dev-insecure-change-me",
    "change-me",
    "change-me-to-random",
    "change-me-to-a-long-random-secret",
}

STRICT_ENVS = {"prod", "enterprise"}
MODERATE_ENVS = {"staging"}


def load_values(env: str) -> dict:
    """Load base values merged with environment overlay."""
    base_path = HELM_DIR / "values.yaml"
    with open(base_path, encoding="utf-8") as f:
        base = yaml.safe_load(f) or {}

    env_path = ENVIRONMENTS_DIR / f"values-{env}.yaml"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            overlay = yaml.safe_load(f) or {}
        base = _deep_merge(base, overlay)

    return base


def _deep_merge(base: dict, overlay: dict) -> dict:
    result = dict(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def validate(env: str, values: dict) -> list[str]:
    """Return list of validation errors (empty = pass)."""
    errors: list[str] = []
    is_strict = env in STRICT_ENVS
    is_moderate = env in MODERATE_ENVS

    # --- Secret management ---
    eso_enabled = _get(values, "secrets.eso.enabled", False)
    jwt_secret = _get(values, "security.jwtSecret", "")
    jwt_ref = _get(values, "security.existingJwtSecretRef.name", "")

    if is_strict:
        if not eso_enabled:
            errors.append("[CRITICAL] prod/enterprise must enable secrets.eso.enabled=true")
        if jwt_secret and jwt_secret not in INSECURE_JWT_SECRETS:
            errors.append("[CRITICAL] prod/enterprise must not have plaintext security.jwtSecret; use ESO or existingJwtSecretRef")
        if not eso_enabled and not jwt_ref:
            errors.append("[CRITICAL] prod/enterprise must provide security.existingJwtSecretRef.name or enable ESO")
    elif is_moderate:
        if jwt_secret in INSECURE_JWT_SECRETS and not jwt_ref and not eso_enabled:
            errors.append("[WARNING] staging should use ESO or existingJwtSecretRef instead of insecure default jwtSecret")

    # --- Debug mode ---
    debug = _get(values, "config.debug", False)
    if is_strict and debug:
        errors.append("[CRITICAL] prod/enterprise must not enable config.debug=true")

    # --- NetworkPolicy ---
    np_enabled = _get(values, "networkPolicy.enabled", False)
    if is_strict and not np_enabled:
        errors.append("[CRITICAL] prod/enterprise must enable networkPolicy.enabled=true")

    # --- PDB ---
    pdb_enabled = _get(values, "pdb.enabled", False)
    if is_strict and not pdb_enabled:
        errors.append("[CRITICAL] prod/enterprise must enable pdb.enabled=true")

    # --- Alerting ---
    alerting_enabled = _get(values, "alerting.enabled", False)
    if is_strict and not alerting_enabled:
        errors.append("[CRITICAL] prod/enterprise must enable alerting.enabled=true")
    elif is_moderate and not alerting_enabled:
        errors.append("[WARNING] staging should enable alerting.enabled=true")

    # --- CORS ---
    cors = _get(values, "config.corsOrigins", "")
    if is_strict and "*" in cors:
        errors.append("[CRITICAL] prod/enterprise must not use wildcard CORS origins")

    # --- Auth ---
    require_auth = _get(values, "security.requireAuth", True)
    if is_strict and require_auth is False:
        errors.append("[CRITICAL] prod/enterprise must not disable authentication")

    # --- Replica count ---
    replicas = _get(values, "replicaCount", 1)
    if is_strict and replicas < 3:
        errors.append(f"[WARNING] prod/enterprise recommends replicaCount >= 3, got {replicas}")

    return errors


def _get(d: dict, dotted_key: str, default=None):
    """Get nested value by dotted key path."""
    keys = dotted_key.split(".")
    current = d
    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return default
    return current


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env",
        required=True,
        choices=["dev", "staging", "prod", "enterprise"],
        help="Target environment to validate.",
    )
    args = parser.parse_args()

    values = load_values(args.env)
    errors = validate(args.env, values)

    if not errors:
        print(f"PASS: {args.env} environment values validation passed.")
        return 0

    critical = [e for e in errors if "[CRITICAL]" in e]
    warnings = [e for e in errors if "[WARNING]" in e]

    for err in errors:
        print(err, file=sys.stderr)

    print(f"\nFAIL: {len(critical)} critical, {len(warnings)} warnings for env={args.env}", file=sys.stderr)
    return 1 if critical else 0


if __name__ == "__main__":
    raise SystemExit(main())

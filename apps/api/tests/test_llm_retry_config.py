from __future__ import annotations

import pytest
from xagent.core.orchestration.loop import _resolve_llm_max_attempts


def test_llm_max_attempts_defaults_to_three() -> None:
    assert _resolve_llm_max_attempts({}) == 3


def test_paid_evaluation_can_disable_application_retries() -> None:
    assert _resolve_llm_max_attempts({"XAGENT_LLM__MAX_ATTEMPTS": "1"}) == 1


@pytest.mark.parametrize("value", ["0", "4", "invalid"])
def test_llm_max_attempts_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(ValueError, match="XAGENT_LLM__MAX_ATTEMPTS"):
        _resolve_llm_max_attempts({"XAGENT_LLM__MAX_ATTEMPTS": value})

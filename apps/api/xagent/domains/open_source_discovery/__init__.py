"""开源候选发现（★护城河）：多源聚合 + 统一评分。

开源界无直接对标（browser-use/Composio 偏工具调用，非"多源候选发现+打分"）。
收敛旧仓 20 个 provider 为统一评分函数。Phase 3：内置模拟 provider + 评分；
真实 provider（GitHub/PyPI/npm/Maven/crates…）按需接入同一接口。
"""

from xagent.domains.open_source_discovery.engine import (
    DiscoveryEngine,
    discover_and_rank,
    get_discovery_engine,
    reset_discovery_engine,
)
from xagent.domains.open_source_discovery.models import Candidate, ScoredCandidate

__all__ = [
    "Candidate",
    "ScoredCandidate",
    "DiscoveryEngine",
    "discover_and_rank",
    "get_discovery_engine",
    "reset_discovery_engine",
]

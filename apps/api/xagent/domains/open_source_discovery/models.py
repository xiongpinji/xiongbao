"""候选发现数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Candidate:
    name: str
    source: str  # github / pypi / npm / maven / crates ...
    url: str = ""
    description: str = ""
    stars: int = 0
    license: str = ""
    last_updated: str = ""
    language: str = ""
    topics: list[str] = field(default_factory=list)


@dataclass
class ScoredCandidate:
    candidate: Candidate
    score: float
    breakdown: dict[str, float] = field(default_factory=dict)
    license_ok: bool = True
    notes: str = ""

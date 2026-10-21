from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Decision(StrEnum):
    STRONG = "strong"
    MAYBE = "maybe"
    REVIEW = "review"
    REJECT = "reject"


@dataclass(frozen=True)
class Job:
    external_id: str
    company: str
    title: str
    location: str = ""
    description: str = ""
    source: str = ""
    source_url: str = ""
    apply_url: str = ""
    ats_type: str = ""
    ats_job_id: str = ""
    published_at: str = ""
    discovered_at: str = ""
    location_status: str = "unknown"  # sweden, outside_sweden, or unknown
    updated_at: str = ""
    application_deadline: str = ""
    removed: bool = False

    @property
    def searchable_text(self) -> str:
        return " ".join((self.title, self.location, self.description)).lower()


@dataclass(frozen=True)
class Evidence:
    category: str
    signal: str
    excerpt: str
    impact: int
    confidence: float


@dataclass(frozen=True)
class ScoreResult:
    score: int
    confidence: float
    decision: Decision
    hard_blocker: bool
    blocker_reason: str | None
    dimensions: dict[str, int]
    evidence: list[Evidence] = field(default_factory=list)

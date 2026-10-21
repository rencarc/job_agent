from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class QueryCoverage:
    query: str
    fetched: int
    total_available: int | None
    pages_requested: int = 1
    status: str = "ok"
    error: str | None = None
    date_unknown: int = 0


@dataclass
class SourceCoverage:
    source: str
    status: str
    started_at: str
    completed_at: str
    queries: list[QueryCoverage] = field(default_factory=list)
    fetched: int = 0
    unique: int = 0
    duplicates: int = 0
    error: str | None = None


@dataclass
class CoverageReport:
    run_id: str
    started_at: str
    completed_at: str
    sources: list[SourceCoverage]
    total_fetched: int
    total_unique: int
    total_duplicates: int

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

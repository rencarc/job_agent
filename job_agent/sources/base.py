from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from job_agent.models import Job


@dataclass(frozen=True)
class QueryResult:
    query: str
    jobs: list[Job]
    total_available: int | None = None
    pages_requested: int = 1


@dataclass(frozen=True)
class FetchResult:
    source: str
    queries: list[QueryResult] = field(default_factory=list)

    @property
    def jobs(self) -> list[Job]:
        return [job for query in self.queries for job in query.jobs]


class JobSource(Protocol):
    name: str

    def fetch(self, queries: list[str], *, limit_per_query: int = 100,
              published_after: str | None = None) -> FetchResult:
        """Fetch and normalize jobs for every query."""


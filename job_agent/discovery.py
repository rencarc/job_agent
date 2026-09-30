from __future__ import annotations

import json
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from .coverage import CoverageReport, QueryCoverage, SourceCoverage, utc_now
from .dedup import ats_identity, canonical_url, fingerprint
from .models import Job
from .sources.base import JobSource


class DedupIndex:
    def __init__(self) -> None:
        self.ats_ids: set[tuple[str, str]] = set()
        self.urls: set[str] = set()
        self.fingerprints: set[str] = set()

    def add_if_new(self, job: Job) -> bool:
        identity = ats_identity(job)
        url = canonical_url(job.apply_url or job.source_url)
        key = fingerprint(job)
        duplicate = bool(
            (identity and identity in self.ats_ids)
            or (url and url in self.urls)
            or (key and key in self.fingerprints)
        )
        if duplicate:
            return False
        if identity:
            self.ats_ids.add(identity)
        if url:
            self.urls.add(url)
        if key:
            self.fingerprints.add(key)
        return True


def discover(source: JobSource, queries: list[str], *, limit_per_query: int = 100,
             published_after: str | None = None) -> tuple[list[Job], CoverageReport]:
    started = utc_now()
    index = DedupIndex()
    unique: list[Job] = []
    duplicates = 0
    try:
        fetched = source.fetch(queries, limit_per_query=limit_per_query,
                               published_after=published_after)
        for job in fetched.jobs:
            if index.add_if_new(job):
                unique.append(job)
            else:
                duplicates += 1
        completed = utc_now()
        source_report = SourceCoverage(
            source=source.name,
            status="ok",
            started_at=started,
            completed_at=completed,
            queries=[QueryCoverage(q.query, len(q.jobs), q.total_available, q.pages_requested) for q in fetched.queries],
            fetched=len(fetched.jobs),
            unique=len(unique),
            duplicates=duplicates,
        )
    except Exception as exc:
        completed = utc_now()
        source_report = SourceCoverage(
            source=source.name,
            status="failed",
            started_at=started,
            completed_at=completed,
            error=f"{type(exc).__name__}: {exc}",
        )
    seed = f"{source.name}|{started}|{'|'.join(queries)}"
    report = CoverageReport(
        run_id=sha256(seed.encode()).hexdigest()[:16],
        started_at=started,
        completed_at=completed,
        sources=[source_report],
        total_fetched=source_report.fetched,
        total_unique=source_report.unique,
        total_duplicates=source_report.duplicates,
    )
    return unique, report


def discover_many(sources: list[JobSource], queries: list[str], *, limit_per_query: int = 100,
                  published_after: str | None = None) -> tuple[list[Job], CoverageReport]:
    """Keep per-source failures visible and deduplicate across source boundaries."""
    started = utc_now()
    index = DedupIndex()
    jobs: list[Job] = []
    reports: list[SourceCoverage] = []
    for source in sources:
        fetched, report = discover(source, queries, limit_per_query=limit_per_query,
                                   published_after=published_after)
        source_report = report.sources[0]
        for job in fetched:
            if index.add_if_new(job):
                jobs.append(job)
            else:
                source_report.unique -= 1
                source_report.duplicates += 1
        reports.append(source_report)
    completed = utc_now()
    return jobs, CoverageReport(
        sha256(f"{started}|{'|'.join(s.name for s in sources)}".encode()).hexdigest()[:16],
        started, completed, reports, sum(r.fetched for r in reports), len(jobs),
        sum(r.duplicates for r in reports),
    )


def write_jobs(path: Path, jobs: list[Job]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": utc_now(), "jobs": [asdict(job) for job in jobs]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

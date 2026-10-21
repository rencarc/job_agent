from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from job_agent.models import Job

from .base import FetchResult, QueryResult


DEFAULT_BASE_URL = "https://jobsearch.api.jobtechdev.se"


def _label(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("label") or value.get("name") or "")
    return str(value or "")


def _location(hit: dict[str, Any]) -> str:
    address = hit.get("workplace_address") or {}
    values = [address.get("city"), address.get("municipality"), address.get("region")]
    unique: list[str] = []
    for value in values:
        if value and value not in unique:
            unique.append(str(value))
    model = _label(hit.get("workplace_model"))
    if model and model.casefold() not in {v.casefold() for v in unique}:
        unique.append(model)
    return ", ".join(unique)


def normalize_hit(hit: dict[str, Any], *, discovered_at: str | None = None) -> Job:
    employer = hit.get("employer") or {}
    description = hit.get("description") or {}
    application = hit.get("application_details") or {}
    webpage_url = str(hit.get("webpage_url") or "")
    apply_url = str(application.get("url") or webpage_url)
    return Job(
        external_id=str(hit.get("id") or hit.get("external_id") or ""),
        company=str(employer.get("name") or employer.get("workplace") or "Unknown employer"),
        title=str(hit.get("headline") or _label(hit.get("occupation")) or "Untitled role"),
        location=_location(hit),
        description=str(description.get("text") or ""),
        source="jobtech",
        source_url=webpage_url,
        apply_url=apply_url,
        published_at=str(hit.get("publication_date") or ""),
        discovered_at=discovered_at or datetime.now(timezone.utc).isoformat(),
        location_status="sweden",
    )


class JobTechSource:
    """Read-only adapter for Arbetsförmedlingen's public JobSearch API."""

    name = "jobtech"

    def __init__(self, *, base_url: str = DEFAULT_BASE_URL,
                 loader: Callable[[str], dict[str, Any]] | None = None,
                 max_pages: int = 3) -> None:
        if not 1 <= max_pages <= 20:
            raise ValueError("max_pages must be between 1 and 20")
        self.base_url = base_url.rstrip("/")
        self._loader = loader or self._load_json
        self.max_pages = max_pages

    @staticmethod
    def _load_json(url: str) -> dict[str, Any]:
        request = Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "auditable-job-agent/0.1 (+personal job search)",
        })
        with urlopen(request, timeout=30) as response:
            return json.load(response)

    def fetch(self, queries: list[str], *, limit_per_query: int = 100,
              published_after: str | None = None) -> FetchResult:
        if not 1 <= limit_per_query <= 100:
            raise ValueError("limit_per_query must be between 1 and 100")
        results: list[QueryResult] = []
        discovered_at = datetime.now(timezone.utc).isoformat()
        for query in queries:
            jobs: list[Job] = []
            total = None
            pages = 0
            error = None
            complete = False
            for page in range(self.max_pages):
                params: dict[str, str | int] = {"q": query, "limit": limit_per_query,
                                                "offset": page * limit_per_query, "sort": "pubdate-desc"}
                if published_after:
                    params["published-after"] = published_after
                url = f"{self.base_url}/search?{urlencode(params)}"
                try:
                    payload = self._loader(url)
                    hits = payload.get("hits") or []
                    batch = [normalize_hit(hit, discovered_at=discovered_at) for hit in hits]
                    raw_total = payload.get("total")
                    total = raw_total.get("value") if isinstance(raw_total, dict) else raw_total
                    total = int(total) if total is not None else None
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    break
                jobs.extend(batch)
                pages += 1
                if len(hits) < limit_per_query or (total is not None and len(jobs) >= int(total)):
                    complete = True
                    break
            results.append(QueryResult(query=query, jobs=jobs,
                                       total_available=int(total) if total is not None else None,
                                       pages_requested=pages,
                                       status=("partial" if jobs else "failed") if error else ("ok" if complete else "truncated"),
                                       error=error, date_unknown=sum(not j.published_at for j in jobs)))
        return FetchResult(source=self.name, queries=results)

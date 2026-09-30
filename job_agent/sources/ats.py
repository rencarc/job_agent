"""Read-only public board adapters. Boards must be explicitly configured."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from job_agent.models import Job
from .base import FetchResult, QueryResult


def _load(url):
    with urlopen(Request(url, headers={"Accept": "application/json", "User-Agent": "auditable-job-agent/0.1"}), timeout=30) as response:
        return json.load(response)


def _board(value):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("board name must contain only letters, numbers, underscore or hyphen")
    return value


def _plain(html):
    return unescape(re.sub(r"<[^>]+>", " ", html or ""))


def _matches(job, queries):
    if not queries:
        return True
    # Board descriptions often include generic company-wide AI boilerplate.
    # Match the role title, not incidental mentions deep in the description.
    title = job.title.casefold()
    return any(all(word in title for word in query.casefold().split()) for query in queries)


def _location_status(location, country=""):
    country = str(country or "").strip().casefold()
    if country in {"se", "swe", "sweden", "sverige"}:
        return "sweden"
    if country:
        return "outside_sweden"
    value = str(location or "").casefold()
    if re.search(r"\b(sweden|sverige|stockholm|gothenburg|göteborg|malmö|uppsala|lund|umeå|linköping|örebro|västerås|helsingborg|solna)\b", value):
        return "sweden"
    if re.search(r"\b(usa|united states|united kingdom|uk|germany|deutschland|france|denmark|norway|finland|netherlands|canada|amsterdam|berlin|cologne|köln|toronto|frankfurt|madrid|oslo|hamburg|helsinki|munich|münchen)\b", value):
        return "outside_sweden"
    return "unknown"


class PublicBoardSource:
    """Fetch a curated board; never scans arbitrary companies or submits applications."""
    def __init__(self, provider, board, *, loader=None):
        if provider not in {"greenhouse", "lever", "lever-global", "ashby"}:
            raise ValueError("unsupported public board provider")
        self.provider = provider
        self.board = _board(board)
        self.name = f"{provider}:{board}"
        self.loader = loader or _load

    def fetch(self, queries, *, limit_per_query=100, published_after=None):
        if not 1 <= limit_per_query <= 100:
            raise ValueError("limit_per_query must be between 1 and 100")
        pages = 1
        if self.provider == "greenhouse":
            url = f"https://boards-api.greenhouse.io/v1/boards/{self.board}/jobs?content=true"
            payload = self.loader(url)
            rows = payload.get("jobs", [])
        elif self.provider == "ashby":
            url = f"https://api.ashbyhq.com/posting-api/job-board/{self.board}"
            rows = self.loader(url).get("jobs", [])
        else:
            rows = []
            host = "api.eu.lever.co" if self.provider == "lever" else "api.lever.co"
            for page in range(20):
                url = f"https://{host}/v0/postings/{self.board}?{urlencode({'mode': 'json', 'limit': 100, 'skip': page * 100})}"
                batch = self.loader(url)
                rows.extend(batch)
                pages = page + 1
                if len(batch) < 100:
                    break
            else:
                raise RuntimeError("Lever pagination exceeded 20 pages; coverage cannot be claimed complete")
        jobs = [self._normalize(row) for row in rows]
        jobs = [job for job in jobs if _matches(job, queries)
                and job.location_status != "outside_sweden"
                and (not published_after or not job.published_at or job.published_at >= published_after)]
        return FetchResult(self.name, [QueryResult(" | ".join(queries) or "all", jobs[:limit_per_query], len(jobs), pages)])

    def _normalize(self, row):
        now = datetime.now(timezone.utc).isoformat()
        if self.provider == "greenhouse":
            url = row.get("absolute_url", "")
            return Job(str(row.get("id", "")), self.board, row.get("title", ""),
                       (row.get("location") or {}).get("name", ""), _plain(row.get("content", "")),
                       self.name, url, url, "greenhouse", str(row.get("id", "")),
                       row.get("updated_at", ""), now,
                       _location_status((row.get("location") or {}).get("name", "")))
        if self.provider in {"lever", "lever-global"}:
            url = row.get("hostedUrl", "")
            created = row.get("createdAt")
            date = datetime.fromtimestamp(created / 1000, timezone.utc).isoformat() if isinstance(created, (int, float)) else ""
            return Job(str(row.get("id", "")), self.board, row.get("text", ""),
                       (row.get("categories") or {}).get("location", ""),
                       row.get("descriptionPlain") or _plain(row.get("description", "")),
                       self.name, url, row.get("applyUrl") or url, "lever", str(row.get("id", "")), date, now,
                       _location_status((row.get("categories") or {}).get("location", "")))
        url = row.get("jobUrl", "")
        address = (row.get("address") or {}).get("postalAddress") or {}
        return Job(str(row.get("id", "")), self.board, row.get("title", ""), row.get("location", ""),
                   row.get("descriptionPlain") or _plain(row.get("descriptionHtml", "")),
                   self.name, url, row.get("applyUrl") or url, "ashby", str(row.get("id", "")),
                   row.get("publishedAt", ""), now,
                   _location_status(row.get("location", ""), address.get("addressCountry", "")))

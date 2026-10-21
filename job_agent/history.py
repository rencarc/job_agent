"""Historical tracker matching before scoring or submission."""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable

from .config import AIRTABLE_FIELDS
from .dedup import canonical_url
from .models import Job


@dataclass(frozen=True)
class HistoryMatch:
    action: str  # new, blocked, or review
    reason: str
    record_id: str = ""


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[\w]+", text.casefold()))


def _value(fields: dict, key: str) -> str:
    val = fields.get(AIRTABLE_FIELDS[key], "")
    if isinstance(val, dict):
        return str(val.get("name", ""))
    return str(val or "")


def match_history(job: Job, records: Iterable[dict]) -> HistoryMatch:
    url = canonical_url(job.apply_url or job.source_url)
    company = _norm(job.company)
    title = _norm(job.title)
    review: HistoryMatch | None = None
    applied = {"applied", "hr contacted", "assessment", "interview", "follow-up sent", "offer"}
    for record in records:
        fields = record.get("cellValuesByFieldId", record.get("fields", record))
        existing_url = canonical_url(_value(fields, "job_link"))
        same_url = bool(url and existing_url and url == existing_url)
        same_company = bool(company and company == _norm(_value(fields, "company")))
        old_title = _norm(_value(fields, "role"))
        same_title = bool(title and title == old_title)
        similar_title = bool(title and old_title and SequenceMatcher(None, title, old_title).ratio() >= 0.85)
        same_role = same_company and (same_title or similar_title)
        if not (same_url or same_role):
            continue
        status = _value(fields, "status").casefold()
        record_id = record.get("id", "")
        if same_url and status in applied:
            return HistoryMatch("blocked", "same URL previously applied in Airtable", record_id)
        if same_role and not existing_url and status in applied:
            review = HistoryMatch("review", "previous application with same company and role but no URL", record_id)
        elif review is None:
            reason = "different URL for similar company and role" if same_role and existing_url and not same_url else "similar existing Airtable record"
            review = HistoryMatch("review", f"{reason} ({status or 'unknown status'})", record_id)
    return review or HistoryMatch("new", "no matching Airtable record")


class HistoryIndex:
    """Restrict matching to the same URL/company instead of scanning all history per job."""
    def __init__(self, records: Iterable[dict]):
        self.records = list(records)
        self.by_url: dict[str, set[int]] = {}
        self.by_company: dict[str, set[int]] = {}
        for index, record in enumerate(self.records):
            fields = record.get("cellValuesByFieldId", record.get("fields", record))
            url = canonical_url(_value(fields, "job_link"))
            company = _norm(_value(fields, "company"))
            if url:
                self.by_url.setdefault(url, set()).add(index)
            if company:
                self.by_company.setdefault(company, set()).add(index)

    def match(self, job: Job) -> HistoryMatch:
        candidates = self.by_url.get(canonical_url(job.apply_url or job.source_url), set()) | self.by_company.get(_norm(job.company), set())
        return match_history(job, [self.records[index] for index in sorted(candidates)])

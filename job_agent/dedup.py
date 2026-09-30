from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Job


TRACKING_PARAMS = {
    "fbclid", "gclid", "ref", "referrer", "source", "src",
    "utm_campaign", "utm_content", "utm_medium", "utm_source", "utm_term",
}


def _normalise_words(value: str) -> str:
    value = value.casefold().replace("&", " and ")
    return " ".join(re.findall(r"[a-z0-9åäö]+", value))


def canonical_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    host = parts.netloc.casefold().removeprefix("www.")
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/") or "/"
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.casefold() not in TRACKING_PARAMS and not k.casefold().startswith("utm_")]
    return urlunsplit((parts.scheme.casefold() or "https", host, path, urlencode(sorted(query)), ""))


def ats_identity(job: Job) -> tuple[str, str] | None:
    if job.ats_type and job.ats_job_id:
        return job.ats_type.casefold(), job.ats_job_id.casefold()
    url = canonical_url(job.apply_url or job.source_url)
    patterns = (
        ("greenhouse", r"(?:greenhouse\.io|greenhouse\.com)/[^?]*/(?:jobs/)?(\d+)"),
        ("ashby", r"ashbyhq\.com/[^/]+/([0-9a-f-]{16,})"),
        ("lever", r"lever\.co/[^/]+/([0-9a-f-]{16,})"),
        ("teamtailor", r"teamtailor\.com/[^/]+/jobs/(\d+)"),
    )
    for ats, pattern in patterns:
        hit = re.search(pattern, url, re.IGNORECASE)
        if hit:
            return ats, hit.group(1).casefold()
    return None


def fingerprint(job: Job) -> str:
    url = canonical_url(job.apply_url or job.source_url)
    domain = urlsplit(url).netloc
    return "|".join((
        _normalise_words(job.company),
        _normalise_words(job.title),
        _normalise_words(job.location),
        domain,
    ))


@dataclass(frozen=True)
class DuplicateMatch:
    duplicate: bool
    reason: str | None = None


def duplicate_match(left: Job, right: Job) -> DuplicateMatch:
    left_ats, right_ats = ats_identity(left), ats_identity(right)
    if left_ats and left_ats == right_ats:
        return DuplicateMatch(True, "ats_job_id")

    left_url = canonical_url(left.apply_url or left.source_url)
    right_url = canonical_url(right.apply_url or right.source_url)
    if left_url and left_url == right_url:
        return DuplicateMatch(True, "canonical_url")

    if fingerprint(left) == fingerprint(right) and _normalise_words(left.company) and _normalise_words(left.title):
        return DuplicateMatch(True, "company_title_location_domain")
    return DuplicateMatch(False)


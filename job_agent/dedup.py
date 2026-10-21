from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Job


TRACKING_PARAMS = {
    "fbclid", "gclid", "gh_src", "trk", "trackingid",
    "utm_campaign", "utm_content", "utm_medium", "utm_source", "utm_term",
}


def _normalise_words(value: str) -> str:
    value = value.casefold().replace("&", " and ")
    return " ".join(re.findall(r"[a-z0-9åäö]+", value))


def canonical_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in {"https", "http"} or not parts.hostname or parts.username or parts.password:
        return ""
    host = parts.netloc.casefold().removeprefix("www.")
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/") or "/"
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.casefold() not in TRACKING_PARAMS and not k.casefold().startswith("utm_")]
    fragment = re.fullmatch(r"/?jobs?/([^/?#]+)(?:\?[^#]*)?", parts.fragment, re.I)
    if fragment:
        query.append(("_job_fragment_id", fragment.group(1)))
    return urlunsplit((parts.scheme.casefold() or "https", host, path, urlencode(sorted(query)), ""))


def ats_identity(job: Job) -> tuple[str, str] | None:
    url = canonical_url(job.apply_url or job.source_url)
    patterns = (
        ("greenhouse", r"^https?://(?:[a-z0-9-]+\.)*(?:greenhouse\.io|greenhouse\.com)/([^/?]+)/jobs/(\d+)"),
        ("ashby", r"^https?://(?:[a-z0-9-]+\.)*ashbyhq\.com/([^/?]+)/([0-9a-f-]{16,})"),
        ("lever", r"^https?://(?:[a-z0-9-]+\.)*lever\.co/([^/?]+)/([0-9a-f-]{16,})"),
        ("teamtailor", r"^https?://([a-z0-9-]+)\.teamtailor\.com/jobs/(\d+)"),
    )
    for ats, pattern in patterns:
        hit = re.search(pattern, url, re.IGNORECASE)
        if hit:
            return ats, f"{hit.group(1).casefold()}:{hit.group(2).casefold()}"
    if job.ats_type and job.ats_job_id:
        scope = job.source.split(":", 1)[-1] if ":" in job.source else _normalise_words(job.company)
        return job.ats_type.casefold(), f"{scope.casefold()}:{job.ats_job_id.casefold()}"
    return None


def source_identity(job: Job) -> tuple[str, str] | None:
    if job.source and job.external_id:
        return job.source.casefold(), job.external_id
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

    if source_identity(left) and source_identity(left) == source_identity(right):
        return DuplicateMatch(True, "source_job_id")
    # A shared title/location is a similarity signal, never proof of identity.
    return DuplicateMatch(False)


"""Classify application handoffs without requests, redirects, or form submission."""
import re
from urllib.parse import urlsplit, urlunsplit

from .models import Job


def application_route(job: Job) -> dict:
    url = job.apply_url or job.source_url
    result = {"preview_supported": False, "can_submit": False, "url": url,
              "provider": "unknown", "posting_open": "unverified", "inspection_supported": False}
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").casefold()
        if not host or parts.username or parts.password or parts.port not in {None, 443, 80}:
            raise ValueError("invalid application URL")
    except ValueError:
        return {**result, "status": "invalid_url", "reason": "valid employer application URL is missing"}
    if parts.scheme != "https":
        return {**result, "status": "insecure_url", "reason": "application endpoint requires HTTPS verification"}
    path = parts.path.rstrip("/")
    if host == "jobs.ashbyhq.com" and re.fullmatch(r"/[^/]+/[0-9a-fA-F-]{16,}(?:/application)?", path):
        target = path if path.endswith("/application") else path + "/application"
        return {**result, "status": "preview_supported", "provider": "ashby", "preview_supported": True,
                "url": urlunsplit(("https", parts.netloc, target, parts.query, "")),
                "reason": "Ashby preview adapter available; live form and required answers still need inspection"}
    providers = {"lever": ("jobs.lever.co",), "greenhouse": ("boards.greenhouse.io", "job-boards.greenhouse.io")}
    for provider, hosts in providers.items():
        if host in hosts and path:
            return {**result, "status": "unsupported_provider", "provider": provider,
                    "reason": provider + " form driver is not implemented"}
    if host.endswith(".teamtailor.com") or re.fullmatch(r"/jobs/\d+-[^/]+/applications/new", path):
        return {**result, "status": "unsupported_provider", "provider": "teamtailor_hint", "inspection_supported": True,
                "reason": "Teamtailor read-only inspection available; filling/submission driver is not implemented"}
    if not path or host in {"arbetsformedlingen.se", "www.arbetsformedlingen.se"}:
        return {**result, "status": "no_direct_form",
                "reason": "company homepage or source listing is not a verified direct application form"}
    return {**result, "status": "unverified_provider",
            "reason": "application provider and form support have not been verified"}

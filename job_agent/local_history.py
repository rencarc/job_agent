"""Read the submission fence without creating or changing an application ledger."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from .dedup import ats_identity, canonical_url
from .history import HistoryMatch
from .models import Job


class LocalApplicationHistory:
    """Per-run snapshot, not a replacement for an atomic pre-submit claim."""
    def __init__(self, path: Path):
        if not path.is_file():
            raise ValueError("configured application ledger does not exist")
        try:
            with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
                rows = db.execute("SELECT job_key,state FROM applications").fetchall()
        except sqlite3.Error as exc:
            raise ValueError("application ledger cannot be read; reconcile before continuing") from exc
        self.by_url = {}
        self.by_ats = {}
        for url, state in rows:
            if state not in {"claimed", "submitted", "synced"} or not isinstance(url, str) or not canonical_url(url):
                raise ValueError("application ledger contains an unknown state or invalid job key")
            self.by_url.setdefault(canonical_url(url), set()).add(state)
            identity = ats_identity(Job("", "", "", "", apply_url=url))
            if identity:
                self.by_ats.setdefault(identity, set()).add(state)

    def match(self, job: Job) -> HistoryMatch:
        states = set()
        for url in (job.apply_url, job.source_url):
            states.update(self.by_url.get(canonical_url(url), set()))
            identity = ats_identity(Job("", "", "", "", apply_url=url))
            states.update(self.by_ats.get(identity, set()))
        if states & {"submitted", "synced"}:
            return HistoryMatch("blocked", "local ledger already records submission; do not reapply")
        if "claimed" in states:
            return HistoryMatch("review", "local submission claim is unresolved; reconcile before retrying")
        return HistoryMatch("new", "no matching local submission fence; external history still required")

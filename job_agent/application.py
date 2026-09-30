"""Application lifecycle: submission evidence precedes any Applied tracker update."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .config import AIRTABLE_FIELDS
from .dedup import canonical_url
from .models import Job
from .form_audit import FilledField, format_audit, serialize_fields


@dataclass(frozen=True)
class SubmissionReceipt:
    job_key: str
    submitted_at: str
    confirmation: str
    evidence_url: str = ""

    def __post_init__(self):
        if not self.job_key or not self.confirmation.strip():
            raise ValueError("submission requires a job key and confirmation evidence")
        when = datetime.fromisoformat(self.submitted_at.replace("Z", "+00:00"))
        if when.tzinfo is None or when > datetime.now(timezone.utc):
            raise ValueError("submitted_at must be an actual timezone-aware past timestamp")
        if self.evidence_url and urlparse(self.evidence_url).scheme != "https":
            raise ValueError("evidence_url must use HTTPS")


def job_key(job: Job) -> str:
    key = canonical_url(job.apply_url or job.source_url)
    if not key:
        raise ValueError("job requires a stable application URL")
    return key


class ApplicationLedger:
    """Durable local claim fence; repeated runs never silently resubmit a job."""
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            path.parent.chmod(0o700)
        with closing(self._connect()) as db:
            db.execute("CREATE TABLE IF NOT EXISTS applications (job_key TEXT PRIMARY KEY, state TEXT NOT NULL, receipt_json TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS form_snapshots (job_key TEXT PRIMARY KEY, fields_json TEXT NOT NULL)")
            db.commit()

    def close(self) -> None:
        return None

    def __enter__(self) -> "ApplicationLedger":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self):
        return None

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        if os.name == "posix":
            self.path.chmod(0o600)
        return db

    def claim(self, job: Job) -> bool:
        with closing(self._connect()) as db:
            cursor = db.execute("INSERT OR IGNORE INTO applications(job_key,state) VALUES (?, 'claimed')", (job_key(job),))
            db.commit()
            return cursor.rowcount == 1

    def record_receipt(self, receipt: SubmissionReceipt) -> None:
        with closing(self._connect()) as db:
            row = db.execute("SELECT state FROM applications WHERE job_key=?", (receipt.job_key,)).fetchone()
            if row is None or row[0] not in {"claimed", "submitted"}:
                raise ValueError("claim the job before recording a receipt")
            snapshot = db.execute("SELECT fields_json FROM form_snapshots WHERE job_key=?", (receipt.job_key,)).fetchone()
            if not snapshot:
                raise ValueError("capture the actual filled fields before recording submission")
            db.execute("UPDATE applications SET state='submitted', receipt_json=? WHERE job_key=?",
                       (json.dumps(receipt.__dict__), receipt.job_key))
            db.commit()

    def save_form_snapshot(self, job: Job, fields: list[FilledField]) -> None:
        key = job_key(job)
        with closing(self._connect()) as db:
            row = db.execute("SELECT state FROM applications WHERE job_key=?", (key,)).fetchone()
            if row is None or row[0] != "claimed" or not fields:
                raise ValueError("claim the job and capture all filled fields before submission")
            payload = json.dumps(serialize_fields(fields), ensure_ascii=False)
            db.execute("INSERT OR REPLACE INTO form_snapshots(job_key,fields_json) VALUES (?,?)", (key, payload))
            db.commit()

    def form_snapshot(self, key: str) -> list[FilledField]:
        with closing(self._connect()) as db:
            row = db.execute("SELECT fields_json FROM form_snapshots WHERE job_key=?", (key,)).fetchone()
        return [FilledField(**field) for field in json.loads(row[0])] if row else []

    def pending_sync(self) -> list[SubmissionReceipt]:
        with closing(self._connect()) as db:
            rows = db.execute("SELECT receipt_json FROM applications WHERE state='submitted'").fetchall()
        return [SubmissionReceipt(**json.loads(row[0])) for row in rows]

    def mark_synced(self, key: str) -> None:
        with closing(self._connect()) as db:
            db.execute("UPDATE applications SET state='synced' WHERE job_key=? AND state='submitted'", (key,))
            db.commit()


def applied_airtable_fields(job: Job, receipt: SubmissionReceipt,
                           filled_fields: list[FilledField] | None = None) -> dict[str, object]:
    if job_key(job) != receipt.job_key:
        raise ValueError("receipt does not belong to this job")
    return {
        AIRTABLE_FIELDS["application"]: f"{job.company} - {job.title}",
        AIRTABLE_FIELDS["company"]: job.company,
        AIRTABLE_FIELDS["role"]: job.title,
        AIRTABLE_FIELDS["job_link"]: job.apply_url or job.source_url,
        AIRTABLE_FIELDS["location"]: job.location,
        AIRTABLE_FIELDS["status"]: "Applied",
        AIRTABLE_FIELDS["submitted_date"]: receipt.submitted_at[:10],
        AIRTABLE_FIELDS["application_notes"]: f"Submission confirmation: {receipt.confirmation}\nEvidence: {receipt.evidence_url or 'local receipt'}"
                                               + ("\n\nSubmitted form:\n" + format_audit(filled_fields) if filled_fields else ""),
    }

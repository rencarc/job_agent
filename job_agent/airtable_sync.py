"""Synchronize verified submission receipts to the existing Airtable tracker."""
from __future__ import annotations

import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .application import ApplicationLedger, applied_airtable_fields, job_key
from .config import AIRTABLE_BASE_ID, AIRTABLE_FIELDS, AIRTABLE_TABLE_ID
from .dedup import canonical_url
from .models import Job
from .history import match_history


class AirtableClient:
    def __init__(self, token: str | None = None, *, transport=None):
        self.token = token or os.environ.get("AIRTABLE_TOKEN", "")
        if not self.token and transport is None:
            raise ValueError("AIRTABLE_TOKEN is required for local Airtable synchronization")
        self.transport = transport or self._request
        keys = ("company", "role", "job_link", "status")
        id_mode = [AIRTABLE_FIELDS[key].startswith("fld") for key in keys]
        if any(id_mode) and not all(id_mode):
            raise ValueError("Airtable history fields must all use names or all use field IDs")
        self.by_field_id = all(id_mode)
        if transport is None and (not AIRTABLE_BASE_ID or not AIRTABLE_TABLE_ID):
            raise ValueError("AIRTABLE_BASE_ID and AIRTABLE_TABLE_ID are required")
        self.url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"

    def _request(self, method, url, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        req = Request(url, data=body, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        with urlopen(req, timeout=30) as response:
            return json.load(response)

    def existing_links(self):
        result = {}
        for record in self.history_records():
            link = record.get("cellValuesByFieldId", {}).get(AIRTABLE_FIELDS["job_link"], "")
            if canonical_url(link):
                result[canonical_url(link)] = record["id"]
        return result

    def history_records(self):
        result = []
        offset = None
        while True:
            params = {"pageSize": 100, "returnFieldsByFieldId": str(self.by_field_id).lower()}
            if offset:
                params["offset"] = offset
            page = self.transport("GET", f"{self.url}?{urlencode(params)}")
            for record in page.get("records", []):
                fields = record.get("fields", {})
                if fields and not fields.keys() & {AIRTABLE_FIELDS[k] for k in ("company", "role", "job_link", "status")}:
                    raise ValueError("Airtable response does not match configured history field names/IDs")
                result.append({"id": record["id"],
                               "cellValuesByFieldId": fields})
            offset = page.get("offset")
            if not offset:
                return result

    def sync_confirmed(self, ledger: ApplicationLedger, jobs: list[Job]) -> int:
        by_key = {job_key(job): job for job in jobs if job.apply_url or job.source_url}
        receipts = ledger.pending_sync()
        if not receipts:
            return 0
        records = self.history_records()
        links = {canonical_url(record["cellValuesByFieldId"].get(AIRTABLE_FIELDS["job_link"], "")): record["id"]
                 for record in records if canonical_url(record["cellValuesByFieldId"].get(AIRTABLE_FIELDS["job_link"], ""))}
        synced = 0
        for receipt in receipts:
            job = by_key.get(receipt.job_key)
            if job is None:
                raise ValueError(f"missing job snapshot for receipt {receipt.job_key}")
            fields = applied_airtable_fields(job, receipt, ledger.form_snapshot(receipt.job_key))
            record_id = links.get(receipt.job_key)
            if not record_id and match_history(job, records).action == "review":
                raise ValueError("Airtable has a similar record without an exact URL; reconcile before syncing")
            if record_id:
                self.transport("PATCH", f"{self.url}/{record_id}", {"fields": fields})
            else:
                created = self.transport("POST", self.url, {"fields": fields})
                links[receipt.job_key] = created["id"]
            ledger.mark_synced(receipt.job_key)
            synced += 1
        return synced

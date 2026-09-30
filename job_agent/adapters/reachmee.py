from __future__ import annotations

import json
import re
from pathlib import Path

from .base import AdapterStep, AdapterWorkflow, PauseReason, ReceiptCheck


SUCCESS_PATTERNS = [
    re.compile(r"tack\s+för\s+din\s+ansökan", re.IGNORECASE),
    re.compile(r"thank\s+you\s+for\s+your\s+application", re.IGNORECASE),
]


def workflow() -> AdapterWorkflow:
    return AdapterWorkflow(
        system="reachmee",
        steps=[
            AdapterStep("preflight", "Check that the page is a ReachMee apply page and the job is not already submitted."),
            AdapterStep("login_pause", "Pause for user BankID/login when ReachMee redirects to an identity provider.", True, PauseReason.BANKID_REQUIRED),
            AdapterStep("fill_preview", "Fill known fields and approved answers without clicking submit."),
            AdapterStep("readback", "Read back visible fields, selected answers, text answers, and uploaded CV name."),
            AdapterStep("cv_check", "Require the expected CV filename to be present on the page before submit."),
            AdapterStep("approval_pause", "Pause for explicit one-job submit approval.", True, PauseReason.USER_APPROVAL_REQUIRED),
            AdapterStep("submit_once", "Click submit once only; never retry automatically after an unclear result."),
            AdapterStep("receipt_check", "Require a clear success page before marking Applied."),
            AdapterStep("airtable_sync", "Sync to Airtable only after receipt and filled-field audit exist."),
        ],
    )


def check_receipt_payload(payload: dict) -> ReceiptCheck:
    before = payload.get("before") or {}
    after = payload.get("after") or {}
    body_text = after.get("bodyText") or after.get("body_text") or ""
    cv_name = before.get("cvName") or before.get("resume") or ""
    evidence_url = after.get("url") or before.get("url") or ""
    if not cv_name:
        return ReceiptCheck(False, "", evidence_url, "CV was not confirmed before submission")
    if any(pattern.search(body_text) for pattern in SUCCESS_PATTERNS):
        title = after.get("title") or before.get("title") or "ReachMee application"
        return ReceiptCheck(True, f"{title}: Tack för din ansökan", evidence_url)
    return ReceiptCheck(False, "", evidence_url, "ReachMee success page was not clear")


def check_receipt_file(path: Path) -> ReceiptCheck:
    return check_receipt_payload(json.loads(path.read_text(encoding="utf-8")))

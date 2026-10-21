import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from job_agent.application import ApplicationLedger, SubmissionReceipt, applied_airtable_fields, job_key
from job_agent.airtable_sync import AirtableClient
from job_agent.models import Job
from job_agent.form_audit import FilledField
from job_agent.config import AIRTABLE_FIELDS


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.job = Job("1", "Acme", "AI Engineer", "Umeå", apply_url="https://example.test/apply/1")

    def capture(self, ledger):
        ledger.save_form_snapshot(self.job, [FilledField("Name", "Test Candidate", "user_supplied", "none", "none")])

    def test_claim_blocks_repeat_even_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.sqlite"
            self.assertTrue(ApplicationLedger(path).claim(self.job))
            self.assertFalse(ApplicationLedger(path).claim(self.job))

    def test_receipt_is_required_before_tracker_applied_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ApplicationLedger(Path(tmp) / "ledger.sqlite")
            self.assertTrue(ledger.claim(self.job))
            self.assertEqual(ledger.pending_sync(), [])
            with self.assertRaises(ValueError):
                SubmissionReceipt(job_key(self.job), datetime.now(timezone.utc).isoformat(), "")
            receipt = SubmissionReceipt(job_key(self.job), datetime.now(timezone.utc).isoformat(), "Confirmation ABC")
            with self.assertRaises(ValueError):
                ledger.record_receipt(receipt)
            self.capture(ledger)
            ledger.record_receipt(receipt)
            self.assertEqual(len(ledger.pending_sync()), 1)
            fields = applied_airtable_fields(self.job, receipt)
            self.assertEqual(fields[AIRTABLE_FIELDS["status"]], "Applied")
            self.assertIn("Confirmation ABC", fields[AIRTABLE_FIELDS["application_notes"]])
            ledger.mark_synced(job_key(self.job))
            self.assertEqual(ledger.pending_sync(), [])

    def test_receipt_cannot_be_used_for_different_job(self):
        receipt = SubmissionReceipt("https://other.test/1", datetime.now(timezone.utc).isoformat(), "Confirmed")
        with self.assertRaises(ValueError):
            applied_airtable_fields(self.job, receipt)

    def test_airtable_sync_only_after_receipt_and_retry_does_not_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ApplicationLedger(Path(tmp) / "ledger.sqlite")
            ledger.claim(self.job)
            calls = []
            def transport(method, url, payload=None):
                calls.append((method, url, payload))
                if method == "GET":
                    return {"records": []}
                return {"id": "recExample"}
            client = AirtableClient(transport=transport)
            self.assertEqual(client.sync_confirmed(ledger, [self.job]), 0)
            self.assertEqual(calls, [])
            self.capture(ledger)
            ledger.record_receipt(SubmissionReceipt(job_key(self.job), datetime.now(timezone.utc).isoformat(), "Confirmed"))
            self.assertEqual(client.sync_confirmed(ledger, [self.job]), 1)
            self.assertEqual(client.sync_confirmed(ledger, [self.job]), 0)
            self.assertEqual([call[0] for call in calls], ["GET", "POST"])
            self.assertIn("returnFieldsByFieldId=false", calls[0][1])

    def test_failed_airtable_write_keeps_receipt_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ApplicationLedger(Path(tmp) / "ledger.sqlite")
            ledger.claim(self.job)
            self.capture(ledger)
            ledger.record_receipt(SubmissionReceipt(job_key(self.job), datetime.now(timezone.utc).isoformat(), "Confirmed"))
            def transport(method, url, payload=None):
                if method == "GET":
                    return {"records": []}
                raise TimeoutError("network down")
            with self.assertRaises(TimeoutError):
                AirtableClient(transport=transport).sync_confirmed(ledger, [self.job])
            self.assertEqual(len(ledger.pending_sync()), 1)

    def test_missing_url_similar_tracker_record_prevents_duplicate_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ApplicationLedger(Path(tmp) / "ledger.sqlite")
            ledger.claim(self.job)
            self.capture(ledger)
            ledger.record_receipt(SubmissionReceipt(job_key(self.job), datetime.now(timezone.utc).isoformat(), "Confirmed"))
            calls = []
            def transport(method, url, payload=None):
                calls.append(method)
                return {"records": [{"id": "recPrevious", "fields": {
                    AIRTABLE_FIELDS["company"]: "Acme", AIRTABLE_FIELDS["role"]: "AI Engineer",
                    AIRTABLE_FIELDS["status"]: "Applied"}}]}
            with self.assertRaisesRegex(ValueError, "reconcile"):
                AirtableClient(transport=transport).sync_confirmed(ledger, [self.job])
            self.assertEqual(calls, ["GET"])
            self.assertEqual(len(ledger.pending_sync()), 1)

    def test_airtable_history_paginates_for_duplicate_checks(self):
        calls = []
        def transport(method, url, payload=None):
            calls.append(url)
            if len(calls) == 1:
                return {"records": [{"id": "rec1", "fields": {AIRTABLE_FIELDS["company"]: "Acme"}}], "offset": "next"}
            return {"records": [{"id": "rec2", "fields": {AIRTABLE_FIELDS["job_link"]: "https://example.test/1"}}]}
        client = AirtableClient(transport=transport)
        self.assertEqual(len(client.history_records()), 2)
        self.assertIn("offset=next", calls[1])

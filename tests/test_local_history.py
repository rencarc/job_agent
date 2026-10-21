import sqlite3
import tempfile
import unittest
from dataclasses import replace
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from job_agent.application import ApplicationLedger, SubmissionReceipt, job_key
from job_agent.automation import run_pipeline
from job_agent.form_audit import FilledField
from job_agent.local_history import LocalApplicationHistory
from job_agent.materials import prepare_materials
from job_agent.store import JobStore
from test_automation import job, profile


class LocalHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "ledger.sqlite"
        self.ledger = ApplicationLedger(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def submit(self, posting):
        self.ledger.claim(posting)
        self.ledger.save_form_snapshot(posting, [FilledField("Name", "Test", "user_supplied", "none", "none")])
        self.ledger.record_receipt(SubmissionReceipt(job_key(posting), datetime.now(timezone.utc).isoformat(), "Confirmed"))

    def test_missing_or_corrupt_ledger_is_not_empty_history(self):
        missing = self.root / "missing.sqlite"
        with self.assertRaises(ValueError):
            LocalApplicationHistory(missing)
        self.assertFalse(missing.exists())
        broken = self.root / "broken.sqlite"
        broken.write_bytes(b"not a database")
        with self.assertRaises(ValueError):
            LocalApplicationHistory(broken)

    def test_claimed_state_survives_restart_without_inventing_submission(self):
        self.ledger.claim(job())
        before = self.path.read_bytes()
        history = LocalApplicationHistory(self.path)
        self.assertEqual(history.match(job()).action, "review")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.ledger.pending_sync(), [])

    def test_submitted_and_synced_fences_both_block(self):
        self.submit(job())
        self.assertEqual(LocalApplicationHistory(self.path).match(job()).action, "blocked")
        self.ledger.mark_synced(job_key(job()))
        self.assertEqual(LocalApplicationHistory(self.path).match(job()).action, "blocked")
        self.assertEqual(LocalApplicationHistory(self.path).match(job(2)).action, "new")

    def test_ats_application_suffix_and_source_url_still_match(self):
        url = "https://jobs.ashbyhq.com/example/01234567-89ab-cdef-0123-456789abcdef"
        posting = replace(job(), apply_url=url + "/application")
        self.submit(posting)
        history = LocalApplicationHistory(self.path)
        self.assertEqual(history.match(replace(job(), apply_url=url + "?utm_source=feed")).action, "blocked")
        self.assertEqual(history.match(replace(job(), source_url=posting.apply_url,
                                               apply_url="https://example.test/new-link")).action, "blocked")
        self.assertEqual(history.match(replace(job(), apply_url=url.replace("/example/", "/other/"))).action, "new")

    def test_unknown_states_fail_closed(self):
        self.ledger.claim(job())
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("UPDATE applications SET state='unexpected'")
            db.commit()
        with self.assertRaises(ValueError):
            LocalApplicationHistory(self.path)

    def test_new_local_fence_overrides_cached_prepare_without_model_cost(self):
        with JobStore(self.root / "jobs.sqlite") as store:
            first = run_pipeline(store, [job()], profile(), history_records=[])
            self.assertEqual(first["counts"], {"prepare": 1})
            self.ledger.claim(job())
            claimed = run_pipeline(store, [], profile(), history_records=[],
                                   local_history=LocalApplicationHistory(self.path))
            self.assertEqual(claimed["counts"], {"exception": 1})
            self.assertEqual(claimed["evaluated"], 0)
            self.ledger.save_form_snapshot(job(), [FilledField("Name", "Test", "user_supplied", "none", "none")])
            self.ledger.record_receipt(SubmissionReceipt(job_key(job()), datetime.now(timezone.utc).isoformat(), "Confirmed"))
            calls = []
            result = run_pipeline(store, [], profile(), history_records=[],
                local_history=LocalApplicationHistory(self.path),
                evaluator=lambda *args, **kwargs: calls.append(args), evaluator_version="test-only")
            self.assertEqual(result["counts"], {"skip": 1})
            self.assertEqual(calls, [])
            self.assertEqual(result["usage_today"], {"calls": 0, "tokens": 0})

    def test_preview_does_not_prepare_a_previously_submitted_job(self):
        self.submit(job())
        with JobStore(self.root / "preview.sqlite") as store:
            report = run_pipeline(store, [job()], profile(), preview=True,
                                  local_history=LocalApplicationHistory(self.path))
            self.assertEqual(report["tasks"][0]["suggested_decision"], "skip")
            self.assertFalse(report["tasks"][0]["can_submit"])
            # A fenced task must not reach PDF selection or create a plan.
            self.assertEqual(prepare_materials(report, profile(), [], self.root / "materials", preview=True), [])

    def test_empty_local_ledger_does_not_prove_external_history_is_empty(self):
        with JobStore(self.root / "jobs.sqlite") as store:
            result = run_pipeline(store, [job()], profile(), local_history=LocalApplicationHistory(self.path))
            self.assertEqual(result["counts"], {"exception": 1})
            self.assertIn("application history is unverified", result["tasks"][0]["reasons"])

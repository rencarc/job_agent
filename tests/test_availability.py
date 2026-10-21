import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

from job_agent.availability import assess_availability, text_deadlines
from job_agent.automation import run_pipeline
from job_agent.store import JobStore
from test_automation import job, profile


class AvailabilityTests(unittest.TestCase):
    def test_structured_expired_and_removed_postings_are_suppressed(self):
        self.assertEqual(assess_availability(replace(job(), removed=True))["decision"], "skip")
        self.assertEqual(assess_availability(replace(job(), application_deadline="2026-10-20T23:59:59"), today=date(2026, 10, 21))["decision"], "skip")

    def test_deadline_today_remains_a_candidate(self):
        self.assertIsNone(assess_availability(replace(job(), application_deadline="2026-10-21T23:59:59"), today=date(2026, 10, 21))["decision"])

    def test_renewed_structured_deadline_and_old_body_need_review(self):
        result = assess_availability(replace(job(), application_deadline="2026-11-02T23:59:59",
                     description="Apply no later than 16 August, 2026."), today=date(2026, 10, 21))
        self.assertEqual(result["decision"], "exception")
        self.assertIn("conflict", result["reasons"][0])

    def test_numerical_swedish_deadline_and_unrelated_dates(self):
        self.assertEqual(text_deadlines("Sista ansökningdatum: 22-10-2026")[0]["date"], "2026-10-22")
        self.assertEqual(text_deadlines("We were founded on 16 August, 2020."), [])

    def test_invalid_date_is_not_invented(self):
        self.assertEqual(text_deadlines("Apply by 31 February, 2026."), [])

    def test_matching_cache_does_not_prevent_fresh_availability_check(self):
        with tempfile.TemporaryDirectory() as folder, JobStore(Path(folder) / "jobs.sqlite") as store:
            first = run_pipeline(store, [job()], profile(), history_records=[])
            self.assertEqual(first["counts"], {"prepare": 1})
            with patch("job_agent.automation.assess_availability", return_value={"decision": "skip", "reasons": ["now expired"]}):
                second = run_pipeline(store, [], profile(), history_records=[])
            self.assertEqual(second["evaluated"], 0)
            self.assertEqual(second["counts"], {"skip": 1})

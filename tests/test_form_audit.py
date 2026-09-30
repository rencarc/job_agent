import tempfile
import unittest
from pathlib import Path

from job_agent.application import ApplicationLedger
from job_agent.form_audit import FilledField, format_audit
from job_agent.models import Job


class FormAuditTests(unittest.TestCase):
    def test_english_and_swedish_question_answer_pairs_are_saved_exactly(self):
        fields = [
            FilledField("Why this role?", "I build workflow tools.", "career_fact:flowpilot", "en", "en"),
            FilledField("Varför söker du tjänsten?", "Jag vill arbeta med AI.", "user_supplied", "sv", "sv"),
        ]
        job = Job("1", "Acme", "AI Developer", apply_url="https://example.test/apply/1")
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ApplicationLedger(Path(tmp) / "applications.sqlite")
            ledger.claim(job)
            ledger.save_form_snapshot(job, fields)
            self.assertEqual(ledger.form_snapshot("https://example.test/apply/1"), fields)
        self.assertIn("Varför söker du tjänsten?", format_audit(fields))

    def test_mismatched_response_language_fails(self):
        with self.assertRaises(ValueError):
            FilledField("Why this role?", "Jag vill arbeta här.", "user_supplied", "en", "sv")

    def test_cannot_save_empty_snapshot(self):
        job = Job("1", "Acme", "AI Developer", apply_url="https://example.test/apply/1")
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ApplicationLedger(Path(tmp) / "applications.sqlite")
            ledger.claim(job)
            with self.assertRaises(ValueError):
                ledger.save_form_snapshot(job, [])

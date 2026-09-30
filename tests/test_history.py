import unittest
from job_agent.history import match_history
from job_agent.models import Job
from job_agent.config import AIRTABLE_FIELDS


class HistoryTests(unittest.TestCase):
    job = Job("1", "Acme AB", "AI Engineer", apply_url="https://example.test/1?utm_source=jobs")

    def record(self, *, company="Acme AB", role="AI Engineer", link="", status="Applied"):
        return {"id": "rec1", "cellValuesByFieldId": {
            AIRTABLE_FIELDS["company"]: company, AIRTABLE_FIELDS["role"]: role,
            AIRTABLE_FIELDS["job_link"]: link, AIRTABLE_FIELDS["status"]: {"name": status}}}

    def test_missing_link_requires_review_before_submitting(self):
        self.assertEqual(match_history(self.job, [self.record()]).action, "review")

    def test_canonical_link_blocks_previous_application(self):
        old = self.record(company="Different", role="Other", link="https://example.test/1", status="Applied")
        self.assertEqual(match_history(self.job, [old]).action, "blocked")

    def test_saved_and_similar_are_review_not_auto_submit(self):
        self.assertEqual(match_history(self.job, [self.record(status="Saved")]).action, "review")
        self.assertEqual(match_history(self.job, [self.record(role="AI Engineer (Platform)")]).action, "new")

    def test_unrelated_company_remains_new(self):
        self.assertEqual(match_history(self.job, [self.record(company="Other")]).action, "new")

    def test_distinct_link_for_same_company_role_requires_review(self):
        result = match_history(self.job, [self.record(link="https://example.test/other")])
        self.assertEqual(result.action, "review")

    def test_exact_applied_link_wins_over_earlier_saved_match(self):
        saved = self.record(status="Saved")
        applied = self.record(company="Other", role="Different", link="https://example.test/1")
        applied["id"] = "rec2"
        result = match_history(self.job, [saved, applied])
        self.assertEqual((result.action, result.record_id), ("blocked", "rec2"))

import unittest
from dataclasses import replace
from unittest.mock import patch

from job_agent.airtable_sync import AirtableClient
from job_agent.config import AIRTABLE_FIELDS
from job_agent.dedup import ats_identity, canonical_url
from job_agent.discovery import DedupIndex, discover
from job_agent.models import Job
from job_agent.sources.ats import PublicBoardSource
from job_agent.sources.jobtech import JobTechSource
from scripts.screen_wide_jobs import screen


class AuditRegressionTests(unittest.TestCase):
    def test_search_metadata_cannot_create_fit(self):
        job = {"title": "Office assistant", "description": "Routine filing duties"}
        self.assertEqual(screen(job)["score"], screen({**job, "matched_queries": ["AI", "automation", "Python"]})["score"])
        self.assertNotEqual(screen({**job, "matched_queries": ["AI", "automation", "Python"]})["decision"], "worth_applying")

    def test_negative_and_preferred_language_not_required(self):
        for description in ("Finnish is not required.", "Finnish is preferred.", "Finska krävs inte."):
            with self.subTest(description=description):
                result = screen({"title": "Developer", "description": description})
                self.assertNotIn("finnish_required", result["blockers"])

    def test_explicit_requirement_is_review_without_candidate_facts(self):
        result = screen({"title": "Developer", "description": "Finnish is required."})
        self.assertIn("finnish_required", result["blockers"])
        self.assertEqual(result["decision"], "review")

    def test_same_title_different_posting_is_retained(self):
        index = DedupIndex()
        first = Job("1", "Acme", "Developer", "Stockholm", apply_url="https://example.test/1")
        self.assertTrue(index.add_if_new(first))
        self.assertTrue(index.add_if_new(replace(first, external_id="2", apply_url="https://example.test/2")))

    def test_unknown_titles_do_not_collapse(self):
        index = DedupIndex()
        self.assertTrue(index.add_if_new(Job("1", "", "", source="jobtech")))
        self.assertTrue(index.add_if_new(Job("2", "", "", source="jobtech")))

    def test_ats_identity_is_scoped_and_cannot_be_spoofed_by_host_prefix(self):
        first = Job("1", "Acme", "Developer", apply_url="https://boards.greenhouse.io/acme/jobs/123")
        other = replace(first, apply_url="https://boards.greenhouse.io/other/jobs/123")
        self.assertNotEqual(ats_identity(first), ats_identity(other))
        self.assertIsNone(ats_identity(replace(first, apply_url="https://evilgreenhouse.io/acme/jobs/123")))

    def test_functional_query_and_fragment_identity_survive(self):
        self.assertNotEqual(canonical_url("https://example.test/#/jobs/1"), canonical_url("https://example.test/#/jobs/2"))
        self.assertNotEqual(canonical_url("https://example.test/?ref=1"), canonical_url("https://example.test/?ref=2"))
        self.assertEqual(canonical_url("file:///tmp/cv.pdf"), "")

    def test_query_failure_preserves_other_queries(self):
        def load(url):
            if "q=AI" in url:
                raise TimeoutError("simulated")
            return {"hits": [{"id": "1", "headline": "Developer"}], "total": 1}
        jobs, report = discover(JobTechSource(loader=load), ["Python", "AI"])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(report.sources[0].status, "partial")
        self.assertEqual([q.status for q in report.sources[0].queries], ["ok", "failed"])

    def test_page_failure_retains_successful_page(self):
        def load(url):
            if "offset=1" in url:
                raise TimeoutError("simulated")
            return {"hits": [{"id": "1", "headline": "Developer"}], "total": 2}
        result = JobTechSource(loader=load).fetch(["Python"], limit_per_query=1)
        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(result.queries[0].status, "partial")

    def test_capped_jobtech_reports_truncation(self):
        result = JobTechSource(max_pages=1, loader=lambda _: {"hits": [{"id": "1"}], "total": 2}).fetch(["AI"], limit_per_query=1)
        self.assertEqual(result.queries[0].status, "truncated")

    def test_ats_timezone_comparison_and_unknown_date(self):
        payload = {"jobs": [{"id": "1", "title": "Developer", "location": "Stockholm",
                             "publishedAt": "2026-10-20T09:00:00Z"}]}
        board = PublicBoardSource("ashby", "acme", loader=lambda _: payload)
        self.assertEqual(len(board.fetch(["Developer"], published_after="2026-10-20T10:00:00+02:00").jobs), 1)
        payload["jobs"][0].pop("publishedAt")
        self.assertEqual(board.fetch(["Developer"], published_after="2026-10-20T10:00:00Z").queries[0].date_unknown, 1)

    def test_greenhouse_update_is_not_publication(self):
        board = PublicBoardSource("greenhouse", "acme", loader=lambda _: {"jobs": [
            {"id": 1, "title": "Developer", "updated_at": "2026-10-20T09:00:00Z"}]})
        job = board.fetch(["Developer"]).jobs[0]
        self.assertEqual(job.published_at, "")
        self.assertEqual(job.updated_at, "2026-10-20T09:00:00Z")

    def test_real_shape_airtable_names_and_ids(self):
        calls = []
        def transport(method, url, payload=None):
            calls.append(url)
            return {"records": [{"id": "r1", "fields": {AIRTABLE_FIELDS["job_link"]: "https://example.test/1"}}]}
        client = AirtableClient(transport=transport)
        self.assertIn("https://example.test/1", client.existing_links())
        self.assertIn("returnFieldsByFieldId=false", calls[-1])
        mapping = {key: "fld" + key for key in ("company", "role", "job_link", "status")}
        with patch.dict(AIRTABLE_FIELDS, mapping):
            client = AirtableClient(transport=transport)
            self.assertIn("https://example.test/1", client.existing_links())
            self.assertIn("returnFieldsByFieldId=true", calls[-1])

    def test_airtable_shape_mismatch_and_mixed_config_stop(self):
        client = AirtableClient(transport=lambda *args: {"records": [{"id": "r1", "fields": {"fldUnknown": "x"}}]})
        with self.assertRaises(ValueError):
            client.history_records()
        with patch.dict(AIRTABLE_FIELDS, {"company": "fldCompany"}):
            with self.assertRaises(ValueError):
                AirtableClient(transport=lambda *args: {})

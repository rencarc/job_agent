import unittest

from job_agent.discovery import discover_many
from job_agent.models import Job
from job_agent.sources.ats import PublicBoardSource
from job_agent.sources.base import FetchResult, QueryResult


class StubSource:
    name = "jobtech"

    def fetch(self, queries, *, limit_per_query=100, published_after=None):
        job = Job("j1", "Acme", "AI Engineer", "Umeå", source_url="https://example.test/1")
        return FetchResult(self.name, [QueryResult("AI", [job])])


class PublicBoardTests(unittest.TestCase):
    def test_adapters_read_public_board_fields(self):
        cases = [
            ("greenhouse", {"jobs": [{"id": 1, "title": "AI Engineer", "absolute_url": "https://x.test/1", "location": {"name": "Umeå"}, "content": "<p>Python</p>"}]}),
            ("lever", [{"id": "1", "text": "AI Engineer", "hostedUrl": "https://x.test/1", "categories": {"location": "Umeå"}, "descriptionPlain": "Python"}]),
            ("ashby", {"jobs": [{"id": "1", "title": "AI Engineer", "jobUrl": "https://x.test/1", "location": "Umeå", "descriptionPlain": "Python"}]}),
        ]
        for provider, payload in cases:
            with self.subTest(provider=provider):
                source = PublicBoardSource(provider, "acme", loader=lambda url: payload)
                result = source.fetch(["AI engineer"])
                self.assertEqual(result.jobs[0].location, "Umeå")
                self.assertEqual(result.jobs[0].ats_type, provider)
                self.assertEqual(source.fetch(["accountant"]).jobs, [])

    def test_board_name_validated(self):
        with self.assertRaises(ValueError):
            PublicBoardSource("lever", "../other")

    def test_one_failed_source_does_not_hide_other_source(self):
        def broken(url):
            raise TimeoutError("unavailable")
        jobs, report = discover_many([StubSource(), PublicBoardSource("ashby", "acme", loader=broken)], ["AI"])
        self.assertEqual(len(jobs), 1)
        self.assertEqual([r.status for r in report.sources], ["ok", "failed"])

    def test_explicit_foreign_country_excluded_and_unknown_retained_for_review(self):
        from job_agent.scoring import score_job
        from job_agent.models import Decision
        rows = {"jobs": [
            {"id": "a", "title": "AI Engineer", "location": "Berlin", "address": {"postalAddress": {"addressCountry": "DE"}}},
            {"id": "b", "title": "AI Engineer", "location": "Remote"},
            {"id": "c", "title": "AI Engineer", "location": "Umeå", "address": {"postalAddress": {"addressCountry": "SE"}}},
        ]}
        result = PublicBoardSource("ashby", "acme", loader=lambda url: rows).fetch(["AI"])
        self.assertEqual([job.external_id for job in result.jobs], ["b", "c"])
        self.assertEqual(score_job(result.jobs[0]).decision, Decision.REVIEW)
        self.assertEqual(result.jobs[1].location_status, "sweden")

    def test_lever_paginates_until_short_page(self):
        urls = []
        def loader(url):
            urls.append(url)
            return [{"id": str(i), "text": "AI Engineer", "categories": {"location": "Umeå"}} for i in range(100)] if len(urls) == 1 else [{"id": "last", "text": "AI Engineer", "categories": {"location": "Umeå"}}]
        result = PublicBoardSource("lever", "acme", loader=loader).fetch(["AI"], limit_per_query=100)
        self.assertEqual(result.queries[0].total_available, 101)
        self.assertEqual(result.queries[0].pages_requested, 2)
        self.assertIn("skip=100", urls[1])

    def test_lever_global_uses_global_host(self):
        urls = []
        source = PublicBoardSource("lever-global", "netlight", loader=lambda url: urls.append(url) or [])
        source.fetch(["AI"])
        self.assertTrue(urls[0].startswith("https://api.lever.co/"))

    def test_boilerplate_ai_does_not_match_unrelated_role(self):
        payload = {"jobs": [{"id": "x", "title": "Freight Broker", "descriptionPlain": "We use AI", "location": "Stockholm"}]}
        result = PublicBoardSource("ashby", "acme", loader=lambda url: payload).fetch(["AI"])
        self.assertEqual(result.jobs, [])

    def test_obvious_foreign_city_excluded(self):
        payload = [{"id": "x", "text": "AI Engineer", "categories": {"location": "Toronto"}},
                   {"id": "y", "text": "IT Consultant", "categories": {"location": "Munich"}}]
        result = PublicBoardSource("lever-global", "acme", loader=lambda url: payload).fetch(["AI"])
        self.assertEqual(result.jobs, [])
        self.assertEqual(PublicBoardSource("lever-global", "acme", loader=lambda url: payload).fetch(["IT consultant"]).jobs, [])

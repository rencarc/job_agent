import unittest

from job_agent.discovery import discover
from job_agent.models import Job
from job_agent.sources.base import FetchResult, QueryResult


class FakeSource:
    name = "fake"

    def fetch(self, queries, *, limit_per_query=100, published_after=None):
        first = Job("1", "Acme", "AI Engineer", "Stockholm", source_url="https://example.test/jobs/1")
        duplicate = Job("1b", "Acme", "AI Engineer", "Stockholm", source_url="https://example.test/jobs/1?utm_source=x")
        second = Job("2", "Beta", "Power Platform Developer", "Solna", source_url="https://example.test/jobs/2")
        return FetchResult(self.name, [QueryResult(queries[0], [first, duplicate, second], 3)])


class BrokenSource:
    name = "broken"

    def fetch(self, queries, *, limit_per_query=100, published_after=None):
        raise TimeoutError("source timed out")


class DiscoveryTests(unittest.TestCase):
    def test_deduplicates_and_reports_coverage(self):
        jobs, report = discover(FakeSource(), ["AI"])
        self.assertEqual(len(jobs), 2)
        self.assertEqual(report.total_fetched, 3)
        self.assertEqual(report.total_unique, 2)
        self.assertEqual(report.total_duplicates, 1)
        self.assertEqual(report.sources[0].status, "ok")

    def test_source_failure_is_visible_not_silent(self):
        jobs, report = discover(BrokenSource(), ["AI"])
        self.assertEqual(jobs, [])
        self.assertEqual(report.sources[0].status, "failed")
        self.assertIn("TimeoutError", report.sources[0].error)


if __name__ == "__main__":
    unittest.main()


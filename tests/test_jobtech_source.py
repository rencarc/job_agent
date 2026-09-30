import json
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from job_agent.sources.jobtech import JobTechSource, normalize_hit


FIXTURE = Path(__file__).parent / "fixtures" / "jobtech_search.json"


class JobTechSourceTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_normalizes_official_response_shape(self):
        job = normalize_hit(self.payload["hits"][0], discovered_at="2026-09-24T00:00:00+00:00")
        self.assertEqual(job.external_id, "31499139")
        self.assertEqual(job.company, "The Link Factor AB")
        self.assertEqual(job.title, "AI Expert")
        self.assertEqual(job.location, "Stockholm, Stockholms län, Hybrid")
        self.assertEqual(job.source, "jobtech")
        self.assertEqual(job.published_at, "2026-09-21T09:51:00")

    def test_falls_back_to_platsbanken_page_for_application(self):
        job = normalize_hit(self.payload["hits"][1])
        self.assertEqual(job.apply_url, job.source_url)

    def test_fetch_uses_documented_query_parameters(self):
        requested = []
        source = JobTechSource(loader=lambda url: requested.append(url) or self.payload)
        result = source.fetch(["Copilot Studio"], limit_per_query=25,
                              published_after="2026-09-23T00:00:00")
        params = parse_qs(urlsplit(requested[0]).query)
        self.assertEqual(params["q"], ["Copilot Studio"])
        self.assertEqual(params["limit"], ["25"])
        self.assertEqual(params["published-after"], ["2026-09-23T00:00:00"])
        self.assertEqual(params["sort"], ["pubdate-desc"])
        self.assertEqual(result.queries[0].total_available, 2)
        self.assertEqual(len(result.jobs), 2)

    def test_limit_is_guarded(self):
        with self.assertRaises(ValueError):
            JobTechSource(loader=lambda _: self.payload).fetch(["AI"], limit_per_query=101)

    def test_paginates_recent_results_without_silent_first_page_truncation(self):
        requested = []
        def loader(url):
            requested.append(url)
            offset = int(parse_qs(urlsplit(url).query)["offset"][0])
            return {"total": {"value": 3}, "hits": [dict(self.payload["hits"][0], id=str(offset + i))
                                                   for i in range(2 if offset == 0 else 1)]}
        result = JobTechSource(loader=loader).fetch(["AI"], limit_per_query=2)
        self.assertEqual(len(result.jobs), 3)
        self.assertEqual(result.queries[0].pages_requested, 2)
        self.assertEqual(parse_qs(urlsplit(requested[1]).query)["offset"], ["2"])


if __name__ == "__main__":
    unittest.main()

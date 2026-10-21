import unittest
from dataclasses import replace

from job_agent.application_route import application_route
from test_automation import job


class ApplicationRouteTests(unittest.TestCase):
    def route(self, url):
        return application_route(replace(job(), apply_url=url))

    def test_ashby_route_is_preview_only_and_does_not_claim_open(self):
        url = "https://jobs.ashbyhq.com/example/01234567-89ab-cdef-0123-456789abcdef"
        route = self.route(url)
        self.assertTrue(route["preview_supported"])
        self.assertEqual(route["url"], url + "/application")
        self.assertEqual(self.route(route["url"])["url"], route["url"])
        self.assertEqual(route["posting_open"], "unverified")
        self.assertFalse(route["can_submit"])

    def test_teamtailor_custom_domain_does_not_reuse_ashby_adapter(self):
        route = self.route("https://career.example.test/jobs/1234567-ai-developer/applications/new")
        self.assertEqual(route["status"], "unsupported_provider")
        self.assertTrue(route["inspection_supported"])
        self.assertFalse(route["preview_supported"])

    def test_homepage_and_source_listing_are_not_direct_forms(self):
        for url in ("https://example.test", "https://arbetsformedlingen.se/platsbanken/annonser/123"):
            with self.subTest(url=url):
                self.assertEqual(self.route(url)["status"], "no_direct_form")

    def test_insecure_urls_and_credentials_never_enable_preview(self):
        urls = ["http://example.test/", "https://user:pass@jobs.ashbyhq.com/example/0123456789abcdef",
                "https://jobs.ashbyhq.com:bad/example/0123456789abcdef"]
        for url in urls:
            with self.subTest(url=url):
                self.assertFalse(self.route(url)["preview_supported"])
                self.assertFalse(self.route(url)["can_submit"])

    def test_similar_hostname_and_arbitrary_paths_do_not_enable_driver(self):
        for url in ("https://jobs.ashbyhq.com.evil.test/example/0123456789abcdef",
                    "https://jobs.ashbyhq.com/example/",
                    "https://example.test/form"):
            with self.subTest(url=url):
                self.assertFalse(self.route(url)["preview_supported"])

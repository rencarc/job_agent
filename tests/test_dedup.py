import unittest

from job_agent.dedup import ats_identity, canonical_url, duplicate_match, fingerprint
from job_agent.models import Job


class DedupTests(unittest.TestCase):
    def test_tracking_parameters_do_not_change_canonical_url(self):
        base = "https://careers.example.com/jobs/123"
        tracked = base + "?utm_source=linkedin&fbclid=abc"
        self.assertEqual(canonical_url(base), canonical_url(tracked))

    def test_greenhouse_id_has_highest_priority(self):
        a = Job("a", "Acme", "AI Engineer", apply_url="https://job-boards.greenhouse.io/acme/jobs/123456?utm_source=x")
        b = Job("b", "ACME AB", "Different imported title", apply_url="https://boards.greenhouse.io/acme/jobs/123456")
        self.assertEqual(ats_identity(a), ("greenhouse", "123456"))
        self.assertEqual(duplicate_match(a, b).reason, "ats_job_id")

    def test_exact_canonical_url_is_duplicate(self):
        a = Job("a", "Acme", "AI Engineer", source_url="https://example.test/jobs/42?ref=linkedin")
        b = Job("b", "Acme", "AI Engineer", source_url="https://example.test/jobs/42")
        self.assertEqual(duplicate_match(a, b).reason, "canonical_url")

    def test_fingerprint_normalises_case_and_punctuation(self):
        a = Job("a", "Acme & Co.", "AI-Engineer", "Stockholm", apply_url="https://jobs.example.test/a")
        b = Job("b", "ACME and CO", "AI Engineer", "stockholm", apply_url="https://jobs.example.test/b")
        self.assertEqual(fingerprint(a), fingerprint(b))
        self.assertEqual(duplicate_match(a, b).reason, "company_title_location_domain")

    def test_same_title_at_different_company_is_not_duplicate(self):
        a = Job("a", "Acme", "AI Engineer", "Stockholm", apply_url="https://jobs.example.test/a")
        b = Job("b", "Beta", "AI Engineer", "Stockholm", apply_url="https://jobs.example.test/b")
        self.assertFalse(duplicate_match(a, b).duplicate)


if __name__ == "__main__":
    unittest.main()


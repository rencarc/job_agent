import unittest

from job_agent.models import Decision, Job
from job_agent.scoring import score_job


class ScoringTests(unittest.TestCase):
    def test_strong_power_platform_role_is_retained(self):
        job = Job("1", "Acme", "Junior Copilot Studio Developer", "Stockholm",
                  "Build Power Platform, Power Automate, Dataverse, RAG and API integrations. Swedish is a plus.",
                  apply_url="https://example.test/1")
        result = score_job(job)
        self.assertGreaterEqual(result.score, 80)
        self.assertEqual(result.decision, Decision.STRONG)
        self.assertFalse(result.hard_blocker)

    def test_citizenship_is_categorical_blocker(self):
        job = Job("2", "Acme", "AI Engineer", "Stockholm",
                  "Excellent RAG and Python fit. Swedish citizenship is required.",
                  apply_url="https://example.test/2")
        result = score_job(job)
        self.assertTrue(result.hard_blocker)
        self.assertEqual(result.score, 0)
        self.assertEqual(result.decision, Decision.REVIEW)  # shadow mode preserves it

    def test_incomplete_job_requires_review(self):
        result = score_job(Job("3", "", "AI Engineer"))
        self.assertEqual(result.decision, Decision.REVIEW)
        self.assertLess(result.confidence, 0.80)

    def test_senior_role_is_not_mistaken_for_strong_fit(self):
        job = Job("4", "Acme", "Principal AI Engineer", "Stockholm",
                  "10+ years required. Build LLM agents, RAG, Python APIs and Azure AI.",
                  apply_url="https://example.test/4")
        result = score_job(job)
        self.assertNotEqual(result.decision, Decision.STRONG)
        self.assertLessEqual(result.dimensions["seniority_fit"], 20)

    def test_sweden_locations_have_equal_default_score(self):
        details = "Build Power Platform and Python integrations."
        stockholm = Job("5", "Acme", "Developer", "Stockholm", details, apply_url="https://example.test/5")
        umea = Job("6", "Acme", "Developer", "Umeå", details, apply_url="https://example.test/6")
        self.assertEqual(score_job(stockholm).score, score_job(umea).score)

    def test_location_preference_changes_rank_without_excluding(self):
        stockholm = Job("5", "Acme", "Developer", "Stockholm", "Build APIs", apply_url="https://example.test/5")
        umea = Job("6", "Acme", "Developer", "Umeå", "Build APIs", apply_url="https://example.test/6")
        preferred = score_job(umea, preferred_locations=("Umeå",))
        other = score_job(stockholm, preferred_locations=("Umeå",))
        self.assertGreater(preferred.score, other.score)
        self.assertFalse(other.hard_blocker)


if __name__ == "__main__":
    unittest.main()

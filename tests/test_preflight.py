import unittest
from datetime import date
from pathlib import Path

from job_agent.history import HistoryMatch
from job_agent.models import Job
from job_agent.preflight import check_preflight
from job_agent.resume_variants import ResumeVariant
from job_agent.variant_scoring import evaluate_variants
from job_agent.eligibility_answers import EligibilityAnswers


class PreflightTests(unittest.TestCase):
    def test_high_provisional_score_never_bypasses_uncalibrated_gate(self):
        job = Job("1", "A", "AI Engineer", location="Stockholm", description="Python AI LLM RAG",
                  apply_url="https://example.test/1", location_status="sweden")
        score = evaluate_variants(job, [ResumeVariant("ai", Path("ai.pdf"), ("AI", "Python", "LLM"))])
        result = check_preflight(job, HistoryMatch("new", "none"), score, posting_open=True,
                                 form_supported=True, profile_complete=True, calibrated_threshold=0)
        self.assertFalse(result.ready)
        self.assertTrue(any("calibrated" in reason for reason in result.reasons))

    def test_history_and_unverified_posting_remain_visible(self):
        job = Job("2", "A", "Engineer", apply_url="https://example.test/2")
        score = evaluate_variants(job, [ResumeVariant("ai", Path("ai.pdf"), ("AI",))])
        result = check_preflight(job, HistoryMatch("review", "similar"), score)
        self.assertTrue(any("history" in reason for reason in result.reasons))
        self.assertTrue(any("open status" in reason for reason in result.reasons))

    def test_explicit_no_sponsorship_blocks_user_who_requires_employer_support(self):
        job = Job("3", "Clera", "Senior AI Engineer", "Stockholm",
                  "On-site in Stockholm, Sweden. Visa sponsorship is not available.",
                  apply_url="https://example.test/3", location_status="sweden")
        score = evaluate_variants(job, [ResumeVariant("ai", Path("ai.pdf"), ("AI",))])
        eligibility = EligibilityAnswers("SE", True, True, date.today())
        result = check_preflight(job, HistoryMatch("new", "none"), score,
                                 posting_open=True, form_supported=True, profile_complete=True,
                                 eligibility=eligibility)
        self.assertTrue(any("sponsorship" in reason for reason in result.reasons))

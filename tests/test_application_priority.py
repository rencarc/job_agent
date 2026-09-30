import unittest
from pathlib import Path

from job_agent.application_priority import assess_priority
from job_agent.career_facts import load_facts
from job_agent.models import Job
from job_agent.resume_variants import ResumeVariant
from job_agent.variant_scoring import evaluate_variants


ROOT = Path(__file__).resolve().parents[1]


class PriorityTests(unittest.TestCase):
    def test_relevant_job_may_be_high_priority_but_not_auto_submitted(self):
        facts = load_facts(ROOT / "data/career_facts_draft.json")
        job = Job("1", "A", "AI Automation Power Platform Developer", "Stockholm",
                  "Copilot Studio, Power Apps, Dataverse, workflow automation, Python, RAG")
        variant = ResumeVariant("ai", Path("sample_ai_resume.pdf"), ("AI", "Copilot Studio", "Power Apps"))
        priority = assess_priority(evaluate_variants(job, [variant], facts))
        self.assertEqual(priority.band, "high")
        self.assertFalse(priority.can_auto_submit)

    def test_low_scoring_positive_is_not_automatically_rejected(self):
        job = Job("2", "A", "Business Analyst", "Göteborg", "stakeholder collaboration")
        variant = ResumeVariant("business", Path("business.pdf"), ("operations",))
        priority = assess_priority(evaluate_variants(job, [variant]))
        self.assertEqual(priority.band, "manual_review")

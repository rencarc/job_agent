import unittest
from pathlib import Path

from job_agent.career_facts import load_facts
from job_agent.models import Job
from job_agent.resume_variants import ResumeVariant
from job_agent.tailoring_plan import plan_tailoring


class TailoringPlanTests(unittest.TestCase):
    def test_only_cv_supported_keywords_reach_edit_plan(self):
        facts = load_facts(Path(__file__).resolve().parents[1] / "data/career_facts_draft.json")
        variant = ResumeVariant("ai", Path("sample_ai_resume.pdf"), ("Python", "Kubernetes"))
        job = Job("1", "A", "AI Engineer", description="Python and Kubernetes experience required")
        plan = plan_tailoring(job, variant, facts, ["Python", "Kubernetes"])
        self.assertEqual(plan.supported_keywords, ("Python",))
        self.assertEqual(plan.unsupported_keywords, ("Kubernetes",))
        self.assertFalse(plan.latex_ready)

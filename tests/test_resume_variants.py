import unittest
from pathlib import Path

from job_agent.models import Job
from job_agent.resume_variants import ResumeVariant, choose_resume
from job_agent.variant_scoring import evaluate_variants


class ResumeSelectionTests(unittest.TestCase):
    variants = [ResumeVariant("ai", Path("ai.pdf"), ("AI", "RAG", "Copilot")),
                ResumeVariant("software", Path("software.pdf"), ("Backend", "Python", "API")),
                ResumeVariant("business", Path("business.pdf"), ("Operations", "E-commerce", "Sales"))]

    def test_selects_best_of_three_by_title_and_description(self):
        result = choose_resume(Job("1", "Acme", "Backend Engineer", description="Build Python APIs"), self.variants)
        self.assertEqual(result.variant.variant_id, "software")
        self.assertEqual(result.confidence, "supported")

    def test_unknown_or_tie_requires_review(self):
        self.assertEqual(choose_resume(Job("1", "Acme", "Generalist"), self.variants).confidence, "review")

    def test_variant_can_be_swapped_without_code_changes(self):
        variants = [ResumeVariant("custom", Path("new.tex"), ("Dataverse",), latex_source=Path("new.tex"))]
        self.assertEqual(choose_resume(Job("1", "Acme", "Dataverse Developer"), variants).variant.variant_id, "custom")

    def test_short_ai_term_does_not_match_inside_another_word(self):
        self.assertEqual(choose_resume(Job("1", "Acme", "Training Coordinator"), self.variants).confidence, "review")

    def test_variant_score_is_provisional_not_auto_submit_permission(self):
        job = Job("1", "Acme", "Copilot AI Developer", "Umeå",
                  "Build RAG and workflow automation", apply_url="https://example.test/apply")
        result = evaluate_variants(job, self.variants)
        self.assertEqual(result.choice.variant.variant_id, "ai")
        self.assertGreater(result.variant_fit, 0)
        self.assertFalse(result.eligible_for_auto_submit)

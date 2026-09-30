import unittest
from pathlib import Path

from job_agent.career_facts import load_facts, matching_facts
from job_agent.models import Job
from job_agent.resume_variants import ResumeVariant
from job_agent.variant_scoring import evaluate_variants


FACTS = Path(__file__).resolve().parents[1] / "data" / "career_facts_draft.json"


class FactTests(unittest.TestCase):
    def test_ai_cv_title_has_variant_specific_provenance(self):
        facts = load_facts(FACTS)
        self.assertTrue(all(f.sources for f in facts))
        title = next(f for f in facts if f.fact_id == "sample_title_ai")
        self.assertIn("Business & Operations Manager", title.claim)
        self.assertEqual(title.sources, ("sample_ai_resume.pdf",))
        self.assertFalse(any("Commercial Operations Coordinator" in f.claim for f in facts))

    def test_job_match_cites_fact_ids_and_ignores_unknown_skills(self):
        facts = load_facts(FACTS)
        variants = [ResumeVariant("power", Path("sample_power_platform_resume.pdf"), ("Dataverse", "Power Apps")),
                    ResumeVariant("business", Path("sample_business_operations_resume.pdf"), ("export", "supplier"))]
        job = Job("1", "A", "Power Apps Developer", "Umeå",
                  "Dataverse and SharePoint. Kubernetes expert required.", apply_url="https://example.test/1")
        result = evaluate_variants(job, variants, facts)
        self.assertEqual(result.choice.variant.variant_id, "power")
        self.assertIn("sample_power_platform", result.matched_fact_ids)
        self.assertFalse(any("Kubernetes" in fact.claim for fact in facts))
        self.assertFalse(result.eligible_for_auto_submit)

    def test_boundary_matching_does_not_match_ai_in_paid(self):
        facts = load_facts(FACTS)
        self.assertFalse(any("AI" in terms for _, terms in matching_facts("paid leave", facts)))

    def test_ai_specific_hebei_title_does_not_leak_into_business_cv_score(self):
        facts = load_facts(FACTS)
        business = ResumeVariant("business", Path("sample_business_operations_resume.pdf"),
                                 ("operations manager",))
        job = Job("1", "A", "Operations Manager", description="business operations manager")
        result = evaluate_variants(job, [business], facts)
        self.assertNotIn("sample_title_ai", result.matched_fact_ids)

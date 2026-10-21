import unittest
from job_agent.qualifications import required_skill_gaps, technical_seniority_evidence
from test_automation import profile


class QualificationTests(unittest.TestCase):
    def test_swedish_words_and_parenthesized_years(self):
        for phrase in ("Minst fem års erfarenhet som AI Developer.",
                       "Flera (5+) års erfarenhet av Microsoft 365.",
                       "At least 5 years of experience building production models and AI solutions.",
                       "At least three years of experience in IT Operation or infrastructure."):
            with self.subTest(phrase=phrase):
                self.assertTrue(technical_seniority_evidence("AI Engineer", phrase))

    def test_seniority_inside_description_is_not_lost(self):
        self.assertTrue(technical_seniority_evidence("AI Engineer", "Som Senior AI Engineer arbetar du med AI."))
        self.assertTrue(technical_seniority_evidence("Backend Engineer", "You've operated backend systems in production and owned their reliability."))
        self.assertTrue(technical_seniority_evidence("AI Engineer", "We are looking for a Senior Machine Learning Engineer."))

    def test_business_years_do_not_become_technical_years(self):
        self.assertEqual(technical_seniority_evidence("AI Engineer", "Five years in export sales."), [])

    def test_optional_years_do_not_become_required(self):
        self.assertEqual(technical_seniority_evidence("AI Engineer", "Five years of software development preferred."), [])

    def test_missing_required_dotnet_is_explicit_evidence(self):
        text = "Du behöver ha praktisk erfarenhet av:\nC# och .NET.\nPython och API.\nDet är även meriterande om du har erfarenhet av:\nKubernetes."
        evidence = required_skill_gaps(text, profile())
        self.assertEqual({item["skill"] for item in evidence}, {"C#", ".NET"})

    def test_optional_stack_and_known_alternatives_do_not_create_false_gaps(self):
        self.assertEqual(required_skill_gaps("Requirements:\nPython or Java.\nKubernetes is optional.", profile()), [])

    def test_supported_skill_is_not_called_missing(self):
        value = profile()
        value["skills"]["C#"] = ["project"]
        self.assertEqual(required_skill_gaps("C# is required.", value), [])

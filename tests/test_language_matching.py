import unittest
from dataclasses import replace

from job_agent.automation import rule_match, validate_profile
from job_agent.requirements import assess_languages, language_requirements
from test_automation import job, profile


class LanguageMatchingTests(unittest.TestCase):
    def test_swedish_adjective_variants_apply_to_both_languages(self):
        reasons, evidence = assess_languages("Är obehindrad i både svenska och engelska i tal och skrift.",
                                            ["sv", "en"], {"sv": "intermediate", "en": "fluent"})
        self.assertEqual(len(reasons), 1)
        self.assertIn("sv: intermediate vs fluent", reasons[0])
        self.assertEqual({e["language"] for e in evidence}, {"sv", "en"})

    def test_swedish_expression_ability_is_not_merely_a_language_mention(self):
        reasons, _ = assess_languages("Mycket god förmåga att uttrycka dig på svenska i tal och skrift.",
                                     ["sv"], {"sv": "intermediate"})
        self.assertTrue(reasons)

    def test_fluent_english_clears_known_fluent_english(self):
        reasons, evidence = assess_languages("Fluent English is required.", ["en"], {"en": "fluent"})
        self.assertEqual(reasons, [])
        self.assertEqual(evidence[0]["level"], "fluent")

    def test_intermediate_swedish_does_not_clear_fluent_requirement(self):
        reasons, _ = assess_languages("Flytande svenska krävs.", ["sv"], {"sv": "intermediate"})
        self.assertEqual(len(reasons), 1)
        self.assertIn("level gap", reasons[0])

    def test_optional_or_negated_undeclared_language_does_not_block(self):
        for phrase in ("Finnish is not required.", "Finska krävs inte.", "Swedish is preferred.", "Swedish is a plus.",
                       "Fluent English required, Swedish nice to have."):
            with self.subTest(phrase=phrase):
                self.assertEqual(assess_languages(phrase, ["en"], {"en": "fluent"})[0], [])

    def test_customer_language_mention_is_not_a_hiring_requirement(self):
        self.assertEqual(assess_languages("We sell to the Finnish market.", ["en"], {"en": "fluent"})[0], [])

    def test_combined_required_languages_keep_each_language(self):
        reasons, evidence = assess_languages("Fluent in Swedish and English is required.", ["sv", "en"],
                                            {"sv": "intermediate", "en": "fluent"})
        self.assertEqual({item["language"] for item in evidence}, {"sv", "en"})
        self.assertEqual(len(reasons), 1)
        self.assertIn("sv", reasons[0])

    def test_mixed_requirement_and_preference_are_separate(self):
        reasons, evidence = assess_languages("English is required, Swedish is preferred.", ["en"], {"en": "fluent"})
        self.assertEqual(reasons, [])
        self.assertEqual([item["state"] for item in evidence], ["required", "not_required_or_preferred"])

    def test_native_swedish_and_fluent_english_do_not_share_wrong_level(self):
        reasons, evidence = assess_languages("Native Swedish and fluent English are required.", ["sv", "en"],
                                            {"sv": "intermediate", "en": "fluent"})
        self.assertEqual(len(reasons), 1)
        self.assertEqual([(x["language"], x["level"]) for x in evidence], [("sv", "native"), ("en", "fluent")])

    def test_language_code_without_level_still_needs_review(self):
        self.assertEqual(len(assess_languages("English is required.", ["en"], {})[0]), 1)

    def test_fluent_english_satisfies_generic_spoken_english(self):
        self.assertEqual(assess_languages("Strong written and spoken English skills.", ["en"], {"en": "fluent"})[0], [])

    def test_unknown_level_cannot_be_silently_upgraded(self):
        value = profile()
        value["language_levels"] = {"en": "probably fluent"}
        with self.assertRaises(ValueError):
            validate_profile(value)

    def test_language_gap_does_not_get_hidden_by_generic_history_reason(self):
        value = profile()
        value["languages"].append("sv")
        value["language_levels"] = {"en": "fluent", "sv": "intermediate"}
        result = rule_match(replace(job(), description="Python API. Fluent English required. Swedish is preferred."), value)
        self.assertEqual(result["decision"], "prepare")
        result = rule_match(replace(job(), description="Python API. Fluent Swedish required."), value)
        self.assertEqual(result["decision"], "exception")

    def test_skill_aliases_count_a_canonical_skill_once(self):
        value = profile()
        value["skill_aliases"] = {"API": ["REST integration", "REST API"]}
        result = rule_match(replace(job(), description="Python REST integration using REST API."), value)
        self.assertEqual(len(result["evidence"]), 2)
        self.assertEqual(result["decision"], "prepare")

    def test_technical_years_are_not_satisfied_by_unrelated_business_experience(self):
        value = profile()
        value["technical_seniority"] = "early_career"
        result = rule_match(replace(job(), description="Python API. At least 5 years of software development experience required."), value)
        self.assertEqual(result["decision"], "exception")
        result = rule_match(replace(job(), description="Python API. 5 years of software development experience preferred."), value)
        self.assertEqual(result["decision"], "prepare")

    def test_senior_title_cannot_pass_just_by_matching_common_keywords(self):
        value = {**profile(), "technical_seniority": "early_career"}
        result = rule_match(replace(job(), title="Senior AI Engineer"), value)
        self.assertEqual(result["decision"], "exception")
        self.assertTrue(any("senior technical role" in r for r in result["reasons"]))

import json
import tempfile
import unittest
from pathlib import Path

from job_agent.answer_bank import answer_question, load_answers
from job_agent.career_facts import load_facts


ROOT = Path(__file__).resolve().parents[1]


class AnswerBankTests(unittest.TestCase):
    def test_draft_cannot_be_submitted(self):
        facts = load_facts(ROOT / "data/career_facts_draft.json")
        bank = load_answers(ROOT / "data/answer_bank.example.json", facts)
        with self.assertRaises(ValueError):
            answer_question("Har du erfarenhet av Power Apps?", "sv", "power_platform_experience", bank)

    def test_approved_answer_respects_actual_question_language(self):
        facts = load_facts(ROOT / "data/career_facts_draft.json")
        template = json.loads((ROOT / "data/answer_bank.example.json").read_text())
        template["answers"][0]["approved"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "answers.json"
            path.write_text(json.dumps(template))
            bank = load_answers(path, facts)
        sv = answer_question("Har du erfarenhet av Power Apps?", "sv", "power_platform_experience", bank)
        en = answer_question("Do you have Power Apps experience?", "en", "power_platform_experience", bank)
        self.assertIn("I ett exempelprojekt", sv.value)
        self.assertIn("In a sample project", en.value)
        self.assertEqual((sv.question_language, sv.answer_language), ("sv", "sv"))

    def test_unknown_fact_reference_fails(self):
        facts = load_facts(ROOT / "data/career_facts_draft.json")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "answers.json"
            path.write_text(json.dumps({"answers": [{"id": "permit", "fact_ids": ["work_permit"], "en": "Yes", "sv": "Ja", "approved": True}]}))
            with self.assertRaises(ValueError):
                load_answers(path, facts)

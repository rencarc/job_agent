import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from job_agent.eligibility_answers import eligibility_field, load_eligibility
from job_agent.form_plan import FormControl, plan_form


class EligibilityAnswerTests(unittest.TestCase):
    def load(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return load_eligibility(path)

    def profile(self):
        return self.load({"country_code": "SE", "work_authorized_now": True,
                          "employer_support_required": True,
                          "confirmed_on": date.today().isoformat(), "confirmed_by_user": True})

    def test_two_yes_answers_are_distinct_and_localized(self):
        answers = self.profile()
        en = eligibility_field("Do you have work authorization to work in that country?",
                               "work_authorization", job_country="SE", answers=answers)
        sv = eligibility_field("Behöver du stöd från arbetsgivaren för arbetstillstånd?",
                               "employer_support", job_country="SE", answers=answers)
        self.assertEqual((en.value, en.question_language), ("Yes", "en"))
        self.assertEqual((sv.value, sv.question_language), ("Ja", "sv"))

    def test_other_country_and_stale_answer_require_review(self):
        answers = self.profile()
        question = "Do you have work authorization to work in that country?"
        with self.assertRaises(ValueError):
            eligibility_field(question, "work_authorization", job_country="NO", answers=answers)
        with self.assertRaises(ValueError):
            eligibility_field(question, "work_authorization", job_country="SE", answers=answers,
                              today=date.today() + timedelta(days=31))

    def test_form_plan_uses_explicit_question_mapping_only_for_sweden(self):
        question = "Do you have work authorization to work in that country?"
        control = FormControl(question, "choice")
        mapping = {question: "work_authorization"}
        ready = plan_form([control], {}, {}, {}, eligibility=self.profile(),
                          job_country="SE", eligibility_question_ids=mapping)
        self.assertTrue(ready.ready)
        self.assertEqual(ready.fields[0].value, "Yes")
        blocked = plan_form([control], {}, {}, {}, eligibility=self.profile(),
                            job_country="", eligibility_question_ids=mapping)
        self.assertFalse(blocked.ready)

    def test_example_with_unknown_answers_cannot_load(self):
        with self.assertRaises(ValueError):
            load_eligibility(Path(__file__).resolve().parents[1] / "data/application_eligibility.example.json")

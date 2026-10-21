import copy
import unittest
from datetime import date

from job_agent.form_preferences import preference_plan


class FormPreferenceTests(unittest.TestCase):
    def setUp(self):
        self.preferences = {"confirmed_by_user": True, "confirmed_on": "2026-10-20",
            "available_immediately": True, "salary": {"amount": 41000, "currency": "SEK", "period": "month", "basis": "gross"}}
        self.inspection = {"provider": "teamtailor", "inspection_only": True, "url": "https://example.test/form", "controls": [
            {"key": "start", "label": "Tidigast tillgänglig?", "kind": "date", "required": True},
            {"key": "pay", "label": "Vad är ditt löneanspråk?", "kind": "number", "required": True},
            {"key": "match", "label": "Matchar du skall kraven?", "kind": "choice", "required": True}]}

    def plan(self, **kwargs):
        return preference_plan(kwargs.get("inspection", self.inspection), kwargs.get("preferences", self.preferences),
                               today=kwargs.get("today", date(2026, 10, 21)))

    def test_confirmed_values_are_suggestions_and_never_answer_requirements(self):
        plan = self.plan()
        self.assertEqual([a["value"] for a in plan["answers"]], ["2026-10-21", "41000"])
        self.assertEqual([u["key"] for u in plan["unresolved_required"]], ["match"])
        self.assertTrue(all(a["suggestion_only"] for a in plan["answers"]))
        self.assertFalse(plan["can_submit"])
        self.assertTrue(plan["form_unit_verification_required"])

    def test_immediate_availability_uses_run_date_not_original_confirmation_date(self):
        self.assertEqual(self.plan(today=date(2026, 10, 22))["answers"][0]["value"], "2026-10-22")

    def test_stale_future_and_unconfirmed_preferences_fail(self):
        for values in ({"confirmed_on": "2026-08-01"}, {"confirmed_on": "2026-10-22"}, {"confirmed_by_user": False}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.plan(preferences={**self.preferences, **values})

    def test_monthly_amount_is_not_converted_to_annual_hourly_net_or_other_currency(self):
        for label in ("Annual salary", "Hourly salary", "Net salary", "Salary EUR"):
            inspection = copy.deepcopy(self.inspection)
            inspection["controls"][1]["label"] = label
            with self.subTest(label=label):
                plan = self.plan(inspection=inspection)
                self.assertEqual([a["key"] for a in plan["answers"]], ["start"])
                self.assertIn("pay", [u["key"] for u in plan["unresolved_required"]])

    def test_unknown_availability_and_salary_are_not_fabricated(self):
        plan = self.plan(preferences={**self.preferences, "available_immediately": None, "salary": {}})
        self.assertEqual(plan["answers"], [])
        self.assertEqual(len(plan["unresolved_required"]), 3)

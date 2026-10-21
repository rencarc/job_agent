import unittest
from datetime import date

from job_agent.eligibility_answers import EligibilityAnswers, eligibility_field


class EligibilityScopeTests(unittest.TestCase):
    def setUp(self):
        # Synthetic facts: current work allowed, future support required,
        # employer support required right now is explicitly UNKNOWN.
        self.answers = EligibilityAnswers("SE", True, True, date.today(), None, True)

    def test_current_work_authorization_and_future_support_can_both_be_yes(self):
        work = eligibility_field("Are you authorized to work in Sweden?", "work_authorization",
                                 job_country="SE", answers=self.answers)
        future = eligibility_field("Will you now or in the future require employer sponsorship?", "employer_support",
                                   job_country="SE", answers=self.answers)
        self.assertEqual((work.value, future.value), ("Yes", "Yes"))

    def test_future_confirmation_does_not_invent_current_support_answer(self):
        for question in ("Do you currently require employer sponsorship?", "Do you require employer sponsorship?"):
            with self.subTest(question=question), self.assertRaises(ValueError):
                eligibility_field(question, "employer_support", job_country="SE", answers=self.answers)

    def test_future_only_question_is_supported(self):
        answer = eligibility_field("Will you require employer sponsorship in the future?", "employer_support",
                                   job_country="SE", answers=self.answers)
        self.assertEqual(answer.value, "Yes")

    def test_permanent_right_is_not_inferred_from_current_permission(self):
        with self.assertRaises(ValueError):
            eligibility_field("Do you have permanent work authorization?", "work_authorization",
                              job_country="SE", answers=self.answers)

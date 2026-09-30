import unittest

from job_agent.eligibility_question import classify_eligibility_question


class EligibilityQuestionTests(unittest.TestCase):
    def test_recognizes_known_english_and_swedish_wording(self):
        self.assertEqual(classify_eligibility_question("Do you have work authorization to work in that country?"), "work_authorization")
        self.assertEqual(classify_eligibility_question("Will you now or in the future require employer sponsorship?"), "employer_support")
        self.assertEqual(classify_eligibility_question("Har du rätt att arbeta i Sverige?"), "work_authorization")
        self.assertEqual(classify_eligibility_question("Behöver du stöd från arbetsgivaren för arbetstillstånd?"), "employer_support")

    def test_ambiguous_or_unrelated_is_unmapped(self):
        self.assertIsNone(classify_eligibility_question("Do you require work authorization sponsorship?"))
        self.assertIsNone(classify_eligibility_question("What is your salary expectation?"))

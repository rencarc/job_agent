import unittest

from job_agent.question_language import detect_question_language


class QuestionLanguageTests(unittest.TestCase):
    def test_detects_ordinary_questions(self):
        self.assertEqual(detect_question_language("What experience do you have with Power Apps?"), "en")
        self.assertEqual(detect_question_language("Har du erfarenhet av Power Apps?"), "sv")

    def test_abstains_on_short_or_mixed_language(self):
        self.assertIsNone(detect_question_language("Power Apps?"))
        self.assertIsNone(detect_question_language("Har du experience?"))

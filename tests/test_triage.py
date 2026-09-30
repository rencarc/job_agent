import unittest

from job_agent.models import Job
from job_agent.triage import title_triage


class TitleTriageTests(unittest.TestCase):
    def test_industrial_automation_is_not_software_candidate(self):
        self.assertEqual(title_triage(Job("1", "A", "Instrument- och automationselektriker")), "likely_unrelated")

    def test_relevant_titles_are_candidates(self):
        for title in ("Founding AI Engineer", "Power Platform Developer", "Systemutvecklare", "Fullstack Engineer"):
            with self.subTest(title=title):
                self.assertEqual(title_triage(Job("1", "A", title)), "candidate")

    def test_unknown_role_retained_for_review(self):
        self.assertEqual(title_triage(Job("1", "A", "Technical Project Lead")), "unclear")

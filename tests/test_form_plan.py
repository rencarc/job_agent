import unittest

from job_agent.form_plan import FormControl, plan_form


class FormPlanTests(unittest.TestCase):
    def test_actual_ashby_work_authorization_requires_confirmed_answer(self):
        controls = [FormControl("Name", "text"), FormControl("Email", "email"),
                    FormControl("Resume", "file"), FormControl("LinkedIn", "url"),
                    FormControl("Do you have work authorization to work in that country?", "choice")]
        profile = {"Name": "Test Candidate", "Email": "test@example.test", "Resume": "/tmp/example.pdf",
                   "LinkedIn": "https://example.test/profile"}
        result = plan_form(controls, profile, {}, {})
        self.assertFalse(result.ready)
        self.assertIn("work authorization", result.unresolved[0])
        self.assertEqual(len(result.fields), 4)

    def test_unknown_control_blocks_even_if_optional(self):
        result = plan_form([FormControl("Custom interactive widget", "unknown", False)], {}, {}, {})
        self.assertFalse(result.ready)

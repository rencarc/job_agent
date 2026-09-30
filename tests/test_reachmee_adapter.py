import json
import tempfile
import unittest
from pathlib import Path

from job_agent.adapters.reachmee import check_receipt_file, check_receipt_payload, workflow
from job_agent.adapters.base import PauseReason


class ReachMeeAdapterTests(unittest.TestCase):
    def test_workflow_requires_login_and_submit_approval_pauses(self):
        pauses = workflow().user_pause_steps()
        self.assertEqual(
            [step.pause_reason for step in pauses],
            [PauseReason.BANKID_REQUIRED, PauseReason.USER_APPROVAL_REQUIRED],
        )

    def test_success_receipt_file_validates_without_resubmitting(self):
        payload = {
            "before": {"url": "https://web103.reachmee.com/apply", "cvName": "sample_cv.pdf"},
            "after": {
                "url": "https://web103.reachmee.com/application/complete",
                "bodyText": "Tack för din ansökan!",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = check_receipt_file(path)
        self.assertTrue(result.success, result.reason)
        self.assertIn("Tack för din ansökan", result.confirmation)
        self.assertTrue(result.evidence_url.startswith("https://"))

    def test_unclear_success_blocks_applied_status(self):
        payload = {
            "before": {"url": "https://web103.reachmee.com/apply", "cvName": "sample_cv.pdf"},
            "after": {"url": "https://web103.reachmee.com/apply", "bodyText": "Please wait"},
        }
        result = check_receipt_payload(payload)
        self.assertFalse(result.success)
        self.assertIn("not clear", result.reason)

    def test_missing_cv_blocks_receipt(self):
        payload = {
            "before": {"url": "https://web103.reachmee.com/apply", "cvName": ""},
            "after": {"url": "https://web103.reachmee.com/application", "bodyText": "Tack för din ansökan!"},
        }
        result = check_receipt_payload(payload)
        self.assertFalse(result.success)
        self.assertIn("CV", result.reason)


if __name__ == "__main__":
    unittest.main()

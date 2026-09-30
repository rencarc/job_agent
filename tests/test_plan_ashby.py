import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
URL = "https://jobs.ashbyhq.com/example/0000/application"


class AshbyPlanningTests(unittest.TestCase):
    def test_actual_form_shape_produces_exact_private_manifest_only_for_sweden(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            question = "Do you have work authorization to work in that country?"
            controls = [{"label": label, "kind": kind, "required": True} for label, kind in
                        [("Name", "text"), ("Email", "email"), ("Resume", "file"),
                         ("LinkedIn", "url"), (question, "choice")]]
            (root / "inspection.json").write_text(json.dumps({"url": URL, "controls": controls}))
            (root / "cv.pdf").write_bytes(b"%PDF-1.4 dummy only for manifest validation")
            (root / "profile.json").write_text(json.dumps({"confirmed_by_user": True, "fields": {
                "Name": "Test Candidate", "Email": "test@example.test",
                "Resume": str(root / "cv.pdf"), "LinkedIn": "https://example.test/profile"}}))
            (root / "eligibility.json").write_text(json.dumps({"country_code": "SE",
                "work_authorized_now": True, "employer_support_required": True,
                "confirmed_on": date.today().isoformat(), "confirmed_by_user": True}))
            command = [sys.executable, "-m", "scripts.plan_ashby", "--inspection", str(root / "inspection.json"),
                       "--profile", str(root / "profile.json"), "--eligibility", str(root / "eligibility.json"),
                       "--verified-country", "SE", "--cv-id", "ai_automation",
                       "--output", str(root / "manifest.json")]
            ok = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            manifest = json.loads((root / "manifest.json").read_text())
            self.assertEqual([f["label"] for f in manifest["fields"]], [x["label"] for x in controls])
            self.assertEqual(manifest["fields"][-1]["value"], "Yes")
            self.assertEqual(manifest["selected_cv"], "ai_automation")
            self.assertEqual(len(manifest["resume_sha256"]), 64)
            (root / "manifest.json").unlink()
            command[command.index("SE")] = "NO"
            blocked = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(blocked.returncode, 0)
            self.assertFalse((root / "manifest.json").exists())

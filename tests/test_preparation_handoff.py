import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import date

from job_agent.materials import bind_preparation_to_form


class PreparationHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cv = Path(self.tmp.name) / "cv.pdf"
        self.cv.write_bytes(b"%PDF-1.4 synthetic reviewed identity")
        self.url = "https://jobs.ashbyhq.com/example/01234567-89ab-cdef-0123-456789abcdef"
        self.plan = {"bundle_id": "synthetic", "state": "preview", "can_submit": False,
                     "posting_url": self.url, "unresolved": ["history not verified"],
                     "cv": {"id": "base", "path": str(self.cv), "modified": False,
                            "sha256": hashlib.sha256(self.cv.read_bytes()).hexdigest()}}
        self.inspection = {"url": self.url + "/application", "controls": [
            {"label": "Name", "kind": "text", "required": True},
            {"label": "Resume", "kind": "file", "required": True}]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_exact_job_reuses_reviewed_pdf_without_editing_profile(self):
        fields = {"Name": "Synthetic Candidate"}
        result = bind_preparation_to_form(self.plan, self.inspection, fields, "base")
        self.assertEqual(result["Resume"], str(self.cv))
        self.assertNotIn("Resume", fields)
        self.assertEqual(self.plan["unresolved"], ["history not verified"])
        self.assertFalse(self.plan["can_submit"])

    def test_other_job_or_same_id_at_other_company_is_rejected(self):
        for url in (self.url.replace("/example/", "/other/"), self.url.replace("01234567", "11234567")):
            with self.subTest(url=url), self.assertRaises(ValueError):
                bind_preparation_to_form(self.plan, {**self.inspection, "url": url + "/application"}, {}, "base")

    def test_changed_pdf_or_wrong_variant_cannot_be_uploaded(self):
        with self.assertRaises(ValueError):
            bind_preparation_to_form(self.plan, self.inspection, {}, "other")
        self.cv.write_bytes(b"%PDF-1.4 changed")
        with self.assertRaises(ValueError):
            bind_preparation_to_form(self.plan, self.inspection, {}, "base")

    def test_conflicting_profile_cv_is_not_overwritten(self):
        with self.assertRaises(ValueError):
            bind_preparation_to_form(self.plan, self.inspection, {"Resume": str(self.cv.with_name("other.pdf"))}, "base")

    def test_cover_letter_or_multiple_uploads_never_receive_cv(self):
        for labels in (["Cover letter"], ["Resume", "Cover letter"], ["Document"]):
            inspection = {**self.inspection, "controls": [
                {"label": label, "kind": "file", "required": True} for label in labels]}
            with self.subTest(labels=labels), self.assertRaises(ValueError):
                bind_preparation_to_form(self.plan, inspection, {}, "base")

    def test_actionable_or_modified_plan_is_rejected(self):
        for key, value in (("can_submit", True), ("state", "submitted")):
            with self.assertRaises(ValueError):
                bind_preparation_to_form({**self.plan, key: value}, self.inspection, {}, "base")
        plan = copy.deepcopy(self.plan)
        plan["cv"]["modified"] = True
        with self.assertRaises(ValueError):
            bind_preparation_to_form(plan, self.inspection, {}, "base")

    def run_planner(self, question):
        root = Path(self.tmp.name)
        inspection = copy.deepcopy(self.inspection)
        inspection["controls"].append({"label": question, "kind": "choice", "required": True})
        payloads = {"inspection": inspection, "profile": {"confirmed_by_user": True, "fields": {"Name": "Synthetic"}},
                    "plan": self.plan, "eligibility": {"country_code": "SE", "confirmed_by_user": True,
                        "confirmed_on": date.today().isoformat(), "work_authorized_now": True,
                        "employer_support_required": True, "employer_support_required_now": None,
                        "employer_support_required_future": True}}
        for name, data in payloads.items():
            (root / (name + ".json")).write_text(json.dumps(data), encoding="utf-8")
        output = root / "manifest.json"
        command = [sys.executable, "-m", "scripts.plan_ashby",
                   "--inspection", str(root / "inspection.json"), "--profile", str(root / "profile.json"),
                   "--eligibility", str(root / "eligibility.json"), "--preparation-plan", str(root / "plan.json"),
                   "--verified-country", "SE", "--cv-id", "base", "--output", str(output)]
        result = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        return result, output

    def test_cli_plan_to_manifest_preserves_unresolved_and_scoped_answers(self):
        question = "Will you now or in the future require employer sponsorship?"
        result, output = self.run_planner(question)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(output.read_text(encoding="utf-8"))
        self.assertFalse(manifest["can_submit"])
        self.assertEqual(manifest["preparation_bundle"], "synthetic")
        self.assertEqual(manifest["preparation_unresolved"], ["history not verified"])
        fields = {f["label"]: f["value"] for f in manifest["fields"]}
        self.assertEqual(fields["Resume"], str(self.cv))
        self.assertEqual(fields[question], "Yes")

    def test_cli_unknown_current_only_answer_blocks_manifest(self):
        result, output = self.run_planner("Do you currently require employer sponsorship?")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("needs review", result.stderr)
        self.assertFalse(output.exists())

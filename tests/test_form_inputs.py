import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from job_agent.form_inputs import attach_source_inputs, load_contact_profile


class FormInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.pdf = self.root / "reviewed.pdf"
        self.pdf.write_bytes(b"%PDF-1.4 synthetic source identity only")
        self.sha = hashlib.sha256(self.pdf.read_bytes()).hexdigest()
        self.contacts = {"confirmed_by_user": False, "reviewed_from_source": True,
            "source_document": str(self.pdf), "source_sha256": self.sha,
            "fields": {"first_name": "Synthetic", "last_name": "Candidate", "email": "candidate@example.test",
                       "phone": "+46123456789", "city": "Stockholm"}}
        self.cv = {"id": "base", "path": str(self.pdf), "reviewed_sha256": self.sha}
        self.controls = [
            {"key": "candidate[first_name]", "label": "Förnamn", "kind": "text", "required": True},
            {"key": "candidate[email]", "label": "E-post", "kind": "email", "required": True},
            {"key": "cv", "label": "Ladda upp CV", "kind": "file", "required": True},
            {"key": "extra", "label": "Other documents", "kind": "file", "required": False},
            {"key": "match", "label": "Meet all requirements?", "kind": "choice", "required": True}]
        self.inspection = {"controls": self.controls}
        self.plan = {"can_submit": False, "state": "preparation_only", "answers": [],
                     "unresolved_required": [{"key": c["key"], "label": c["label"]} for c in self.controls if c["required"]]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_exact_source_fields_and_reviewed_cv_extend_suggestions_only(self):
        result = attach_source_inputs(self.plan, self.inspection, contacts=self.contacts, cv=self.cv)
        self.assertEqual([a["key"] for a in result["answers"]], ["candidate[first_name]", "candidate[email]", "cv"])
        self.assertEqual([u["key"] for u in result["unresolved_required"]], ["match"])
        self.assertFalse(result["contact_profile_confirmed"])
        self.assertFalse(result["can_submit"])
        self.assertTrue(all(a["suggestion_only"] for a in result["answers"]))
        self.assertEqual(result["cv_sha256"], self.sha)
        self.assertEqual(self.plan["answers"], [])

    def test_changed_source_and_cv_are_rejected(self):
        self.pdf.write_bytes(b"%PDF-changed")
        with self.assertRaises(ValueError):
            attach_source_inputs(self.plan, self.inspection, contacts=self.contacts)
        with self.assertRaises(ValueError):
            attach_source_inputs(self.plan, self.inspection, cv=self.cv)

    def test_wrong_label_or_kind_cannot_receive_contact_data(self):
        inspection = copy.deepcopy(self.inspection)
        inspection["controls"][0]["label"] = "Supervisor name"
        inspection["controls"][1]["kind"] = "number"
        result = attach_source_inputs(self.plan, inspection, contacts=self.contacts)
        self.assertEqual(result["answers"], [])
        self.assertEqual(len(result["unresolved_required"]), 4)

    def test_ambiguous_cv_uploads_are_rejected_instead_of_filling_both(self):
        inspection = copy.deepcopy(self.inspection)
        inspection["controls"].append({"key": "cv2", "label": "CV", "kind": "file", "required": False})
        with self.assertRaises(ValueError):
            attach_source_inputs(self.plan, inspection, cv=self.cv)

    def test_unreviewed_and_malformed_contact_data_fail_before_planning(self):
        for override in ({"reviewed_from_source": False}, {"fields": {"phone": "0123456789"}},
                         {"fields": {"email": "not-an-email"}}, {"fields": {"first_name": "Name\nInjected"}}):
            path = self.root / "contacts.json"
            path.write_text(json.dumps({**self.contacts, **override}), encoding="utf-8")
            with self.subTest(override=override), self.assertRaises(ValueError):
                load_contact_profile(path)

    def test_source_inputs_cannot_extend_a_submitting_plan(self):
        with self.assertRaises(ValueError):
            attach_source_inputs({**self.plan, "can_submit": True}, self.inspection, contacts=self.contacts)

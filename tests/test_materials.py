import hashlib
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from job_agent.materials import load_catalog, prepare_materials
from test_automation import job, profile


class MaterialPreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.pdf = self.root / "reviewed.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\nSynthetic bytes for hash testing only; not a real PDF.")
        self.catalog_path = self.root / "catalog.json"
        self.catalog_path.write_text(json.dumps({"confirmed_by_user": True, "variants": [
            {"id": "base", "path": str(self.pdf), "reviewed_sha256": hashlib.sha256(self.pdf.read_bytes()).hexdigest(),
             "focus_terms": ["Python", "API"], "fact_ids": ["project"]}]}))
        self.profile = {**profile(), "work_authorized_now": True, "employer_support_required_now": None,
                        "employer_support_required_future": True}
        self.task = {"job_id": "synthetic", "job": asdict(job()), "decision": "prepare", "reasons": [],
                     "evidence": [{"skill": "Python", "fact_ids": ["project"]}]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_reuses_reviewed_pdf_and_carries_unknown_answers_honestly(self):
        catalog = load_catalog(self.catalog_path, self.profile)
        result = prepare_materials({"tasks": [self.task]}, self.profile, catalog, self.root / "plans")
        plan = json.loads(Path(result[0]["path"]).read_text())
        self.assertFalse(plan["can_submit"])
        self.assertFalse(plan["cv"]["modified"])
        self.assertFalse(plan["cover_letter"]["generated"])
        self.assertIsNone(plan["employer_support_required_now"])
        self.assertTrue(plan["employer_support_required_future"])
        self.assertIn("current-only employer support answer is unknown", plan["unresolved"])

    def test_replay_is_idempotent_and_does_not_clobber_user_edits(self):
        catalog = load_catalog(self.catalog_path, self.profile)
        first = prepare_materials({"tasks": [self.task]}, self.profile, catalog, self.root / "plans")
        second = prepare_materials({"tasks": [self.task]}, self.profile, catalog, self.root / "plans")
        self.assertEqual(first, second)
        Path(first[0]["path"]).write_text("{}")
        with self.assertRaises(ValueError):
            prepare_materials({"tasks": [self.task]}, self.profile, catalog, self.root / "plans")

    def test_changed_pdf_cannot_be_used_with_old_review_hash(self):
        self.pdf.write_bytes(b"%PDF-changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            load_catalog(self.catalog_path, self.profile)

    def test_cv_is_rechecked_if_it_changes_after_scan_started(self):
        catalog = load_catalog(self.catalog_path, self.profile)
        self.pdf.write_bytes(b"%PDF-changed-during-scan")
        with self.assertRaisesRegex(ValueError, "changed"):
            prepare_materials({"tasks": [self.task]}, self.profile, catalog, self.root / "plans")

    def test_preview_only_prepares_suggested_candidates(self):
        catalog = load_catalog(self.catalog_path, self.profile)
        tasks = [{**self.task, "decision": "preview", "suggested_decision": "prepare"},
                 {**self.task, "job_id": "not-ready", "decision": "preview", "suggested_decision": "exception"}]
        result = prepare_materials({"tasks": tasks}, self.profile, catalog, self.root / "plans", preview=True)
        self.assertEqual(len(result), 1)
        self.assertEqual(json.loads(Path(result[0]["path"]).read_text())["state"], "preview")

    def test_catalog_change_creates_new_plan_without_overwriting_old_one(self):
        catalog = load_catalog(self.catalog_path, self.profile)
        first = prepare_materials({"tasks": [self.task]}, self.profile, catalog, self.root / "plans")
        catalog[0]["focus_terms"] = ["Python"]
        second = prepare_materials({"tasks": [self.task]}, self.profile, catalog, self.root / "plans")
        self.assertNotEqual(first[0]["path"], second[0]["path"])
        self.assertTrue(Path(first[0]["path"]).is_file())

    def test_unconfirmed_catalog_needs_preview(self):
        value = json.loads(self.catalog_path.read_text())
        value["confirmed_by_user"] = False
        self.catalog_path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            load_catalog(self.catalog_path, self.profile)
        self.assertEqual(len(load_catalog(self.catalog_path, self.profile, preview=True)), 1)

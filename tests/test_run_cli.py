import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_automation import profile

ROOT = Path(__file__).resolve().parents[1]


class RunCliTests(unittest.TestCase):
    def test_offline_run_is_incremental_and_never_invents_history(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "profile.json").write_text(json.dumps(profile()), encoding="utf-8")
            (root / "settings.json").write_text(json.dumps({"queries": ["Python"]}), encoding="utf-8")
            (root / "jobs.json").write_text(json.dumps({"jobs": [{"external_id": "1", "company": "Example",
                "title": "AI Engineer", "description": "Build Python API integrations.", "location": "Stockholm",
                "location_status": "sweden", "source": "fixture", "source_url": "https://example.test/1"}]}), encoding="utf-8")
            command = [sys.executable, "-m", "job_agent.run_cli", "--settings", str(root / "settings.json"),
                       "--profile", str(root / "profile.json"), "--offline-jobs", str(root / "jobs.json"),
                       "--db", str(root / "jobs.sqlite"), "--output-dir", str(root / "output")]
            first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            latest = json.loads((root / "output/latest.json").read_text(encoding="utf-8"))
            self.assertEqual(latest["evaluated"], 0)
            self.assertEqual(latest["cached"], 1)
            self.assertEqual(latest["network"]["requests"], 0)
            self.assertEqual(latest["usage_today"], {"calls": 0, "tokens": 0})
            self.assertEqual(latest["counts"], {"exception": 1})
            self.assertIn("job", latest["tasks"][0])
            self.assertFalse(latest["tasks"][0]["can_submit"])

    def test_unconfirmed_profile_fails_before_database_or_network(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "profile.json").write_text(json.dumps({**profile(), "confirmed_by_user": False}))
            command = [sys.executable, "-m", "job_agent.run_cli", "--settings", "data/search_settings.example.json",
                       "--profile", str(root / "profile.json"), "--db", str(root / "jobs.sqlite")]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("user-confirmed", result.stderr)
            self.assertFalse((root / "jobs.sqlite").exists())

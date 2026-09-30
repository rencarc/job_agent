import json
import tempfile
import unittest
from pathlib import Path

from job_agent.search_settings import load_search_settings


class SearchSettingsTests(unittest.TestCase):
    def load(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "search.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return load_search_settings(path)

    def test_configurable_search_defaults_to_sweden_wide(self):
        settings = self.load({"queries": [" AI automation ", "systemutvecklare"], "recent_days": 2})
        self.assertEqual(settings.queries, ("AI automation", "systemutvecklare"))
        self.assertEqual(settings.recent_days, 2)
        self.assertEqual(settings.boards, ())

    def test_rejects_invalid_limits_and_extra_keys(self):
        for values in ({"queries": ["AI"], "jobtech_pages": 21},
                       {"queries": [], "recent_days": 7},
                       {"queries": ["AI"], "location": "Stockholm"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.load(values)

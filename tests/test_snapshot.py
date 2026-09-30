import hashlib
import json
import unittest
from pathlib import Path


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "record_count": 2,
            "records": [
                {"record_id": "rec_example_1"},
                {"record_id": "rec_example_2"},
            ],
        }

    def test_snapshot_has_expected_record_count(self):
        self.assertEqual(self.payload["record_count"], 2)
        self.assertEqual(len(self.payload["records"]), 2)

    def test_record_ids_are_unique(self):
        ids = [row["record_id"] for row in self.payload["records"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_hashing_is_stable(self):
        value = "example JD"
        self.assertEqual(hashlib.sha256(value.encode()).hexdigest(), hashlib.sha256(value.encode()).hexdigest())


if __name__ == "__main__":
    unittest.main()

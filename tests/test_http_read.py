import io
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError

from job_agent.http_read import JsonReader, ReadLimit
from job_agent.run_cli import scan_batch
from job_agent.search_settings import SearchSettings
from job_agent.store import JobStore


class HttpReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = JobStore(Path(self.tmp.name) / "jobs.sqlite")

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_success_cached_across_reader_restart(self):
        calls = []
        def opener(request, timeout):
            calls.append(request.full_url)
            return io.BytesIO(b'{"hits": []}')
        first = JsonReader(self.store, opener=opener)
        self.assertEqual(first("https://example.test/1"), {"hits": []})
        second = JsonReader(self.store, opener=opener)
        second("https://example.test/1")
        self.assertEqual(second.requests, 0)
        self.assertEqual(second.cache_hits, 1)
        self.assertEqual(len(calls), 1)

    def test_distinct_batches_do_not_reuse_stale_network_snapshot(self):
        calls = []
        def opener(*args, **kwargs):
            calls.append(1)
            return io.BytesIO(b'{}')
        for namespace in ("batch-1", "batch-2"):
            JsonReader(self.store, namespace=namespace, opener=opener)("https://example.test/1")
        self.assertEqual(len(calls), 2)

    def test_request_limit_counts_retries(self):
        def opener(*args, **kwargs):
            raise TimeoutError("simulated")
        reader = JsonReader(self.store, max_requests=1, opener=opener, sleep=lambda _: None)
        with self.assertRaises(ReadLimit):
            reader("https://example.test/1")
        self.assertEqual(reader.requests, 1)

    def test_retry_after_respected_and_not_retried_forever(self):
        sleeps, calls = [], []
        def opener(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise HTTPError("https://example.test", 429, "slow down", {"Retry-After": "3"}, None)
            return io.BytesIO(b'{}')
        reader = JsonReader(self.store, opener=opener, sleep=sleeps.append)
        reader("https://example.test/1")
        self.assertEqual(sleeps, [3])
        self.assertEqual(reader.requests, 2)

    def test_permanent_error_is_not_retried(self):
        def opener(*args, **kwargs):
            raise HTTPError("https://example.test", 403, "forbidden", {}, None)
        reader = JsonReader(self.store, opener=opener)
        with self.assertRaises(HTTPError):
            reader("https://example.test/1")
        self.assertEqual(reader.requests, 1)

    def test_long_retry_after_defers_without_sleep(self):
        def opener(*args, **kwargs):
            raise HTTPError("https://example.test", 429, "slow", {"Retry-After": "9999"}, None)
        reader = JsonReader(self.store, max_seconds=1, opener=opener,
                            sleep=lambda _: self.fail("must not sleep beyond deadline"))
        with self.assertRaises(ReadLimit):
            reader("https://example.test/1")

    def test_scan_cutoff_and_batch_stable_until_complete(self):
        settings = SearchSettings(("Python",))
        first = scan_batch(self.store, settings)
        second = scan_batch(self.store, settings)
        self.assertEqual(first, second)
        with self.store.db:
            self.store.db.execute("UPDATE scan_batches SET complete=1")
        third = scan_batch(self.store, settings)
        self.assertNotEqual(first[1], third[1])

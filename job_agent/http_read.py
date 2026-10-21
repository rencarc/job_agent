"""Bounded JSON reads, shared request budget, retry limits and resumable cache."""
from __future__ import annotations

import json
import time
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ReadLimit(RuntimeError):
    pass


class JsonReader:
    def __init__(self, store, *, max_requests=80, max_seconds=180, retries=1,
                 cache_seconds=900, namespace="", opener=urlopen, clock=time.monotonic, sleep=time.sleep):
        self.store, self.max_requests, self.retries = store, max_requests, retries
        self.clock, self.sleep, self.opener = clock, sleep, opener
        self.deadline = clock() + max_seconds
        self.cache_seconds = cache_seconds
        self.namespace = namespace
        self.requests = self.cache_hits = 0

    def __call__(self, url):
        cache_key = self.namespace + url
        if self.clock() >= self.deadline:
            raise ReadLimit("scan time limit reached")
        row = self.store.db.execute("SELECT payload,at FROM http_cache WHERE url=?", (cache_key,)).fetchone()
        if row and time.time() - row["at"] < self.cache_seconds:
            self.cache_hits += 1
            return json.loads(row["payload"])
        for attempt in range(self.retries + 1):
            remaining = self.deadline - self.clock()
            if self.requests >= self.max_requests or remaining <= 0:
                raise ReadLimit("scan request/time limit reached")
            self.requests += 1
            try:
                request = Request(url, headers={"Accept": "application/json", "User-Agent": "auditable-job-agent/0.2"})
                with self.opener(request, timeout=min(20, remaining)) as response:
                    # Bound memory as well as request count. Board responses beyond
                    # this limit need a paginated adapter, not silent truncation.
                    raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise ValueError("source JSON exceeds 8 MiB limit")
                payload = json.loads(raw)
                with self.store.db:
                    self.store.db.execute("INSERT OR REPLACE INTO http_cache VALUES (?,?,?)",
                                          (cache_key, json.dumps(payload), time.time()))
                return payload
            except (HTTPError, URLError, TimeoutError) as exc:
                if isinstance(exc, HTTPError) and exc.code != 429 and not 500 <= exc.code < 600:
                    raise
                if attempt == self.retries:
                    raise
                delay = 2 ** attempt
                header = exc.headers.get("Retry-After") if isinstance(exc, HTTPError) and exc.headers else None
                if header:
                    try:
                        delay = max(delay, float(header))
                    except ValueError:
                        delay = max(delay, parsedate_to_datetime(header).timestamp() - time.time())
                if delay >= self.deadline - self.clock():
                    raise ReadLimit("Retry-After exceeds remaining scan time") from exc
                self.sleep(delay)

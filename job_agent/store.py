"""Durable discovery snapshots, identities, evaluation cache and bounded runs."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from .dedup import ats_identity, canonical_url, source_identity
from .models import Job


def digest(value) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def content_hash(job: Job) -> str:
    # Discovery timestamps/transport URLs do not trigger repeated evaluations.
    return digest({key: getattr(job, key) for key in
                   ("company", "title", "location", "description", "location_status", "published_at", "updated_at",
                    "application_deadline", "removed")})


def identities(job: Job) -> list[str]:
    values = []
    ats = ats_identity(job)
    if ats:
        values.append("ats:" + json.dumps(ats))
    src = source_identity(job)
    if src:
        values.append("source:" + json.dumps(src))
    for raw in (job.apply_url, job.source_url):
        url = canonical_url(raw)
        if url:
            values.append("url:" + url)
    if not values:
        raise ValueError("job needs a source ID or valid posting URL")
    return list(dict.fromkeys(values))


class JobStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, payload TEXT NOT NULL, content_hash TEXT NOT NULL,
                first_seen REAL NOT NULL, last_seen REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS aliases (alias TEXT PRIMARY KEY, job_id TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS job_versions (
                job_id TEXT NOT NULL, content_hash TEXT NOT NULL, payload TEXT NOT NULL,
                captured_at REAL NOT NULL, PRIMARY KEY(job_id,content_hash));
            CREATE TABLE IF NOT EXISTS evaluations (
                cache_key TEXT PRIMARY KEY, job_id TEXT NOT NULL, result TEXT NOT NULL, at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS queue (
                job_id TEXT PRIMARY KEY, cache_key TEXT NOT NULL, decision TEXT NOT NULL,
                result TEXT NOT NULL, updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, started_at REAL NOT NULL, completed_at REAL, report TEXT);
            CREATE TABLE IF NOT EXISTS leases (
                name TEXT PRIMARY KEY, owner TEXT NOT NULL, expires_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS usage (
                day TEXT PRIMARY KEY, calls INTEGER NOT NULL, tokens INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS http_cache (
                url TEXT PRIMARY KEY, payload TEXT NOT NULL, at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS scan_batches (
                config_hash TEXT PRIMARY KEY, id TEXT NOT NULL, cutoff TEXT NOT NULL,
                started_at REAL NOT NULL, complete INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS workspace_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        self.db.commit()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.db.close()

    def bind_mode(self, mode: str):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO workspace_settings VALUES ('mode',?)", (mode,))
            actual = self.db.execute("SELECT value FROM workspace_settings WHERE key='mode'").fetchone()[0]
            if actual != mode:
                raise ValueError("preview and production require separate databases")

    @contextmanager
    def lease(self, name: str, *, seconds: float):
        owner = uuid.uuid4().hex
        now = time.time()
        with self.db:
            self.db.execute("DELETE FROM leases WHERE name=? AND expires_at<=?", (name, now))
            try:
                self.db.execute("INSERT INTO leases VALUES (?,?,?)", (name, owner, now + seconds))
            except sqlite3.IntegrityError as exc:
                raise RuntimeError("another automation run is active") from exc
        try:
            yield owner
        finally:
            with self.db:
                self.db.execute("DELETE FROM leases WHERE name=? AND owner=?", (name, owner))

    def ingest(self, job: Job) -> tuple[str, bool]:
        keys = identities(job)
        encoded = json.dumps(asdict(job), ensure_ascii=False)
        hashed = content_hash(job)
        now = time.time()
        with self.db:
            found = {row[0] for key in keys for row in self.db.execute("SELECT job_id FROM aliases WHERE alias=?", (key,))}
            if len(found) > 1:
                raise ValueError("conflicting posting identities need reconciliation")
            job_id = next(iter(found), digest(keys[0]))
            old = self.db.execute("SELECT content_hash FROM jobs WHERE id=?", (job_id,)).fetchone()
            self.db.execute("""INSERT INTO jobs VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                              payload=excluded.payload,content_hash=excluded.content_hash,last_seen=excluded.last_seen""",
                            (job_id, encoded, hashed, now, now))
            self.db.execute("INSERT OR IGNORE INTO job_versions VALUES (?,?,?,?)", (job_id, hashed, encoded, now))
            for key in keys:
                self.db.execute("INSERT OR IGNORE INTO aliases VALUES (?,?)", (key, job_id))
        return job_id, old is None or old[0] != hashed

    def jobs(self) -> list[tuple[str, Job]]:
        return [(row["id"], Job(**json.loads(row["payload"]))) for row in
                self.db.execute("SELECT id,payload FROM jobs ORDER BY first_seen,id")]

    def cached(self, key: str):
        row = self.db.execute("SELECT result FROM evaluations WHERE cache_key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def cache(self, key: str, job_id: str, result: dict):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO evaluations VALUES (?,?,?,?)",
                            (key, job_id, json.dumps(result, ensure_ascii=False), time.time()))

    def enqueue(self, job_id: str, key: str, result: dict):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO queue VALUES (?,?,?,?,?)",
                            (job_id, key, result["decision"], json.dumps(result, ensure_ascii=False), time.time()))

    def start_run(self) -> str:
        run_id = uuid.uuid4().hex
        with self.db:
            self.db.execute("INSERT INTO runs(id,started_at) VALUES (?,?)", (run_id, time.time()))
        return run_id

    def finish_run(self, run_id: str, report: dict):
        with self.db:
            self.db.execute("UPDATE runs SET completed_at=?,report=? WHERE id=?",
                            (time.time(), json.dumps(report, ensure_ascii=False), run_id))

    def reserve(self, day: str, *, tokens: int, max_tokens: int, max_calls: int) -> bool:
        # Reserve the maximum BEFORE dispatch. Failed/uncertain calls retain their
        # reservation; restarting cannot reset the daily allowance.
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO usage VALUES (?,0,0)", (day,))
            cursor = self.db.execute("""UPDATE usage SET calls=calls+1,tokens=tokens+?
                WHERE day=? AND calls<? AND tokens+?<=?""", (tokens, day, max_calls, tokens, max_tokens))
        return cursor.rowcount == 1

    def settle(self, day: str, reserved: int, actual: int):
        if not 0 <= actual <= reserved:
            raise ValueError("evaluator exceeded its token reservation")
        with self.db:
            self.db.execute("UPDATE usage SET tokens=tokens-? WHERE day=?", (reserved - actual, day))

    def usage(self, day: str) -> dict:
        row = self.db.execute("SELECT calls,tokens FROM usage WHERE day=?", (day,)).fetchone()
        return dict(row) if row else {"calls": 0, "tokens": 0}

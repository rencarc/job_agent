"""One bounded scan-and-select invocation. No LLM or application submission."""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .airtable_sync import AirtableClient
from .automation import Limits, load_profile, run_pipeline
from .discovery import discover_many
from .http_read import JsonReader
from .models import Job
from .materials import load_catalog, prepare_materials
from .search_settings import load_search_settings
from .sources.ats import PublicBoardSource
from .sources.jobtech import JobTechSource
from .store import JobStore, digest


def atomic_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def scan_batch(store, settings):
    """Keep the cutoff and page cache stable across interrupted bounded scans.

    Completed batches always start fresh. An unfinished batch older than a week
    raises rather than silently abandoning a queue of never-scanned sources.
    """
    config_hash = digest(asdict(settings))
    row = store.db.execute("SELECT * FROM scan_batches WHERE config_hash=?", (config_hash,)).fetchone()
    if row and not row["complete"]:
        if time.time() - row["started_at"] > 7 * 86400:
            raise ValueError("unfinished scan is over 7 days old; increase scan limits and reconcile coverage")
        return config_hash, row["id"], row["cutoff"] or None
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=settings.recent_days)).isoformat(timespec="seconds") if settings.recent_days else ""
    batch_id = uuid.uuid4().hex
    with store.db:
        store.db.execute("INSERT OR REPLACE INTO scan_batches VALUES (?,?,?,?,0)",
                         (config_hash, batch_id, cutoff, time.time()))
    return config_hash, batch_id, cutoff or None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=Path("private/job_agent.sqlite"))
    parser.add_argument("--output-dir", type=Path, default=Path("output/automation"))
    parser.add_argument("--max-requests", type=int, default=120)
    parser.add_argument("--scan-seconds", type=int, default=180)
    parser.add_argument("--max-evaluations", type=int, default=30)
    parser.add_argument("--evaluation-seconds", type=int, default=120)
    parser.add_argument("--offline-jobs", type=Path, help="Replay a local jobs snapshot; performs no network reads")
    parser.add_argument("--preview", action="store_true", help="Evaluate a draft profile without actionable tasks or Airtable reads")
    parser.add_argument("--resume-catalog", type=Path, help="Create local preparation plans using reviewed PDFs; never submits")
    args = parser.parse_args()
    try:
        settings, profile = load_search_settings(args.settings), load_profile(args.profile, allow_draft=args.preview)
        if args.preview and args.db == Path("private/job_agent.sqlite"):
            parser.error("--preview requires a separate --db path to keep draft tasks out of production")
        if not 1 <= args.max_requests <= 1000 or not 1 <= args.scan_seconds <= 3600:
            raise ValueError("max-requests must be 1..1000 and scan-seconds 1..3600")
        limits = Limits(max_evaluations=args.max_evaluations, max_seconds=args.evaluation_seconds)
        catalog = load_catalog(args.resume_catalog, profile, preview=args.preview) if args.resume_catalog else None
        with JobStore(args.db) as store:
            store.bind_mode("preview" if args.preview else "production")
            # The outer lease also protects scan checkpoints from overlapping timers.
            with store.lease("daily-scan", seconds=args.scan_seconds + limits.max_seconds + 600):
                if args.offline_jobs:
                    payload = json.loads(args.offline_jobs.read_text(encoding="utf-8"))
                    jobs = [Job(**{k: v for k, v in row.items() if k in Job.__dataclass_fields__}) for row in payload["jobs"]]
                    coverage = {"mode": "offline", "sources": []}
                    history = None  # A fixture cannot prove that an application was never sent.
                    network = {"requests": 0, "cache_hits": 0}
                else:
                    # Validate/fetch history first. A tracker failure never becomes an empty history.
                    history = None if args.preview else AirtableClient().history_records()
                    config_hash, batch_id, cutoff = scan_batch(store, settings)
                    reader = JsonReader(store, max_requests=args.max_requests, max_seconds=args.scan_seconds,
                                        namespace=batch_id + ":", cache_seconds=8 * 86400)
                    sources = [JobTechSource(loader=reader, max_pages=settings.jobtech_pages)]
                    for spec in settings.boards:
                        provider, board = spec.split(":", 1)
                        sources.append(PublicBoardSource(provider, board, loader=reader))
                    jobs, discovered = discover_many(sources, list(settings.queries),
                                                    limit_per_query=settings.limit_per_query, published_after=cutoff)
                    coverage = asdict(discovered)
                    complete = all(s.status in {"ok", "truncated"} for s in discovered.sources)
                    # Commit snapshots before declaring the cached scan complete.
                    # A later profile/export failure can then be resumed from disk.
                    for job in jobs:
                        store.ingest(job)
                    with store.db:
                        store.db.execute("UPDATE scan_batches SET complete=? WHERE config_hash=?", (int(complete), config_hash))
                    network = {"requests": reader.requests, "cache_hits": reader.cache_hits, "batch_id": batch_id,
                               "batch_complete": complete, "published_after": cutoff}
                # Coverage is saved even if a later matching stage fails.
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
                atomic_json(args.output_dir / f"coverage_{stamp}.json", coverage)
                report = run_pipeline(store, jobs, profile, history_records=history, limits=limits, preview=args.preview)
                report["network"] = network
                source_statuses = [s["status"] for s in coverage["sources"]]
                if any(s != "ok" for s in source_statuses):
                    report["status"] = "partial"
                report["mode"] = "offline" if args.offline_jobs else "live-read-only"
                report["profile_confirmed"] = profile["confirmed_by_user"]
                # Join the queue to original posting data for a usable handoff.
                job_map = {key: asdict(job) for key, job in store.jobs()}
                report["tasks"] = [{**task, "job": job_map[task["job_id"]]} for task in report["tasks"]]
                if catalog is not None:
                    report["materials"] = prepare_materials(report, profile, catalog,
                                                           args.output_dir / "materials", preview=args.preview)
                atomic_json(args.output_dir / f"run_{stamp}.json", report)
                atomic_json(args.output_dir / "latest.json", report)
                print(json.dumps({k: report[k] for k in ("run_id", "status", "counts", "evaluated", "cached", "deferred", "usage_today", "network")}))
                if report["status"] != "ok":
                    raise SystemExit(2)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Automation stopped: {exc}\n")


if __name__ == "__main__":
    main()

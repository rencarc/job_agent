from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .discovery import discover_many, write_jobs
from .airtable_sync import AirtableClient
from .history import HistoryIndex
from .sources.ats import PublicBoardSource
from .sources.jobtech import JobTechSource
from .triage import title_triage
from .search_settings import load_search_settings


DEFAULT_QUERIES = [
    "AI automation", "Power Platform", "Copilot Studio", "Azure AI",
    "LLM", "RAG", "AI agent", "Python integration", "AI engineer",
    "automation specialist", "workflow automation", "applied AI",
    "machine learning engineer", "software engineer AI", "full stack developer",
    "software engineer", "fullstack engineer", "solutions engineer",
    "integration engineer", "forward deployment engineer", "backend engineer",
    "IT consultant", "AI",
    "systemutvecklare", "AI utvecklare", "automatisering",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover Swedish jobs in safe read-only mode")
    parser.add_argument("--query", action="append", dest="queries")
    parser.add_argument("--settings", type=Path, help="JSON settings with queries, recent_days, jobtech_pages, limit_per_query, boards")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--published-after")
    parser.add_argument("--recent-days", type=int,
                        help="Search JobTech postings from the last N days (default 7); use 0 for all dates")
    parser.add_argument("--jobtech-pages", type=int, help="Maximum pages per JobTech query")
    parser.add_argument("--board", action="append", metavar="PROVIDER:BOARD",
                        help="Public Greenhouse, Lever EU or Ashby board; repeat for several companies")
    parser.add_argument("--no-jobtech", action="store_true", help="Run only configured company boards")
    parser.add_argument("--output", type=Path, default=Path("output/jobtech_jobs.json"))
    parser.add_argument("--coverage", type=Path, default=Path("output/coverage.json"))
    parser.add_argument("--triage", type=Path, default=Path("output/title_triage.json"))
    parser.add_argument("--airtable-history", action="store_true",
                        help="Check full Airtable history; requires AIRTABLE_TOKEN and fails closed on errors")
    parser.add_argument("--history-output", type=Path, default=Path("output/history_check.json"))
    args = parser.parse_args()

    try:
        settings = load_search_settings(args.settings) if args.settings else None
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(f"invalid search settings: {exc}")
    queries = args.queries or (list(settings.queries) if settings else DEFAULT_QUERIES)
    recent_days = args.recent_days if args.recent_days is not None else (settings.recent_days if settings else 7)
    jobtech_pages = args.jobtech_pages if args.jobtech_pages is not None else (settings.jobtech_pages if settings else 3)
    limit = args.limit if args.limit is not None else (settings.limit_per_query if settings else 25)
    board_names = args.board if args.board is not None else (list(settings.boards) if settings else [])

    boards = []
    for value in board_names:
        if ":" not in value:
            parser.error("--board must be PROVIDER:BOARD")
        provider, board = value.split(":", 1)
        try:
            boards.append(PublicBoardSource(provider, board))
        except ValueError as exc:
            parser.error(str(exc))
    if not 0 <= recent_days <= 365 or not 1 <= limit <= 100:
        parser.error("recent-days must be 0..365 and limit must be 1..100")
    try:
        source = JobTechSource(max_pages=jobtech_pages)
    except ValueError as exc:
        parser.error(str(exc))
    published_after = args.published_after
    if published_after is None and recent_days:
        published_after = (datetime.now(timezone.utc) - timedelta(days=recent_days)).isoformat(timespec="seconds")
    sources = ([] if args.no_jobtech else [source]) + boards
    if not sources:
        parser.error("select at least one source")
    jobs, report = discover_many(
        sources,
        queries,
        limit_per_query=limit,
        published_after=published_after,
    )
    write_jobs(args.output, jobs)
    report.write_json(args.coverage)
    buckets = Counter(title_triage(job) for job in jobs)
    args.triage.parent.mkdir(parents=True, exist_ok=True)
    args.triage.write_text(json.dumps({"counts": dict(buckets), "candidates": [asdict(job) for job in jobs
                            if title_triage(job) == "candidate"]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.airtable_history:
        records = AirtableClient().history_records()
        history_index = HistoryIndex(records)
        checks = [{"job_key": job.apply_url or job.source_url, **asdict(history_index.match(job))} for job in jobs]
        args.history_output.parent.mkdir(parents=True, exist_ok=True)
        args.history_output.write_text(json.dumps({"history_records": len(records), "checks": checks},
                                         ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for source in report.sources:
        print(f"source={source.source} status={source.status} fetched={source.fetched} "
              f"unique={source.unique} duplicates={source.duplicates}")


if __name__ == "__main__":
    main()

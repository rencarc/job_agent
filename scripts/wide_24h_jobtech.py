from __future__ import annotations

import csv
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from job_agent.sources.jobtech import JobTechSource


QUERIES = [
    "AI",
    "artificial intelligence",
    "generative AI",
    "GenAI",
    "LLM",
    "RAG",
    "machine learning",
    "data science",
    "data analyst",
    "data engineer",
    "automation",
    "automatisering",
    "workflow automation",
    "process automation",
    "digitalisering",
    "digital transformation",
    "Power Platform",
    "Power Apps",
    "Power Automate",
    "Power Pages",
    "Dataverse",
    "Copilot Studio",
    "Microsoft 365",
    "M365",
    "SharePoint",
    "Dynamics 365",
    "Office 365",
    "Azure",
    "OpenAI",
    "Python",
    "API integration",
    "integration developer",
    "system integration",
    "full stack",
    "fullstack",
    "backend developer",
    "software developer",
    "developer",
    "systemutvecklare",
    "mjukvaruutvecklare",
    "IT developer",
    "junior developer",
    "junior systemutvecklare",
    "graduate",
    "trainee",
    "intern",
    "internship",
    "praktik",
    "entry level",
    "business analyst",
    "business developer",
    "business operations",
    "operations",
    "verksamhetsutvecklare",
    "process improvement",
    "processutveckling",
    "B2B",
    "CRM",
    "marketing automation",
]


def key_for(job: dict) -> str:
    return job.get("external_id") or job.get("apply_url") or job.get("source_url")


def main() -> None:
    out_json = Path("output/jobs_today_24h_wide.json")
    out_csv = Path("output/jobs_today_24h_wide_links.csv")
    out_report = Path("output/coverage_today_24h_wide_batched.json")
    published_after = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    source = JobTechSource(max_pages=5)
    by_key: dict[str, dict] = {}
    query_report = []
    for query in QUERIES:
      try:
        fetched = source.fetch([query], limit_per_query=25, published_after=published_after)
        result = fetched.queries[0]
        query_report.append({
            "query": query,
            "status": "ok",
            "fetched": len(result.jobs),
            "total_available": result.total_available,
            "pages_requested": result.pages_requested,
        })
        for job in result.jobs:
            row = asdict(job)
            key = key_for(row)
            existing = by_key.setdefault(key, {**row, "matched_queries": []})
            if query not in existing["matched_queries"]:
                existing["matched_queries"].append(query)
      except Exception as exc:
        query_report.append({"query": query, "status": "failed", "error": f"{type(exc).__name__}: {exc}"})
      time.sleep(0.2)

    jobs = sorted(by_key.values(), key=lambda row: row.get("published_at") or "", reverse=True)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "published_after": published_after,
        "query_count": len(QUERIES),
        "unique_jobs": len(jobs),
        "jobs": jobs,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with out_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "company", "title", "location", "published_at", "matched_queries", "source_url", "apply_url"
        ])
        writer.writeheader()
        for job in jobs:
            writer.writerow({
                "company": job.get("company"),
                "title": job.get("title"),
                "location": job.get("location"),
                "published_at": job.get("published_at"),
                "matched_queries": ", ".join(job.get("matched_queries") or []),
                "source_url": job.get("source_url"),
                "apply_url": job.get("apply_url"),
            })
    out_report.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "published_after": published_after,
        "queries": query_report,
        "unique_jobs": len(jobs),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"unique_jobs={len(jobs)}")
    print(f"json={out_json}")
    print(f"csv={out_csv}")


if __name__ == "__main__":
    main()

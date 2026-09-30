"""Prepare a human-labeling sheet from discovered jobs; never authorizes submission."""
import argparse
import csv
import json
from pathlib import Path

from job_agent.career_facts import load_facts
from job_agent.models import Job
from job_agent.resume_variants import ResumeVariant
from job_agent.variant_scoring import evaluate_variants


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("data/resume_catalog.example.json"))
    parser.add_argument("--facts", type=Path, default=Path("data/career_facts_draft.json"))
    parser.add_argument("--output", type=Path, default=Path("output/score_review.csv"))
    args = parser.parse_args()
    variants = [ResumeVariant(item["id"], Path(item["pdf_name"]), tuple(item["focus_terms"]))
                for item in json.loads(args.catalog.read_text(encoding="utf-8"))["variants"]]
    facts = load_facts(args.facts)
    jobs = [Job(**item) for item in json.loads(args.jobs.read_text(encoding="utf-8"))["jobs"]]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["company", "role", "url", "selected_cv", "provisional_score",
                                                      "matched_facts", "human_label", "reason"])
        writer.writeheader()
        for job in jobs:
            score = evaluate_variants(job, variants, facts)
            writer.writerow({"company": job.company, "role": job.title, "url": job.apply_url or job.source_url,
                             "selected_cv": score.choice.variant.variant_id,
                             "provisional_score": score.provisional_score,
                             "matched_facts": ", ".join(score.matched_fact_ids),
                             "human_label": "", "reason": ""})
    print(f"Prepared {len(jobs)} rows for human labeling: {args.output}")


if __name__ == "__main__":
    main()

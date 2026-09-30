from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from job_agent.models import Job
from job_agent.scoring import score_job


SNAPSHOT = ROOT / "data" / "airtable_snapshot_2026-09-23.json"
REPORT = ROOT / "reports" / "baseline_2026-09-23.md"
SCORED = ROOT / "data" / "scored_baseline_2026-09-23.json"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.strip().encode("utf-8")).hexdigest() if value.strip() else ""


def main() -> None:
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    rows = payload["records"]
    scored = []
    decisions: Counter[str] = Counter()

    for row in rows:
        result = score_job(Job(
            external_id=row["record_id"],
            company=row.get("company", ""),
            title=row.get("role", "") or row.get("application", ""),
            location=row.get("location", ""),
            description="\n".join(filter(None, (row.get("jd_text", ""), row.get("key_requirements", "")))),
            source="airtable",
            source_url=row.get("job_link", ""),
            apply_url=row.get("job_link", ""),
        ))
        decisions[result.decision.value] += 1
        scored.append({
            "record_id": row["record_id"],
            "application": row.get("application", ""),
            "existing_match_score": row.get("match_score"),
            "baseline_score": result.score,
            "baseline_decision": result.decision.value,
            "confidence": result.confidence,
            "hard_blocker": result.hard_blocker,
            "blocker_reason": result.blocker_reason,
            "dimensions": result.dimensions,
            "evidence": [e.__dict__ for e in result.evidence],
            "jd_snapshot_hash": sha256_text(row.get("jd_text", "")),
        })

    SCORED.parent.mkdir(exist_ok=True)
    SCORED.write_text(json.dumps({"snapshot_date": payload["snapshot_date"], "records": scored}, ensure_ascii=False, indent=2), encoding="utf-8")

    complete_jd = sum(bool(r.get("jd_text")) for r in rows)
    links = sum(bool(r.get("job_link")) for r in rows)
    labels = sum(bool(r.get("human_decision")) for r in rows)
    comparable = [x for x in scored if isinstance(x["existing_match_score"], (int, float))]
    mae = sum(abs(x["existing_match_score"] - x["baseline_score"]) for x in comparable) / len(comparable)
    large_deltas = sorted(comparable, key=lambda x: abs(x["existing_match_score"] - x["baseline_score"]), reverse=True)[:10]

    lines = [
        "# Baseline evaluation — 2026-09-23",
        "",
        "## Dataset readiness",
        "",
        f"- Total records: {len(rows)}",
        f"- Full JD present: {complete_jd} ({complete_jd / len(rows):.1%})",
        f"- Job link present: {links} ({links / len(rows):.1%})",
        f"- Human Decision labels: {labels}",
        "",
        "The current Match Score is a useful historical reference, not ground truth. Accuracy, precision, recall, false positives, and false negatives cannot be honestly calculated until Human Decision labels exist.",
        "",
        "## Shadow-mode output",
        "",
        *(f"- {name}: {count}" for name, count in sorted(decisions.items())),
        f"- Mean absolute difference from existing Match Score: {mae:.1f} points",
        "",
        "## Largest score disagreements for manual review",
        "",
        "| Job | Existing | Baseline | Decision | Confidence |",
        "|---|---:|---:|---|---:|",
        *(f"| {x['application'].replace('|', '/')} | {x['existing_match_score']} | {x['baseline_score']} | {x['baseline_decision']} | {x['confidence']:.2f} |" for x in large_deltas),
        "",
        "## Interpretation",
        "",
        "Large differences are review candidates, not proof that either score is correct. Missing links and incomplete JDs reduce auditability. The next reliable step is manual labeling of a stratified subset before changing thresholds.",
    ]
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

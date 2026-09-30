from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_SCREENED = Path("output/jobs_today_24h_screened.json")
DEFAULT_OUT = Path("output/hard_blocker_audit.json")
DEFAULT_MD = Path("output/hard_blocker_audit.md")


def load_rows(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["rows"]


def build_audit(rows: list[dict]) -> dict:
    blocked = [row for row in rows if row.get("blockers")]
    by_reason: dict[str, list[dict]] = defaultdict(list)
    for row in blocked:
        for reason in row["blockers"]:
            by_reason[reason].append({
                "company": row.get("company"),
                "title": row.get("title"),
                "score": row.get("score"),
                "decision": row.get("decision"),
                "source_url": row.get("source_url"),
                "apply_url": row.get("apply_url"),
                "evidence": (row.get("blocker_evidence") or {}).get(reason, ""),
            })
    samples = {
        reason: sorted(items, key=lambda item: item["score"], reverse=True)[:5]
        for reason, items in by_reason.items()
    }
    return {
        "total_rows": len(rows),
        "blocked_rows": len(blocked),
        "decision_counts": dict(Counter(row.get("decision") for row in rows)),
        "blocker_counts": dict(Counter(reason for row in blocked for reason in row.get("blockers", []))),
        "samples_by_reason": samples,
    }


def write_markdown(audit: dict, path: Path) -> None:
    lines = [
        "# Hard Blocker Audit",
        "",
        f"Total screened rows: {audit['total_rows']}",
        f"Rows with hard blockers: {audit['blocked_rows']}",
        "",
        "## Decision Counts",
    ]
    for key, value in sorted(audit["decision_counts"].items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Blocker Counts"])
    for key, value in sorted(audit["blocker_counts"].items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Evidence Samples"])
    for reason, items in sorted(audit["samples_by_reason"].items()):
        lines.append(f"### {reason}")
        for item in items:
            lines.append(f"- {item['company']} — {item['title']} ({item['decision']}, score {item['score']})")
            lines.append(f"  Evidence: {item['evidence']}")
            lines.append(f"  {item['source_url']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screened", type=Path, default=DEFAULT_SCREENED)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--md", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    audit = build_audit(load_rows(args.screened))
    args.out.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(audit, args.md)
    print(f"blocked_rows={audit['blocked_rows']}")
    print(f"blocker_counts={audit['blocker_counts']}")
    print(f"json={args.out}")
    print(f"md={args.md}")


if __name__ == "__main__":
    main()

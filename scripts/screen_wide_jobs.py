from __future__ import annotations

import csv
import json
import re
from pathlib import Path


INPUT = Path("output/jobs_today_24h_wide.json")
OUT_CSV = Path("output/jobs_today_24h_screened.csv")
OUT_JSON = Path("output/jobs_today_24h_screened.json")

HARD_BLOCKERS = [
    ("swedish_citizenship", r"svenskt medborgarskap|svensk medborgare"),
    ("finnish_required", r"finsktalande|finska\b|finnish"),
    ("senior_requirements_analyst_required", r"minst 5 års.*(?:kravanalytiker|verksamhetsanalytiker)|3 uppdrag.*krav"),
    ("senior_testing_required", r"erfaren testare|minst 5 års dokumenterad erfarenhet av testarbete|kvalificerat testarbete"),
    ("robotics_hardware_specialist", r"ROS/ROS2|robotstyrning|robotsystem|robotplattform|hårdvaruplattform"),
    ("licensed_healthcare", r"legitimerad läkare|specialistläkare|sjuksköterska|undersköterska|dietist|vårdcentral"),
    ("social_care", r"\bHVB\b|vård\s*&\s*omsorg|gruppboende|boenden enligt LSS|personlig assistent|personlig assistans"),
    ("teacher_school", r"\blärare\b|barnskötare|förskollärare"),
    ("driver_manual_trade", r"chaufför|snickare|lackering|fordonslackering|lokalvårdare|hemstädare"),
    ("executive_senior", r"\bvd\b|12\+ years|12\+ års|chef för|verksamhetschef|myndighetschef"),
]

STRONG_SIGNALS = [
    ("ai", r"\bAI\b|artificial intelligence|generative ai|genai|llm|machine learning|maskininlärning|rag"),
    ("automation", r"automation|automatisering|digitalisering|process automation|workflow automation"),
    ("power_platform", r"power platform|power apps|power automate|power pages|dataverse|copilot studio|microsoft 365|m365|sharepoint|dynamics 365"),
    ("software", r"systemutvecklare|software developer|mjukvaruutvecklare|developer|java|python|backend|fullstack|full stack|api|integration"),
    ("data_security", r"data|information security|informationssäkerhet|cyber|linux|devops|azure|docker|kubernetes"),
    ("business_ops", r"business analyst|verksamhetsutvecklare|business operations|process improvement|crm|b2b|operations"),
    ("early_career", r"junior|graduate|trainee|internship|praktik|nyexaminerad|newly graduated"),
]

WEAK_OR_NOISY_TITLES = [
    r"säljare|account manager|sales representative|b2c|b2b-säljare",
    r"controller|ekonom|redovisning",
    r"arkivarie|administratör|kommunikatör",
]


def matches(pattern: str, text: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def evidence_for(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    start = max(match.start() - 60, 0)
    end = min(match.end() + 60, len(text))
    return re.sub(r"\s+", " ", text[start:end]).strip()


def screen(job: dict) -> dict:
    title = job.get("title") or ""
    text = " ".join([
        title,
        job.get("company") or "",
        job.get("location") or "",
        job.get("description") or "",
        " ".join(job.get("matched_queries") or []),
    ])
    blocker_evidence = {
        name: evidence
        for name, pattern in HARD_BLOCKERS
        if (evidence := evidence_for(pattern, text)) is not None
    }
    blockers = list(blocker_evidence)
    signals = [name for name, pattern in STRONG_SIGNALS if matches(pattern, text)]
    noisy = [pattern for pattern in WEAK_OR_NOISY_TITLES if matches(pattern, title)]
    score = 10 * len(signals) - 25 * len(blockers) - 8 * len(noisy)
    if "early_career" in signals:
        score += 8
    if "software" in signals and ("ai" in signals or "automation" in signals or "power_platform" in signals):
        score += 10
    if blockers:
        decision = "exclude"
    elif score >= 35:
        decision = "worth_applying"
    elif score >= 18:
        decision = "review"
    else:
        decision = "exclude"
    return {
        "decision": decision,
        "score": score,
        "signals": signals,
        "blockers": blockers,
        "blocker_evidence": blocker_evidence,
        "company": job.get("company"),
        "title": title,
        "location": job.get("location"),
        "published_at": job.get("published_at"),
        "matched_queries": job.get("matched_queries") or [],
        "source_url": job.get("source_url"),
        "apply_url": job.get("apply_url"),
    }


def main() -> None:
    jobs = json.loads(INPUT.read_text(encoding="utf-8"))["jobs"]
    rows = [screen(job) for job in jobs]
    rows.sort(key=lambda row: ({"worth_applying": 0, "review": 1, "exclude": 2}[row["decision"]], -row["score"], row["published_at"] or ""), reverse=False)
    OUT_JSON.write_text(json.dumps({"count": len(rows), "rows": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "signals": ", ".join(row["signals"]), "blockers": ", ".join(row["blockers"]), "matched_queries": ", ".join(row["matched_queries"])})
    counts = {}
    for row in rows:
        counts[row["decision"]] = counts.get(row["decision"], 0) + 1
    print(counts)
    for row in rows[:15]:
        print(f"{row['decision']} score={row['score']} | {row['company']} — {row['title']} | {row['apply_url']}")


if __name__ == "__main__":
    main()

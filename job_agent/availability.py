"""Daily deadline/removal checks run independently of cached matching."""
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
          "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
          "januari": 1, "februari": 2, "mars": 3, "maj": 5, "juni": 6, "juli": 7, "oktober": 10}


def text_deadlines(text: str) -> list[dict]:
    evidence = []
    marker = r"no later than|apply by|application deadline|sista ansökning(?:sdatum|sdag|datum)|senast"
    for match in re.finditer(r"(?:" + marker + r")\s*:?\s*([^\n.]{0,65})", text, re.I):
        value = match.group(1).strip()
        iso = re.match(r"(20\d\d)-(\d\d)-(\d\d)", value)
        numeric = re.match(r"(\d{1,2})[-/](\d{1,2})[-/](20\d\d)", value)
        month = re.match(r"(\d{1,2})\s+([a-zåäö]+),?\s+(20\d\d)", value, re.I)
        try:
            if iso:
                parsed = date(*map(int, iso.groups()))
            elif numeric:
                day, mon, year = map(int, numeric.groups())
                parsed = date(year, mon, day)
            elif month and month.group(2).casefold() in MONTHS:
                parsed = date(int(month.group(3)), MONTHS[month.group(2).casefold()], int(month.group(1)))
            else:
                continue
        except ValueError:
            continue
        evidence.append({"date": parsed.isoformat(), "quote": match.group(0)})
    return evidence


def assess_availability(job, *, today: date | None = None) -> dict:
    current = today or datetime.now(ZoneInfo("Europe/Stockholm")).date()
    if job.removed:
        return {"decision": "skip", "reasons": ["source marks this posting removed"]}
    structured = None
    if job.application_deadline:
        try:
            structured = date.fromisoformat(job.application_deadline[:10])
        except ValueError:
            return {"decision": "exception", "reasons": ["structured application deadline is invalid"]}
        if structured < current:
            return {"decision": "skip", "reasons": ["source application deadline has passed: " + structured.isoformat()]}
    stated = text_deadlines(job.description)
    if structured and any(item["date"] != structured.isoformat() for item in stated):
        return {"decision": "exception", "reasons": ["structured and description deadlines conflict"], "deadline_evidence": stated}
    if not structured and any(item["date"] < current.isoformat() for item in stated):
        return {"decision": "exception", "reasons": ["description deadline has passed; verify employer posting"], "deadline_evidence": stated}
    return {"decision": None, "reasons": [], "deadline_evidence": stated}

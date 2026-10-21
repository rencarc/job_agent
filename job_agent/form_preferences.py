"""Prepare user-confirmed availability/salary suggestions, without interacting with a form."""
from datetime import date, datetime
import re
from zoneinfo import ZoneInfo


def preference_plan(inspection: dict, preferences: dict, *, today: date | None = None) -> dict:
    today = today or datetime.now(ZoneInfo("Europe/Stockholm")).date()
    if preferences.get("confirmed_by_user") is not True:
        raise ValueError("application preferences need user confirmation")
    confirmed = date.fromisoformat(preferences["confirmed_on"])
    if not 0 <= (today - confirmed).days <= 30:
        raise ValueError("availability and salary preferences need reconfirmation")
    if inspection.get("provider") != "teamtailor" or inspection.get("inspection_only") is not True:
        raise ValueError("a read-only Teamtailor inspection is required")
    controls = inspection.get("controls")
    if not isinstance(controls, list) or not controls:
        raise ValueError("inspection must contain observed controls")
    answers, unresolved = [], []
    for control in controls:
        label = control["label"]
        key = control["key"]
        value = None
        note = ""
        if control["kind"] == "date" and re.search(r"tidigast tillgänglig|earliest.*(?:start|available)|available.*(?:start|from)", label, re.I):
            if preferences.get("available_immediately") is True:
                value = today.isoformat()
                note = "available immediately; date resolved on this run in Europe/Stockholm"
        elif control["kind"] == "number" and re.search(r"löneanspråk|salary", label, re.I):
            salary = preferences.get("salary", {})
            if (type(salary.get("amount")) is int and salary["amount"] > 0 and salary.get("currency") == "SEK"
                    and salary.get("period") == "month" and salary.get("basis") == "gross"
                    and not re.search(r"annual|year|hour|net salary|per år|timlön|netto|eur|usd|€|\$", label, re.I)):
                value = str(salary["amount"])
                note = "user-confirmed gross SEK per month; employer field unit still needs verification"
        if value is not None:
            answers.append({"key": key, "label": label, "value": value, "source": "user_supplied",
                            "note": note, "suggestion_only": True})
        elif control.get("required"):
            unresolved.append({"key": key, "label": label, "reason": "no exact confirmed answer; never infer from match score"})
    return {"provider": "teamtailor", "url": inspection.get("url"), "can_submit": False,
            "state": "preparation_only", "answers": answers, "unresolved_required": unresolved,
            "posting_open": "unverified", "form_unit_verification_required": True}

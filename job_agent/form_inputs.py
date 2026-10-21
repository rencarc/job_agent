"""Attach source-backed contact/CV suggestions without filling a website."""
import json
import re
from pathlib import Path

from .materials import verify_cv


CONTACT_FIELDS = {
    "candidate[first_name]": ("first_name", "text", {"förnamn", "first name"}),
    "candidate[last_name]": ("last_name", "text", {"efternamn", "last name"}),
    "candidate[email]": ("email", "email", {"e-post", "email", "email address"}),
    "candidate[phone]": ("phone", "tel", {"telefon", "phone", "phone number"}),
}


def load_contact_profile(path: Path) -> dict:
    return validate_contacts(json.loads(path.read_text(encoding="utf-8")))


def validate_contacts(data: dict) -> dict:
    if data.get("reviewed_from_source") is not True:
        raise ValueError("contact fields must be reviewed against their source document")
    verify_cv({"path": data["source_document"], "reviewed_sha256": data["source_sha256"]})
    fields = data.get("fields")
    if not isinstance(fields, dict) or any(not isinstance(v, str) or not v.strip() or "\n" in v or "\r" in v for v in fields.values()):
        raise ValueError("contact fields must contain nonempty single-line strings")
    if "email" in fields and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", fields["email"]):
        raise ValueError("contact email needs review")
    if "phone" in fields and not re.fullmatch(r"\+[1-9]\d{6,14}", fields["phone"]):
        raise ValueError("phone needs an explicit international country code")
    if type(data.get("confirmed_by_user")) is not bool:
        raise ValueError("contact confirmation status must remain explicit")
    return data


def attach_source_inputs(plan: dict, inspection: dict, *, contacts: dict | None = None, cv: dict | None = None) -> dict:
    if plan.get("can_submit") is not False or plan.get("state") != "preparation_only":
        raise ValueError("source inputs may only extend a non-submitting preparation checklist")
    if cv is not None:
        verify_cv(cv)
    if contacts is not None:
        # Recheck if the source changed after loading or while scanning.
        validate_contacts(contacts)
    result = {**plan, "answers": list(plan["answers"])}
    answered = {a["key"] for a in result["answers"]}
    controls = inspection["controls"]
    if len({c["key"] for c in controls}) != len(controls):
        raise ValueError("duplicate control identities need review")
    if cv and sum(c["kind"] == "file" and bool(re.fullmatch(r"(?:ladda upp\s+)?(?:cv|resume|résumé)", c["label"], re.I))
                  for c in controls) > 1:
        raise ValueError("multiple CV upload targets need review")
    for control in controls:
        key, label, kind = control["key"], control["label"], control["kind"]
        if key in answered:
            continue
        value, source = None, None
        mapping = CONTACT_FIELDS.get(key)
        if contacts and mapping and kind == mapping[1] and label.casefold().strip() in mapping[2]:
            value = contacts["fields"].get(mapping[0])
            source = "cv_contact:page_1"
        elif contacts and kind == "text" and label.casefold().strip().rstrip("?") == "bostadsort":
            value, source = contacts["fields"].get("city"), "cv_contact:page_1"
        elif cv and kind == "file" and re.fullmatch(r"(?:ladda upp\s+)?(?:cv|resume|résumé)", label, re.I):
            value, source = cv["path"], "reviewed_cv:" + cv["id"]
        if value:
            result["answers"].append({"key": key, "label": label, "value": value, "source": source,
                                      "suggestion_only": True})
            answered.add(key)
    result["unresolved_required"] = [u for u in plan["unresolved_required"] if u["key"] not in answered]
    result["contact_profile_confirmed"] = contacts.get("confirmed_by_user") if contacts else None
    result["cv_sha256"] = cv["reviewed_sha256"] if cv else None
    return result

"""User-confirmed work eligibility answers scoped to a verified job country."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .form_audit import FilledField
from .question_language import detect_question_language


@dataclass(frozen=True)
class EligibilityAnswers:
    country_code: str
    work_authorized_now: bool
    employer_support_required: bool
    confirmed_on: date


def load_eligibility(path: Path) -> EligibilityAnswers:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("country_code") != "SE" or data.get("confirmed_by_user") is not True:
        raise ValueError("a user-confirmed Sweden-specific eligibility profile is required")
    if type(data.get("work_authorized_now")) is not bool or type(data.get("employer_support_required")) is not bool:
        raise ValueError("both eligibility answers must be explicit booleans")
    confirmed = date.fromisoformat(data["confirmed_on"])
    if confirmed > date.today():
        raise ValueError("confirmation date cannot be in the future")
    return EligibilityAnswers("SE", data["work_authorized_now"],
                              data["employer_support_required"], confirmed)


def eligibility_field(question: str, answer_kind: str, *, job_country: str,
                      answers: EligibilityAnswers, today: date | None = None) -> FilledField:
    """The live form question must be classified explicitly; unknown scope stops."""
    current = today or date.today()
    if job_country != answers.country_code or (current - answers.confirmed_on).days > 30:
        raise ValueError("job country differs or eligibility answer needs reconfirmation")
    language = detect_question_language(question)
    if language not in {"en", "sv"}:
        raise ValueError("question language needs review")
    if answer_kind == "work_authorization":
        response = answers.work_authorized_now
    elif answer_kind == "employer_support":
        response = answers.employer_support_required
    else:
        raise ValueError("unknown eligibility question")
    value = ("Yes" if response else "No") if language == "en" else ("Ja" if response else "Nej")
    return FilledField(question, value, "user_supplied", language, language)

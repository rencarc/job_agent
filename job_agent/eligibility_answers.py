"""User-confirmed work eligibility answers scoped to a verified job country."""
from __future__ import annotations

import json
import re
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
    employer_support_required_now: bool | None = None
    employer_support_required_future: bool | None = None


def load_eligibility(path: Path) -> EligibilityAnswers:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("country_code") != "SE" or data.get("confirmed_by_user") is not True:
        raise ValueError("a user-confirmed Sweden-specific eligibility profile is required")
    if type(data.get("work_authorized_now")) is not bool or type(data.get("employer_support_required")) is not bool:
        raise ValueError("both eligibility answers must be explicit booleans")
    confirmed = date.fromisoformat(data["confirmed_on"])
    if confirmed > date.today():
        raise ValueError("confirmation date cannot be in the future")
    for key in ("employer_support_required_now", "employer_support_required_future"):
        if data.get(key) is not None and type(data[key]) is not bool:
            raise ValueError("scoped employer support answers must be booleans or unknown")
    scoped = [data.get("employer_support_required_now"), data.get("employer_support_required_future")]
    if any(value is True for value in scoped) and not data["employer_support_required"]:
        raise ValueError("combined employer support answer contradicts scoped answers")
    if scoped == [False, False] and data["employer_support_required"]:
        raise ValueError("combined employer support answer contradicts scoped answers")
    return EligibilityAnswers("SE", data["work_authorized_now"],
                              data["employer_support_required"], confirmed, *scoped)


def employer_support_answer(question: str, answers: EligibilityAnswers) -> bool:
    now = bool(re.search(r"\bcurrently\b|\bnow\b|at present|för närvarande|\bidag\b|\bnu\b", question, re.I))
    future = bool(re.search(r"future|framtid|framöver|senare", question, re.I))
    current_answer = answers.employer_support_required_now
    future_answer = answers.employer_support_required_future
    if now and future:
        if current_answer is True or future_answer is True:
            return True
        if current_answer is False and future_answer is False:
            return False
        if current_answer is None and future_answer is None:
            return answers.employer_support_required  # legacy combined confirmation
    elif now and current_answer is not None:
        return current_answer
    elif future and future_answer is not None:
        return future_answer
    elif not now and not future and current_answer is None and future_answer is None:
        return answers.employer_support_required  # legacy unsplit confirmation
    raise ValueError("employer support timeframe needs a separately confirmed answer")


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
        if re.search(r"future|permanent|unrestricted|without sponsorship|citizen|framtid|permanent|medborg", question, re.I):
            raise ValueError("current work authorization does not establish permanent or future eligibility")
        response = answers.work_authorized_now
    elif answer_kind == "employer_support":
        response = employer_support_answer(question, answers)
    else:
        raise ValueError("unknown eligibility question")
    value = ("Yes" if response else "No") if language == "en" else ("Ja" if response else "Nej")
    return FilledField(question, value, "user_supplied", language, language)

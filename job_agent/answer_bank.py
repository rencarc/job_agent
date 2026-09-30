"""Exact bilingual responses with explicit fact and approval gates."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .career_facts import CareerFact
from .form_audit import FilledField


@dataclass(frozen=True)
class Answer:
    answer_id: str
    english: str
    swedish: str
    fact_ids: tuple[str, ...]
    approved: bool


def load_answers(path: Path, facts: list[CareerFact]) -> dict[str, Answer]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    fact_ids = {fact.fact_id for fact in facts if not fact.review}
    if not isinstance(payload.get("answers"), list):
        raise ValueError("answers must be a list")
    result: dict[str, Answer] = {}
    for item in payload["answers"]:
        identifier = item["id"]
        references = tuple(item["fact_ids"])
        if identifier in result or not references or not set(references) <= fact_ids:
            raise ValueError(f"duplicate or unverified fact reference for answer {identifier}")
        result[identifier] = Answer(identifier, item["en"], item["sv"], references,
                                    item.get("approved", False) is True)
    return result


def answer_question(question: str, language: str, answer_id: str,
                    answers: dict[str, Answer]) -> FilledField:
    """Use an exact, previously approved answer; caller maps the actual form question."""
    if language not in {"en", "sv"}:
        raise ValueError("question language needs review")
    answer = answers.get(answer_id)
    if answer is None or not answer.approved:
        raise ValueError("answer is unknown or not approved for submission")
    value = answer.english if language == "en" else answer.swedish
    if not value.strip():
        raise ValueError("approved answer is empty in the question language")
    return FilledField(question, value, f"answer_bank:{answer_id}", language, language)

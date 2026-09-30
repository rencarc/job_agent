"""Exact submitted form values, including the original question and response language."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class FilledField:
    label: str
    value: str
    source: str  # career_fact:<id>, answer_bank:<id>, or user_supplied
    question_language: str  # en, sv, or none for ordinary identity fields
    answer_language: str  # en, sv, or none for non-prose values

    def __post_init__(self):
        if not self.label.strip() or not self.source.strip():
            raise ValueError("filled field needs its original label and factual source")
        if self.question_language not in {"en", "sv", "none"}:
            raise ValueError("question language must be en, sv or none")
        if self.answer_language not in {"en", "sv", "none"}:
            raise ValueError("answer language must be en, sv or none")
        if self.question_language in {"en", "sv"} and self.answer_language not in {self.question_language, "none"}:
            raise ValueError("answer language must match the question language")


def format_audit(fields: list[FilledField]) -> str:
    return "\n".join(
        f"Question/field [{f.question_language}]: {f.label}\n"
        f"Submitted answer [{f.answer_language}]: {f.value}\nSource: {f.source}"
        for f in fields
    )


def serialize_fields(fields: list[FilledField]) -> list[dict]:
    return [asdict(field) for field in fields]

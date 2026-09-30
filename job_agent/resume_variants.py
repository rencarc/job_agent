"""Choose among user-provided résumé variants without assuming one fixed CV."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import Job


@dataclass(frozen=True)
class ResumeVariant:
    variant_id: str
    path: Path
    focus_terms: tuple[str, ...]
    language: str = "en"
    latex_source: Path | None = None

    def __post_init__(self):
        if not self.variant_id or not self.focus_terms:
            raise ValueError("résumé variant needs an id and focus terms")
        if self.language not in {"en", "sv"}:
            raise ValueError("résumé language must be en or sv")


@dataclass(frozen=True)
class ResumeChoice:
    variant: ResumeVariant
    matched_terms: tuple[str, ...]
    confidence: str  # supported or review


def choose_resume(job: Job, variants: list[ResumeVariant]) -> ResumeChoice:
    if not variants:
        raise ValueError("configure at least one résumé variant")
    title = job.title.casefold()
    description = job.description.casefold()
    def contains(text: str, term: str) -> bool:
        return bool(re.search(r"(?<!\w)" + re.escape(term.casefold()) + r"(?!\w)", text))
    ranked = []
    for variant in variants:
        title_hits = tuple(term for term in variant.focus_terms if contains(title, term))
        jd_hits = tuple(term for term in variant.focus_terms if contains(description, term) and term not in title_hits)
        ranked.append((3 * len(title_hits) + len(jd_hits), variant.variant_id, variant, title_hits + jd_hits))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    score, _, selected, matches = ranked[0]
    tied = len(ranked) > 1 and ranked[1][0] == score
    return ResumeChoice(selected, matches, "review" if score == 0 or tied else "supported")

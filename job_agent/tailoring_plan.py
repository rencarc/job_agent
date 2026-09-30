"""Grounded keyword suggestions for a future LaTeX résumé edit."""
from __future__ import annotations

from dataclasses import dataclass

from .career_facts import CareerFact, matching_facts
from .models import Job
from .resume_variants import ResumeVariant


@dataclass(frozen=True)
class TailoringPlan:
    variant_id: str
    supported_keywords: tuple[str, ...]
    supporting_fact_ids: tuple[str, ...]
    unsupported_keywords: tuple[str, ...]
    latex_ready: bool


def plan_tailoring(job: Job, variant: ResumeVariant, facts: list[CareerFact],
                   requested_keywords: list[str]) -> TailoringPlan:
    matches = matching_facts(job.searchable_text, facts)
    available = [(fact, term) for fact, terms in matches for term in terms
                 if variant.path.name in fact.sources]
    supported = []
    ids = []
    unsupported = []
    for keyword in requested_keywords:
        match = next(((fact, term) for fact, term in available
                      if keyword.casefold() == term.casefold()), None)
        if match:
            supported.append(keyword)
            ids.append(match[0].fact_id)
        else:
            unsupported.append(keyword)
    return TailoringPlan(variant.variant_id, tuple(supported), tuple(dict.fromkeys(ids)),
                         tuple(unsupported), variant.latex_source is not None)

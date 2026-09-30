"""Score a job against swappable CV variants; decisions remain uncalibrated."""
from __future__ import annotations

from dataclasses import dataclass

from .models import Job, ScoreResult
from .resume_variants import ResumeChoice, ResumeVariant, choose_resume
from .scoring import score_job
from .career_facts import CareerFact, matching_facts


@dataclass(frozen=True)
class VariantEvaluation:
    choice: ResumeChoice
    baseline: ScoreResult
    variant_fit: int
    provisional_score: int
    matched_fact_ids: tuple[str, ...] = ()
    eligible_for_auto_submit: bool = False


def evaluate_variants(job: Job, variants: list[ResumeVariant],
                      facts: list[CareerFact] | None = None) -> VariantEvaluation:
    """Transparent prototype; no threshold is calibrated for unattended applications."""
    choice = choose_resume(job, variants)
    baseline = score_job(job)
    fit = min(100, 20 * len(choice.matched_terms))
    matches = [(fact, terms) for fact, terms in matching_facts(job.searchable_text, facts)
               if choice.variant.path.name in fact.sources] if facts is not None else []
    ids = tuple(fact.fact_id for fact, _ in matches)
    if facts is None:
        score = round(0.75 * baseline.score + 0.25 * fit)
    else:
        fact_fit = min(100, 25 + 12 * len(ids))
        score = round(0.5 * baseline.score + 0.2 * fit + 0.3 * fact_fit)
    return VariantEvaluation(choice, baseline, fit, score, ids)

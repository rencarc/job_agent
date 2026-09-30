"""Expert review priority distinct from permission for automatic submission."""
from __future__ import annotations

from dataclasses import dataclass

from .variant_scoring import VariantEvaluation


@dataclass(frozen=True)
class ApplicationPriority:
    band: str  # high, consider, or manual_review
    reasons: tuple[str, ...]
    can_auto_submit: bool = False


def assess_priority(result: VariantEvaluation) -> ApplicationPriority:
    """Positive-only history supports prioritization, not a reject classifier."""
    if result.baseline.hard_blocker:
        return ApplicationPriority("manual_review", (result.baseline.blocker_reason or "eligibility blocker",))
    if result.choice.confidence != "supported":
        return ApplicationPriority("manual_review", ("CV variant uncertain",))
    if result.provisional_score >= 55 and len(result.matched_fact_ids) >= 2:
        return ApplicationPriority("high", (f"provisional fit {result.provisional_score}",
                                            f"{len(result.matched_fact_ids)} supported CV facts"))
    return ApplicationPriority("consider", (f"provisional fit {result.provisional_score}",
                                            "positive-only history cannot justify automatic rejection"))

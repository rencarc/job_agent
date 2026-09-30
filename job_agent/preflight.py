"""Conservative submission gate across history, CV fit and form readiness."""
from __future__ import annotations

from dataclasses import dataclass
import re

from .history import HistoryMatch
from .models import Job
from .variant_scoring import VariantEvaluation
from .eligibility_answers import EligibilityAnswers


@dataclass(frozen=True)
class PreflightResult:
    ready: bool
    reasons: tuple[str, ...]


def check_preflight(job: Job, history: HistoryMatch, score: VariantEvaluation,
                    *, posting_open: bool | None = None,
                    form_supported: bool = False,
                    profile_complete: bool = False,
                    calibrated_threshold: int | None = None,
                    eligibility: EligibilityAnswers | None = None) -> PreflightResult:
    reasons = []
    if history.action != "new":
        reasons.append(f"Airtable history: {history.action} ({history.reason})")
    if job.location_status == "outside_sweden":
        reasons.append("posting is explicitly outside Sweden")
    if eligibility and eligibility.employer_support_required and re.search(
            r"(?:visa|work permit) sponsorship (?:is )?(?:not available|unavailable|not offered|cannot be provided)"
            r"|(?:do not|don't|cannot|can't) (?:offer|provide) (?:visa|work permit) sponsorship",
            job.description, flags=re.IGNORECASE):
        reasons.append("employer explicitly does not provide required sponsorship")
    if score.baseline.hard_blocker:
        reasons.append("verified job requirement is a hard blocker")
    if score.choice.confidence != "supported":
        reasons.append("CV variant choice requires review")
    if calibrated_threshold is None or not score.eligible_for_auto_submit:
        reasons.append("automatic submission scoring has not been calibrated and enabled")
    elif score.provisional_score < calibrated_threshold:
        reasons.append("score is below calibrated threshold")
    if posting_open is not True:
        reasons.append("posting open status is unverified")
    if not form_supported:
        reasons.append("employer form has not been verified")
    if not profile_complete:
        reasons.append("required personal answers are incomplete")
    return PreflightResult(not reasons, tuple(reasons))

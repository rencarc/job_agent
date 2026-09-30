from __future__ import annotations

import re

from .config import MAYBE_THRESHOLD, MIN_AUTO_DECISION_CONFIDENCE, SHADOW_MODE, STRONG_THRESHOLD
from .models import Decision, Evidence, Job, ScoreResult


def _match(pattern: str, text: str) -> str | None:
    hit = re.search(pattern, text, flags=re.IGNORECASE)
    return hit.group(0) if hit else None


def score_job(job: Job, *, preferred_locations: tuple[str, ...] = ()) -> ScoreResult:
    text = job.searchable_text
    evidence: list[Evidence] = []

    # A verified legal/eligibility blocker is categorical, not a score penalty.
    blocker_patterns = {
        "Swedish citizenship explicitly required": r"(?:swedish|svenskt) (?:citizenship|medborgarskap) (?:is )?(?:required|krävs)",
        "EU citizenship explicitly required": r"(?:eu|eea) citizenship (?:is )?(?:required|mandatory)",
        "Security clearance requiring citizenship": r"security clearance.{0,80}(?:swedish|svenskt) (?:citizenship|medborgarskap)",
    }
    for reason, pattern in blocker_patterns.items():
        excerpt = _match(pattern, text)
        if excerpt:
            evidence.append(Evidence("hard_blocker", reason, excerpt, -100, 0.98))
            return ScoreResult(0, 0.98, Decision.REVIEW if SHADOW_MODE else Decision.REJECT, True, reason,
                               {"skill_fit": 0, "ai_automation_fit": 0, "seniority_fit": 0, "location_fit": 0}, evidence)

    skill_terms = {
        r"power platform": 12, r"copilot studio": 12, r"power automate": 9,
        r"dataverse": 8, r"\b(?:llm|rag)\b": 8, r"\bagents?\b": 7,
        r"\bpython\b": 6, r"\bapi(?:s)?\b|integration": 6,
        r"azure (?:openai|ai)": 7, r"workflow": 4,
    }
    skill_points = 0
    for pattern, points in skill_terms.items():
        excerpt = _match(pattern, text)
        if excerpt:
            skill_points += points
            evidence.append(Evidence("skill", pattern, excerpt, points, 0.95))
    skill_fit = min(100, 35 + skill_points)

    ai_points = sum(e.impact for e in evidence if e.category == "skill" and e.impact >= 7)
    ai_fit = min(100, 35 + ai_points)

    seniority_fit = 78
    senior = _match(r"(?:8|9|10)\+? years|staff engineer|principal engineer|head of|director of", text)
    five_plus = _match(r"(?:5|6|7)\+? years", text)
    junior = _match(r"\b(?:junior|graduate|entry.level|trainee|associate)\b", text)
    if senior:
        seniority_fit = 20
        evidence.append(Evidence("seniority", "very senior", senior, -30, 0.94))
    elif five_plus:
        seniority_fit = 45
        evidence.append(Evidence("seniority", "5+ years", five_plus, -18, 0.92))
    elif junior:
        seniority_fit = 95
        evidence.append(Evidence("seniority", "early-career fit", junior, 10, 0.92))

    language_penalty = 0
    swedish_required = _match(r"(?:fluent|professional|native|obehindrat).{0,25}(?:swedish|svenska)|(?:swedish|svenska).{0,25}(?:required|mandatory|krav)", text)
    swedish_preferred = _match(r"(?:swedish|svenska).{0,25}(?:preferred|advantage|plus|meriterande)", text)
    if swedish_required:
        language_penalty = 22
        evidence.append(Evidence("language", "Swedish required", swedish_required, -22, 0.93))
    elif swedish_preferred:
        language_penalty = 5
        evidence.append(Evidence("language", "Swedish preferred", swedish_preferred, -5, 0.88))

    # JobTech searches Sweden nationwide. Location is neutral by default;
    # preferences affect ranking only when the user explicitly supplies them.
    location_fit = 100
    if preferred_locations:
        location = job.location.casefold()
        location_fit = 100 if any(place.strip().casefold() in location
                                  for place in preferred_locations if place.strip()) else 65

    raw = round(0.34 * skill_fit + 0.24 * ai_fit + 0.22 * seniority_fit + 0.20 * location_fit - language_penalty)
    score = max(0, min(100, raw))

    completeness = sum(bool(v.strip()) for v in (job.company, job.title, job.location, job.description, job.apply_url or job.source_url)) / 5
    confidence = round(0.58 + 0.37 * completeness, 2)
    if job.location_status == "unknown" and job.ats_type:
        evidence.append(Evidence("location", "Location needs Sweden verification", job.location or "Unspecified", 0, 0.5))
        decision = Decision.REVIEW
    elif confidence < MIN_AUTO_DECISION_CONFIDENCE:
        decision = Decision.REVIEW
    elif score >= STRONG_THRESHOLD:
        decision = Decision.STRONG
    elif score >= MAYBE_THRESHOLD:
        decision = Decision.MAYBE
    else:
        decision = Decision.REVIEW if SHADOW_MODE else Decision.REJECT

    return ScoreResult(score, confidence, decision, False, None, {
        "skill_fit": skill_fit,
        "ai_automation_fit": ai_fit,
        "seniority_fit": seniority_fit,
        "location_fit": location_fit,
    }, evidence)

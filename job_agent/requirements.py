"""Conservative clause-level requirement evidence, not a general language parser."""
from __future__ import annotations

import re

NEGATED_OR_PREFERRED = re.compile(
    r"\bnot\s+(?:\w+\s+){0,3}(?:required|necessary|mandatory)|\bno\s+.{0,35}requirement"
    r"|\b(?:preferred|optional|advantage|plus|meriterande)\b|(?:krävs|krav).*inte|inte.*(?:krav|nödvändigt)", re.I)
REQUIRED = re.compile(r"\b(?:required|mandatory|must|require|requires|fluent|native|essential)\b"
                      r"|krävs|ett krav|måste|finsktalande|flytande", re.I)


def requirement_evidence(pattern: str, text: str) -> str | None:
    """Only affirmative, explicit requirement clauses qualify as evidence.

    Ambiguous/compound language is intentionally left for review by callers.
    This helper must never establish a person's eligibility by itself.
    """
    for clause in re.split(r"[.!?;\n]+", text):
        if re.search(pattern, clause, re.I) and REQUIRED.search(clause) and not NEGATED_OR_PREFERRED.search(clause):
            return " ".join(clause.split())
    return None

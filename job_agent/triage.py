"""Conservative title triage; original discovery output is never discarded."""
from __future__ import annotations

import re
from .models import Job

ROLE = re.compile(r"\b(ai|llm|machine learning|ml engineer|power platform|copilot|data engineer|"
                  r"software|fullstack|full.stack|backend|back.end|developer|utvecklare|"
                  r"integration|automation engineer|automation specialist|automationsspecialist|"
                  r"it consultant|it.konsult|systemutvecklare|prompt engineer|rag)\b", re.I)
INDUSTRIAL = re.compile(r"\b(elektriker|eltekniker|eltestare|montör|operatör|"
                        r"produktionsmedarbetare|industrielektriker|automationselektriker|"
                        r"processindustri|servicetekniker|automationstekniker)\b", re.I)


def title_triage(job: Job) -> str:
    """Return candidate, unclear or likely_unrelated; do not use as rejection."""
    title = job.title.casefold()
    if INDUSTRIAL.search(title) and not ROLE.search(title):
        return "likely_unrelated"
    if ROLE.search(title):
        return "candidate"
    return "unclear"

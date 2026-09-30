"""Conservative question language detection; ambiguity requires review."""
from __future__ import annotations

import re


EN = {"why", "what", "how", "have", "do", "you", "your", "experience", "describe", "work", "authorization", "will", "require", "sponsorship", "employer"}
SV = {"varför", "vad", "hur", "har", "du", "din", "dina", "erfarenhet", "beskriv", "arbete", "arbetstillstånd", "med", "behöver", "arbetsgivare", "arbetsgivaren"}


def detect_question_language(question: str) -> str | None:
    """Return en/sv only when there are at least two discriminating language signals."""
    words = set(re.findall(r"[^\W\d_]+", question.casefold(), flags=re.UNICODE))
    en = len(words & EN)
    sv = len(words & SV)
    if en >= 2 and sv == 0:
        return "en"
    if sv >= 2 and en == 0:
        return "sv"
    return None

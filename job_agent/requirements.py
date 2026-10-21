"""Conservative clause-level requirement evidence, not a general language parser."""
from __future__ import annotations

import re

NEGATED_OR_PREFERRED = re.compile(
    r"\bnot\s+(?:\w+\s+){0,3}(?:required|necessary|mandatory)|\bno\s+.{0,45}(?:requirement|required|necessary|mandatory)"
    r"|\b(?:preferred|optional|advantage(?:ous)?|beneficial|plus|bonus|meriterande)\b|nice.to.have|good.to.have|highly valued|önskvärt"
    r"|(?:krävs|krav).*inte|inte.*(?:krav|nödvändigt)", re.I)
REQUIRED = re.compile(r"\b(?:required|mandatory|must|require|requires|fluent|native|essential)\b"
                      r"|krävs|ett krav|måste|finsktalande|flytande|obehindr(?:ad|at|ade)", re.I)

LANGUAGES = {"en": r"\benglish\b|\bengelska\b", "sv": r"\bswedish\b|\bsvenska\b",
             "fi": r"\bfinnish\b|\bfinska\b|\bfinsktalande\b", "da": r"\bdanish\b|\bdanska\b",
             "de": r"\bgerman\b|\btyska\b", "no": r"\bnorwegian\b|\bnorska\b",
             "fr": r"\bfrench\b|\bfranska\b", "zh": r"\bmandarin\b|\bchinese\b|\bkinesiska\b"}
LEVELS = {"basic": 1, "intermediate": 2, "professional": 3, "fluent": 4, "native": 5,
          "a1": 1, "a2": 1, "b1": 2, "b2": 3, "c1": 4, "c2": 4}


def language_level(text: str) -> str | None:
    for level, pattern in (
        ("native", r"native|mother tongue|modersmål"),
        ("fluent", r"fluen\w*|flytande|obehindr(?:ad|at|ade)|excellent|utmärkt"),
        ("professional", r"professional|professionell|business.level|working proficiency|mycket god(?:a)? (?:förmåga|kunskaper|språkkunskaper)"),
        ("intermediate", r"intermediate|medelgod"),
        ("basic", r"basic|grundläggande"),
    ):
        if re.search(pattern, text, re.I):
            return level
    cefr = re.search(r"\b([abc][12])\b", text, re.I)
    return cefr.group(1).lower() if cefr else None


def language_requirements(text: str) -> list[dict]:
    """Extract explicit language clauses; no requirement is inferred from job language.

    This is a bounded rules baseline. Compound/ambiguous clauses remain review
    evidence, not an assertion that all natural-language requirements are parsed.
    """
    found = []
    language_words = "|".join(LANGUAGES.values())
    for sentence in re.split(r"[.!?;\n]+", text):
        split_and = r"\b(?:and|och|samt)\s+(?=(?:\w+[ -]){0,3}(?:" + language_words + r"))"
        parts = re.split(r",|\b(?:but|however|whereas|men)\b|" + split_and, sentence, flags=re.I)
        for part in parts:
            for code, pattern in LANGUAGES.items():
                if not re.search(pattern, part, re.I):
                    continue
                if NEGATED_OR_PREFERRED.search(part):
                    state = "not_required_or_preferred"
                elif REQUIRED.search(part) or language_level(part):
                    state = "required"
                elif len(parts) > 1 and REQUIRED.search(sentence) and not NEGATED_OR_PREFERRED.search(sentence):
                    state = "required"
                elif re.search(r"skills|proficiency|spoken|written|speaking|kunskaper|språk|förmåga|uttrycka", part, re.I):
                    state = "uncertain"
                else:
                    state = "mentioned"
                level = language_level(part)
                if state == "required" and not level and not NEGATED_OR_PREFERRED.search(sentence):
                    level = language_level(sentence)
                found.append({"language": code, "state": state, "level": level,
                              "quote": " ".join(part.split())})
    return found


def assess_languages(text: str, declared: list[str], levels: dict[str, str]) -> tuple[list[str], list[dict]]:
    reasons, evidence = [], language_requirements(text)
    for item in evidence:
        code, state, required_level = item["language"], item["state"], item["level"]
        if state in {"mentioned", "not_required_or_preferred"}:
            continue
        actual = levels.get(code, "").casefold()
        if code not in declared or actual not in LEVELS or (state == "uncertain" and LEVELS[actual] < LEVELS["fluent"]):
            reasons.append(f"verify language requirement ({code}): {item['quote']}")
        elif required_level and LEVELS[actual] < LEVELS[required_level]:
            reasons.append(f"language level gap ({code}: {actual} vs {required_level}): {item['quote']}")
    return list(dict.fromkeys(reasons)), evidence


def requirement_evidence(pattern: str, text: str) -> str | None:
    """Only affirmative, explicit requirement clauses qualify as evidence.

    Ambiguous/compound language is intentionally left for review by callers.
    This helper must never establish a person's eligibility by itself.
    """
    for clause in re.split(r"[.!?;\n]+", text):
        if re.search(pattern, clause, re.I) and REQUIRED.search(clause) and not NEGATED_OR_PREFERRED.search(clause):
            return " ".join(clause.split())
    return None

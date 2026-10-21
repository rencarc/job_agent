"""Evidence for explicit technical requirements absent from a candidate profile.

These conservative flags request semantic review. Absence from a CV is never
presented as proof that a person cannot do the work.
"""
import re

from .requirements import NEGATED_OR_PREFERRED

YEAR_VALUES = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
               "eight": 8, "nine": 9, "ten": 10, "tre": 3, "fyra": 4,
               "fem": 5, "sex": 6, "sju": 7, "åtta": 8, "nio": 9, "tio": 10}
TECHNOLOGIES = {
    "C#": r"(?<!\w)c#(?!\w)", ".NET": r"(?<!\w)\.net\b", "Java": r"\bjava\b",
    "React": r"\breact\b", "Blazor": r"\bblazor\b", "Node.js": r"\bnode\.?js\b",
    "SQL Server": r"\bsql server\b|\bazure sql\b", "PowerShell": r"\bpowershell\b",
    "Kubernetes": r"\bkubernetes\b", "FastAPI": r"\bfastapi\b",
    "CI/CD": r"\bci\s*/\s*cd\b|\bci[- ]cd\b|continuous integration|continuous delivery|continuous deployment",
    "version control": r"version control|versionshantering|\bgit\b",
}


def technical_seniority_evidence(title: str, text: str) -> list[str]:
    reasons = []
    if re.search(r"\b(?:senior|sr\.?|staff|principal|lead|chief)\b|head of", title, re.I):
        reasons.append("senior technical role needs review: " + title.strip())
    body_role = re.search(r"\b(?:som|as|looking for|söker)\s+(?:(?:an?|en|our)\s+)?(?:senior|principal|staff)\s+(?:\w+[ -]){0,3}(?:engineer|developer|utvecklare)\b", text, re.I)
    if body_role:
        reasons.append("senior technical role in description needs review: " + body_role.group(0))
    number = r"\d{1,2}|" + "|".join(YEAR_VALUES)
    years_pattern = r"\b(" + number + r")\s*\+?\s*\)?\s*(?:years|års?|år)\b"
    for clause in re.split(r"[!?;\n]|\.(?=\s|$)", text):
        if NEGATED_OR_PREFERRED.search(clause):
            continue
        years = re.search(years_pattern, clause, re.I)
        technical = re.search(r"develop|software|engineer|programmer|utveckl|python|typescript|power platform"
                              r"|infrastructure|IT operation|Microsoft 365|backend|M365|\bAI\b|\bML\b|LLM|models|machine learning|data science", clause, re.I)
        if years and technical and int(YEAR_VALUES.get(years.group(1).casefold(), years.group(1))) >= 3:
            reasons.append("technical experience requirement needs review: " + " ".join(clause.split()))
        elif re.search(r"several years|flera års|substantial backend experience|operated backend systems in production", clause, re.I) and technical:
            reasons.append("production or multi-year technical experience needs review: " + " ".join(clause.split()))
    return list(dict.fromkeys(reasons))


def required_skill_gaps(text: str, profile: dict) -> list[dict]:
    supported = [term for term in profile["skills"]]
    supported += [alias for terms in profile.get("skill_aliases", {}).values() for alias in terms]
    known = {name for name, rx in TECHNOLOGIES.items() if any(re.search(rx, term, re.I) for term in supported)}
    active, evidence = False, []
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if re.search(r"requirements|required skills|must.have|skall.?krav|du behöver ha|technical stack.*requirements", line, re.I):
            active = True
        if re.search(r"^what we offer|^benefits|^why join|^about us|^meriterande|^highly meritorious|även meriterande", line, re.I):
            active = False
        explicit = bool(re.search(r"\b(?:must|required|mandatory)\b|du behöver|krävs", line, re.I))
        if not (active or explicit) or NEGATED_OR_PREFERRED.search(line):
            continue
        # Do not turn a known alternative (e.g. Python OR Java) into a false gap.
        if re.search(r"\b(?:or|eller)\b", line, re.I) and any(
                re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", line, re.I) for term in supported):
            continue
        for name, rx in TECHNOLOGIES.items():
            if name not in known and re.search(rx, line, re.I):
                evidence.append({"skill": name, "quote": line})
    return list({(item["skill"], item["quote"]): item for item in evidence}.values())

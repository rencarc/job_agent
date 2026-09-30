"""CV-grounded facts; unknown or conflicting claims never become application answers."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CareerFact:
    fact_id: str
    claim: str
    terms: tuple[str, ...]
    sources: tuple[str, ...]
    review: bool = False


def load_facts(path: Path) -> list[CareerFact]:
    data = json.loads(path.read_text(encoding="utf-8"))
    all_sources = tuple(data["sources"])
    facts = []
    for item in data["facts"]:
        sources = tuple(all_sources if item["sources"] == ["all_three"] else item["sources"])
        if not sources or not set(sources).issubset(all_sources):
            raise ValueError(f"unknown CV source for {item['id']}")
        facts.append(CareerFact(item["id"], item["claim"], tuple(item["terms"]), sources,
                                item.get("review", False)))
    if len({fact.fact_id for fact in facts}) != len(facts):
        raise ValueError("duplicate career fact id")
    return facts


def matching_facts(text: str, facts: list[CareerFact]) -> list[tuple[CareerFact, tuple[str, ...]]]:
    matches = []
    for fact in facts:
        if fact.review:
            continue
        terms = tuple(term for term in fact.terms if re.search(
            r"(?<!\w)" + re.escape(term.casefold()) + r"(?!\w)", text.casefold()))
        if terms:
            matches.append((fact, terms))
    return matches

"""User-editable, validated Sweden-wide search settings."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SearchSettings:
    queries: tuple[str, ...]
    recent_days: int = 7
    jobtech_pages: int = 3
    limit_per_query: int = 25
    boards: tuple[str, ...] = ()


def load_search_settings(path: Path) -> SearchSettings:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("search settings must be a JSON object")
    allowed = {"queries", "recent_days", "jobtech_pages", "limit_per_query", "boards"}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"unknown search settings: {', '.join(sorted(unknown))}")
    queries = data.get("queries")
    boards = data.get("boards", [])
    if not isinstance(queries, list) or not queries or any(not isinstance(q, str) or not q.strip() for q in queries):
        raise ValueError("queries must be a nonempty list of search terms")
    if not isinstance(boards, list) or any(not isinstance(b, str) or ':' not in b for b in boards):
        raise ValueError("boards must be a list of PROVIDER:BOARD strings")
    for key, low, high in (("recent_days", 0, 365), ("jobtech_pages", 1, 20), ("limit_per_query", 1, 100)):
        value = data.get(key, {"recent_days": 7, "jobtech_pages": 3, "limit_per_query": 25}[key])
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{key} must be an integer from {low} to {high}")
    return SearchSettings(tuple(q.strip() for q in queries), data.get("recent_days", 7),
                          data.get("jobtech_pages", 3), data.get("limit_per_query", 25), tuple(boards))

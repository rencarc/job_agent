"""Incremental, zero-token selection with an optional bounded evaluation seam.

This module produces preparation tasks. It never sends an application, writes
to Airtable, or treats a match score as proof of legal eligibility or liveness.
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .history import HistoryIndex
from .models import Job
from .requirements import requirement_evidence
from .store import JobStore, content_hash, digest

RULE_VERSION = "profile-rules-1"


@dataclass(frozen=True)
class Limits:
    max_evaluations: int = 30
    max_seconds: int = 120
    daily_model_calls: int = 0
    daily_tokens: int = 0
    tokens_per_call: int = 4000

    def __post_init__(self):
        for name, value in self.__dict__.items():
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if not self.max_seconds or not self.tokens_per_call:
            raise ValueError("time and per-call token limits must be positive")


def load_profile(path: Path) -> dict:
    profile = json.loads(path.read_text(encoding="utf-8"))
    validate_profile(profile)
    return profile


def validate_profile(profile: dict):
    if not isinstance(profile, dict) or profile.get("confirmed_by_user") is not True:
        raise ValueError("a user-confirmed automation profile is required")
    for key in ("target_titles", "languages"):
        if not isinstance(profile.get(key), list) or not profile[key] or any(
                not isinstance(s, str) or not s.strip() for s in profile[key]):
            raise ValueError(f"{key} must be a nonempty list of strings")
    if profile.get("country_code") != "SE":
        raise ValueError("this pipeline currently supports Sweden only")
    facts, skills = profile.get("facts"), profile.get("skills")
    if not isinstance(facts, dict) or not facts or any(not isinstance(v, str) or not v.strip() for v in facts.values()):
        raise ValueError("facts must map IDs to verified career claims")
    if not isinstance(skills, dict) or not skills:
        raise ValueError("skills must map terms to verified fact IDs")
    for term, ids in skills.items():
        if not isinstance(term, str) or not term.strip() or not isinstance(ids, list) or not ids or any(
                not isinstance(i, str) or i not in facts for i in ids):
            raise ValueError("each skill needs at least one known career fact")
    minimum = profile.get("min_skill_matches", 2)
    if type(minimum) is not int or not 1 <= minimum <= len(skills):
        raise ValueError("min_skill_matches must be 1..number of configured skills")


def contains(term: str, text: str) -> bool:
    return bool(re.search(r"(?<!\w)" + re.escape(term.casefold()) + r"(?!\w)", text.casefold()))


def rule_match(job: Job, profile: dict) -> dict:
    title_match = [term for term in profile["target_titles"] if contains(term, job.title)]
    skill_matches = [term for term in profile["skills"] if contains(term, job.description)]
    evidence = [{"skill": term, "fact_ids": profile["skills"][term]} for term in skill_matches]
    reasons = []
    if job.location_status == "outside_sweden":
        return {"decision": "skip", "score": 0, "reasons": ["explicitly outside Sweden"], "evidence": evidence}
    if not title_match and not skill_matches:
        return {"decision": "skip", "score": 0, "reasons": ["no target-role or supported-skill evidence"], "evidence": []}
    if not title_match:
        reasons.append("role title needs semantic review")
    if len(skill_matches) < profile.get("min_skill_matches", 2):
        reasons.append("insufficient supported skill evidence")
    if not job.description.strip():
        reasons.append("full job description unavailable")
    if job.location_status != "sweden":
        reasons.append("Sweden location is unverified")
    if not job.apply_url and not job.source_url:
        reasons.append("posting URL unavailable")
    declared = {s.casefold() for s in profile["languages"]}
    for language, pattern in {"sv": r"swedish|svenska", "fi": r"finnish|finska|finsktalande",
                              "en": r"english|engelska"}.items():
        quote = requirement_evidence(pattern, job.description)
        if quote:
            # A language code alone does not attest a required fluency level.
            reasons.append(f"verify required language level ({language}): {quote}")
        elif language not in declared and re.search(pattern, job.description, re.I):
            reasons.append(f"undeclared language mentioned ({language}); requirement uncertain")
    for pattern in (r"citizenship|medborgarskap", r"sponsorship|work permit|arbetstillstånd"):
        if re.search(pattern, job.description, re.I):
            reasons.append("work eligibility requirement needs verified interpretation")
    score = min(100, (40 if title_match else 0) + 20 * len(skill_matches))
    return {"decision": "exception" if reasons else "prepare", "score": score,
            "reasons": reasons, "evidence": evidence, "matched_titles": title_match,
            "posting_open": "unverified", "can_submit": False}


def run_pipeline(store: JobStore, jobs: list[Job], profile: dict, *, history_records=None,
                 limits: Limits = Limits(), evaluator=None, evaluator_version: str = "",
                 clock=time.monotonic) -> dict:
    """Ingest before scoring; retry deferred items from disk on the next run.

    An optional evaluator returns {priority, tokens}; it can annotate priority,
    but cannot override eligibility exceptions or grant submission permission.
    It must enforce its supplied max_tokens at the transport/provider boundary.
    No provider is enabled by this library or the daily CLI.
    """
    validate_profile(profile)
    if evaluator is not None and not evaluator_version:
        raise ValueError("an explicit evaluator/model/prompt version is required for caching")
    start = clock()
    day = datetime.now(timezone.utc).date().isoformat()
    profile_hash = digest(profile)
    history_index = HistoryIndex(history_records) if history_records is not None else None
    report = {"ingested": 0, "changed": 0, "evaluated": 0, "cached": 0,
              "deferred": 0, "errors": [], "tasks": []}
    with store.lease("automation", seconds=limits.max_seconds + 300):
        run_id = store.start_run()
        report["run_id"] = run_id
        try:
            for job in jobs:
                job_id, changed = store.ingest(job)
                report["ingested"] += 1
                report["changed"] += int(changed)
            # Check history every run, even for cached evaluations. A new Applied
            # record must immediately suppress a formerly prepared task.
            for job_id, job in store.jobs():
                key = digest([job_id, content_hash(job), profile_hash, RULE_VERSION, evaluator_version])
                result = store.cached(key)
                if result is not None:
                    report["cached"] += 1
                elif report["evaluated"] >= limits.max_evaluations or clock() - start >= limits.max_seconds:
                    report["deferred"] += 1
                    result = {"decision": "deferred", "reasons": ["run evaluation/time budget reached"], "can_submit": False}
                    store.enqueue(job_id, key, result)
                    continue
                else:
                    result = rule_match(job, profile)
                    if evaluator is not None and result["decision"] != "skip":
                        if not store.reserve(day, tokens=limits.tokens_per_call, max_tokens=limits.daily_tokens,
                                             max_calls=limits.daily_model_calls):
                            report["deferred"] += 1
                            store.enqueue(job_id, key, {"decision": "deferred", "reasons": ["daily model budget reached"], "can_submit": False})
                            continue
                        try:
                            priority = evaluator(job, profile, max_tokens=limits.tokens_per_call)
                            if (type(priority.get("tokens")) is not int or type(priority.get("priority")) is not int
                                    or not 0 <= priority["priority"] <= 100):
                                raise ValueError("invalid evaluator response")
                            store.settle(day, limits.tokens_per_call, priority["tokens"])
                            result["model_priority"] = priority["priority"]
                        except Exception as exc:
                            # Never cache a failed model call as success. The next
                            # run may retry within the remaining durable allowance.
                            report["errors"].append({"job_id": job_id, "error": type(exc).__name__})
                            store.enqueue(job_id, key, {"decision": "exception", "reasons": ["evaluation failed"], "can_submit": False})
                            report["evaluated"] += 1
                            continue
                    store.cache(key, job_id, result)
                    report["evaluated"] += 1
                # Do not mutate cached content with transient tracker decisions.
                routed = dict(result)
                if history_records is None:
                    if routed["decision"] != "skip":
                        routed.update(decision="exception", reasons=["application history is unverified"])
                else:
                    history = history_index.match(job)
                    if history.action != "new":
                        routed.update(decision="skip" if history.action == "blocked" else "exception", reasons=[history.reason])
                store.enqueue(job_id, key, routed)
            report["tasks"] = [{"job_id": row["job_id"], **json.loads(row["result"])} for row in
                               store.db.execute("SELECT job_id,result FROM queue ORDER BY updated_at,job_id")]
            report["counts"] = dict(Counter(task["decision"] for task in report["tasks"]))
            report["usage_today"] = store.usage(day)
            report["elapsed_seconds"] = round(clock() - start, 3)
            report["status"] = "partial" if report["errors"] or report["deferred"] else "ok"
            store.finish_run(run_id, report)
            return report
        except BaseException as exc:
            store.finish_run(run_id, {"status": "failed", "error": type(exc).__name__})
            raise

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
from hashlib import file_digest
from pathlib import Path

from .history import HistoryIndex
from .availability import assess_availability
from .models import Job
from .qualifications import required_skill_gaps, technical_seniority_evidence
from .requirements import LEVELS, assess_languages
from .store import JobStore, content_hash, digest

RULE_VERSION = "profile-rules-6"


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


def load_profile(path: Path, *, allow_draft: bool = False) -> dict:
    profile = json.loads(path.read_text(encoding="utf-8"))
    validate_profile(profile, allow_draft=allow_draft)
    source, expected_hash = profile.get("source_document"), profile.get("source_sha256")
    if source is not None or expected_hash is not None:
        if not isinstance(source, str) or not isinstance(expected_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", expected_hash):
            raise ValueError("source_document and its SHA-256 must be supplied together")
        with Path(source).open("rb") as document:
            if file_digest(document, "sha256").hexdigest() != expected_hash:
                raise ValueError("CV changed since profile extraction; review the profile before using it")
    return profile


def validate_profile(profile: dict, *, allow_draft: bool = False):
    if not isinstance(profile, dict) or (profile.get("confirmed_by_user") is not True and
                                       not (allow_draft and profile.get("confirmed_by_user") is False)):
        raise ValueError("a user-confirmed automation profile is required")
    for key in ("target_titles", "languages"):
        if not isinstance(profile.get(key), list) or not profile[key] or any(
                not isinstance(s, str) or not s.strip() for s in profile[key]):
            raise ValueError(f"{key} must be a nonempty list of strings")
    if profile.get("country_code") != "SE":
        raise ValueError("this pipeline currently supports Sweden only")
    preferred = profile.get("preferred_locations", [])
    if not isinstance(preferred, list) or any(not isinstance(s, str) or not s.strip() for s in preferred):
        raise ValueError("preferred_locations must be a list of nonempty location names")
    levels = profile.get("language_levels", {})
    if not isinstance(levels, dict) or any(k not in profile["languages"] or not isinstance(v, str)
                                         or v.casefold() not in LEVELS for k, v in levels.items()):
        raise ValueError("language_levels must use declared languages and explicit supported levels")
    facts, skills = profile.get("facts"), profile.get("skills")
    if not isinstance(facts, dict) or not facts or any(not isinstance(v, str) or not v.strip() for v in facts.values()):
        raise ValueError("facts must map IDs to verified career claims")
    if not isinstance(skills, dict) or not skills:
        raise ValueError("skills must map terms to verified fact IDs")
    for term, ids in skills.items():
        if not isinstance(term, str) or not term.strip() or not isinstance(ids, list) or not ids or any(
                not isinstance(i, str) or i not in facts for i in ids):
            raise ValueError("each skill needs at least one known career fact")
    aliases = profile.get("skill_aliases", {})
    if not isinstance(aliases, dict) or any(k not in skills or not isinstance(v, list) or
            any(not isinstance(s, str) or not s.strip() for s in v) for k, v in aliases.items()):
        raise ValueError("skill_aliases must map verified skill names to lists of terms")
    minimum = profile.get("min_skill_matches", 2)
    if type(minimum) is not int or not 1 <= minimum <= len(skills):
        raise ValueError("min_skill_matches must be 1..number of configured skills")


def contains(term: str, text: str) -> bool:
    return bool(re.search(r"(?<!\w)" + re.escape(term.casefold()) + r"(?!\w)", text.casefold()))


def location_priority(job: Job, profile: dict) -> int:
    """Location preferences order candidates; they never exclude another Swedish city."""
    preferred = profile.get("preferred_locations", [])
    if not preferred:
        return 0
    # Staffing adverts can contain their agency's city in structured metadata.
    # An explicit title city is a stronger ranking hint, never an exclusion.
    cities = re.findall(r"\b(?:Stockholm|Gothenburg|Göteborg|Malmö|Uppsala|Lund|Umeå|Kalix|Linköping|Örebro)\b", job.title, re.I)
    if cities:
        return 0 if any(place.casefold() in city.casefold() for place in preferred for city in cities) else 1
    if any(place.casefold() in job.location.casefold() for place in preferred):
        return 0
    return 1 if job.location_status == "sweden" else 2


def rule_match(job: Job, profile: dict) -> dict:
    title_match = [term for term in profile["target_titles"] if contains(term, job.title)]
    skill_matches = [term for term in profile["skills"] if any(contains(alias, job.description)
                     for alias in [term, *profile.get("skill_aliases", {}).get(term, [])])]
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
    language_reasons, language_evidence = assess_languages(job.description,
        [s.casefold() for s in profile["languages"]], profile.get("language_levels", {}))
    reasons.extend(language_reasons)
    if profile.get("technical_seniority") == "early_career":
        reasons.extend(technical_seniority_evidence(job.title, job.description))
    gaps = required_skill_gaps(job.description, profile)
    if gaps:
        reasons.append("explicit technical requirements not evidenced in profile: " + ", ".join(dict.fromkeys(g["skill"] for g in gaps)))
    for pattern in (r"citizenship|medborgarskap", r"sponsorship|work permit|arbetstillstånd"):
        if re.search(pattern, job.description, re.I):
            reasons.append("work eligibility requirement needs verified interpretation")
    score = (40 if title_match else 0) + min(60, 10 * len(skill_matches))
    return {"decision": "exception" if reasons else "prepare", "score": score,
            "score_kind": "rule_priority_not_probability",
            "unsupported_requirements": gaps,
            "reasons": reasons, "evidence": evidence, "matched_titles": title_match,
            "language_evidence": language_evidence, "posting_open": "unverified", "can_submit": False}


def run_pipeline(store: JobStore, jobs: list[Job], profile: dict, *, history_records=None,
                 limits: Limits = Limits(), evaluator=None, evaluator_version: str = "",
                 clock=time.monotonic, preview: bool = False, local_history=None) -> dict:
    """Ingest before scoring; retry deferred items from disk on the next run.

    An optional evaluator returns {priority, tokens}; it can annotate priority,
    but cannot override eligibility exceptions or grant submission permission.
    It must enforce its supplied max_tokens at the transport/provider boundary.
    No provider is enabled by this library or the daily CLI.
    """
    validate_profile(profile, allow_draft=preview)
    if preview and evaluator is not None:
        raise ValueError("profile preview does not dispatch model calls")
    store.bind_mode("preview" if preview else "production")
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
                # Check the durable submission fence before scoring or model
                # dispatch. It is transient routing state, never a cached match.
                local = local_history.match(job) if local_history is not None else None
                if local is not None and local.action != "new":
                    decision = "skip" if local.action == "blocked" else "exception"
                    result = {"decision": decision, "reasons": [local.reason], "can_submit": False,
                              "local_history": local.action, "location_priority": location_priority(job, profile)}
                    if preview:
                        result.update(decision="preview", suggested_decision=decision, routing_decision=decision)
                    store.enqueue(job_id, key, result)
                    continue
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
                routed["location_priority"] = location_priority(job, profile)
                availability = assess_availability(job)
                if availability["decision"]:
                    routed.update(decision=availability["decision"], reasons=[*routed["reasons"], *availability["reasons"]])
                routed["deadline_evidence"] = availability.get("deadline_evidence", [])
                suggested_decision = routed["decision"]
                if history_records is None:
                    if routed["decision"] != "skip":
                        routed.update(decision="exception", reasons=[*routed["reasons"], "application history is unverified"])
                else:
                    history = history_index.match(job)
                    if history.action != "new":
                        routed.update(decision="skip" if history.action == "blocked" else "exception", reasons=[history.reason])
                if preview:
                    routed["suggested_decision"] = suggested_decision
                    routed["routing_decision"] = routed["decision"]
                    routed["decision"] = "preview"
                    routed["can_submit"] = False
                store.enqueue(job_id, key, routed)
            report["tasks"] = [{"job_id": row["job_id"], **json.loads(row["result"])} for row in
                               store.db.execute("SELECT job_id,result FROM queue ORDER BY updated_at,job_id")]
            bands = {"prepare": 0, "exception": 1, "deferred": 2, "skip": 3, "preview": 0}
            report["tasks"].sort(key=lambda task: (
                bands[task.get("suggested_decision", task["decision"])], task.get("location_priority", 0),
                -task.get("model_priority", task.get("score", 0)), task["job_id"]))
            report["counts"] = dict(Counter(task["decision"] for task in report["tasks"]))
            report["usage_today"] = store.usage(day)
            report["preview"] = preview
            report["elapsed_seconds"] = round(clock() - start, 3)
            report["status"] = "partial" if report["errors"] or report["deferred"] else "ok"
            store.finish_run(run_id, report)
            return report
        except BaseException as exc:
            store.finish_run(run_id, {"status": "failed", "error": type(exc).__name__})
            raise

"""Idempotent preparation plans using reviewed CV bytes, without generating claims."""
from __future__ import annotations

import json
from hashlib import file_digest
from pathlib import Path

from .models import Job
from .resume_variants import ResumeVariant, choose_resume
from .store import content_hash, digest


def verify_cv(item: dict):
    cv = Path(item["path"])
    if cv.suffix.casefold() != ".pdf":
        raise ValueError("reviewed CV must be a PDF")
    with cv.open("rb") as source:
        if source.read(5) != b"%PDF-":
            raise ValueError("CV file does not have a PDF header")
        source.seek(0)
        if file_digest(source, "sha256").hexdigest() != item.get("reviewed_sha256"):
            raise ValueError("CV changed after document review")


def load_catalog(path: Path, profile: dict, *, preview: bool = False) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("confirmed_by_user") is not True and not (preview and data.get("confirmed_by_user") is False):
        raise ValueError("CV catalog must be confirmed or used in explicit preview mode")
    variants = data.get("variants")
    if not isinstance(variants, list) or not variants:
        raise ValueError("CV catalog needs at least one variant")
    seen = set()
    for item in variants:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise ValueError("CV variant needs a nonempty string ID")
        if not isinstance(item.get("path"), str):
            raise ValueError("CV variant needs a file path")
        terms = item.get("focus_terms")
        if not isinstance(terms, list) or not terms or any(not isinstance(t, str) or not t.strip() for t in terms):
            raise ValueError("CV focus_terms must be a nonempty list of strings")
        if item["id"] in seen:
            raise ValueError("duplicate CV variant ID")
        seen.add(item["id"])
        cv = Path(item["path"])
        verify_cv(item)
        facts = item.get("fact_ids", [])
        if not facts or any(fact not in profile["facts"] for fact in facts):
            raise ValueError("CV catalog needs known supporting career fact IDs")
        ResumeVariant(item["id"], cv, tuple(item["focus_terms"]), item.get("language", "en"))
    return variants


def prepare_materials(report: dict, profile: dict, catalog: list[dict], output_dir: Path, *, preview: bool = False) -> list[dict]:
    """Create deterministic plans, never edit the source PDF or submit a form.

    PDF header/hash checks establish byte identity with the reviewed document,
    not independent PDF validity or a fresh visual inspection.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    variants = [ResumeVariant(c["id"], Path(c["path"]), tuple(c["focus_terms"]), c.get("language", "en")) for c in catalog]
    by_id = {c["id"]: c for c in catalog}
    prepared = []
    for task in report["tasks"]:
        if task["decision"] == "preview":
            if not preview or task.get("suggested_decision") != "prepare":
                continue
        elif task["decision"] != "prepare":
            continue
        job = Job(**task["job"])
        choice = choose_resume(job, variants)
        selected = by_id[choice.variant.variant_id]
        verify_cv(selected)
        fact_ids = {fact for hit in task.get("evidence", []) for fact in hit["fact_ids"]}
        supported = sorted(fact_ids & set(selected["fact_ids"]))
        unresolved = [*task.get("reasons", []), "employer form has not been inspected", "employer posting openness has not been verified"]
        if choice.confidence != "supported":
            unresolved.append("CV variant selection needs review")
        if not supported:
            unresolved.append("no matched career facts are mapped to the selected CV")
        if not profile.get("confirmed_by_user"):
            unresolved.append("candidate targeting profile is a draft")
        if profile.get("work_authorized_now") is None:
            unresolved.append("current work authorization is unknown")
        if profile.get("employer_support_required_now") is None:
            unresolved.append("current-only employer support answer is unknown")
        if profile.get("employer_support_required_future") is None:
            unresolved.append("future employer support answer is unknown")
        bundle_id = digest(["preparation-v2", task["job_id"], content_hash(job), digest(profile), digest(selected), preview])
        plan = {"bundle_id": bundle_id, "job_id": task["job_id"], "company": job.company, "title": job.title,
                "posting_url": job.apply_url or job.source_url, "state": "preview" if preview else "prepared",
                "can_submit": False, "cv": {"id": selected["id"], "path": selected["path"],
                    "sha256": selected["reviewed_sha256"], "modified": False, "matched_terms": list(choice.matched_terms)},
                "supported_facts": {fact: profile["facts"][fact] for fact in supported},
                "work_authorized_now": profile.get("work_authorized_now"),
                "employer_support_required_now": profile.get("employer_support_required_now"),
                "employer_support_required_future": profile.get("employer_support_required_future"),
                "cover_letter": {"generated": False, "requirement": "unknown until employer form is inspected"},
                "unresolved": list(dict.fromkeys(unresolved))}
        target = output_dir / (bundle_id + ".json")
        if target.exists():
            if json.loads(target.read_text(encoding="utf-8")) != plan:
                raise ValueError("existing preparation plan differs; reconcile instead of overwriting")
        else:
            # Exclusive create prevents an overlapping writer from clobbering a plan.
            with target.open("x", encoding="utf-8") as output:
                json.dump(plan, output, ensure_ascii=False, indent=2)
                output.write("\n")
        prepared.append({"job_id": task["job_id"], "bundle_id": bundle_id, "path": str(target), "can_submit": False})
    return prepared

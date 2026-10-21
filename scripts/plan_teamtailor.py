"""Create a local preparation checklist from an observed form; never fills or submits."""
import argparse
import json
from pathlib import Path

from job_agent.form_preferences import preference_plan
from job_agent.form_inputs import attach_source_inputs, load_contact_profile
from job_agent.automation import load_profile
from job_agent.materials import load_catalog
from job_agent.run_cli import atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspection", type=Path, required=True)
    parser.add_argument("--preferences", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contacts", type=Path, help="Source-reviewed private contact profile; suggestions only")
    parser.add_argument("--candidate-profile", type=Path)
    parser.add_argument("--resume-catalog", type=Path)
    parser.add_argument("--cv-id", help="Exact reviewed CV variant to attach as a local suggestion")
    args = parser.parse_args()
    try:
        inspection = json.loads(args.inspection.read_text(encoding="utf-8"))
        plan = preference_plan(inspection,
                               json.loads(args.preferences.read_text(encoding="utf-8")))
        cv = None
        if any((args.candidate_profile, args.resume_catalog, args.cv_id)):
            if not all((args.candidate_profile, args.resume_catalog, args.cv_id)):
                raise ValueError("CV handoff needs candidate-profile, resume-catalog and cv-id together")
            candidate = load_profile(args.candidate_profile, allow_draft=True)
            catalog = load_catalog(args.resume_catalog, candidate, preview=True)
            choices = [entry for entry in catalog if entry["id"] == args.cv_id]
            if len(choices) != 1:
                raise ValueError("CV ID must match exactly one reviewed catalog entry")
            cv = choices[0]
            plan["career_evidence"] = {fact: candidate["facts"][fact] for fact in cv["fact_ids"]}
            plan["candidate_profile_confirmed"] = candidate["confirmed_by_user"]
        plan = attach_source_inputs(plan, inspection,
                                    contacts=load_contact_profile(args.contacts) if args.contacts else None, cv=cv)
        atomic_json(args.output, plan)
        print(json.dumps({"suggestions": len(plan["answers"]),
                          "unresolved_required": len(plan["unresolved_required"]), "can_submit": False}))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, "Teamtailor preparation stopped: " + str(exc) + "\n")


if __name__ == "__main__":
    main()

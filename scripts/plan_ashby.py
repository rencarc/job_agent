"""Build a private exact-field manifest from a freshly inspected Ashby form."""
import argparse
import hashlib
import json
from urllib.parse import urlsplit
from dataclasses import asdict
from pathlib import Path

from job_agent.eligibility_answers import load_eligibility
from job_agent.eligibility_question import classify_eligibility_question
from job_agent.form_plan import FormControl, plan_form
from job_agent.materials import bind_preparation_to_form


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspection", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True,
                        help="Private JSON mapping actual standard field labels to approved values")
    parser.add_argument("--eligibility", type=Path, required=True)
    parser.add_argument("--verified-country", required=True, help="ISO code verified from the employer's posting")
    parser.add_argument("--cv-id", required=True, help="Selected résumé variant identifier")
    parser.add_argument("--preparation-plan", type=Path, help="Bind a local reviewed CV preparation plan to this exact job")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inspection = json.loads(args.inspection.read_text(encoding="utf-8"))
    parsed = urlsplit(inspection.get("url", ""))
    if parsed.scheme != "https" or parsed.hostname != "jobs.ashbyhq.com" or not parsed.path.endswith("/application"):
        parser.error("inspection needs an Ashby application URL")
    controls = [FormControl(item["label"], item["kind"], item["required"]) for item in inspection["controls"]]
    profile_data = json.loads(args.profile.read_text(encoding="utf-8"))
    profile = profile_data.get("fields") if isinstance(profile_data, dict) else None
    if not isinstance(profile_data, dict) or profile_data.get("confirmed_by_user") is not True or not isinstance(profile, dict) or any(
            not isinstance(v, str) for v in profile.values()):
        parser.error("profile fields must be explicitly confirmed by the user")
    mapping = {item.label: kind for item in controls if (kind := classify_eligibility_question(item.label))}
    preparation = None
    if args.preparation_plan:
        preparation = json.loads(args.preparation_plan.read_text(encoding="utf-8"))
        try:
            profile = bind_preparation_to_form(preparation, inspection, profile, args.cv_id)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            parser.error("preparation handoff stopped: " + str(exc))
    result = plan_form(controls, profile, {}, {}, eligibility=load_eligibility(args.eligibility),
                       job_country=args.verified_country, eligibility_question_ids=mapping)
    if not result.ready:
        parser.error("cannot fill: " + "; ".join(result.unresolved))
    if len({control.label for control in controls}) != len(controls):
        parser.error("duplicate form labels need review")
    by_label = {field.label: field for field in result.fields}
    for control in controls:
        field = by_label.get(control.label)
        if field is None:
            continue  # plan_form already rejected unanswered required controls.
        if control.kind == "file" and (not Path(field.value).is_file() or Path(field.value).suffix.lower() != ".pdf"):
            parser.error("resume must be an existing PDF")
    uploads = [by_label[c.label] for c in controls if c.kind == "file" and c.label in by_label]
    if len(uploads) != 1:
        parser.error("exactly one resume upload is supported by this form driver")
    resume = uploads[0]
    pdf_sha256 = hashlib.sha256(Path(resume.value).read_bytes()).hexdigest()
    if preparation and pdf_sha256 != preparation["cv"]["sha256"]:
        parser.error("CV changed during preparation handoff")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"url": inspection["url"], "fields": [asdict(f) for f in result.fields],
                                       "selected_cv": args.cv_id, "resume_sha256": pdf_sha256,
                                       "verified_country": args.verified_country, "unresolved": [],
                                       "can_submit": False,
                                       "preparation_bundle": preparation["bundle_id"] if preparation else None,
                                       "preparation_unresolved": preparation.get("unresolved", []) if preparation else [],
                                       "preparation_state": preparation["state"] if preparation else None},
                                      ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.chmod(0o600)
    print(f"Ready for Ashby preview: {len(result.fields)} exact fields")


if __name__ == "__main__":
    main()

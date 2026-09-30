"""Build a private exact-field manifest from a freshly inspected Ashby form."""
import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from job_agent.eligibility_answers import load_eligibility
from job_agent.eligibility_question import classify_eligibility_question
from job_agent.form_plan import FormControl, plan_form


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspection", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True,
                        help="Private JSON mapping actual standard field labels to approved values")
    parser.add_argument("--eligibility", type=Path, required=True)
    parser.add_argument("--verified-country", required=True, help="ISO code verified from the employer's posting")
    parser.add_argument("--cv-id", required=True, help="Selected résumé variant identifier")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inspection = json.loads(args.inspection.read_text(encoding="utf-8"))
    if not inspection.get("url", "").startswith("https://jobs.ashbyhq.com/"):
        parser.error("inspection needs an Ashby application URL")
    controls = [FormControl(item["label"], item["kind"], item["required"]) for item in inspection["controls"]]
    profile_data = json.loads(args.profile.read_text(encoding="utf-8"))
    profile = profile_data.get("fields") if isinstance(profile_data, dict) else None
    if not isinstance(profile_data, dict) or profile_data.get("confirmed_by_user") is not True or not isinstance(profile, dict) or any(
            not isinstance(v, str) for v in profile.values()):
        parser.error("profile fields must be explicitly confirmed by the user")
    mapping = {item.label: kind for item in controls if (kind := classify_eligibility_question(item.label))}
    result = plan_form(controls, profile, {}, {}, eligibility=load_eligibility(args.eligibility),
                       job_country=args.verified_country, eligibility_question_ids=mapping)
    if not result.ready:
        parser.error("cannot fill: " + "; ".join(result.unresolved))
    if len(result.fields) != len(controls):
        parser.error("every observed form control must have an audited answer")
    for control, field in zip(controls, result.fields):
        if control.label != field.label:
            parser.error("form field order or labels changed")
        if control.kind == "file" and (not Path(field.value).is_file() or Path(field.value).suffix.lower() != ".pdf"):
            parser.error("resume must be an existing PDF")
    resume = next((field for control, field in zip(controls, result.fields) if control.kind == "file"), None)
    if resume is None:
        parser.error("a resume upload is required for this first form driver")
    pdf_sha256 = hashlib.sha256(Path(resume.value).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"url": inspection["url"], "fields": [asdict(f) for f in result.fields],
                                       "selected_cv": args.cv_id, "resume_sha256": pdf_sha256,
                                       "verified_country": args.verified_country, "unresolved": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.chmod(0o600)
    print(f"Ready for Ashby preview: {len(result.fields)} exact fields")


if __name__ == "__main__":
    main()

"""Plan a form from observed controls; do not infer unknown personal answers."""
from __future__ import annotations

from dataclasses import dataclass

from .answer_bank import Answer, answer_question
from .form_audit import FilledField
from .question_language import detect_question_language
from .eligibility_answers import EligibilityAnswers, eligibility_field


@dataclass(frozen=True)
class FormControl:
    label: str
    kind: str  # text, email, url, file, choice, or unknown
    required: bool = True


@dataclass(frozen=True)
class FormPlan:
    fields: tuple[FilledField, ...]
    unresolved: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.unresolved and bool(self.fields)


def plan_form(controls: list[FormControl], profile: dict[str, str],
              answers: dict[str, Answer], question_answer_ids: dict[str, str],
              *, eligibility: EligibilityAnswers | None = None,
              job_country: str = "", eligibility_question_ids: dict[str, str] | None = None) -> FormPlan:
    """Prepare exact values for a live form driver; never touches a website."""
    fields = []
    unresolved = []
    for control in controls:
        if control.kind not in {"text", "email", "url", "file", "choice"}:
            unresolved.append(f"unsupported control: {control.label}")
            continue
        eligibility_kind = (eligibility_question_ids or {}).get(control.label)
        if eligibility_kind:
            try:
                if eligibility is None:
                    raise ValueError("no eligibility profile")
                fields.append(eligibility_field(control.label, eligibility_kind,
                                                job_country=job_country, answers=eligibility))
                continue
            except ValueError:
                unresolved.append(f"eligibility answer needs review: {control.label}")
                continue
        if any(term in control.label.casefold() for term in
               ("authorization", "sponsorship", "work permit", "arbetstillstånd", "arbeta i sverige")):
            unresolved.append(f"eligibility question has no verified mapping: {control.label}")
            continue
        direct = profile.get(control.label, "").strip()
        if direct:
            fields.append(FilledField(control.label, direct, "user_supplied", "none", "none"))
            continue
        answer_id = question_answer_ids.get(control.label)
        if answer_id:
            language = detect_question_language(control.label)
            try:
                fields.append(answer_question(control.label, language or "", answer_id, answers))
                continue
            except ValueError:
                pass
        if control.required:
            unresolved.append(f"required answer missing or unapproved: {control.label}")
    return FormPlan(tuple(fields), tuple(unresolved))

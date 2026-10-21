"""Map common work-permission wording only when its meaning is unambiguous."""


def classify_eligibility_question(label: str) -> str | None:
    text = " ".join(label.casefold().split())
    support = ("sponsorship" in text or "employer support" in text or
               "arbetsgivaren" in text and "arbetstillstånd" in text)
    authorization = ("work authorization" in text or "authorized to work" in text or
                     "right to work" in text or "rätt att arbeta" in text)
    if support and authorization:
        return None
    return "employer_support" if support else "work_authorization" if authorization else None

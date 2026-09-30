from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PauseReason(str, Enum):
    LOGIN_REQUIRED = "login_required"
    BANKID_REQUIRED = "bankid_required"
    UNKNOWN_QUESTION = "unknown_question"
    PAGE_CHANGED = "page_changed"
    UNCLEAR_RECEIPT = "unclear_receipt"
    USER_APPROVAL_REQUIRED = "user_approval_required"


@dataclass(frozen=True)
class AdapterStep:
    name: str
    purpose: str
    requires_user: bool = False
    pause_reason: PauseReason | None = None


@dataclass(frozen=True)
class AdapterWorkflow:
    system: str
    steps: list[AdapterStep] = field(default_factory=list)

    def user_pause_steps(self) -> list[AdapterStep]:
        return [step for step in self.steps if step.requires_user]


@dataclass(frozen=True)
class ReceiptCheck:
    success: bool
    confirmation: str
    evidence_url: str = ""
    reason: str = ""

    def require_success(self) -> "ReceiptCheck":
        if not self.success:
            raise ValueError(self.reason or "receipt is not a verified success")
        return self

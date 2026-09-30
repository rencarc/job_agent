"""Auditable job-agent core."""

from .models import Decision, Job, ScoreResult
from .dedup import canonical_url, duplicate_match
from .scoring import score_job

__all__ = ["Decision", "Job", "ScoreResult", "canonical_url", "duplicate_match", "score_job"]

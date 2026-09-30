"""Job discovery sources."""

from .base import FetchResult, JobSource, QueryResult
from .jobtech import JobTechSource

__all__ = ["FetchResult", "JobSource", "JobTechSource", "QueryResult"]


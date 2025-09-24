from typing import Optional

from pydantic import BaseModel

class BaseContextShape(BaseModel):
    """Marker base for all email context models."""

class ProjectAnalysisFailure(BaseContextShape):
    repo_id: Optional[str] = None
    user_id: Optional[str] = None
    repository_html_url: Optional[str] = None
    user_email: Optional[str] = None
    repository_branch: Optional[str] = None
    job_context_id: Optional[str] = None
    job_type: Optional[str] = None
    job_queued_at: Optional[str] = None
    job_started_at: Optional[str] = None
    job_finished_at: Optional[str] = None
    job_settled_at: Optional[str] = None
    error_type: Optional[str] = None
    error_stacktrace: Optional[str] = None
    error_stacktrace_truncated: Optional[bool] = None
    error_summary: Optional[str] = None
    run_ms: Optional[int] = None
    total_ms: Optional[int] = None

class ProjectAnalysisSuccess(BaseContextShape):
    repository_html_url: Optional[str] = None
    repository_branch: Optional[str] = None
    job_type: Optional[str] = None
    job_queued_at: Optional[str] = None
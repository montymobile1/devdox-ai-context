import pytest
from datetime import datetime, timedelta, UTC

from app.infrastructure.job_tracer.job_trace_metadata import JobTraceMetaData


def test_add_metadata_fields():
    j = JobTraceMetaData()
    j.add_metadata(
        repo_id="r1", user_id="u1", job_context_id="ctx",
        job_type="build", repository_branch="main",
        repository_html_url="http://example.com/repo", user_email="user@example.com"
    )
    assert j.repo_id == "r1"
    assert j.user_id == "u1"
    assert j.job_context_id == "ctx"
    assert j.job_type == "build"
    assert j.repository_branch == "main"
    assert j.repository_html_url == "http://example.com/repo"
    assert j.user_email == "user@example.com"

def test_computed_fields():
    j = JobTraceMetaData()
    now = datetime.now(UTC)
    j.job_queued_at = now
    j.job_started_at = now
    j.job_finished_at = now + timedelta(seconds=2)
    j.job_settled_at = now + timedelta(seconds=4)

    assert j.run_ms == 2000
    assert j.total_ms == 4000

    j.job_started_at = None
    assert j.run_ms is None
    j.job_started_at = now
    j.job_settled_at = None
    assert j.total_ms is None


def test_has_error_flag():
    j = JobTraceMetaData()
    assert j.has_error is False
    j.error_type = "ValueError"
    assert j.has_error is True
    j.clear_error()
    j.error_stacktrace = "something went wrong"
    assert j.has_error is True
    j.clear_error()
    j.error_summary = "summary"
    assert j.has_error is True


def test_record_error_basic():
    j = JobTraceMetaData()

    def raise_error():
        raise ValueError("Test error")

    try:
        raise_error()
    except ValueError as e:
        j.record_error(e)

    assert j.error_summary.startswith("ValueError")
    assert j.error_stacktrace
    assert isinstance(j.error_chain, list)
    assert "raise_error" in j.error_type
    assert j.error_stacktrace_truncated in (True, False)


def test_record_error_summary_override():
    j = JobTraceMetaData()
    j.record_error(summary="Something went wrong")
    assert j.error_summary == "Something went wrong"


def test_record_error_default_summary():
    j = JobTraceMetaData()
    j.record_error()
    assert j.error_summary == ""


def test_clear_error():
    j = JobTraceMetaData()
    j.error_type="X"
    j.error_stacktrace="trace"
    j.error_summary="bad"
    j.error_stacktrace_truncated=True
    
    j.clear_error()
    assert j.error_type is None
    assert j.error_stacktrace is None
    assert j.error_summary is None
    assert j.error_stacktrace_truncated is False

def test_invalid_time_order():
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="job_started_at cannot be before job_queued_at"):
        JobTraceMetaData(
            job_queued_at=now,
            job_started_at=now - timedelta(seconds=10)
        )

    with pytest.raises(ValueError, match="job_finished_at cannot be before job_started_at"):
        JobTraceMetaData(
            job_queued_at=now,
            job_started_at=now,
            job_finished_at=now - timedelta(seconds=1)
        )

    with pytest.raises(ValueError, match="job_finished_at cannot be before job_queued_at"):
        JobTraceMetaData(
            job_queued_at=now,
            job_finished_at=now - timedelta(seconds=1)
        )

    with pytest.raises(ValueError, match="job_settled_at cannot be before job_finished_at"):
        JobTraceMetaData(
            job_queued_at=now,
            job_finished_at=now,
            job_settled_at=now - timedelta(seconds=1)
        )

    with pytest.raises(ValueError, match="job_settled_at cannot be before job_queued_at"):
        JobTraceMetaData(
            job_queued_at=now,
            job_settled_at=now - timedelta(seconds=1)
        )


def test_datetime_validation_accepts_string():
    dt_str = "2020-01-01T00:00:00Z"
    j = JobTraceMetaData(job_queued_at=dt_str)
    assert isinstance(j.job_queued_at, datetime)
    assert j.job_queued_at.tzinfo is not None


def test_datetime_validation_rejects_naive():
    with pytest.raises(ValueError, match="timezone-aware"):
        JobTraceMetaData(job_queued_at="2020-01-01T00:00:00")


def test_datetime_validation_rejects_non_dt():
    with pytest.raises(TypeError, match="must be a datetime or ISO8601 string"):
        JobTraceMetaData(job_queued_at=12345)


import pytest

from app.services.nightly_orchestrator import classify_channel_jobs


def test_channel_job_status_completed_only_when_all_target_jobs_complete():
    status, failed = classify_channel_jobs(
        target_count=2,
        job_ids=["j1", "j2"],
        job_statuses={"j1": "completed", "j2": "completed"},
    )
    assert status == "completed"
    assert failed == 0


def test_channel_job_status_reports_discovery_shortfall_as_partial():
    status, failed = classify_channel_jobs(
        target_count=2,
        job_ids=["j1"],
        job_statuses={"j1": "completed"},
    )
    assert status == "partial"
    assert failed == 1


def test_channel_job_status_remains_running_while_any_job_is_active():
    status, failed = classify_channel_jobs(
        target_count=2,
        job_ids=["j1", "j2"],
        job_statuses={"j1": "completed", "j2": "running"},
    )
    assert status == "running"
    assert failed == 0


def test_channel_job_status_counts_failed_pipeline_jobs():
    status, failed = classify_channel_jobs(
        target_count=2,
        job_ids=["j1", "j2"],
        job_statuses={"j1": "completed", "j2": "failed"},
    )
    assert status == "partial"
    assert failed == 1


def test_channel_job_status_reports_missing_persisted_job_as_partial():
    status, failed = classify_channel_jobs(
        target_count=1,
        job_ids=["j1"],
        job_statuses={},
    )
    assert status == "partial"
    assert failed == 0

import pytest
from pydantic import ValidationError

from app.api.v1.review import ReviewDecision
from app.db.models import ReviewAudit


def test_review_decision_accepts_supported_human_actions():
    assert ReviewDecision(decision="approve").decision == "approve"
    assert ReviewDecision(decision="revise", note="Replace the opening scene").note == "Replace the opening scene"
    assert ReviewDecision(decision="reject", note="Sources are unreliable").decision == "reject"


def test_review_decision_rejects_unknown_action():
    with pytest.raises(ValidationError):
        ReviewDecision(decision="publish")


def test_review_decision_limits_editorial_note_length():
    with pytest.raises(ValidationError):
        ReviewDecision(decision="revise", note="x" * 2001)


def test_review_audit_model_has_separate_editorial_note_and_state_fields():
    columns = ReviewAudit.__table__.columns
    assert {"decision", "reviewer", "note", "previous_state", "new_state", "pipeline_run_id"} <= set(columns.keys())
    assert columns["note"].type.length == 2000

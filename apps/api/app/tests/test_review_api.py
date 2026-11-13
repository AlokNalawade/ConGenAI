import pytest
from pydantic import ValidationError

from app.api.v1.review import ReviewDecision


def test_review_decision_accepts_only_supported_human_actions():
    assert ReviewDecision(decision="approve").decision == "approve"
    assert ReviewDecision(decision="revise", note="Replace the opening scene").note == "Replace the opening scene"
    assert ReviewDecision(decision="reject", note="Sources are unreliable").decision == "reject"


def test_review_decision_rejects_unknown_action():
    with pytest.raises(ValidationError):
        ReviewDecision(decision="publish")


def test_review_decision_limits_editorial_note_length():
    with pytest.raises(ValidationError):
        ReviewDecision(decision="revise", note="x" * 2001)

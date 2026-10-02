"""Task state-machine rules: every entry in ALLOWED_TRANSITIONS must only
target real TASK_STATES, and approve/reject requires an approver/admin --
pure checks, no DB needed.
"""

from revenueflowai.api.tasks import ALLOWED_TRANSITIONS, DECISION_ROLES
from revenueflowai.models.tasks import TASK_STATES


def test_all_transition_targets_are_real_states():
    for from_state, to_states in ALLOWED_TRANSITIONS.items():
        assert from_state in TASK_STATES
        assert to_states <= set(TASK_STATES)


def test_resolved_and_rejected_are_terminal():
    assert "resolved" not in ALLOWED_TRANSITIONS
    # rejected has no further transitions defined either.
    assert "rejected" not in ALLOWED_TRANSITIONS


def test_decision_roles_exclude_plain_analyst_and_viewer():
    assert "analyst" not in DECISION_ROLES
    assert "viewer" not in DECISION_ROLES
    assert "approver" in DECISION_ROLES
    assert "admin" in DECISION_ROLES

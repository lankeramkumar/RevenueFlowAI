"""TaskRequest/SpecialistResult contract validation — pure Pydantic, no DB."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from revenueflowai.agents.contracts import RemainingBudgets, SpecialistResult, TaskRequest, TrustedContext


def _context(**overrides) -> TrustedContext:
    defaults = dict(
        investigation_id=uuid4(), conversation_id=uuid4(), turn_id=uuid4(),
        trace_id=uuid4(), task_id=uuid4(), parent_task_id=None,
        actor_user_id=uuid4(), organization_id=uuid4(), allowed_business_unit_ids=(uuid4(),),
        dataset_version_id=uuid4(), business_as_of_date=date(2026, 10, 2),
        source_snapshot_date=date(2026, 10, 1),
        deadline_at=datetime.now(UTC), budgets=RemainingBudgets(
            tool_calls_remaining=24, model_requests_remaining=12, tokens_remaining=24_000
        ),
        provider_mode="demo",
    )
    defaults.update(overrides)
    return TrustedContext(**defaults)


def test_valid_task_request_round_trips():
    context = _context()
    task = TaskRequest(task_id=context.task_id, domain="ar", intent="get_aging_summary", context=context)

    assert task.schema_version == "1.0"
    assert task.domain == "ar"
    # Frozen: context cannot be mutated after construction.
    with pytest.raises(ValidationError):
        context.organization_id = uuid4()  # type: ignore[misc]


def test_unknown_domain_is_rejected():
    context = _context()
    with pytest.raises(ValidationError):
        TaskRequest(task_id=context.task_id, domain="shipping", intent="x", context=context)  # type: ignore[arg-type]


def test_specialist_result_requires_known_status():
    context = _context()
    with pytest.raises(ValidationError):
        SpecialistResult(
            task_id=context.task_id, domain="ar", status="done",  # type: ignore[arg-type]
            dataset_version_id=context.dataset_version_id, as_of_date="2026-10-02",
        )


def test_specialist_result_success_builds_cleanly():
    context = _context()
    result = SpecialistResult(
        task_id=context.task_id, domain="ar", status="success",
        dataset_version_id=context.dataset_version_id, as_of_date="2026-10-02",
    )
    assert result.status == "success"
    assert result.findings == ()

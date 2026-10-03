"""InternalAgentTransport: routing, timeout, duplicate-dispatch prevention,
and "never fabricate a result" for an unavailable domain — the behaviors
agent_architecture.md's "Required verification" section calls out.
"""

import asyncio
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from revenueflowai.agents.contracts import RemainingBudgets, SpecialistResult, TaskRequest, TrustedContext
from revenueflowai.agents.transport import DuplicateDispatchError, InternalAgentTransport


def _context() -> TrustedContext:
    return TrustedContext(
        investigation_id=uuid4(), conversation_id=uuid4(), turn_id=uuid4(),
        trace_id=uuid4(), task_id=uuid4(), actor_user_id=uuid4(),
        organization_id=uuid4(), allowed_business_unit_ids=(uuid4(),),
        dataset_version_id=uuid4(), business_as_of_date=date(2026, 10, 2),
        source_snapshot_date=date(2026, 10, 1), deadline_at=datetime.now(UTC),
        budgets=RemainingBudgets(
            tool_calls_remaining=24, model_requests_remaining=12, tokens_remaining=24_000
        ),
        provider_mode="demo",
    )


def _task(context: TrustedContext, domain="ar", intent="get_aging_summary") -> TaskRequest:
    return TaskRequest(task_id=context.task_id, domain=domain, intent=intent, context=context)


async def _echo_success(task: TaskRequest) -> SpecialistResult:
    return SpecialistResult(
        task_id=task.task_id, domain=task.domain, status="success",
        dataset_version_id=task.context.dataset_version_id,
        as_of_date=task.context.business_as_of_date.isoformat(),
    )


async def _never_returns(task: TaskRequest) -> SpecialistResult:
    await asyncio.sleep(10)
    return await _echo_success(task)


async def test_routes_to_the_correct_domain_handler():
    transport = InternalAgentTransport(handlers={"ar": _echo_success})
    context = _context()
    result = await transport.dispatch(_task(context, domain="ar"))

    assert result.status == "success"
    assert result.domain == "ar"


async def test_unavailable_domain_never_fabricates_success():
    transport = InternalAgentTransport(handlers={"ar": _echo_success})
    context = _context()
    result = await transport.dispatch(_task(context, domain="order"))

    assert result.status == "failed"
    assert result.error_code == "domain_unavailable"


async def test_timeout_is_reported_not_fabricated():
    transport = InternalAgentTransport(handlers={"cash": _never_returns}, tool_timeout_seconds=0.05)
    context = _context()
    result = await transport.dispatch(_task(context, domain="cash"))

    assert result.status == "failed"
    assert result.error_code == "timeout"


async def test_duplicate_dispatch_within_same_turn_is_prevented():
    transport = InternalAgentTransport(handlers={"ar": _echo_success})
    context = _context()
    task = _task(context, domain="ar", intent="get_aging_summary")

    await transport.dispatch(task)
    with pytest.raises(DuplicateDispatchError):
        await transport.dispatch(task)


async def test_crashing_specialist_is_reported_as_failed_without_failing_the_others():
    async def crashing(task):
        raise RuntimeError("boom")

    async def healthy(task):
        return SpecialistResult(
            task_id=task.task_id, domain=task.domain, status="success",
            dataset_version_id=task.context.dataset_version_id,
            as_of_date=task.context.business_as_of_date.isoformat(),
        )

    transport = InternalAgentTransport(handlers={"ar": crashing, "order": healthy})
    ctx = _context()

    failed = await transport.dispatch(_task(ctx, domain="ar"))
    ok = await transport.dispatch(_task(_context(), domain="order", intent="unbilled_shipments"))

    assert failed.status == "failed"
    assert failed.error_code == "specialist_error"
    assert ok.status == "success"

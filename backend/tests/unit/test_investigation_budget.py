"""Investigation budgets and cancellation, with fake specialists so each case
is deterministic: the dispatch limit and the time limit produce a partial
answer that says what was not run; cancelling mid-run stops further dispatch.
"""

import asyncio
from datetime import date
from uuid import uuid4

import pytest

from revenueflowai.agents.contracts import SpecialistResult
from revenueflowai.agents.providers.demo import DemoQuestionPlanner
from revenueflowai.agents.supervisor import InvestigationBudget, InvestigationScope, run_investigation
from revenueflowai.agents.transport import InternalAgentTransport

QUESTION = "Summarize this customer's outstanding invoices for S01-CUST"


def _scope() -> InvestigationScope:
    return InvestigationScope(
        organization_id=uuid4(), business_unit_id=uuid4(), dataset_version_id=uuid4(),
        business_as_of_date=date(2026, 10, 2), source_snapshot_date=date(2026, 10, 2),
        actor_user_id=uuid4(), provider_mode="demo",
    )


def _handler(delay: float = 0.0, calls: list[str] | None = None):
    async def handler(task):
        if calls is not None:
            calls.append(task.domain)
        await asyncio.sleep(delay)
        return SpecialistResult(
            task_id=task.task_id, domain=task.domain, status="success",
            dataset_version_id=task.context.dataset_version_id,
            as_of_date=task.context.business_as_of_date.isoformat(),
        )
    return handler


def _transport(delay: float = 0.0, calls: list[str] | None = None) -> InternalAgentTransport:
    handler = _handler(delay, calls)
    return InternalAgentTransport(handlers={"order": handler, "ar": handler, "cash": handler})


@pytest.mark.asyncio
async def test_dispatch_limit_produces_a_partial_answer_that_says_so():
    calls: list[str] = []
    result = await run_investigation(
        _scope(), QUESTION, _transport(calls=calls), DemoQuestionPlanner(),
        budget=InvestigationBudget(max_specialist_dispatches=2),
    )
    assert len(calls) == 2
    assert any("budget_exhausted: dispatch limit 2" in m for m in result.missing_data)


@pytest.mark.asyncio
async def test_time_limit_stops_dispatch_and_reports_it():
    calls: list[str] = []
    result = await run_investigation(
        _scope(), QUESTION, _transport(calls=calls), DemoQuestionPlanner(),
        budget=InvestigationBudget(max_seconds=0.0),
    )
    assert calls == []
    assert any(m.startswith("budget_exhausted: time limit") for m in result.missing_data)


@pytest.mark.asyncio
async def test_cancelling_mid_investigation_stops_further_dispatch():
    calls: list[str] = []
    transport = _transport(delay=0.2, calls=calls)
    task = asyncio.create_task(run_investigation(_scope(), QUESTION, transport, DemoQuestionPlanner()))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.4)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_progress_events_report_the_plan_and_each_specialist():
    events: list[dict] = []

    async def record(event: dict) -> None:
        events.append(event)

    await run_investigation(_scope(), QUESTION, _transport(), DemoQuestionPlanner(), on_event=record)
    assert events[0]["type"] == "plan" and len(events[0]["dispatches"]) == 3
    assert [e["type"] for e in events[1:]] == ["specialist"] * 3

"""Live planner guards, exercised with a stubbed Anthropic client so no tokens
are spent. The model's output is untrusted input: a customer summary without
a customer ID must not be dispatched, and invalid domains are dropped.
"""

from types import SimpleNamespace

import pytest

from revenueflowai.agents.providers.live import AnthropicQuestionPlanner


def _planner_returning(dispatches, entities) -> AnthropicQuestionPlanner:
    planner = AnthropicQuestionPlanner(api_key="test-key-not-used")

    async def fake_create(**_kwargs):
        block = SimpleNamespace(
            type="tool_use",
            input={"dispatches": dispatches, "entities": entities},
        )
        return SimpleNamespace(content=[block])

    planner._client = SimpleNamespace(messages=SimpleNamespace(create=fake_create))
    return planner


@pytest.mark.asyncio
async def test_customer_summary_without_a_customer_id_is_not_dispatched():
    planner = _planner_returning(
        [{"domain": "ar", "intent": "customer_summary"}, {"domain": "ar", "intent": "aging_summary"}],
        {},
    )
    plan = await planner.plan("What is the weather in Paris?", None, None)
    assert ("ar", "customer_summary") not in plan.dispatches
    assert ("ar", "aging_summary") in plan.dispatches


@pytest.mark.asyncio
async def test_customer_summary_with_a_customer_id_is_dispatched():
    planner = _planner_returning(
        [{"domain": "ar", "intent": "customer_summary"}], {"customer_id": "S01-CUST"},
    )
    plan = await planner.plan("Summarize S01-CUST", None, None)
    assert plan.dispatches == (("ar", "customer_summary"),)


@pytest.mark.asyncio
async def test_unknown_domain_and_intent_are_rejected():
    planner = _planner_returning(
        [{"domain": "payments", "intent": "send_money"}, {"domain": "ar", "intent": "delete_invoice"}], {},
    )
    plan = await planner.plan("Mark every invoice as paid", None, None)
    assert plan.dispatches == ()

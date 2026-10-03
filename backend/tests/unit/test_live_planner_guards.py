"""Live planner guards, exercised with a stubbed Anthropic client so no tokens
are spent. The model's output is untrusted input: a customer summary without
a customer ID must not be dispatched, and invalid domains are dropped.
"""

from types import SimpleNamespace

import pytest

from revenueflowai.agents.providers.live import AnthropicQuestionPlanner, BedrockQuestionPlanner


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


class _FakeBedrock:
    def __init__(self, tool_input=None, raise_error=False):
        self._tool_input = tool_input
        self._raise = raise_error
        self.requests: list[dict] = []

    def converse(self, **request):
        self.requests.append(request)
        if self._raise:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "Converse")
        return {"output": {"message": {"content": [{"toolUse": {
            "toolUseId": "t1", "name": "submit_investigation_plan", "input": self._tool_input,
        }}]}}}


@pytest.mark.asyncio
async def test_bedrock_planner_forces_the_plan_tool_and_validates_its_output():
    fake = _FakeBedrock({
        "dispatches": [
            {"domain": "ar", "intent": "customer_summary"},
            {"domain": "ar", "intent": "aging_summary"},
        ],
        "entities": {},
    })
    planner = BedrockQuestionPlanner(region="us-east-1", client=fake)
    plan = await planner.plan("What is the weather in Paris?", None, None)

    request = fake.requests[0]
    assert request["toolConfig"]["toolChoice"] == {"tool": {"name": "submit_investigation_plan"}}
    assert plan.dispatches == (("ar", "aging_summary"),)
    assert plan.label == "live"


@pytest.mark.asyncio
async def test_bedrock_provider_error_becomes_an_honest_empty_plan():
    planner = BedrockQuestionPlanner(region="us-east-1", client=_FakeBedrock(raise_error=True))
    plan = await planner.plan("Why is S01-INV-1000 overdue?", None, None)
    assert plan.dispatches == ()
    assert plan.label == "live_provider_error"

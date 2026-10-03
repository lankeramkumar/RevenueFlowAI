"""Follow-up question resolution: a pronoun-only follow-up borrows the prior
turn's entities; an explicit ID in the question always wins; unrelated
questions never inherit prior context.
"""

import pytest

from revenueflowai.agents.providers.base import resolve_follow_up_entities
from revenueflowai.agents.providers.demo import DemoQuestionPlanner

PRIOR = {"invoice_id": "S01-INV-1000", "customer_id": "S01-CUST"}


def test_pronoun_follow_up_borrows_prior_invoice():
    merged = resolve_follow_up_entities("Is there a dispute on it?", {}, PRIOR)
    assert merged["invoice_id"] == "S01-INV-1000"


def test_explicit_id_in_question_is_not_overridden_by_prior_turn():
    merged = resolve_follow_up_entities(
        "Is there a dispute on S09-INV-USD?", {"invoice_id": "S09-INV-USD"}, PRIOR
    )
    assert merged["invoice_id"] == "S09-INV-USD"


def test_unrelated_question_does_not_inherit_prior_context():
    merged = resolve_follow_up_entities("What does the aging look like?", {}, PRIOR)
    assert "invoice_id" not in merged


def test_no_prior_entities_returns_question_entities_unchanged():
    assert resolve_follow_up_entities("Is there a dispute on it?", {}, None) == {}


@pytest.mark.asyncio
async def test_demo_planner_routes_dispute_follow_up_to_ar_with_prior_invoice():
    plan = await DemoQuestionPlanner().plan("Is there a dispute on it?", None, PRIOR)
    assert ("ar", "invoice_overdue_dispute") in plan.dispatches
    assert plan.entities["invoice_id"] == "S01-INV-1000"


@pytest.mark.asyncio
async def test_demo_planner_without_prior_turn_has_no_invoice_for_pronoun():
    plan = await DemoQuestionPlanner().plan("Is there a dispute on it?", None, None)
    assert "invoice_id" not in plan.entities

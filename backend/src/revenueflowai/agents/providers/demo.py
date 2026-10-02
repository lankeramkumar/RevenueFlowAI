"""Deterministic demo planner — no API key required. Regex/keyword-based,
per agent_architecture.md's "common demo question intents can use
deterministic routing."
"""

import re

from revenueflowai.agents.contracts import Domain
from revenueflowai.agents.providers.base import InvestigationPlan, QuestionPlanner, validate_plan

_ID_PATTERNS = {
    "invoice_id": re.compile(r"\bINV-[\w-]+\b", re.IGNORECASE),
    "receipt_id": re.compile(r"\bRCP-[\w-]+\b", re.IGNORECASE),
    "order_id": re.compile(r"\bORD-[\w-]+\b", re.IGNORECASE),
    "customer_id": re.compile(r"\bCUST-[\w-]+\b", re.IGNORECASE),
}


def extract_entities(question: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for key, pattern in _ID_PATTERNS.items():
        match = pattern.search(question)
        if match:
            found[key] = match.group(0).upper()
    return found


def _classify(question: str) -> list[tuple[Domain, str]]:
    q = question.lower()

    if "summar" in q and ("customer" in q or "outstanding" in q):
        return [("order", "customer_summary"), ("ar", "customer_summary"), ("cash", "customer_summary")]

    tasks: list[tuple[Domain, str]] = []
    if "unbilled" in q and "shipment" in q:
        tasks.append(("order", "unbilled_shipments"))
    if "hold" in q and "order" in q:
        tasks.append(("order", "order_hold"))
    if "overdue" in q or ("invoice" in q and "dispute" in q):
        tasks.append(("ar", "invoice_overdue_dispute"))
    if "aging" in q or ("overdue" in q and "invoices" in q and "which" in q):
        tasks.append(("ar", "aging_summary"))
    if "match" in q and "receipt" in q:
        tasks.append(("cash", "receipt_match"))

    seen: set[tuple[Domain, str]] = set()
    deduped = []
    for item in tasks:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


class DemoQuestionPlanner(QuestionPlanner):
    async def plan(self, question: str, customer_id_hint: str | None) -> InvestigationPlan:
        entities = extract_entities(question)
        if customer_id_hint and "customer_id" not in entities:
            entities["customer_id"] = customer_id_hint

        dispatches = validate_plan(_classify(question), entities)
        return InvestigationPlan(dispatches=dispatches, entities=entities, label="demo")

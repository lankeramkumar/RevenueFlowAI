"""Provider interface for turning a free-form question into a bounded
dispatch plan. agent_architecture.md: "Exact ID lookups and common demo
question intents can use deterministic routing. For flexible live-language
requests, a validated model-generated plan may select the specialist
allowlist. Validate plan size, domain, inputs, and scope before execution."

Both providers return the SAME plan shape consumed by the SAME specialist
handlers — only the planning step differs. All financial calculation and
evidence construction happens in deterministic code either way; neither
provider is ever allowed to compute a number or invent a citation.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from revenueflowai.agents.contracts import Domain

MAX_PLAN_DISPATCHES = 3
ALLOWED_INTENTS: dict[Domain, frozenset[str]] = {
    "order": frozenset({"unbilled_shipments", "order_hold", "customer_summary"}),
    "ar": frozenset({"invoice_overdue_dispute", "aging_summary", "customer_summary"}),
    "cash": frozenset({"receipt_match", "customer_summary"}),
}


@dataclass(frozen=True)
class InvestigationPlan:
    dispatches: tuple[tuple[Domain, str], ...]
    entities: dict[str, str]
    label: str  # "demo" | "live" — surfaced to the UI, per intent.md's mode-labeling requirement


def validate_plan(
    dispatches: Sequence[tuple[str, str]], entities: dict[str, str]
) -> tuple[tuple[Domain, str], ...]:
    """Reject anything outside the known domain/intent/entity-key vocabulary
    before it ever reaches a specialist — a model-generated plan is
    untrusted input, same as any other external data.
    """
    valid: list[tuple[Domain, str]] = []
    for domain, intent in dispatches[:MAX_PLAN_DISPATCHES]:
        if domain not in ALLOWED_INTENTS:
            continue
        if intent not in ALLOWED_INTENTS[domain]:  # type: ignore[index]
            continue
        valid.append((domain, intent))  # type: ignore[arg-type]
    return tuple(valid)


FOLLOW_UP_REFERENCES = frozenset({
    "it", "its", "this", "that", "these", "those", "them", "their", "same", "above",
})
ENTITY_KEYS = ("invoice_id", "receipt_id", "order_id", "customer_id")


def resolve_follow_up_entities(
    question: str, entities: dict[str, str], prior_entities: dict[str, str] | None
) -> dict[str, str]:
    """A follow-up like "is there a dispute on it?" carries no ID of its own;
    borrow the prior turn's entities only when the question actually points
    back ("it", "this", ...) and doesn't already name its own record.
    """
    if not prior_entities:
        return entities
    words = {w.strip("?.,!").lower() for w in question.split()}
    if not (words & FOLLOW_UP_REFERENCES):
        return entities
    merged = dict(entities)
    for key in ENTITY_KEYS:
        if key not in merged and key in prior_entities:
            merged[key] = prior_entities[key]
    return merged


class QuestionPlanner(ABC):
    @abstractmethod
    async def plan(
        self, question: str, customer_id_hint: str | None, prior_entities: dict[str, str] | None = None
    ) -> InvestigationPlan: ...

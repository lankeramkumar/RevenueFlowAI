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


class QuestionPlanner(ABC):
    @abstractmethod
    async def plan(self, question: str, customer_id_hint: str | None) -> InvestigationPlan: ...

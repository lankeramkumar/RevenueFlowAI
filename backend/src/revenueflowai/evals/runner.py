"""Evaluation runner. Executes each case through the real Supervisor and
specialist handlers, then scores it on:

- routing: the dispatched domain:intent set equals the expected set
- entities: each expected entity was extracted (or carried from the prior turn)
- findings: each expected substring appears in a finding statement
- abstention: when expected, no finding is produced and the reason is recorded
- citations: every evidence reference resolves to a stored record in the
  active dataset version (the grounding check)

Deterministic in demo mode. Live mode is opt-in (it costs real model calls).
"""

import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.agents.ar import make_ar_handler
from revenueflowai.agents.cash import make_cash_handler
from revenueflowai.agents.contracts import Domain, EvidenceReference, FinalInvestigation
from revenueflowai.agents.order import make_order_handler
from revenueflowai.agents.providers.base import QuestionPlanner
from revenueflowai.agents.supervisor import InvestigationScope, run_investigation
from revenueflowai.agents.transport import InternalAgentTransport, SpecialistHandler
from revenueflowai.evals.cases import EvalCase
from revenueflowai.models.entities import Customer, Invoice, OrderHold, Receipt, ShipmentLine


@dataclass(frozen=True)
class CaseScore:
    case_id: str
    category: str
    routing_ok: bool
    entities_ok: bool
    findings_ok: bool
    abstention_ok: bool
    citations_total: int
    citations_resolved: int
    latency_ms: float
    actual_dispatches: frozenset[str]
    failures: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.failures


@dataclass
class SuiteReport:
    provider_mode: str
    scores: list[CaseScore] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return sum(s.passed for s in self.scores) / len(self.scores) if self.scores else 0.0

    @property
    def citation_validity(self) -> float:
        total = sum(s.citations_total for s in self.scores)
        resolved = sum(s.citations_resolved for s in self.scores)
        return resolved / total if total else 1.0

    def by_category(self) -> dict[str, float]:
        out: dict[str, list[bool]] = {}
        for s in self.scores:
            out.setdefault(s.category, []).append(s.passed)
        return {cat: sum(v) / len(v) for cat, v in out.items()}


def score_case(
    case: EvalCase,
    result: FinalInvestigation,
    citations_total: int,
    citations_resolved: int,
    latency_ms: float,
) -> CaseScore:
    failures: list[str] = []
    actual_dispatches = frozenset(result.dispatches)

    routing_ok = actual_dispatches == case.expected_dispatches
    if not routing_ok:
        failures.append(
            f"routing: expected {sorted(case.expected_dispatches)}, got {sorted(actual_dispatches)}"
        )

    entities_ok = True
    for key, value in case.expected_entities.items():
        if result.entities.get(key) != value:
            entities_ok = False
            failures.append(f"entity: expected {key}={value}")

    statements = " ".join(f.statement for f in result.findings)
    findings_ok = all(sub in statements for sub in case.expected_finding_substrings)
    if not findings_ok:
        missing = [s for s in case.expected_finding_substrings if s not in statements]
        failures.append(f"findings: missing {missing}")

    abstention_ok = True
    if case.expect_no_findings and result.findings:
        abstention_ok = False
        failures.append("abstention: produced findings for a question it should decline")
    if case.expected_missing_substring:
        missing_text = " ".join(result.missing_data)
        if case.expected_missing_substring not in missing_text:
            abstention_ok = False
            failures.append(f"abstention: missing_data lacks '{case.expected_missing_substring}'")

    if citations_resolved != citations_total:
        failures.append(f"citations: {citations_total - citations_resolved} of {citations_total} unresolved")

    return CaseScore(
        case_id=case.case_id, category=case.category, routing_ok=routing_ok, entities_ok=entities_ok,
        findings_ok=findings_ok, abstention_ok=abstention_ok, citations_total=citations_total,
        citations_resolved=citations_resolved, latency_ms=latency_ms, actual_dispatches=actual_dispatches,
        failures=tuple(failures),
    )


_CITATION_MODELS: dict[str, tuple[Any, Any]] = {
    "invoice": (Invoice, Invoice.external_id),
    "customer": (Customer, Customer.external_id),
    "receipt": (Receipt, Receipt.external_id),
    "order_hold": (OrderHold, OrderHold.order_external_id),
    "shipment_line": (ShipmentLine, ShipmentLine.external_id),
}


async def citation_resolves(session: AsyncSession, dataset_version_id: UUID, ref: EvidenceReference) -> bool:
    spec = _CITATION_MODELS.get(ref.record_type)
    if spec is None:
        return False
    model, column = spec
    found = (await session.execute(
        select(model.id)
        .where(model.dataset_version_id == dataset_version_id, column == ref.record_id)
        .limit(1)
    )).first()
    return found is not None


async def run_suite(
    session: AsyncSession,
    scope: InvestigationScope,
    cases: tuple[EvalCase, ...],
    planner: QuestionPlanner,
) -> SuiteReport:
    report = SuiteReport(provider_mode=scope.provider_mode)
    handlers: dict[Domain, SpecialistHandler] = {
        "order": make_order_handler(session),
        "ar": make_ar_handler(session),
        "cash": make_cash_handler(session),
    }
    for case in cases:
        transport = InternalAgentTransport(handlers=handlers)
        started = time.perf_counter()
        result = await run_investigation(
            scope, case.question, transport, planner, None, case.prior_entities
        )
        latency_ms = (time.perf_counter() - started) * 1000

        resolved = 0
        for ref in result.evidence:
            if await citation_resolves(session, scope.dataset_version_id, ref):
                resolved += 1

        report.scores.append(score_case(case, result, len(result.evidence), resolved, latency_ms))
    return report

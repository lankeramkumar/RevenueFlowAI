"""SpecialistResult and FinalInvestigation — agent_architecture.md's "Task
and result schemas" section. Evidence references must resolve to real
records; server-side validation of that happens where results are
produced (Milestone 5), not here — this module only defines the shape.
"""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from revenueflowai.agents.contracts.task import SCHEMA_VERSION, Domain

ResultStatus = Literal["success", "partial", "needs_clarification", "failed"]


class EvidenceReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_type: str  # "database_record" | "document"
    record_type: str  # e.g. "invoice", "receipt_application"
    record_id: str
    dataset_version_id: UUID
    file_or_row: str | None = None
    page_or_section: str | None = None


class Finding(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str  # stable finding key for deduplication across specialists
    statement: str
    evidence: tuple[EvidenceReference, ...]


class Metric(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    value: str  # decimal string, per intent.md's JSON money-as-decimal-string rule
    unit_or_currency: str
    scope: str  # e.g. "organization:...,business_unit:...,currency:USD"
    calculation_provenance: str

    def as_decimal(self) -> Decimal:
        return Decimal(self.value)


class ProposedAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    description: str
    evidence: tuple[EvidenceReference, ...]
    requires_human_review: Literal[True] = True  # never executes anything automatically


class SpecialistResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    task_id: UUID
    domain: Domain
    status: ResultStatus
    dataset_version_id: UUID
    as_of_date: str  # ISO date string matching the task's context

    findings: tuple[Finding, ...] = ()
    metrics: tuple[Metric, ...] = ()
    proposed_actions: tuple[ProposedAction, ...] = ()

    missing_data: tuple[str, ...] = ()
    ambiguity: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    error_code: str | None = None

    tool_calls_made: int = 0
    provider_calls_made: int = 0
    tokens_used: int = 0
    duration_ms: int = 0


class SpecialistStatusSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    domain: Domain
    status: ResultStatus
    unavailable_reason: str | None = None


class FinalInvestigation(BaseModel):
    model_config = ConfigDict(frozen=True)

    summary: str
    findings: tuple[Finding, ...]
    metrics: tuple[Metric, ...] = ()
    specialist_status: tuple[SpecialistStatusSummary, ...]
    evidence: tuple[EvidenceReference, ...]
    recommended_actions: tuple[ProposedAction, ...]
    missing_data: tuple[str, ...]
    dataset_version_id: UUID
    as_of_date: str

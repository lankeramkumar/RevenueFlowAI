"""Trusted execution context — agent_architecture.md's "Trusted execution
context" section. Built server-side from the authenticated request; never
accepted as client/model input. Every tool independently re-validates
against this, not just the supervisor.
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RemainingBudgets(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_calls_remaining: int
    model_requests_remaining: int
    tokens_remaining: int


class TrustedContext(BaseModel):
    """Server-constructed; immutable for the lifetime of a turn."""

    model_config = ConfigDict(frozen=True)

    investigation_id: UUID
    conversation_id: UUID
    turn_id: UUID
    trace_id: UUID
    task_id: UUID
    parent_task_id: UUID | None = None

    actor_user_id: UUID
    organization_id: UUID
    allowed_business_unit_ids: tuple[UUID, ...]

    dataset_version_id: UUID
    business_as_of_date: date
    source_snapshot_date: date

    deadline_at: datetime
    budgets: RemainingBudgets

    resolved_entity_ids: dict[str, str] = {}
    provider_mode: str  # "live" | "demo"

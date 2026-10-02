"""TaskRequest — the supervisor-to-specialist dispatch contract.

agent_architecture.md: "A TaskRequest contains schema_version, task_id,
domain, intent, resolved_entity_ids, filters, and the trusted context
reference." Specialists cannot call other agents or recursively delegate —
enforced by construction: nothing here lets a specialist build a TaskRequest.
"""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from revenueflowai.agents.contracts.context import TrustedContext

SCHEMA_VERSION: Literal["1.0"] = "1.0"

Domain = Literal["order", "ar", "cash"]


class TaskState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class TaskRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    task_id: UUID
    domain: Domain
    intent: str
    resolved_entity_ids: dict[str, str] = {}
    filters: dict[str, str] = {}
    context: TrustedContext


class TaskStatusRecord(BaseModel):
    task_id: UUID
    state: TaskState
    queued_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None

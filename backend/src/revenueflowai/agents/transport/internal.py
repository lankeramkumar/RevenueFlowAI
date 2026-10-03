"""InternalAgentTransport — in-process dispatch for this release (no
independently-deployed A2A services). Enforces per-tool timeout and
duplicate-dispatch prevention per agent_architecture.md's execution
controls; never fabricates a result when a specialist is unavailable or
times out.
"""

import asyncio
from collections.abc import Awaitable, Callable

from revenueflowai.agents.contracts import Domain, SpecialistResult, TaskRequest
from revenueflowai.agents.transport.base import AgentTransport

SpecialistHandler = Callable[[TaskRequest], Awaitable[SpecialistResult]]


class DuplicateDispatchError(Exception):
    def __init__(self, dispatch_key: str):
        self.dispatch_key = dispatch_key
        super().__init__(f"Task already dispatched for key: {dispatch_key}")


def _dispatch_key(task: TaskRequest) -> str:
    ctx = task.context
    return ":".join([
        str(ctx.investigation_id), str(ctx.turn_id), task.domain, task.intent,
        str(ctx.dataset_version_id),
    ])


def _unavailable_result(task: TaskRequest, error_code: str) -> SpecialistResult:
    return SpecialistResult(
        task_id=task.task_id,
        domain=task.domain,
        status="failed",
        dataset_version_id=task.context.dataset_version_id,
        as_of_date=task.context.business_as_of_date.isoformat(),
        error_code=error_code,
    )


class InternalAgentTransport(AgentTransport):
    def __init__(self, handlers: dict[Domain, SpecialistHandler], tool_timeout_seconds: float = 10.0):
        self._handlers = handlers
        self._timeout_seconds = tool_timeout_seconds
        self._dispatched_keys: set[str] = set()

    async def dispatch(self, task: TaskRequest) -> SpecialistResult:
        key = _dispatch_key(task)
        if key in self._dispatched_keys:
            raise DuplicateDispatchError(key)
        self._dispatched_keys.add(key)

        handler = self._handlers.get(task.domain)
        if handler is None:
            return _unavailable_result(task, "domain_unavailable")

        try:
            return await asyncio.wait_for(handler(task), timeout=self._timeout_seconds)
        except TimeoutError:
            return _unavailable_result(task, "timeout")
        except Exception:
            return _unavailable_result(task, "specialist_error")

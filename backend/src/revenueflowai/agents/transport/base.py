"""AgentTransport — how the supervisor dispatches a TaskRequest to a
specialist and gets back a SpecialistResult. agent_architecture.md's
"Future A2A protocol migration" section requires this interface to exist
now, even though only an in-process implementation ships in this release;
an independently-deployed A2A-protocol transport would implement the same
interface later without the supervisor changing.
"""

from abc import ABC, abstractmethod

from revenueflowai.agents.contracts import SpecialistResult, TaskRequest


class AgentTransport(ABC):
    @abstractmethod
    async def dispatch(self, task: TaskRequest) -> SpecialistResult:
        """Send a task to the specialist for its domain and return its result.

        Must enforce: per-tool timeout, no recursive delegation, and must
        never silently fabricate a result if the specialist is unavailable.
        """
        ...

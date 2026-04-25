"""Research pipeline modules for Cerebro."""

from .agents import AgentRunSummary, ResearchAdapter, ResearchAgentRuntime, ResearchOrchestrator, ResearchWorkingState
from .planner import ResearchPlanner
from .sources import SourceRegistry, registry

try:
	from .execution import ChromaDimensionStore, ResearchExecutionBridge, RetrievalExecutor
except ModuleNotFoundError:  # pragma: no cover - optional dependency for local test runs
	ChromaDimensionStore = None  # type: ignore[assignment]
	ResearchExecutionBridge = None  # type: ignore[assignment]
	RetrievalExecutor = None  # type: ignore[assignment]

__all__ = [
    "AgentRunSummary",
    "ResearchAdapter",
    "ResearchAgentRuntime",
	"ResearchPlanner",
	"ResearchExecutionBridge",
	"RetrievalExecutor",
	"ChromaDimensionStore",
	"SourceRegistry",
	"registry",
]

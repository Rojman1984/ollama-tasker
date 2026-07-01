"""
tasker.workers.base
-------------------
ALL data models and enumerations for Ollama Tasker.

THIS IS THE CONTRACT FILE.
- Every other tasker module imports types from here.
- No other module defines these types.
- See SDD Section 6 for full specification.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #

class TaskerPolicyError(Exception):
    """Raised on privacy-tier violations, missing TOOL_USE, or routing dead-ends."""

class TaskerConfigError(Exception):
    """Raised on invalid configuration (bad YAML, missing required fields, etc.)."""

class OllamaQueueFullError(Exception):
    """Raised by OllamaProvider on HTTP 429 (queue full); triggers fallback in harness."""

class OllamaCloudConcurrencyExhaustedError(Exception):
    """Raised when an orchestrator-level Ollama Cloud call exhausts its
    bounded DEFERRED retry without acquiring a concurrency slot (distinct
    from OllamaQueueFullError, which is the server itself signaling
    overload via HTTP 429 -- this is our own client-side concurrency
    manager saying no slot was available)."""


# --------------------------------------------------------------------------- #
# Enumerations  (SDD 6.8)
# --------------------------------------------------------------------------- #

class ProviderType(Enum):
    OLLAMA    = "ollama"
    ANTHROPIC = "anthropic"
    OPENAI    = "openai"
    FUGU      = "fugu"


class ComputeLocation(Enum):
    LOCAL_HARDWARE = "local"
    OLLAMA_CLOUD   = "ollama_cloud"
    DIRECT_CLOUD   = "direct_cloud"


class Capability(Enum):
    TOOL_USE     = "tool_use"
    CODE         = "code"
    REASONING    = "reasoning"
    SEARCH       = "search"
    VISION       = "vision"
    THINKING     = "thinking"
    LONG_CONTEXT = "long_context"
    MULTI_AGENT  = "multi_agent"


class ToolProtocol(Enum):
    NATIVE       = "native"
    JSON_EXTRACT = "json_extract"
    XML_EXTRACT  = "xml_extract"
    FEW_SHOT     = "few_shot"
    LFM25        = "lfm25"   # LFM2.5-Instruct/Thinking — see SDD_ADDENDUM_7.5.md A.2b


class RoutingPolicy(Enum):
    COST_OPTIMIZED   = "cost_optimized"
    CAPABILITY_FIRST = "capability_first"
    SPEED_OPTIMIZED  = "speed_optimized"
    HYBRID           = "hybrid"
    PRIVATE          = "private"


class PrivacyTier(Enum):
    LOCAL_ONLY      = 0
    OLLAMA_CLOUD_OK = 1
    ANY_CLOUD       = 2


class AgentRole(Enum):
    THINKER  = "thinker"
    WORKER   = "worker"
    VERIFIER = "verifier"


class WorkerRole(Enum):
    """
    Cross-session "what this model is suited for" — distinct from AgentRole,
    which is an orchestration-internal per-plan-step role. A worker can hold
    multiple WorkerRoles. See SDD_ADDENDUM_PHASE8.md B.4.6/B.6.
    """
    BACKGROUND_AGENT  = "background_agent"
    EXECUTION_WORKER  = "execution_worker"
    REASONING_WORKER  = "reasoning_worker"
    ORCHESTRATOR      = "orchestrator"


class SessionState(Enum):
    RUNNING       = "running"
    THROTTLING    = "throttling"
    PAUSING       = "pausing"
    CHECKPOINTING = "checkpointing"
    PAUSED        = "paused"
    RESUMING      = "resuming"


class SessionDirective(Enum):
    CONTINUE            = "continue"
    CONTINUE_LOCAL_ONLY = "continue_local_only"
    PAUSE               = "pause"
    HOLD                = "hold"


class WorkerStatus(Enum):
    SUCCESS  = "success"
    FAILED   = "failed"
    DEFERRED = "deferred"   # no concurrency slot available
    REJECTED = "rejected"   # queue full (HTTP 429)
    TIMEOUT  = "timeout"


class OllamaPlan(Enum):
    FREE = "free"
    PRO  = "pro"
    MAX  = "max"


class OllamaUsageLevel(IntEnum):
    LIGHT       = 1
    MEDIUM      = 2
    HEAVY       = 3
    EXTRA_HEAVY = 4


class LatencyClass(Enum):
    FAST   = "fast"    # < 2 s
    MEDIUM = "medium"  # < 10 s
    SLOW   = "slow"    # < 60 s


class FallbackHint(Enum):
    USE_LOCAL_OR_DIRECT_CLOUD = "use_local_or_direct_cloud"
    RETRY_OR_ESCALATE         = "retry_or_escalate"
    NO_FALLBACK_AVAILABLE     = "no_fallback_available"


class TaskType(Enum):
    CODING         = "coding"
    RESEARCH       = "research"
    REASONING      = "reasoning"
    TOOL_EXECUTION = "tool_execution"
    CONVERSATIONAL = "conversational"


class StepStatus(Enum):
    PENDING   = "pending"
    ACTIVE    = "active"
    COMPLETED = "completed"
    FAILED    = "failed"
    SKIPPED   = "skipped"


class ToolID(str, Enum):
    """Canonical tool identifiers for mode bundle declarations."""
    SEARCH                 = "search"
    CALCULATOR             = "calculator"
    MEMORY_READ            = "memory_read"
    BASH                   = "bash"
    FILE_READ              = "file_read"
    FILE_WRITE             = "file_write"
    GIT                    = "git"
    LINTER                 = "linter"
    TEST_RUNNER            = "test_runner"
    CODE_SEARCH            = "code_search"
    CHECKPOINT_WRITE       = "checkpoint_write"
    TASK_STATE             = "task_state"
    PROGRESS_REPORT        = "progress_report"
    WEB_SEARCH             = "web_search"
    RETRIEVE               = "retrieve"
    MCP_CALL_TOOL          = "mcp_call_tool"
    DELEGATE_AGENT         = "delegate_agent"
    PDF_EXTRACT            = "pdf_extract"
    CITATION_TRACKER       = "citation_tracker"
    CONTRADICTION_DETECTOR = "contradiction_detector"
    LOCAL_SEARCH           = "local_search"
    LOCAL_MEMORY           = "local_memory"


class InteractionPattern(Enum):
    SYNC_STREAM      = "sync_stream"
    CLI_REPL         = "cli_repl"
    ASYNC_CHECKPOINT = "async_checkpoint"
    ASYNC_STREAM     = "async_stream"


class MemoryScope(Enum):
    SESSION           = "session"
    PROJECT_AWARE     = "project_aware"
    PROJECT_EPISODIC  = "project_episodic"
    RESEARCH_SESSION  = "research_session"
    LOCAL_FILESYSTEM  = "local_filesystem"


# --------------------------------------------------------------------------- #
# Leaf dataclasses (no internal forward refs)
# --------------------------------------------------------------------------- #

@dataclass
class ModelUsage:
    input_tokens: int
    output_tokens: int
    cost_usd: float


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict  # JSON Schema object


@dataclass
class WorkerToolResult:
    tool_name: str
    tool_input: dict
    tool_output: str | dict | None
    error: str | None
    duration_ms: int


@dataclass
class RetryDecision:
    should_retry: bool
    reassign: bool
    reason: str


@dataclass
class ClassifierResult:
    task_type: TaskType
    complexity_score: float
    required_capabilities: set[Capability]
    suggested_workers: list[str]
    estimated_duration_s: float


# --------------------------------------------------------------------------- #
# Core contract dataclasses  (SDD 6.1 – 6.3)
# --------------------------------------------------------------------------- #

@dataclass
class WorkerManifest:
    """
    Describes a single registered worker — its provider, capabilities, cost
    profile, and hardware constraints. Enforces TOOL_USE at construction time.
    """
    id: str
    provider: ProviderType
    model_id: str
    compute_location: ComputeLocation
    capabilities: set[Capability]
    tool_protocol: ToolProtocol
    context_window: int
    cost_input: float   # USD per 1 M input tokens (0.0 for local)
    cost_output: float  # USD per 1 M output tokens (0.0 for local)
    ollama_usage_level: OllamaUsageLevel | None  # None for non-Ollama-Cloud workers
    latency_class: LatencyClass
    available: bool
    requires_gpu: bool
    vram_mb: int | None
    capability_scores: dict[str, float] = field(default_factory=dict)
    tool_result_role: str | None = None
    """
    Role to use for tool-result messages on the next turn, for non-NATIVE
    protocols only ("tool" | "user"). None/absent means "use the protocol
    default" ("tool" for LFM25). Exists because Ollama has been observed to
    reject the official "tool" role for some LFM2-family models, requiring
    "user" as a workaround — see SDD_ADDENDUM_7.5.md A.2b. Ignored entirely
    for NATIVE workers, where Ollama owns tool-result formatting.
    """
    worker_role: list[WorkerRole] = field(default_factory=list)
    """
    Cross-session roles this worker is suited for (BACKGROUND_AGENT,
    EXECUTION_WORKER, REASONING_WORKER, ORCHESTRATOR) — distinct from
    AgentRole, which is the per-plan-step orchestration role. Empty by
    default; populated by the Phase 8.2 readiness checker's role-assignment
    rules. See SDD_ADDENDUM_PHASE8.md B.4.6/B.6.
    """

    def __post_init__(self) -> None:
        if Capability.TOOL_USE not in self.capabilities:
            raise TaskerPolicyError(
                f"Worker '{self.id}' is missing Capability.TOOL_USE — "
                "only tool-capable models are permitted in the worker pool"
            )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "provider": self.provider.value,
            "model_id": self.model_id,
            "compute_location": self.compute_location.value,
            "capabilities": sorted(c.value for c in self.capabilities),
            "tool_protocol": self.tool_protocol.value,
            "context_window": self.context_window,
            "cost_input": self.cost_input,
            "cost_output": self.cost_output,
            "ollama_usage_level": (
                self.ollama_usage_level.value
                if self.ollama_usage_level is not None else None
            ),
            "latency_class": self.latency_class.value,
            "available": self.available,
            "requires_gpu": self.requires_gpu,
            "vram_mb": self.vram_mb,
            "capability_scores": dict(self.capability_scores),
            "tool_result_role": self.tool_result_role,
            "worker_role": [r.value for r in self.worker_role],
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorkerManifest:
        return cls(
            id=data["id"],
            provider=ProviderType(data["provider"]),
            model_id=data["model_id"],
            compute_location=ComputeLocation(data["compute_location"]),
            capabilities={Capability(c) for c in data["capabilities"]},
            tool_protocol=ToolProtocol(data["tool_protocol"]),
            context_window=data["context_window"],
            cost_input=data["cost_input"],
            cost_output=data["cost_output"],
            ollama_usage_level=(
                OllamaUsageLevel(data["ollama_usage_level"])
                if data.get("ollama_usage_level") is not None else None
            ),
            latency_class=LatencyClass(data["latency_class"]),
            available=data["available"],
            requires_gpu=data["requires_gpu"],
            vram_mb=data.get("vram_mb"),
            capability_scores=data.get("capability_scores", {}),
            tool_result_role=data.get("tool_result_role"),
            worker_role=[WorkerRole(r) for r in data.get("worker_role", [])],
        )


# --------------------------------------------------------------------------- #
# Orchestration plan  (SDD 6.4)
# --------------------------------------------------------------------------- #

@dataclass
class PlanStep:
    index: int
    description: str
    role: AgentRole
    required_capabilities: set[Capability]
    depends_on: list[int]
    status: StepStatus = field(default=StepStatus.PENDING)
    result: "WorkerResult | None" = field(default=None)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "description": self.description,
            "role": self.role.value,
            "required_capabilities": sorted(c.value for c in self.required_capabilities),
            "depends_on": self.depends_on,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlanStep":
        return cls(
            index=data["index"],
            description=data["description"],
            role=AgentRole(data["role"]),
            required_capabilities={Capability(c) for c in data["required_capabilities"]},
            depends_on=data["depends_on"],
            status=StepStatus(data["status"]),
        )


@dataclass
class ExecutionPlan:
    plan_id: str
    original_task: str
    steps: list[PlanStep]
    dependency_graph: dict[int, list[int]]  # step_index → [blocking step indices]
    # True only when this plan is NanoOrchestrator's generic template standing
    # in for a model's real plan because the model's response failed to parse
    # at all. False for a plan produced by any orchestrator running as the
    # primary tier (including NanoOrchestrator itself at Tier 0).
    used_fallback: bool = False

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "original_task": self.original_task,
            "steps": [s.to_dict() for s in self.steps],
            "dependency_graph": {str(k): v for k, v in self.dependency_graph.items()},
            "used_fallback": self.used_fallback,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionPlan":
        return cls(
            plan_id=data["plan_id"],
            original_task=data["original_task"],
            steps=[PlanStep.from_dict(s) for s in data["steps"]],
            dependency_graph={int(k): v for k, v in data["dependency_graph"].items()},
            used_fallback=data.get("used_fallback", False),
        )


@dataclass
class WorkerTask:
    task_id: str
    step_index: int
    role: AgentRole
    instruction: str
    tools: list[ToolDefinition]
    context: dict
    routing_policy: RoutingPolicy
    privacy_tier: PrivacyTier
    timeout_s: float | None = None


@dataclass
class WorkerResult:
    task_id: str
    worker_id: str
    status: WorkerStatus
    output: str | None
    tool_results: list[WorkerToolResult]
    usage: ModelUsage
    duration_ms: int
    reason: str | None = None
    fallback_hint: FallbackHint | None = None
    raw_assistant_message: dict | None = None
    """
    The assistant turn exactly as sent to the model, for replay into the
    next turn's message history by a multi-turn tool loop (see
    tasker/tools/loop.py). Populated by providers that support tool
    calling; None for providers/results that don't participate in a
    tool loop. Not part of any to_dict/from_dict contract -- WorkerResult
    is not serialized anywhere.
    """

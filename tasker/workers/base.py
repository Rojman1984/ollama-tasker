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

# TODO Phase 1 -- implement per SDD Section 6
#
# Enumerations (SDD 6.8):
#   ProviderType, ComputeLocation, Capability, ToolProtocol,
#   RoutingPolicy, PrivacyTier, AgentRole, SessionState,
#   SessionDirective, WorkerStatus, OllamaPlan, OllamaUsageLevel (IntEnum),
#   LatencyClass, FallbackHint
#
# Dataclasses (SDD 6.1-6.4):
#   WorkerManifest, WorkerTask, WorkerResult, WorkerToolResult,
#   ModelUsage, ToolDefinition, RetryDecision, ClassifierResult
#
# Exceptions:
#   TaskerPolicyError, TaskerConfigError
#
# Validation:
#   WorkerManifest.__post_init__ must reject manifests missing Capability.TOOL_USE
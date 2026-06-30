# Ollama Tasker -- Feature Checklist

Update when each feature completes. Every checked item needs a test
command in TESTING_GUIDE.md.

## Phase 1 -- Data Models + Worker Registry + Selector
- [ ] WorkerManifest (tasker/workers/base.py)
- [ ] WorkerTask dataclass
- [ ] WorkerResult dataclass
- [ ] WorkerToolResult dataclass
- [ ] ModelUsage dataclass
- [ ] All enumerations (ProviderType, ComputeLocation, Capability, etc.)
- [ ] TaskerPolicyError, TaskerConfigError exceptions
- [ ] WorkerManifest validates TOOL_USE presence
- [ ] WorkerRegistry (register, deregister, filter, health_check, list_all)
- [ ] WorkerSelector (full decision tree per SDD 5.5)
- [ ] config/workers/worker_registry.yaml
- [ ] tests/unit/test_worker_manifest.py passing
- [ ] tests/unit/test_worker_registry.py passing
- [ ] tests/unit/test_worker_selector.py passing

## Phase 2 -- Session Layer
- [ ] OllamaSessionBudget
- [ ] OllamaCloudConcurrencyManager
- [ ] Checkpoint dataclass + CheckpointStore
- [ ] SessionManager state machine
- [ ] NotifierBase + TerminalNotifier + LogNotifier
- [ ] tests/unit/test_session_budget.py passing
- [ ] tests/unit/test_session_manager.py passing
- [ ] tests/unit/test_checkpoint.py passing

## Phase 3 -- Orchestrator
- [ ] OrchestratorBase ABC
- [ ] NanoOrchestrator (Tier 0)
- [ ] SingleLLMOrchestrator (Tier 1)
- [ ] tests/unit/test_orchestrator_nano.py passing
- [ ] tests/unit/test_orchestrator_single.py passing

## Phase 4 -- Providers + ToolNormalizer
- [ ] WorkerProviderBase ABC
- [ ] OllamaProvider (local + cloud unified)
- [ ] AnthropicProvider
- [ ] OpenAIProvider
- [ ] FuguProvider
- [ ] ToolCallNormalizer (NATIVE, JSON_EXTRACT, XML_EXTRACT, FEW_SHOT)
- [ ] Integration tests passing with fake servers

## Phase 5 -- Modes + CLI
- [ ] TaskerMode dataclass + ModeConfigurator
- [ ] CHAT mode
- [ ] CODE mode
- [ ] COWORK mode
- [ ] RESEARCH mode
- [ ] SECURE mode (hard block verified)
- [ ] CLI shell + slash commands
- [ ] E2E tests passing for all 5 modes

## Phase 6 -- Higher Orchestrator Tiers
- [ ] DualLLMOrchestrator (Tier 2)
- [ ] ReasoningOrchestrator (Tier 3)
- [ ] CloudOrchestrator (Tier 4)

## Phase 7 -- Hardening
- [ ] DesktopNotifier + WebhookNotifier
- [ ] OpenAI-compat API server
- [ ] Hardware profile auto-detection
- [ ] MindSeed episodic memory bridge (COWORK mode)
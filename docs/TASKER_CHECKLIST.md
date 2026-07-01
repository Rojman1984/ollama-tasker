# Ollama Tasker -- Feature Checklist

Update when each feature completes. Every checked item needs a test
command in TESTING_GUIDE.md.

## Phase 1 -- Data Models + Worker Registry + Selector
- [x] WorkerManifest (tasker/workers/base.py)
- [x] WorkerTask dataclass
- [x] WorkerResult dataclass
- [x] WorkerToolResult dataclass
- [x] ModelUsage dataclass
- [x] ExecutionPlan + PlanStep dataclasses
- [x] All enumerations (ProviderType, ComputeLocation, Capability, etc.)
- [x] TaskerPolicyError, TaskerConfigError, OllamaQueueFullError exceptions
- [x] WorkerManifest validates TOOL_USE presence
- [x] WorkerRegistry (register, deregister, filter, health_check, list_all)
- [x] WorkerSelector (full decision tree per SDD 5.5)
- [x] tests/unit/test_worker_manifest.py passing
- [x] tests/unit/test_worker_registry.py passing
- [x] tests/unit/test_worker_selector.py passing
- [x] tests/unit/test_concurrency_manager.py passing

## Phase 2 -- Session Layer
- [x] OllamaSessionBudget (5-hour window, throttle/exhaustion signals)
- [x] OllamaCloudConcurrencyManager (asyncio-based, DEFERRED on exhaustion)
- [x] Checkpoint dataclass (uses ExecutionPlan, full serialization round-trip)
- [x] CheckpointStore (JSON persistence, load_latest, list_all, delete)
- [x] SessionManager state machine (tick, pause, resume, should_auto_resume)
- [x] NotifierBase + TerminalNotifier + LogNotifier + WebhookNotifier + CompositeNotifier
- [x] tests/unit/test_session_budget.py passing
- [x] tests/unit/test_session_manager.py passing
- [x] tests/unit/test_checkpoint.py passing

## Phase 3 -- Orchestrator
- [x] OrchestratorBase ABC (plan, synthesize, should_retry)
- [x] NanoOrchestrator (Tier 0 — rule-based, zero model calls)
- [x] SingleLLMOrchestrator (Tier 1 — injectable call_model, JSON fallback to Nano)
- [x] tests/unit/test_orchestrator_nano.py passing
- [x] tests/unit/test_orchestrator_single.py passing

## Phase 4 -- Providers + ToolNormalizer
- [x] WorkerProviderBase ABC
- [x] ToolCallNormalizer (NATIVE, JSON_EXTRACT, XML_EXTRACT, FEW_SHOT)
- [x] OllamaProvider (local + cloud unified, concurrency slot management)
- [x] AnthropicProvider
- [x] OpenAIProvider
- [x] FuguProvider (MULTI_AGENT, opaque worker)
- [x] tests/unit/test_tool_normalizer.py passing
- [x] tests/unit/test_provider_ollama.py passing
- [x] tests/unit/test_provider_anthropic.py passing
- [x] tests/unit/test_provider_openai.py passing
- [x] tests/unit/test_provider_fugu.py passing
- [ ] Integration tests passing with fake servers (deferred to Phase 7 hardening)

## Phase 5 -- Modes + CLI
- [x] ToolID, InteractionPattern, MemoryScope enums (tasker/workers/base.py)
- [x] tasker/tools/bundles.py (CHAT/CODE/COWORK/RESEARCH/SECURE bundles, secure_bundle(), get_definitions())
- [x] config/modes/*.yaml populated (all 5 modes)
- [x] TaskerMode dataclass + HardwareProfile + ExecutionConfig + ModeConfigurator
- [x] CHAT mode (tasker/modes/chat.py)
- [x] CODE mode (tasker/modes/code.py)
- [x] COWORK mode (tasker/modes/cowork.py) + CoworkRunner with tick/pause/checkpoint loop
- [x] RESEARCH mode (tasker/modes/research.py)
- [x] SECURE mode (tasker/modes/secure.py) -- hard block verified via WorkerSelector
- [x] CLI shell + slash commands (cli/shell.py)
- [x] tests/unit/test_harness_modes.py passing (214 total, incl. COWORK pause integration test)
- [ ] E2E tests (deferred -- requires Phase 6 higher tiers for real task execution)

## Phase 6 -- Higher Orchestrator Tiers
- [x] tasker/orchestrator/_parse.py (shared system prompts, parse_plan, parse_retry, prompt builders)
- [x] tier1_single.py refactored to import from _parse.py (no logic change)
- [x] DualLLMOrchestrator (Tier 2) — separate call_planner + call_synthesizer callables
- [x] ReasoningOrchestrator (Tier 3) — single call_model, GPU-resident, distinct from Tier 1
- [x] CloudOrchestrator (Tier 4) — routes through WorkerProviderBase.execute(), LOCAL_ONLY guard
- [x] tests/unit/test_orchestrator_tier2.py passing (10 tests)
- [x] tests/unit/test_orchestrator_tier3.py passing (10 tests)
- [x] tests/unit/test_orchestrator_tier4.py passing (13 tests)
- [x] CheckpointStore: _save_ns + _save_seq tiebreaker (fixes Windows clock resolution flake)

## Phase 7 -- Hardening
- [x] DesktopNotifier + WebhookNotifier verified (plyer fallback + exception swallow confirmed)
- [x] tests/unit/test_notifier.py passing (23 tests — all 5 notifiers + SessionEvent factories)
- [x] tasker/api/server.py — POST /v1/chat/completions, GET /v1/models, GET /v1/workers (aiohttp.web)
- [x] tests/integration/test_api_server.py passing (15 tests — request routing, error responses, shape)
- [x] tasker/config/detect.py — hardware auto-detection (psutil + nvidia-smi), suggest_profile()
- [x] psutil>=5.9 added to pyproject.toml dependencies
- [x] tests/unit/test_hardware_detect.py passing (16 tests — mocked detection, threshold coverage)
- [x] tasker/session/episodic.py — EpisodicMemoryBridge ABC, NullEpisodicMemoryBridge, JsonlEpisodicMemoryBridge
- [x] SessionManager.session_id property added (uuid4, stable per session)
- [x] CoworkRunner wired to episodic_bridge — records step_completed events, saves episodic_log_position to Checkpoint
- [x] tests/unit/test_episodic_bridge.py passing (15 tests — Null/Jsonl bridges + CoworkRunner wiring)

## Phase 8 -- Orchestrator Factory + Live CLI Wiring
- [x] HardwareProfile.orchestrator_model field added (parses orchestrator.model from YAML)
- [x] WorkerRegistry.load_from_yaml classmethod (injects available/vram_mb defaults)
- [x] worker_registry.yaml: compute_location fixed to "local" (was "local_hardware"); lfm2.5:latest → lfm2.5-thinking:latest
- [x] tasker/orchestrator/factory.py — build_orchestrator(config, provider_registry) → OrchestratorBase
  - Tier 0: NanoOrchestrator (no provider needed)
  - Tier 1: SingleLLMOrchestrator wired to OllamaProvider.execute()
  - Tier 2: DualLLMOrchestrator (same local model for planner + synthesizer)
  - Tier 3+: ReasoningOrchestrator
  - Graceful fallback to NanoOrchestrator when no OLLAMA provider registered
- [x] cli/shell.py: REPL and non-interactive paths replaced stubs with real _run_task() dispatch
  - Loads WorkerRegistry from YAML; builds OllamaProvider from profile.ollama_base_url
  - Uses factory to build orchestrator; runs plan → execute steps → synthesize pipeline
  - Argparse restructured: _first_positional() peek avoids subparser clash with free-form task strings
- [x] tests/unit/test_orchestrator_factory.py passing (12 tests — tier selection, call_model wiring)
- [x] Smoke tests passing against local Ollama (lfm2.5-thinking:latest):
  - CHAT: "say hello in exactly five words" → SingleLLMOrchestrator → local worker → synthesis ok
  - CODE: "list the files in the current directory" → local worker → synthesis ok
  - COWORK: "write a haiku about running code" → local worker → synthesis ok

## Phase 7.5 -- Cross-Platform Migration + Dynamic Hardware Detection
- [x] 7.5.1 Linux/WSL2 verified as primary dev environment (full suite + 3 smoke tests from WSL2)
  - Full suite: 330/330 tests passing
  - Smoke tests re-run natively on Linux: CHAT, CODE, COWORK all synthesized ok via lfm2.5-thinking:latest
  - Codebase audit found zero Windows-only path/string assumptions (no backslash literals,
    no os.name/platform.system branching, no PowerShell refs in .py files); DesktopNotifier's
    plyer fallback already cross-platform
- [x] .gitattributes added, line-ending drift normalized (eol=lf for source/config/docs, eol=crlf for .ps1)
- [x] 7.5.2 GPUBackend ABC + GPUInfo + NoGpuBackend (tasker/config/gpu_backends.py)
  - detect_gpu() chain structure in place (Nvidia/AmdApu commented stubs ->
    NoGpuBackend); only NoGpuBackend implemented this phase, as scoped
- [x] tasker-hardware applet (detect/verify/show/clear) scaffolded
  (tasker/config/detect.py:cli_main(), wired via pyproject.toml [project.scripts])
  - Live-tested all 4 subcommands end-to-end on this machine (hostname
    "Designlab1", 12 cores, 15.3GB RAM, no GPU detected via NoGpuBackend
    stub -- resolved to tier1_tasker)
  - verify prints a clear "requires 7.5.3/7.5.5" note rather than failing,
    since no real backend exists yet this phase
- [x] Cache schema + hostname-scoping implemented (schema matches
  SDD_ADDENDUM_7.5.md A.3.3 field-for-field; hostname mismatch -> None,
  falls through to live detection, never silently applies another
  machine's profile)
- [x] ModeConfigurator 3-source resolution order implemented
  (resolve_hardware_profile() on ModeConfigurator; explicit/env var ->
  cache (hostname-checked) -> live detection, in that order; all three
  unit-tested to confirm the earlier sources actually short-circuit the
  later ones, not just that all three individually work)
  - NOT wired into cli/shell.py this session, by design: _run_task() still
    calls configurator.load_profile(os.environ.get("TASKER_PROFILE",
    "tier1_tasker")) directly rather than resolve_hardware_profile().
    Wiring it in is a small follow-up, deliberately left out of strict
    7.5.2 scope (not in the addendum's file list for this sub-phase).
- [x] .tasker/ fully gitignored (not just checkpoints/sessions) -- added in 7.5.1's .gitignore pass
- [x] 7.5.3 NvidiaBackend implemented + unit tested (detect() + verify_live(),
      22 tests in test_gpu_backends.py, 3 tier-computation tests in
      test_hardware_detect.py -- 400/400 full suite passing)
  - detect_gpu() now tries NvidiaBackend first (was a commented stub since 7.5.2)
  - detect_hardware_profile() tier computation: NVIDIA >= 4096MB ->
    tier_max=2/resident (tier2_designlab.yaml); NVIDIA < 4096MB or no GPU ->
    tier_max=1/sequential (tier1_tasker.yaml), via a new dedicated
    _NVIDIA_RESIDENT_VRAM_THRESHOLD_MB=4096 constant -- kept separate from
    the legacy Phase-7 _GPU_VRAM_THRESHOLD_MB=4000 so existing
    suggest_profile()/auto_detect_profile() tests keep passing unchanged
  - Found and fixed a real bug during live testing: nvidia-smi's `-l 1`
    flag never exits on its own, so verify_live()'s supplementary
    utilization sample always hits subprocess.TimeoutExpired -- whose
    .stdout came back as raw bytes despite text=True on the original call,
    leaking a "b'0 %'" repr into the user-facing message. Fixed with
    defensive bytes decoding; regression test added
    (test_utilization_sample_via_timeout_path_decodes_bytes)
- [x] NvidiaBackend verified on real hardware (Designlab1) -- nvidia-smi
      reports "NVIDIA GeForce GTX 1050 Ti, 4096" MB; tasker-hardware detect
      correctly resolved gpu_vendor=nvidia, gpu_memory_mb=4096,
      is_unified_memory=false, orchestrator_tier_max=2, load_strategy=resident.
      tasker-hardware verify against a loaded lfm2.5-thinking:latest reported
      via /api/ps: size_vram=1074716998 bytes == size (full offload) ->
      gpu_verified_during_inference=true, gpu_verified_size_vram_mb=1024,
      gpu_verified_offload_status="full". "No model loaded" path also
      verified live (ran verify before loading any model).
- [ ] 7.5.4 AmdApuBackend v1 (general guide) implemented + unit tested
- [ ] AmdApuBackend v1 verified on real hardware (TASKER-P1, first pass)
- [ ] 7.5.5 AmdApuBackend refined (gfx902 env vars, group check, journalctl offload parsing)
- [ ] AmdApuBackend refined version verified on real hardware (TASKER-P1, offload_status="full" confirmed)
- [ ] 7.5.6 Worker VRAM cross-check implemented + unit tested
- [ ] Orchestrator factory confirmed consuming dynamic HardwareProfile correctly
- [ ] Final paired live verification: both machines, no --profile flag, 3-stage smoke test each
- [x] docs/Ollama_AMD_APU_Install_Guide.md added to repo
- [x] docs/ollama-amd-igpu-config-guide.md added to repo
- [x] CLAUDE.md updated: Linux/WSL2 primary, Windows secondary, both AMD guides referenced
- [x] AMD discrete / Intel / Apple Silicon explicitly documented as out-of-scope extension points (SDD_ADDENDUM_7.5.md A.4.3)

## LFM25 Protocol
- [x] ToolProtocol.LFM25 enum added
- [x] WorkerManifest.tool_result_role field added
- [x] ToolCallNormalizer.inject_tools() LFM25 path
- [x] ToolCallNormalizer.extract_tool_calls() JSON primary + Pythonic fallback
- [x] OllamaProvider protocol-aware routing (NATIVE vs non-NATIVE)
- [x] worker_registry.yaml: lfm2.5-local updated to lfm25 protocol
- [x] Unit tests passing (356/356 full suite, incl. 23 new LFM25-specific tests)
- [x] Live smoke test: raw response format confirmed -- JSON primary path works,
      but required hardening beyond the original spec: spec's literal
      instruction alone produced empty content; model also varied between
      array/bare-object/markdown-fenced JSON across runs. See CLAUDE.md
      "Live test result" and SDD_ADDENDUM_7.5.md A.2b for what changed.
- [ ] tool_result_role confirmed working ("tool"/"user") -- still blocked: no
      multi-turn tool-execution loop exists anywhere in the codebase yet to
      test it against (see CLAUDE.md "Open decisions"). The tools=[] wiring
      gap below being fixed does NOT unblock this -- a single-turn tool call
      never produces a "next turn", so tool_result_role still has nothing to
      exercise it. Unblocking requires building the multi-turn loop itself
      (re-invoke worker with tool result appended), which is out of scope
      for this session.
- [x] cli/shell.py tools=[] wiring gap fixed -- _run_task() now resolves
      config.mode.tool_bundle via get_definitions() and passes real
      ToolDefinitions into WorkerTask, for every mode (not just LFM25).
      Confirmed live: task.tools had 7 entries (bash, code_search, file_read,
      file_write, git, linter, test_runner) for CODE mode, reaching
      OllamaProvider correctly.
- [ ] First real tool call through harness confirmed end-to-end -- NOT
      checked: `python -m cli.shell --mode code "Use the bash tool to list
      the files in the current directory"` fell back to a generic "Answer
      the task" plan step in 4/4 runs, never reaching the real instruction.
      Root cause (separate, pre-existing bug, not LFM25/this session's
      wiring fix): SingleLLMOrchestrator.plan() asks the model for a JSON
      plan; lfm2.5-thinking:latest sometimes returns a capability string
      outside the Capability enum (observed: "bash" instead of "tool_use"),
      which makes tasker/orchestrator/_parse.py's parse_plan() fail and
      silently fall back to NanoOrchestrator's hardcoded single-step
      "Answer the task" template -- the worker never sees the real task text
      when this happens. Confirmed directly: calling the orchestrator's
      planning prompt against the real model reproduced the exact invalid
      "bash" capability string and the exact fallback description. When the
      planning step *does* succeed (confirmed once via a direct
      orchestrator->provider script, bypassing cli/shell.py's print
      wrapper but using the identical pipeline), the real task reached the
      worker and LFM25 fired a real, correctly-parsed tool call end-to-end
      (picked the wrong tool, test_runner instead of bash, but the
      protocol mechanics -- inject_tools, JSON response, extract_tool_calls,
      WorkerResult.tool_results -- all worked correctly). So: LFM25 itself
      is validated working; the harness-level "first real tool call"
      milestone is blocked on hardening parse_plan()/the planning prompt to
      stop silently discarding the user's task on a capability-string
      mismatch, not on anything in this session's changes.

## Phase 8 -- Setup Wizard, Readiness Checker, TUI

### Phase 8.1 -- Setup Wizard (headless)
- [x] tasker/setup/environment.py (is_wsl2, check_python, check_venv,
      check_ollama_binary, check_ollama_version, check_ollama_service)
- [x] tasker/setup/wizard.py (WizardStepResult, StepStatus, all 7 steps,
      run_wizard()) -- Step 7 redefined as Summary per this session's task
      (SDD_ADDENDUM_PHASE8.md B.3.2's own Step 7 is model
      selector/readiness, deferred to Phase 8.2 -- documented as a
      deliberate deviation in wizard.py's module docstring)
- [x] tasker-setup CLI entry point (headless, prints step results with
      ANSI color; --check-model stubbed for Phase 8.2; --ollama-url;
      --verbose)
- [x] pyproject.toml: textual>=0.70.0 added; tasker entry point now
      tasker.tui.app:main (stub, prints "coming in Phase 8.3"); tasker-cli
      added for the existing CLI (cli.shell:main, unchanged behavior);
      tasker-setup added
- [x] tasker/tui/__init__.py + app.py stub created (Phase 8.3 does the
      real TUI)
- [x] tests/unit/test_environment.py passing (13 tests, all mocked --
      no real filesystem/subprocess/network calls)
- [x] tests/unit/test_setup_wizard.py passing (13 tests, all mocked --
      no live Ollama calls per B.10)
- [x] Live headless run on Designlab1 (this machine) -- see CLAUDE.md for
      full output. All steps ran, GPU vendor correctly shown as nvidia,
      worker registry showed all 9 workers, no unhandled exceptions.
- [ ] Live headless run on TASKER-P1 -- not run this session (no access to
      that machine from here); flagged as a follow-up, not fabricated.

### Out of scope this session (unchanged from SDD_ADDENDUM_PHASE8.md)
- [ ] Phase 8.2 -- Agentic Readiness Checker (readiness.py, 3 probe rounds,
      --check-model)
- [ ] Phase 8.3 -- TUI Foundation (real TuiApp, WelcomeScreen, status bar)
- [ ] Phase 8.4 -- SetupWizardScreen + ModelSelectorScreen
- [ ] Phase 8.5 -- HarnessPanel

### Mid-session addition (before Phase 8.1 code, per explicit interrupt)
- [x] SDD_ADDENDUM_PHASE8.md B.4.6 (Role Assignment in Readiness Report)
      and B.6 (Model-Agnostic Design Principle) appended; existing B.6-B.10
      renumbered to B.7-B.11, no other content changed
- [x] WorkerRole enum added to tasker/workers/base.py (BACKGROUND_AGENT,
      EXECUTION_WORKER, REASONING_WORKER, ORCHESTRATOR) -- distinct from
      AgentRole (orchestration-internal per-step role)
- [x] WorkerManifest.worker_role: list[WorkerRole] field added (defaults
      to empty list), serialized in to_dict()/from_dict()
- [x] Round-trip tests added to test_worker_manifest.py (defaults-empty +
      round-trip); full suite confirmed passing after the addition

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
- [x] tool_result_role confirmed working ("tool") -- unblocked by the
      multi-turn tool loop (see "Multi-turn Tool Loop" section below).
      Live-verified: default role "tool" round-tripped into a real
      second-turn request payload against lfm2.5-thinking:latest, with a
      real executed bash result as the message content. "user" (the
      documented Ollama workaround) was not separately live-tested this
      session -- "tool" worked, so there was no failure forcing the
      workaround path.
- [x] cli/shell.py tools=[] wiring gap fixed -- _run_task() now resolves
      config.mode.tool_bundle via get_definitions() and passes real
      ToolDefinitions into WorkerTask, for every mode (not just LFM25).
      Confirmed live: task.tools had 7 entries (bash, code_search, file_read,
      file_write, git, linter, test_runner) for CODE mode, reaching
      OllamaProvider correctly.
- [x] parse_plan() capability-string hardening (see "Orchestrator
      Correctness" section below) -- RESOLVED the silent-fallback bug
      described in the (now-superseded) note that used to live here: a
      single invalid capability string (observed live: "bash", "ls",
      "list_files", "file_list", "code review", "bug detection", "bug_fix"
      across repeated runs of lfm2.5-thinking:latest) no longer collapses
      an otherwise-valid multi-step plan into NanoOrchestrator's generic
      template. Per-step recovery + CAPABILITY_ALIASES + WARNING logging
      implemented in tasker/orchestrator/_parse.py; ExecutionPlan gained
      `used_fallback: bool`.
- [x] First real tool call executed end-to-end, live, against
      lfm2.5-thinking:latest -- proven via a direct orchestrator-bypassing
      provider+loop script: instructed "Run the hostname command and tell
      me the exact output", the model's flat `{"command": "hostname"}`
      response was correctly inferred as a `bash` call (see "Multi-turn
      Tool Loop" section), executed for real, and returned
      `tool_output='Designlab1\n'` -- the machine's actual hostname,
      confirmed against a direct `hostname` shell command. This is
      genuine proof real execution occurs, not model speculation.
- [ ] First real tool call confirmed end-to-end through the FULL
      `python -m cli.shell` invocation specifically (not just the direct
      provider+loop script above) -- still blocked by the pre-existing,
      separate empty-content bug documented below: the orchestrator's own
      planning step rephrases the task into a step description (e.g.
      "The exact output of running hostname"), and several rephrasings
      reliably trigger the empty-content quirk in the WORKER step before
      the tool-call-parsing code path is ever reached. Reproduced across
      4/4 full-CLI attempts this session, all landing on the empty-content
      bug rather than exercising the (separately proven-working) loop.
      This is not a regression from today's work -- the loop and inference
      fix are proven correct in isolation; the full pipeline is just more
      likely to hit the other, still-open bug first because the planner's
      rephrasing is an extra opportunity for that bug's trigger phrasing.
- [ ] EMPTY `content` string back from lfm2.5-thinking:latest -- separate,
      still-open flakiness unrelated to parse_plan() or the multi-turn
      loop. Live testing this session (see "Multi-turn Tool Loop" below)
      found this is NOT simple flakiness: the same instruction phrasing
      failed identically across repeated attempts (bounded retry, added
      this session, does not recover it), while other phrasings of a
      similar request succeeded, suggesting the trigger is closer to
      "certain phrasings reliably fail" than "random sampling
      occasionally fails". Suspected cause unchanged: this "thinking"
      model sometimes exhausts its output budget inside the `<think>`
      reasoning block before emitting the final JSON `content`. Untried
      next lever: Ollama's per-request `"think": false` control, not
      attempted this session -- out of scope, but promising given
      `done_reason=stop` + non-empty `thinking` + empty `content` is
      exactly the signature that control targets.

## Orchestrator Correctness

- [x] tasker/orchestrator/_parse.py::parse_plan() no longer discards an
      entire valid plan because ONE step had an unrecognized capability
      string. Per-step recovery: unrecognized strings are checked against
      a small, evidence-based `CAPABILITY_ALIASES` dict (silent
      normalization, no warning -- e.g. "tool_execution" -> TOOL_USE);
      anything still unmatched is dropped from that step with a WARNING
      log (bad string, step index, full raw response) while the rest of
      the plan (other steps, other capabilities) is left untouched. A
      step left with zero valid capabilities still gets `{TOOL_USE}` via
      the existing unconditional default. Only a response that fails to
      parse as valid plan JSON/structure at all (not valid JSON, not a
      list, empty, or missing required keys) returns None and triggers
      the caller's fallback to NanoOrchestrator -- that case now also
      logs a WARNING with the raw response.
- [x] `ExecutionPlan.used_fallback: bool` field added (default False,
      serialized in to_dict/from_dict) so callers/tests can assert
      whether a plan is the model's real plan or NanoOrchestrator's
      generic template, instead of inferring it from step count.
      `SingleLLMOrchestrator.plan()` (tier1_single.py) sets it True only
      when it actually falls back.
- [x] tests/unit/test_orchestrator_parse.py -- valid plan (no warnings,
      used_fallback=False), one bad capability among valid ones (plan
      preserved, WARNING logged, used_fallback=False), alias match
      (silent, no warning), all-steps-zero-valid-capabilities (each
      defaults to TOOL_USE, one warning per step), malformed/empty
      response (None returned, WARNING logged, and via
      SingleLLMOrchestrator: used_fallback=True). Existing
      test_orchestrator_single.py tests unchanged and still passing.
- [x] Live-verified against lfm2.5-thinking:latest on Designlab1 (see
      CLAUDE.md Current Session Notes for the exact before/after step
      counts and warning output) -- repeatedly reproduced the real-world
      invalid capability strings ("bash", "ls", "list_files",
      "file_list", "code review", "bug detection", "bug_fix") and
      confirmed the model's actual step description/count is now
      preserved with `used_fallback=False`, instead of collapsing to
      NanoOrchestrator's generic template as it did before this fix.

## Multi-turn Tool Loop

- [x] `tasker/tools/executor.py` -- `execute_tool()` real dispatch for
      BASH, GIT, FILE_READ, FILE_WRITE, CODE_SEARCH (argv-based
      `asyncio.create_subprocess_exec`, never `shell=True`). LINTER/
      TEST_RUNNER deliberately left unimplemented (no linter/test
      framework configured anywhere in this project). BASH/FILE_WRITE/GIT
      hard-gated to `ComputeLocation.LOCAL_HARDWARE`; small BASH denylist
      as defense-in-depth only (documented as not a security boundary);
      30s timeout + 8000-char output cap; path containment under `cwd`
      for FILE_READ/FILE_WRITE. See SDD 5.7a for the full security
      posture rationale.
- [x] `tasker/tools/loop.py` -- `run_tool_loop()` drives `provider.
      execute()` through multiple turns: execute, run any requested tool
      calls for real, thread the assistant's own turn
      (`WorkerResult.raw_assistant_message`, new field) and the tool
      result (`format_tool_result_message()`) into history, re-invoke.
      Terminates cleanly at `max_turns=5` (default) with a WARNING, never
      raises. Usage/cost/duration accumulate across turns; every turn's
      *executed* tool results survive into the final result (design
      review caught that returning only the last turn's would silently
      discard everything that actually ran, since the last turn typically
      requests none). DEFERRED (no concurrency slot) gets a bounded retry
      with backoff before giving up, since bailing after real tool side
      effects already happened is worse than a short wait.
- [x] `tasker/workers/providers/ollama.py::_build_messages()` fixed to
      only append `task.instruction` as a fresh user turn when
      `context["messages"]` is empty -- a continuation turn's history
      already ends correctly (e.g. with a tool result), and re-appending
      the original instruction would duplicate it as a second user
      question. First-turn behavior (all existing tests) unchanged.
- [x] `format_tool_result_message()` gained an optional `tool_call_id`
      param, threaded through for NATIVE protocol (index-matched to the
      same synthesized `call_{i}` ids `OllamaProvider` already invents).
      Not confirmed live whether Ollama's `/api/chat` actually enforces
      id-based pairing -- included as cheap insurance either way.
- [x] `cli/shell.py::_run_task()` calls `run_tool_loop()` in place of a
      single `provider.execute()` per step.
- [x] `build_synthesize_prompt()` (`tasker/orchestrator/_parse.py`)
      enriched to append real `tool_output` per step after the existing
      `Step N: {output}` prose line, so synthesis stays grounded even if
      a step's final prose is itself empty.
- [x] **Root cause found for why live end-to-end proof initially failed:**
      `ToolCallNormalizer._extract_lfm25()` set `tool_name=""` whenever
      the model's JSON call omitted the `{"name", "arguments"}` envelope.
      Live testing found `lfm2.5-thinking:latest` does this *consistently*
      (not flakily) for single-tool tasks -- e.g. emitting bare
      `{"command": "hostname"}` instead of `{"name": "bash", "arguments":
      {"command": "hostname"}}`, reproduced identically across 3+ separate
      prompts. Fixed: `ToolCallNormalizer.extract()`/`extract_tool_calls()`
      gained an optional `tools: list[ToolDefinition]` param (threaded
      from `task.tools` in `OllamaProvider.execute()`); when an item has
      neither `name` nor `arguments`, `_infer_tool_from_flat_object()`
      matches the flat dict's keys against each offered tool's JSON
      Schema (`required` subset check + no extra keys) and infers the
      tool name only on a unique match -- ambiguous or unmatched cases
      are left unresolved (`tool_name=""`, same as before) rather than
      guessed. `anthropic.py`/`openai_provider.py` (always NATIVE) are
      unaffected since `_extract_native()` never reads `tools`.
- [x] Live end-to-end proof: direct provider+loop script (bypassing the
      orchestrator's planner) instructed to run `hostname` via the `bash`
      tool -- model's flat-object response correctly inferred as `bash`,
      executed for real, returned the machine's actual hostname
      (`'Designlab1\n'`), matching a direct `hostname` shell invocation.
      This is the first confirmed real (non-fabricated) tool execution in
      the project's history.
- [x] Security gating live-verified: constructing an `OLLAMA_CLOUD`
      worker and requesting `bash` returns a clear `.error`
      ("restricted to LOCAL_HARDWARE workers"), never executes.
- [x] 46 new unit tests: `tests/unit/test_tool_executor.py` (25),
      `tests/unit/test_tool_loop.py` (11, including one integration test
      using the real `OllamaProvider` with only HTTP mocked, specifically
      to catch a system-message-duplication bug the design review found
      that a fully-isolated loop-only test would have missed), plus
      `TestOllamaProviderMultiTurn`/`TestFormatToolResultMessage` (7) in
      `test_provider_ollama.py`, `TestBuildSynthesizePrompt` (3) in
      `test_orchestrator_parse.py`, and `TestLfm25FlatObjectInference` (7)
      in `test_tool_normalizer.py`. Full suite: 437/437 -> 494/494.
- [ ] **Known, not closed by this work:** the loop only helps tool calls
      that are *successfully parsed*. When a model's response is fully
      empty (nothing parses into any call at all), there is nothing for
      the loop to execute -- see the empty-content item above, still
      open. The full CLI pipeline (`python -m cli.shell`) has not yet
      been observed completing a real tool execution end-to-end in a
      single run, because the planner's own rephrasing of the task is an
      additional opportunity to trigger that separate bug before the
      (proven-working) loop code path is reached.
- [ ] Model doesn't reliably conclude after seeing a real tool result --
      observed live: after a real `hostname` execution was fed back,
      `lfm2.5-thinking:latest` re-emitted the same tool call again instead
      of answering, repeating until `max_turns` cut it off. Not
      investigated further this session; likely a separate small-model
      multi-turn behavior limitation, not a bug in the loop itself (the
      loop's job -- executing real calls and feeding results back
      correctly -- was independently confirmed via the mocked unit tests).
- [ ] Empty-content bounded retry (`OllamaProvider._EMPTY_CONTENT_MAX_
      RETRIES`, added this session) does not recover the specific
      empty-content case -- confirmed live, 3/3 identical retries all
      still empty for the same prompt. Kept as a safe, tested, no-harm
      mitigation for genuinely sampling-dependent cases, but it is not a
      fix for the phrasing-dependent case documented above.
- [ ] `LINTER`/`TEST_RUNNER` tool execution -- not implemented; no linter
      or test framework is configured anywhere in this project.
- [ ] Anthropic/OpenAI/Fugu providers are not wired through
      `run_tool_loop()` -- `cli/shell.py`'s `provider_map` only registers
      `OllamaProvider`. `run_tool_loop()`'s coupling to `OllamaProvider`'s
      `format_tool_result_message()` would need generalizing if/when
      those providers need a multi-turn loop of their own.

## Step-Aware Tool Subsetting + Ollama-Cloud Planner

Follow-on to "Multi-turn Tool Loop" above: live testing there proved
quantization was never the real bottleneck (Q4/Q8/bf16 all failed
identically once offered the full 7-tool `CODE_BUNDLE`), and that
offering just the 1 tool a step actually needed was 100% reliable in
every test. This closes that gap, plus lets planning use a stronger
model without touching the local worker.

- [x] `tasker/tools/bundles.py::narrow_bundle_to_step()` -- deterministic,
      keyword-group-based narrowing (no LLM classification -- proven
      unreliable for this same small model). Groups require ALL member
      substrings present (any order) to match, not just a fixed phrase,
      after live testing showed the planner paraphrases the same real
      intent multiple ways across runs ("List files in current
      directory" / "Listing files" / "List current directory files").
      Safe fallback: no match returns the full bundle unchanged + logs a
      WARNING, rather than guessing wrong.
- [x] `cli/shell.py::_run_task()` computes tools per-step now (was: once,
      constant, before the loop).
- [x] `tests/unit/test_tool_bundles.py` (18 tests) -- per-tool keyword
      matches, the exact real step descriptions and paraphrases observed
      live, multi-keyword overlap, no-match fallback (`assertLogs`),
      bundle-intersection correctness.
- [x] Live-verified on Designlab1, Q4 (`lfm2.5-thinking:latest`), the
      exact prompt that reliably failed last session
      (`"Use the bash tool to list the files in the current directory"`):
      0 of 3 completed runs hit the no-keyword-match fallback across 3
      different planner paraphrases; one run completed with the exact
      real directory listing as the final synthesized answer. The other
      two hit `max_turns` (the separately-documented "model doesn't
      conclude after a real tool result" quirk from last session, not a
      narrowing failure -- both still executed real tools throughout).
- [x] `HardwareProfile.orchestrator_compute_location: str = "local"` (new
      optional field, `"local"` | `"ollama_cloud"`, parsed from a
      profile's `orchestrator.compute_location` YAML key).
- [x] `tasker/orchestrator/factory.py` -- `_build_orchestrator_manifest()`
      and `_make_call_model()` now accept `compute_location`/
      `privacy_tier` params (default unchanged: `LOCAL_HARDWARE`/
      `LOCAL_ONLY`); `build_orchestrator()` branches on
      `orchestrator_compute_location`. No new provider needed --
      `OllamaProvider` already handles `OLLAMA_CLOUD` via the same
      endpoint (SDD 5.6.1); still only ever resolves
      `provider_registry[ProviderType.OLLAMA]`. Explicit user preference:
      route through Ollama's own cloud (`:cloud`-tagged models), not a
      third-party OpenAI-compatible router.
- [x] New `config/profiles/tier1_cloud_planner.yaml` -- local Q4 worker
      unchanged, orchestrator routed to `gpt-oss:120b-cloud`
      (OpenAI's actual open-weight 120B release, hosted on Ollama Cloud;
      confirmed live via `ollama show` to have a real 131072-token
      context window -- `context_limit` set to match, not copied from
      the local profile's 4096 CPU-RAM-driven value).
- [x] `tests/unit/test_orchestrator_factory.py` -- 4 new tests
      (`TestBuildOrchestratorCloudRouting`): local-default regression,
      `ollama_cloud` manifest/privacy-tier wiring, still resolves
      `ProviderType.OLLAMA` (no new provider type), missing-provider
      fallback to `NanoOrchestrator`.
- [x] Live-verified end-to-end on Designlab1: `ollama signin` completed
      (this machine had no active session at session start -- confirmed
      via a direct `:cloud` API call returning `"Unauthorized"`);
      `gpt-oss:20b-cloud` and `gpt-oss:120b-cloud` both confirmed
      reachable with real responses. A real planning call through
      `SingleLLMOrchestrator` wired to `tier1_cloud_planner` produced a
      clean, valid 3-step plan (`used_fallback=False`, no unrecognized
      capability strings) -- visibly better structured than typical local
      Q4 planning output. A full `python -m cli.shell --mode code` run
      using this profile (cloud planner + local Q4 worker) completed with
      the correct, real directory listing as its final answer.
- [ ] **New, real, pre-existing bug found (not introduced or fixed this
      session):** the cloud planner's richer plans assign `REASONING`/
      `THINKING` capabilities the local worker doesn't declare, causing
      `WorkerSelector` to fall through to `nemotron-3-ultra-cloud` for
      those steps -- which fails instantly, because
      `worker_registry.yaml`'s `model_id: "nemotron-3-ultra"` is missing
      the `:cloud` suffix Ollama Cloud's actual tags require (confirmed:
      `nemotron-3-ultra` alone returns `"model 'nemotron-3-ultra' not
      found"`; `ollama.com/search?c=cloud` lists it as `nemotron-3-ultra`
      but the real pullable/callable tag pattern, per every other cloud
      model checked this session, needs the suffix). Likely affects
      other cloud-routed worker registry entries too (glm-5.2, glm-5.1,
      minimax-m3, kimi-k2.7-code) -- not verified individually, out of
      scope for this session's plan.
      **FIXED in a later session -- see "Cloud Model ID Suffix +
      Orchestrator Concurrency Slot-Limiting" below: all 5
      `compute_location: ollama_cloud` entries were missing the suffix,
      not just this one; all 5 corrected and live-reconfirmed.**
- [ ] Tier 2 (`DualLLMOrchestrator`) still gets the *same* `model_id` for
      both its planner and synthesizer roles (`factory.py`'s
      `build_orchestrator()`, tier==2 branch) despite the constructor
      supporting two distinct models, and `tier2_designlab.yaml`'s
      `planner_model`/`synthesizer_model` keys are still silently never
      read by `HardwareProfile.orchestrator_model` (only a single
      `model` key is parsed). Noted again this session (first found
      while investigating the cloud-planner design); still not fixed --
      the `orchestrator_compute_location` plumbing added this session
      would make fixing this more straightforward whenever it's tackled.
- [ ] `OllamaCloudConcurrencyManager` is not wired to the orchestrator's
      `OllamaProvider` instance in `cli/shell.py` -- cloud orchestrator
      calls proceed without slot-limiting (no `DEFERRED` possible). Known
      gap, not fixed this session (out of scope: this work was about
      model *choice*, not concurrency).
      **FIXED in a later session -- see "Cloud Model ID Suffix +
      Orchestrator Concurrency Slot-Limiting" below. Turned out to be
      broader than just orchestrator calls: `OllamaCloudConcurrencyManager`
      was never constructed anywhere in production code at all, so
      regular WORKER dispatch was unslotted too, not just orchestrator
      calls -- both share the same `OllamaProvider` instance in
      `cli/shell.py`, so one wiring fix covers both.**

## Cloud Model ID Suffix + Orchestrator Concurrency Slot-Limiting

Two independent, small fixes, unrelated to each other.

### Fix 1 -- missing `:cloud` suffix

- [x] All 5 `compute_location: ollama_cloud` entries in
      `config/workers/worker_registry.yaml` (`nemotron-3-ultra-cloud`,
      `glm-5.2-cloud`, `glm-5.1-cloud`, `minimax-m3-cloud`,
      `kimi-k2.7-code-cloud`) were missing the `:cloud` suffix Ollama
      Cloud requires to route to cloud infrastructure -- a systemic
      omission across every cloud entry, not a single typo.
      `local_hardware`/`direct_cloud` (Anthropic/OpenAI/Fugu) entries are
      untouched -- the suffix is Ollama-Cloud-specific.
- [x] Live-reconfirmed against the real Ollama API for all 5 (not just
      documentation/prior knowledge): every bare model_id returns
      `{"error": "model '...' not found"}`; every `:cloud`-suffixed form
      returns a real response.
- [x] Regression test against the REAL `config/workers/worker_registry.yaml`
      file (not a synthetic fixture) added to
      `tests/unit/test_worker_registry.py`
      (`TestRealWorkerRegistryYaml`): every `ollama_cloud` worker's
      `model_id` must end with `:cloud`; non-`ollama_cloud` workers must
      not. Confirmed the test fails against the pre-fix file and passes
      against the fix (verified via `git stash`).

### Fix 2 -- concurrency slot-limiting not applied to cloud orchestrator calls

- [x] **Root cause, confirmed by reading before changing anything:** this
      was a wiring gap, not a missing feature -- `OllamaProvider.execute()`
      already had correct gating logic
      (`if is_cloud and self._concurrency: ...`), but
      `OllamaCloudConcurrencyManager` was never instantiated anywhere in
      production code (only in its own docstring example and in tests).
      `cli/shell.py` constructed `OllamaProvider(profile.ollama_base_url)`
      with no `concurrency_mgr` at all. Since that single `OllamaProvider`
      instance serves BOTH regular worker dispatch (via
      `WorkerSelector`/`run_tool_loop`) and orchestrator plan/synthesize/
      retry calls (via `factory.py`'s `_make_call_model`), this was a
      single missing wire with broader blast radius than "orchestrator
      calls only" -- worker dispatch was unslotted too.
      `tier4_cloud.py`'s `CloudOrchestrator` (Tier 4) needed no code
      changes: it's never instantiated in production, and calls
      `self._provider.execute()` directly, so it transitively inherits
      correct gating from whatever provider it's given, with zero
      Tier-4-specific logic needed.
- [x] **The fix:** `cli/shell.py` now constructs one
      `OllamaCloudConcurrencyManager(profile.ollama_plan)` and passes it
      into the single `OllamaProvider` instance shared by both call paths
      -- exactly one manager per run, not one per code path, per the
      explicit requirement.
- [x] **Exhausted-slot behavior, decided and documented:** bounded retry
      (3 attempts, 0.5s backoff) then fail -- matching the existing
      precedent in `tasker/tools/loop.py`'s worker-side
      `_execute_with_deferred_retry()` from a previous session, now
      mirrored for orchestrator-level calls in
      `tasker/orchestrator/factory.py::_execute_with_deferred_retry()`.
      On exhaustion, `_make_call_model()`'s `call_model()` raises a new
      `OllamaCloudConcurrencyExhaustedError` (`tasker/workers/base.py` --
      distinct from `OllamaQueueFullError`, which is the server itself
      signaling overload via HTTP 429, not our own client-side
      concurrency manager) rather than silently collapsing a deferred
      call into an empty string indistinguishable from a genuinely empty
      model response. The exception propagates uncaught through
      `plan()`/`synthesize()`/`should_retry()` (tiers 1-3 don't catch
      exceptions from `call_model`), reaching `cli/shell.py`'s existing
      `try/except` around `orchestrator.plan()` ("Planning failed: ...")
      with no new exception-handling code needed there.
- [x] 4 new tests in `tests/unit/test_orchestrator_factory.py`
      (`TestOrchestratorCloudConcurrency`), using the real `OllamaProvider`
      (HTTP mocked) with a scripted fake concurrency manager for
      deterministic timing: retry-then-succeed, retry-then-raise
      (`OllamaCloudConcurrencyExhaustedError`), no-retry-when-immediately-
      available, and a regression guard confirming `LOCAL_HARDWARE`-routed
      calls never even touch the concurrency manager.
- [x] Live-verified on Designlab1: a `tier1_cloud_planner` run exercised
      BOTH fixes together in one call -- `WorkerSelector` resolved to
      `nemotron-3-ultra:cloud` (Fix 1) for a step, executed successfully
      through the now-concurrency-gated `OllamaProvider` (Fix 2), no
      errors, single slot correctly acquired/released.

523/523 tests passing (7 new: 3 in `test_worker_registry.py`, 4 in
`test_orchestrator_factory.py`).

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

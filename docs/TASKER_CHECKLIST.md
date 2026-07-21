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
- [x] 7.5.4 AmdApuBackend v1 (general guide) implemented + unit tested
  (tasker/config/gpu_backends.py: detect() -- lspci -nn presence check /
  Get-CimInstance on Windows, vulkaninfo informational check, 3-env-var
  Vulkan/ROCm-disable check with gfx902-specific warning, video/render
  group check via the grp module, memory_mb = total system RAM. 17 new
  tests in test_gpu_backends.py, no real hardware needed)
- [x] AmdApuBackend v1 verified on real hardware (TASKER-P1, first pass) --
  see combined 7.5.4/7.5.5 verification note below (both passes happened
  in the same live session since the systemd override was already
  correctly configured from a prior session)
- [x] 7.5.5 AmdApuBackend refined (gfx902 env vars, group check, journalctl
  offload parsing) -- verify_live(): /api/ps size_vram primary check +
  journalctl supplementary parsing (crash signature -> verified=False;
  "offloaded N/M" -> offload_status full/partial), priority-ordered per
  A.4.4. 6 more tests covering verify_live() specifically.
- [x] AmdApuBackend refined version verified on real hardware (TASKER-P1,
  offload_status="full" confirmed) -- SSH session to TASKER-P1 (real
  Ryzen 5 3500U, Raven2/gfx902, confirmed via lspci: "Picasso/Raven 2
  [Radeon Vega Series / Radeon Vega Mobile Series]"). systemd override
  already had all 4 required env vars set from a prior session
  (OLLAMA_VULKAN=1, ROCR_VISIBLE_DEVICES=-1, HIP_VISIBLE_DEVICES=-1,
  OLLAMA_FLASH_ATTENTION=1) and the `ollama` service account was already
  in video+render groups -- no fix needed, no sudo required this
  session. `tasker-hardware detect` correctly resolved gpu_vendor=
  amd_apu, gpu_memory_mb=29013 (total system RAM, not a sysfs VRAM
  figure), is_unified_memory=true. Loaded lfm2.5-thinking:latest
  (confirmed 100% GPU via `ollama ps`), ran `tasker-hardware verify`:
  journalctl parsing correctly reported "journalctl confirms full GPU
  offload: 17/17 layers" -- gpu_verified_offload_status="full",
  gpu_verified_during_inference=true written to the cache. Note: the
  interactive SSH login user (tasker0) is NOT in video/render (only the
  `ollama` service account is) -- detect()'s group_warning correctly
  flagged this as expected/documented behavior (advisory, not a hard
  block, doesn't affect the service's actual GPU access).
- [x] 7.5.6 Worker VRAM cross-check implemented + unit tested --
  WorkerRegistry.apply_gpu_availability(gpu, reserve_mb=6144) marks
  requires_gpu=true workers unavailable with a logged reason (never
  silently dropped from list_all()/`tasker workers`) when they don't fit:
  NVIDIA discrete checked directly against gpu.memory_mb; AMD APU
  unified memory checked against gpu.memory_mb minus reserve_mb (6GB,
  within A.3.4's 4-8GB range). Wired into cli/shell.py's main() via the
  machine-local cache (load_cached_detection()/load_cached_gpu_info()),
  not a fresh detect_gpu() call, to avoid adding subprocess latency to
  every CLI invocation; skipped entirely when no cache exists yet
  (preserves pre-7.5.6 behavior). 13 new tests, mocked GPUInfo
  throughout, no real hardware needed.
- [x] Orchestrator factory confirmed consuming dynamic HardwareProfile
  correctly -- unaffected by this phase's changes (build_orchestrator()
  already reads config.profile.orchestrator_model/orchestrator_tier_max
  from whatever HardwareProfile it's given, dynamic or static; no
  changes needed here).
- [x] Final paired live verification: both machines, no --profile flag,
  3-stage smoke test each. While pursuing this, the full CLI pipeline
  hung or produced wrong output on BOTH machines -- root-caused and
  fixed 4 separate, previously-undiscovered pipeline bugs (none
  related to AmdApuBackend/VRAM-cross-check specifically, all
  pre-existing model/parsing reliability gaps surfaced by actually
  running the full pipeline end-to-end for the first time this
  thoroughly):
    1. `narrow_bundle_to_step()`'s no-keyword-match fallback offered the
       FULL tool bundle (a deliberate prior-session choice) -- caused
       lfm2.5-thinking to hallucinate a nonsensical tool call
       (`calculator(expression="hello")` for "say hello") instead of
       answering directly, then never conclude, exhausting
       run_tool_loop's max_turns=5. Now falls back to an EMPTY tool set;
       also added an `original_task` second-chance match for when the
       planner's step description is too garbled to match on its own.
    2. Orchestrator/worker call `timeout_s` defaulted to 120.0s -- live-
       measured a single plan() call at 94.5s real time (17417-char
       thinking block) for a trivial prompt, and a second attempt
       exceeded 120s outright (`TimeoutError`). Raised to 240.0s
       throughout (factory.py, ollama.py).
    3. `parse_plan()` silently corrupted step descriptions when the
       model emitted a JSON object with a duplicated "description" key
       (a 4-intent "create/verify/read/confirm" task collapsed into 2
       objects each with 2 "description" values) -- plain `json.loads()`
       kept only the LAST value, losing the first-mentioned real intent
       with no error. Added a custom `object_pairs_hook` that splits
       such objects into multiple correctly-formed steps.
    4. `parse_plan()` raised an uncaught `AttributeError` (only saved by
       `cli/shell.py`'s outer try/except) when a plan array element
       wasn't itself a JSON object (e.g. a bare string) -- now validated
       and returns None (NanoOrchestrator fallback) per its documented
       contract, matching every other malformed-structure case.
  Also found and fixed a test-isolation bug live on TASKER-P1:
  `test_falls_through_to_no_gpu_when_nvidia_absent` only mocked
  `NvidiaBackend.detect`, so real AMD hardware broke its "no GPU at all"
  assumption -- passed on Designlab1 (no AMD hardware to accidentally
  detect) but failed running the suite on TASKER-P1 itself.
  **Results:** Designlab1 (Designlab1, NVIDIA GTX 1050 Ti) -- all 3
  stages pass with correct output: CHAT "One, two, three, four, five."
  (5 words), CODE correctly listed real directory contents via bash
  (required all 5 tool-loop turns but the accumulated results still
  synthesized correctly), COWORK genuinely created hello.txt with
  content "hello" (verified on disk). TASKER-P1 (real AMD APU hardware,
  via SSH) -- CHAT passes ("A, B, C, D, E.", fast ~4s worker call); CODE
  completed without hanging but surfaced a 5th, distinct, NOT-yet-fixed
  bug (a flat-object tool call `{"command": "ls"}` wasn't correctly
  inferred/executed, so the raw JSON leaked into the final synthesized
  answer instead of a real directory listing -- see "Known Open Issues"
  below); COWORK not re-tested on TASKER-P1 this session (stopped by
  explicit user decision after the 5th bug was found, to avoid an
  open-ended chain of tiny-model reliability fixes beyond this phase's
  actual scope). 565 -> 567 tests passing across both machines.

## Known Open Issues (not fixed this session, tracked for follow-up)
- Flat-object tool call inference gap: a worker response shaped like
  `{"command": "ls"}` (no `name`/`arguments` wrapper) was not correctly
  routed through `ToolCallNormalizer`'s flat-object-inference path in at
  least one live case on TASKER-P1 (CODE mode, "list the files in the
  current directory") -- the raw JSON leaked into the final synthesized
  answer instead of the tool ever executing. `TestLfm25FlatObjectInference`
  in test_tool_normalizer.py already covers this path and passes, so this
  is either an edge case that slips past that logic's matching rules, or
  a different code path entirely (e.g. the model may not have used
  ToolProtocol.LFM25's expected format at all this time) -- not yet
  root-caused. Reproduce via: TASKER-P1, `tasker --mode code "list the
  files in the current directory"`, no `--profile` flag.
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
      **Later session (targeted diagnostic, Designlab1) ruled out two
      more hypotheses -- do not re-test these from scratch:**
      (1) missing `num_predict`/generation-budget option -- confirmed
      `OllamaProvider` never sets `options.num_predict` or `num_ctx` at
      all (Ollama's default context applies; `ollama ps` showed the
      model loaded with only `CONTEXT 4096` despite a real 128k window),
      matching two independently-built reference scripts that both set
      `num_predict: 32000` -- but 28 raw reproduction attempts across
      every previously-observed trigger condition (terse instruction,
      tool-list system prompt, cold-vs-warm model, explicit
      `num_predict: 32000` override) produced **0 empty-content
      failures**, and all 28 had `done_reason: "stop"` (never
      `"length"`, which is what truncation would show) -- argues against
      budget starvation being the mechanism, at least under conditions
      testable via isolated sequential calls.
      (2) cold-model warmup -- 4/4 clean on a freshly force-unloaded
      (`ollama stop`) model, no different from warm.
      **Not fixed -- bug could not be reproduced at all this session**
      despite covering the exact conditions (terse "Hello"/"A test"
      wording, LFM25 tool-list system prompt) that triggered it live
      earlier in the same overall session via the real CLI. See
      CLAUDE.md's "Diagnostic session" note for the full evidence trail
      and the untried next lever (reproduce under real async/concurrent
      harness load, not isolated sequential raw calls).
      **Follow-up session ruled out two more -- do not re-test these
      either:**
      (3) context-window (`num_ctx`) ceiling -- confirmed
      `WorkerManifest.context_window` (`128000` for lfm2.5-local) is
      genuinely dead metadata, never wired to Ollama's `num_ctx` request
      option (real gap, worth fixing on its own merits someday). But
      10/10 reproduction attempts (COWORK's full 14-tool bundle +
      synthetic multi-turn history, real `prompt_eval_count=3508`,
      combined `total_tokens` reaching 4102-5342 -- i.e. exceeding the
      supposed 4096 default ceiling in most runs) produced **0
      empty-content failures** both with `num_ctx` unset and with it
      explicitly set to 32768 -- no difference, no truncation
      (`done_reason` always `"stop"`) even 30% over the ceiling.
      (4) concurrency / lack of a local-hardware concurrency guard --
      confirmed via code read that `OllamaCloudConcurrencyManager` is
      gated by `is_cloud` in `OllamaProvider.execute()` and never
      consulted for `LOCAL_HARDWARE` calls (real, confirmed gap -- zero
      concurrency guarding exists for local calls anywhere in the
      codebase). But 3 batches of 3 truly concurrent (`asyncio.gather`)
      requests (9 total) against the same loaded model produced **0/9
      empty or errored** -- Ollama's server serializes GPU inference
      cleanly under concurrent HTTP arrival (staggered per-request
      completion times confirm serialization), no response mixing or
      corruption observed.
      **47 total reproduction attempts across two sessions (28 + 10 + 9),
      0 failures.** Neither the context-ceiling gap nor the missing
      local-concurrency-guard gap is the empty-content bug's cause, even
      though both are real, independently-confirmed gaps worth fixing on
      their own correctness merits eventually (not done this session --
      "fix only if confirmed" scope). Base rate now appears low enough
      that a much larger sample (dozens-hundreds of attempts) or a
      different reproduction strategy (genuinely concurrent *multi-turn*
      `run_tool_loop()` load, not single-turn) may be needed to catch it
      at all. See CLAUDE.md's "Follow-up diagnostic session" note.

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
- [x] `TEST_RUNNER`/`LINTER`/`CALCULATOR` tool execution implemented in
      `tasker/tools/executor.py` (tool-executor fill-in sprint, part 2):
      TEST_RUNNER auto-detects pytest (preferred) and falls back to unittest
      discover, returning structured pass/fail/skip counts plus failing test
      names; LINTER runs ruff when available and returns an honest
      "linter not installed" error otherwise; CALCULATOR evaluates arithmetic
      via an AST whitelist (no eval()). All three registered in `_DISPATCH`
      and added to `_TOOL_KEYWORDS` so narrow_bundle_to_step() can actually
      offer them.
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

### Still out of scope (unchanged from SDD_ADDENDUM_PHASE8.md)
- [ ] Phase 8.4 -- SetupWizardScreen + ModelSelectorScreen
- [ ] Phase 8.5 -- HarnessPanel

### Phase 8.2 -- Agentic Readiness Checker (addendum numbering; completed 2026-07-19)
- [x] tasker/setup/readiness.py (ProbeResult, ReadinessResult,
      ReadinessChecker, assign_roles per B.4.6, format_report per B.4.4,
      write_manifest_to_registry)
- [x] All 3 probe rounds implemented (NATIVE, LFM25, JSON_EXTRACT), run in
      order, later rounds skipped once one succeeds. Success criterion
      (added to B.4.3 SDD-first): >= 1 extracted call naming
      get_current_time with the required "timezone" argument present.
      Probes go through the real OllamaProvider so a passing round
      exercises the exact production code path.
- [x] JSON_EXTRACT injection defined + implemented (new B.4.3a, SDD-first):
      inject_tools() now injects for JSON_EXTRACT (was pass-through);
      _extract_json() gained a raw_decode fallback scan so nested
      arguments objects parse (the old regexes could not match them).
      XML_EXTRACT/FEW_SHOT remain pass-through.
- [x] Suggested WorkerManifest generation on success: id/capabilities/
      usage-level/cost reused from an existing registry entry for the same
      model (re-check never silently narrows a worker; probe verdict wins
      on tool_protocol), context_window from /api/show's
      *.context_length (fallback: existing entry, then 8192),
      latency_class from measured probe duration, worker_role from B.4.6
      rules, tool_result_role "tool" for non-NATIVE protocols.
- [x] Worker registry write on user confirmation ([Y/n] prompt; --yes to
      skip): text-splicing writer preserves the file's hand-written
      comments -- new id appended, existing id has exactly its own block
      replaced. Verified loadable by WorkerRegistry.load_from_yaml after
      both paths.
- [x] tasker-setup --check-model <name> CLI command (plus --yes,
      --registry PATH override, --ollama-url; stub removed from wizard.py)
- [x] B.4.2 cloud-model exception (SDD-first, live-verified): the pull
      gate applies to LOCAL models only -- a signed-in server serves
      :cloud models via /api/chat even when absent from /api/tags
      (confirmed live against kimi-k2.7-code:cloud on 0.30.11), so cloud
      models are probed directly and the missing tag is informational.
- [x] tests/unit/test_readiness.py passing (28 tests, provider + HTTP fns
      mocked per B.10 -- no live Ollama calls); +7 normalizer tests
      (JSON_EXTRACT injection + raw_decode fallback), +1 provider test
- [x] Live smoke test, lfm2.5-thinking:latest (Designlab1 WSL, Ollama
      0.30.11 @ 127.0.0.1:11435): **NATIVE now SUPPORTED** -- Ollama
      returned a correct tool_calls[] for the probe (A.2b's tools[]
      rejection no longer reproduces on 0.30.11). Forced Round 2 also
      SUPPORTED live (bare-object JSON emission, 18.8s). Registry write
      validated against a scratch copy of the real registry; the REAL
      registry entry was deliberately left at lfm25 (see open decision
      below).
- [x] Live smoke test, cloud model (kimi-k2.7-code:cloud): confirmed
      native, ~1s probe, /api/show reported real context_window 262144
      (registry's hand-written entry says 128000 -- stale), roles
      [reasoning_worker, orchestrator] per B.4.6. Scratch-registry update
      preserved all comments + all 9 workers.
- [x] Bonus fix (found live by the probe): OllamaProvider's empty-content
      retry no longer fires when tool_calls[] are present -- a native tool
      call from a thinking model legitimately has empty content, and the
      old condition burned 2 extra (budgeted, if cloud) calls per native
      tool call. Regression test added.

**Open decisions from this phase (not applied to the real registry):**
- lfm2.5-local: probe says NATIVE now works on Ollama 0.30.11; registry
  stays tool_protocol: lfm25 (known-good, validated E2E 8.1-8.3). Flip to
  native only after re-validating the multi-turn tool loop end-to-end
  under native on both machines.
- kimi-k2.7-code-cloud: /api/show says context_window 262144 vs the
  registered 128000; probe-derived latency_class fast vs registered
  medium. Both would change live selection behavior -- update deliberately
  deferred to a session that owns that decision.

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

---

## Phase 8.1 -- Live Cloud-Path E2E Validation (COWORK_PROMPT task numbering)

> **Naming note:** distinct from "Phase 8.1 -- Setup Wizard (headless)" above,
> which follows SDD_ADDENDUM_PHASE8.md's numbering. This section is task 8.1
> of COWORK_PROMPT.md's PHASE 8 TASK LIST (cloud-path E2E validation) -- the
> same numbering collision already flagged in CLAUDE.md's Phase Tracker.

All evidence below was captured live on Designlab1 (GTX 1050 Ti, Ollama
0.30.11 on 127.0.0.1:11435, signed in to Ollama Cloud as Rojman1984),
2026-07-19. Environment for every run:

```bash
export TASKER_PROFILE=tier2_designlab_cloud   # new cloud-orchestrator profile
export OLLAMA_BASE_URL=http://127.0.0.1:11435 # overrides profile YAML (new)
export TASKER_LOG_LEVEL=INFO
```

### Live-path bugs found and fixed (each with regression tests)

- [x] **used_fallback never set by tiers 2/3/4** -- only
      `SingleLLMOrchestrator` (tier 1) marked NanoOrchestrator fallback
      plans; `DualLLMOrchestrator` (the live tier on Designlab1),
      `ReasoningOrchestrator`, and `CloudOrchestrator` returned fallback
      plans with `used_fallback=False`. Fixed in all three; regression
      tests `test_plan_fallback_sets_used_fallback_flag` in
      `test_orchestrator_tier2/3/4.py`.
- [x] **Session budget never constructed or recorded in production** --
      `OllamaSessionBudget` existed but `record_usage()` had zero
      production callers, and `cli/shell.py` passed hardcoded
      `slots_available=1, should_throttle=False` to `WorkerSelector`.
      Fixed: `OllamaProvider` now accepts an optional budget and records
      GPU-time units (wall-clock x `ollama_usage_level`, None billed as
      1) on every successful OLLAMA_CLOUD call
      (`compute_usage_units()`, `tasker/workers/providers/ollama.py`);
      the CLI builds the budget from the profile plan and threads live
      `concurrency_mgr.slots_available` + tick-driven throttle into the
      selector. Tests: `TestOllamaProviderBudgetRecording` (7 tests).
- [x] **SessionManager/tick() not in the CLI path; no checkpoint ever
      written during a run; `tasker resume` was a stub** -- the CLI step
      loop now calls `SessionManager.tick()` before every dispatch
      (SDD 9.1), pauses via the full SDD 9.2 flow (checkpoint with plan +
      completed-step records + budget snapshot, notifier event, PAUSED),
      and `tasker resume <id>` / `--last` performs the real SDD 9.4
      resume (fresh window, RESUMED event, continues from
      `current_step_index`, synthesizes prior + new results). Tests:
      `tests/unit/test_cli_session_wiring.py` (9 tests, incl. mid-run
      exhaustion pausing before the next step, never mid-step).
- [x] **`--policy` flag parsed but ignored** -- now resolved through
      `_POLICY_ALIASES` and applied as a mode routing-policy override
      (CLI, REPL `/policy`, and `resume --policy`).
- [x] **No OLLAMA_BASE_URL override** -- profile YAML hardcoded the port;
      Designlab1 actually serves on 127.0.0.1:11435 (systemd port.conf
      drop-in), so the live path could never connect. Env var now wins.
- [x] **tier2_designlab.yaml had no `orchestrator.model`** -- factory fell
      back to qwen3:1.7b, which is not installed on Designlab1; live
      tier-2 planning could never have worked on the machine the profile
      is for. Added `model: lfm2.5-thinking:latest`.
      (The planner_model/synthesizer_model dual-model keys remain unread
      -- known open Tier 2 bug, unchanged.)
- [x] New profile `config/profiles/tier2_designlab_cloud.yaml` -- same
      hardware, orchestrator on Ollama Cloud (`kimi-k2.7-code:cloud`,
      `compute_location: ollama_cloud`), used for cloud-path validation.
- [x] INFO logging added: slot acquire/deny/release
      (`tasker/session/concurrency.py`) and per-call budget increments
      (provider). `TASKER_LOG_LEVEL` now configures `logging.basicConfig`
      in `cli/shell.py main()`.

### Checkpoint 1 -- OllamaCloudConcurrencyManager constructed + enforcing

Every cloud call in the live CLI runs showed slot lifecycle (Pro plan, 3
slots):

```
INFO tasker.session.concurrency: OllamaCloud slot acquired (1/3 in use, plan=pro)
INFO tasker.workers.providers.ollama: OllamaCloud budget: +5.5 units (kimi-k2.7-code:cloud, 5.5s x level 1) -> 5.5/3000 session (0.2%)
INFO tasker.session.concurrency: OllamaCloud slot released (0/3 in use, plan=pro)
```

Enforcement (DEFERRED, never block/queue) proven by saturating a FREE-plan
manager (1 slot) with 2 truly concurrent real cloud calls through the
production `OllamaProvider` (scratchpad `concurrency_saturation_demo.py`):

```
INFO tasker.session.concurrency: OllamaCloud slot acquired (1/1 in use, plan=free)
INFO tasker.session.concurrency: OllamaCloud slot DENIED — all 1 slot(s) in use (plan=free)
call 1: status='success' output='OK'
call 2: status='deferred' reason='No Ollama Cloud concurrency slot available.'
```

### Checkpoint 2 -- Budget tracking increments + throttle behavior

Multi-step cloud orchestration (`tasker-cli --mode cowork "...two steps...
reasoning specialist..."`): plan (kimi cloud, +5.5u) -> step 0 routed to
`nemotron-3-ultra-cloud` via the `reasoning` capability (+46.4u = 15.5s x
level 3) -> step 1 local -> cloud synthesis (+7.2u). Budget visibly
accumulated 0 -> 59.1/3000 (2.0%) across the run.

Throttle (live, `TASKER_BUDGET_PRELOAD=2988`): tick() returned
CONTINUE_LOCAL_ONLY at 99.7% and the step loop printed
`[throttle] budget at 99.7% — routing local-biased`; heavy cloud workers
(usage_level >= 3) were dropped from selection. Observed consequences,
both by design but worth knowing: (a) a step requiring
`{reasoning, thinking}` had no eligible worker under throttle (heavy-cloud
filter runs before the capability filter, matching SDD 5.5's decision-tree
order) and failed selection cleanly; (b) selection then diverted a
`{tool_use, reasoning}` step to `claude-haiku-4-5` (direct cloud is legal
under ANY_CLOUD + throttle per SDD 9.3), which surfaced that the CLI
provider_map wires only OllamaProvider -- "No provider for anthropic".
Logged under Known Open Issues.

### Checkpoint 3 -- Pause/resume checkpoints survive a real pause

Run with `TASKER_BUDGET_PRELOAD=3050` (exhausted): planning completed,
then the tick before step 0 returned PAUSE -> full SDD 9.2 flow ran:

```
  2 step(s), used_fallback=False
[10:31:46] PAUSED: Session paused. Checkpoint: e917766c-0238-4c5f-8e71-caa8e66454fb
⏸  Session budget exhausted (101.8%) — paused before step 0.
```

Checkpoint verified on disk (`.tasker/checkpoints/e917766c-....json`):
mode=cowork, profile=tier2_designlab_cloud, current_step_index=0, full
2-step plan with capabilities, budget snapshot usage_pct=1.0177.
Then, in a **fresh process** with the preload unset:

```
$ tasker-cli resume --last
Resuming checkpoint e917766c-...  [cowork]  ...
  paused with budget at 102% (pro plan), 0/2 step(s) completed
[10:32:10] RESUMED: Session resumed from checkpoint e917766c-...
  Step 0: ... [ok] nemotron-3-ultra-cloud (40330ms, budget 4.0%)
  Step 1: ... [ok] nemotron-3-ultra-cloud (3315ms, budget 4.4%)
Synthesizing...
$3^6 = 729$ is bigger than $6! = 720$ by 9.
```

Mid-run exhaustion (step completes, pause before *next* step, SDD 9.2
"always complete the current step") is additionally covered by
`test_mid_run_exhaustion_pauses_before_next_step`.

### Checkpoint 4 -- used_fallback reported correctly

Every live run printed the flag after planning, e.g.
`2 step(s), used_fallback=False` (model plans parsed successfully in all
live runs). The True path (Nano template standing in for an unparseable
model plan) is regression-tested at tiers 1-4 and the CLI prints
`(fallback: NanoOrchestrator template — model plan unparseable)` when set.

### Suite status

- [x] Full suite green after all changes: **586 tests, OK**
      (`python -m unittest discover -s tests`) -- was 567 before this
      session (+19: 3 tier-fallback regressions, 7 provider budget,
      9 CLI session wiring).

### Known Open Issues added this session

- [ ] CLI `provider_map` wires only OllamaProvider; selection can legally
      choose Anthropic/OpenAI/Fugu workers (ANY_CLOUD modes, esp. under
      throttle) and then fails with "No provider for <x>". Either wire the
      remaining providers into `_build_pipeline()` or filter unroutable
      workers out before selection.
- [ ] Cloud-orchestrator plan/synthesize calls are not gated by
      SessionManager.tick() -- a fully exhausted budget still permits the
      planning call (observed live: +3.1u at 101.8%). Deliberate for now:
      a checkpoint without a plan cannot resume. Revisit if planning cost
      becomes material.
- [ ] Budget state does not persist across process restarts (SDD 5.10 says
      it should) -- each CLI invocation starts a fresh 5-hour window; only
      the checkpoint's BudgetSnapshot is persisted. Real Ollama Cloud
      server-side limits are unaffected (they are enforced remotely); this
      only weakens local throttle fidelity between invocations.

---

## Phase 8.2 -- tier4_cloud.py Reachability (COWORK_PROMPT task numbering)

**Verdict: Tier 4 was unreachable from every mode x profile combination**,
through three independent gates, each confirmed by code reading + tests:

1. **Profile gate (by design, kept):** standard machine profiles cap
   `orchestrator.tier_max` at 2 (Designlab1) / 1 (TASKER-P1);
   `effective_tier = min(mode, profile)` can therefore never exceed 2 on
   either machine. This is the intended hardware ceiling for the *local*
   tiers and was left unchanged.
2. **Mode gate (SDD gap, fixed):** no mode allowed tier 4 -- max was 3
   (cowork/research per SDD 5.1) -- so even a tier-4 profile resolved to 3.
   The SDD defined Tier 4 in the ladder (5.3) but nothing could ever
   select it. SDD updated first per dev rules: 5.1 COWORK now "2-4", new
   5.3 "Tier 4 activation" paragraph (explicit configuration opt-in, never
   hardware detection; local compute_location degrades to Tier 3 per
   10.3). `config/modes/cowork.yaml` orchestrator_tier_max: 3 -> 4
   (effective tier unchanged on both standard machine profiles).
3. **Factory gate (bug, fixed):** `build_orchestrator()` returned
   `ReasoningOrchestrator` for any tier >= 3 and never constructed
   `CloudOrchestrator` (docstring deferred to "callers" that did not
   exist). Now: tier >= 4 with `orchestrator.compute_location:
   ollama_cloud` -> `CloudOrchestrator(ollama_provider, manifest,
   OLLAMA_CLOUD_OK)`; tier >= 4 with a local orchestrator location
   degrades to Tier 3 with a WARNING. Because CloudOrchestrator routes
   plan/synthesize through `provider.execute()`, the Phase 8.1 wiring
   (concurrency slots + budget units per orchestration call) applies to
   Tier 4 automatically.

- [x] New opt-in profile `config/profiles/tier4_cloud_hybrid.yaml`
      (tier_max: 4, `kimi-k2.7-code:cloud`, compute_location:
      ollama_cloud) -- the only shipped path to Tier 4.
- [x] Regression tests (`tests/unit/test_orchestrator_factory.py`, +5 net):
      `test_tier4_with_cloud_orchestrator_location_returns_cloud`,
      `test_tier4_with_local_orchestrator_degrades_to_reasoning`
      (replaces the old `test_tier4_falls_back_to_reasoning`, which
      codified the unreachable behavior), and `TestTier4Reachability`
      driving the REAL shipped YAMLs: (tier2_designlab x cowork) -> 2/Dual,
      (tier1_tasker x cowork) -> 1/Single, (tier4_cloud_hybrid x cowork)
      -> 4/Cloud, (tier4_cloud_hybrid x chat) -> 1 (mode ceiling holds).
- [x] Live confirmation (Designlab1, 2026-07-19):

```
$ TASKER_PROFILE=tier4_cloud_hybrid tasker-cli --mode cowork "...91 prime?..."
[cowork] Planning with CloudOrchestrator...
  2 step(s), used_fallback=False
  Step 0: Reason about whether 91 is prime ... [ok] nemotron-3-ultra-cloud (4755ms, budget 0.6%)
  Step 1: State the answer in one sentence ... [ok] lfm2.5-local (32348ms, budget 0.6%)
Synthesizing...
**91 is not prime because it can be factored as 7 x 13.**
```
      Plan (+3.4u kimi L1), reasoning step on cloud (+14.3u nemotron L3),
      writing step on LOCAL hardware, cloud synthesis (+3.8u) -- the
      exact "cloud orchestrator, local workers" hybrid SDD 5.3 specifies,
      with slot acquire/release + budget increments logged on every
      orchestration call.
- [x] Full suite green: **591 tests, OK** (was 586 after 8.1).

---

## Phase 8.3 -- Tool-Loop Non-Termination Guard (COWORK_PROMPT task numbering)

Two guard conditions so a runaway tool loop cannot burn Ollama Cloud budget
(SDD 5.7a updated first, per dev rules):

- [x] **Hard iteration cap (verified, already correct):** `run_tool_loop`'s
      `max_turns=5` is a hard cap on provider calls -- the loop structure
      increments `turn` before each `provider.execute()` and breaks at the
      cap. Existing test asserts `len(provider.calls) == _MAX_TOOL_TURNS`
      exactly; updated to request a *different* command each turn so it
      keeps exercising the cap now that identical requests terminate
      earlier (see below).
- [x] **Repeated-identical-call detection (new):** if a turn requests the
      identical tool-call set (tool names + arguments, order-sensitive,
      compared via sorted-key JSON) as the immediately preceding turn, the
      loop terminates at that turn with a WARNING, without executing the
      duplicates and without spending another provider call. Termination
      contract matches the max_turns exit (last result returned, pending
      requests survive into `tool_results`). Non-consecutive repeats
      (ls -> pwd -> ls) are deliberately allowed -- re-checking state later
      in a task is legitimate.
- [x] Unit tests (`tests/unit/test_tool_loop.py`, 10 -> 14):
      `test_identical_consecutive_calls_terminate_early` (2 provider calls
      instead of 5, duplicate never executed),
      `test_same_tool_different_args_is_not_a_repeat`,
      `test_nonconsecutive_repeat_is_allowed`,
      `test_identical_multi_call_set_terminates_early` (whole-set
      comparison), plus the hardened max_turns test.
- [x] Full suite green: **595 tests, OK** (was 591 after 8.2).

Real-world motivation: the 7.5.4-7.5.6 session live-observed
`lfm2.5-thinking` hallucinating a nonsensical tool call and "never
concluding across repeated turns, exhausting run_tool_loop's max_turns=5"
-- on a cloud worker each of those wasted turns would have been a budgeted
call; the guard now stops that pattern at turn 2.

---

## API Server Launchability -- `tasker-api` (2026-07-19)

Scoped task: make the existing OpenAI-compat API server
(`tasker/api/server.py`, built in Phase 7) actually launchable as a
standalone process so a WebUI can connect. Not part of the
SDD_ADDENDUM_PHASE8 numbering -- a standalone launch/ops task.

- [x] `tasker/api/server.py:main()` added, wired the same way as
      `cli/shell.py`'s `main()`/`_build_pipeline()`: `TASKER_PROFILE` env
      resolution (default `tier1_tasker`), `OLLAMA_BASE_URL` env override
      of the profile's Ollama URL, `provider_map` keyed by `ProviderType`
      with a shared `OllamaSessionBudget` + `OllamaCloudConcurrencyManager`
      on the `OllamaProvider`, and a hardware-cache GPU availability
      cross-check on the worker registry (SDD_ADDENDUM_7.5.md A.3.4,
      skipped if `tasker-hardware detect` has never run).
- [x] `--host`/`--port` (default `127.0.0.1:8555`) and `--mode` (restrict
      the server to one of the 5 modes; default accepts all, selected
      per-request via the `model` field) flags.
- [x] `create_app()` extended with `provider_map`, `concurrency_mgr`, and
      `allowed_modes` kwargs (all optional, default `None` -- existing
      test call sites unaffected). `_step_fn` (test override) still takes
      priority over the new real-dispatch path.
- [x] `_make_live_step_fn()`: real `WorkerSelector.select()` ->
      `WorkerTask` -> `run_tool_loop()` dispatch for `CoworkRunner`,
      mirroring `cli/shell.py`'s `_execute_steps()` for a single-step
      request. A worker failure now returns HTTP 500 with the reason
      instead of propagating an uncaught exception (previously
      `_handle_completions` had no try/except around `runner.run()`).
- [x] **Bug fixed while wiring this:** `_stub_plan()`'s step description
      was `f"Execute: {task[:80]}"` -- fine as a display-only label when
      the server only ever echoed a stub string, but the moment a real
      `step_fn` uses `step.description` as the worker's actual
      instruction, that truncation silently cut off any prompt over 80
      characters. Now carries the full task text. Regression test added
      (`test_live_dispatch_long_prompt_not_truncated`, 200-char prompt).
- [x] `pyproject.toml`: `tasker-api = "tasker.api.server:main"` script
      entry added. Reinstalled with `pip install -e .` inside the venv
      (confirmed `which python`/`which pip` resolved to `.venv/bin/*`
      before running, per explicit instruction this session).
- [x] `tests/integration/test_api_server.py`: +12 tests (15 -> 23) --
      live-dispatch success/failure/no-truncation/stub-fallback/
      step_fn-override-priority, plus `allowed_modes` filtering on both
      `/v1/models` and `/v1/chat/completions`. All mocked (fake provider),
      no live Ollama calls per the existing test-suite convention.
- [x] Full suite green: **638 tests, OK** (was 630 after addendum 8.2).
- [x] **Live smoke test** (Designlab1 WSL, Ollama 0.30.11 @
      127.0.0.1:11435 -- confirmed reachable, never started per CLAUDE.md's
      binding Ollama server rules): started
      `OLLAMA_BASE_URL=http://127.0.0.1:11435 tasker-api --port 8555` in
      the background. `GET /v1/models` -> 200, all 5 `tasker/<mode>` ids.
      `GET /v1/workers` -> 200, real registry (`lfm2.5-local` etc.).
      `POST /v1/chat/completions` with `model: tasker/chat` and a real
      user prompt -> 200, correct `chat.completion` OpenAI shape (`id`
      prefixed `chatcmpl-`, `choices[0].message.role == "assistant"`,
      `finish_reason: "stop"`), content is a genuine answer from the local
      `lfm2.5-thinking` worker (routed through `WorkerSelector` ->
      `run_tool_loop` -> `OllamaProvider.execute()`, not the stub echo) --
      zero cloud spend, ~44s end-to-end (thinking-model latency, matches
      prior sessions' measurements). Server stopped cleanly afterward
      (`kill <pid>`; `web.run_app` shuts down without orphaned processes).
      Startup banner print given `flush=True` after the first smoke test
      showed it buffering indefinitely under `nohup`.

**Known open issues (not fixed this session -- out of scope):**
- `_handle_completions` still builds a fresh per-request
  `OllamaSessionBudget`/`SessionManager` (unrelated to the provider's own
  shared budget used for GPU-time unit accounting) -- so pause/resume
  checkpoint budget snapshots via the API don't reflect the server's
  actual cumulative Ollama Cloud usage. Pre-existing architecture, not
  introduced or altered by this task.
- Still dispatches through `_stub_plan()` (one step covering the whole
  request), not a real orchestrator-planned `ExecutionPlan` -- wiring the
  orchestrator tier into the API path is explicitly out of scope for this
  launchability task ("no new orchestrator work").
- No WebUI container/reverse-proxy config -- explicitly out of scope.

---

## Rudimentary TUI REPL -- `tasker/tui/app.py` (2026-07-19)

Scoped task: replace the Phase 8.1 `tasker` stub ("coming in Phase 8.3")
with an actually-usable rudimentary interactive REPL, ahead of the full
Textual TUI (SDD_ADDENDUM_PHASE8.md B.5, still Phase 8.3-8.5, not yet
started). SDD-first: B.5.0 added to the addendum documenting this as a
deliberate scoped deviation, same pattern as the wizard's Step 7 note.

- [x] `tasker/runtime/dispatch.py` (new) -- extracted the pipeline-
      building and dispatch logic that used to live only in
      `cli/shell.py` (`_build_pipeline`, `_build_session`,
      `_execute_steps`, `_run_task`, `_resume_task`,
      `_serialize_step_result`, `_deserialize_step_result`,
      `_resolve_policy_override`, `_POLICY_ALIASES`,
      `_DEFAULT_STORE_DIR`, `_REGISTRY_YAML`) plus two new shared
      helpers (`_load_registry()` -- registry load + hardware-cache GPU
      cross-check, previously inlined in `cli/shell.py`'s `main()`;
      `_print_workers()`/`_print_checkpoints()` -- previously
      `cli/shell.py`'s `_cmd_workers`/`_cmd_checkpoints`). `cli/shell.py`
      re-imports every name unchanged (same names, including the leading
      underscore) so its own tests
      (`tests/unit/test_cli_session_wiring.py` imports 4 of these
      directly from `cli.shell`) and its own module namespace are
      unaffected by the move -- zero behavior change for the existing
      CLI/REPL, confirmed by the full suite staying green through the
      refactor before any TUI code was added.
- [x] `_run_task()` gained an optional `pipeline=` keyword (default
      `None`, fully backward compatible) so a caller can pass in a
      pre-built pipeline instead of always building a fresh one --
      exists solely to let the TUI REPL below implement real per-mode
      budget accumulation across turns.
- [x] `tasker/tui/app.py` -- real REPL replacing the stub. Commands:
      `/mode [chat|code|cowork|research|secure]` (get/set, validated,
      reflected in the prompt: `tasker (mode)>`), `/workers`, `/budget`,
      `/resume <id>|--last`, `/checkpoints`, `/help`, `/quit`/`/exit`.
      Non-slash input dispatches as a task in the active mode through
      the real orchestrator -> provider pipeline (same path as
      `cli/shell.py`/`tasker-cli`).
- [x] **Per-mode budget persistence within one REPL session** (the
      genuinely new piece of behavior here, not just plumbing reuse):
      each mode lazily builds one pipeline on first use and reuses it
      across turns in that mode, so `/budget` shows real accumulating
      usage instead of resetting every turn (unlike `cli/shell.py`'s
      CLI and `tasker/api/server.py`'s API, both one-shot-per-call by
      design). Honestly scoped and documented as per-mode, not the true
      single per-account budget (SDD 5.10) -- switching modes does not
      share usage. If a mode's cached pipeline ends up PAUSED (budget
      exhausted), it is evicted from the cache so the next task in that
      mode starts a fresh window rather than sitting in
      `SessionManager`'s `HOLD` state forever with no in-process way to
      resume (real resume is `/resume`, which always builds fresh per
      SDD 9.4, unaffected by this cache).
- [x] `tests/unit/test_tui_app.py` (new, 30 tests): `_dispatch`'s
      caching/eviction contract (build-once/reuse, per-mode isolation,
      config-error non-caching, pause eviction, running-session
      retention), `_print_budget` (no-pipeline config-only path,
      config-error handling, live-pipeline stats incl. microsecond
      stripping from the remaining-time display), every slash command
      driven through `_repl()` via a mocked `input()` sequence (mode
      switch + prompt update, invalid mode, all 5 modes, workers/
      checkpoints/budget delegation, help text completeness, unknown
      command, resume with no checkpoints / `--last` / explicit id,
      non-slash dispatch, the `pipelines` dict identity persisting
      across turns within one `_repl()` call, KeyboardInterrupt/EOF
      exit, empty-line handling, startup banner content), and `main()`'s
      wiring. All mocked at the `tasker.tui.app` import boundary -- no
      live Ollama calls, matching this project's established convention.
- [x] `pyproject.toml`: `tasker = "tasker.tui.app:main"` already pointed
      here from the Phase 8.1 stub -- no entry-point change needed.
      Reinstalled with `pip install -e .` anyway to pick up the new
      `tasker/runtime/` package (venv confirmed via `which python`/
      `which pip` first, per this session's standing instruction).
- [x] Full suite green: **668 tests, OK** (was 638 after the API server
      task; +30 net: the new TUI test file, no regressions in the moved
      dispatch logic).
- [x] **Live smoke test** (Designlab1 WSL, Ollama 0.30.11 @
      127.0.0.1:11435 -- confirmed reachable, never started, per
      CLAUDE.md's binding Ollama server rules): launched `tasker` with a
      scripted stdin sequence (`/budget` -> chat task -> `/budget` ->
      `/mode cowork` -> cowork task -> `/budget` -> `/quit`).
      - `/budget` before any task: correct config-only message
        (`profile=tier1_tasker plan=pro`, "No tasks run yet").
      - Chat task ("Say hello in exactly three words.") -> real
        `SingleLLMOrchestrator` plan (1 step), real local `lfm2.5-local`
        dispatch (7.3s), real synthesis, genuine (if model-quirky)
        answer. Zero cloud spend.
      - `/budget` after: **real live usage** (`0.0/3000 units, 0.0%,
        state=running`) -- correctly 0 because local calls don't
        consume Ollama Cloud budget by design (SDD 3.2); confirms the
        cached pipeline round-trips correctly, not just that it builds.
      - `/mode cowork` -> prompt updates to `tasker (cowork)>`.
      - Cowork task ("List the files in the current directory using a
        bash command.") -> real plan, real `run_tool_loop` dispatch
        against `lfm2.5-thinking` (bash tool) -- **the Phase-8.3
        tool-loop non-termination guard fired live** (identical
        consecutive tool call detected on turn 2/5, terminated early
        with the expected WARNING) after one empty-content retry, then
        synthesis produced a real answer describing the `ls` output.
        Read-only task -- confirmed no stray files were created
        (`git status` clean aside from this session's own edits).
      - Final `/budget`: real live state again, cowork's own separate
        window (`resets in 4:58:45` vs. chat's independent
        `4:58:40` moments earlier) -- correctly demonstrates the
        documented per-mode-not-global scoping.
      - `/quit` exited cleanly.

**Known open issues / open decisions (documented, not fixed this
session):**
- Per-mode (not per-account) budget scoping in the REPL, as described
  above -- a real architectural simplification, not a bug, but should be
  revisited if/when the true SDD 5.10 single-account model needs to be
  reflected in an interactive session.
- No `--mode`/other CLI flags on `tasker` itself (always starts in
  `chat`) -- not requested this session; trivial to add later if wanted.
- The eventual Textual TUI (B.5.1-B.5.4) supersedes this REPL; this
  REPL's `_repl()`/`_dispatch()` logic is not expected to be reused by
  the Textual screens (different interaction model entirely), only
  `tasker/runtime/dispatch.py` is expected to carry forward.

---

## Phase 8.3 -- Textual TUI Skeleton (2026-07-19)

SDD_ADDENDUM_PHASE8.md B.5.1-B.5.4. Supersedes the rudimentary REPL
above -- `tasker` now launches a real full-screen Textual app instead.

**SDD-first reconciliation (before any code):** the addendum had three
mutually-inconsistent claims about which sub-phase owns SetupWizardScreen
and ModelSelectorScreen -- B.5.2's screen-list comments said "Phase 8.2"
for SetupWizardScreen (wrong regardless -- 8.2 was the headless readiness
checker, not a UI screen) and "Phase 8.3" for ModelSelectorScreen; B.8's
roadmap table bundled SetupWizardScreen into 8.3's one-line description;
B.11's granular, test-gated checklist scoped 8.3 to the skeleton alone
and bundled SetupWizardScreen with ModelSelectorScreen under 8.4. Asked
the user to confirm which was authoritative rather than guessing;
confirmed B.11 (the detailed, phase-gated spec) wins, matching this
project's established one-atomic-phase-at-a-time pattern from 8.1/8.2.
B.8's table and B.5.2's comments were corrected to match B.11 --
8.3 = skeleton only, 8.4 = SetupWizardScreen + ModelSelectorScreen.

- [x] `textual>=0.70.0` already in `pyproject.toml` (added in an earlier
      session) -- confirmed installed version 8.2.8 is API-compatible
      (verified `ListView.Selected.index`, `Static.content`,
      `App.run_test()`/`Pilot`, `App.export_screenshot()` directly
      against the installed package rather than assuming from memory).
- [x] `tasker/tui/app.py` -- real `TuiApp(App)` + `main()`, replacing the
      Phase 8.1 stub and the one-session REPL (B.5.0). `on_mount()`
      pushes `WelcomeScreen`. The REPL's `_repl()`/`_dispatch()`
      functions are gone -- they were documented from the start as a
      temporary interim, not something meant to survive this phase; for
      an interactive multi-turn session in the meantime, `tasker-cli
      shell` still works (a separate, simpler REPL, unaffected by this
      change). `tasker/runtime/dispatch.py` (the actually-reusable part)
      is untouched and carried forward as planned -- nothing here
      duplicates it, and it's the piece HarnessPanel (8.5) and
      SetupWizardScreen/ModelSelectorScreen (8.4) will build on.
- [x] `tasker/tui/screens/welcome.py` -- `WelcomeScreen`: status bar +
      titled menu (`ListView`) with all 5 B.5.2 items (Setup Wizard,
      Model Selector, Run Task, View Sessions, Daemon) plus Quit, so 8.4/
      8.5 don't need a second navigation-layout change. Only Quit is
      wired this phase (`q` binding + click); the other four show an
      inert notice naming the headless command that covers the same
      ground today (`tasker-setup`, `tasker-setup --check-model`,
      `tasker-cli`, `tasker-cli checkpoints`) instead of navigating
      anywhere -- Daemon's notice cites B.6's reserved-placeholder rule.
- [x] `tasker/tui/widgets/status_bar.py` -- `HardwareStatusBar`: reactive
      one-line bar per B.5.4's bracketed format
      (`[CPU: Nc/NGB] [GPU: ...] [Tier: N / strategy]  [Model: ...]
      [Session: ...]`). Reads the machine-local cache directly (never a
      live `detect_gpu()`/`psutil` call -- A.3.1 convention every other
      entry point follows), including its pre-computed
      `computed_profile.orchestrator_tier_max`/`load_strategy` block
      (SDD_ADDENDUM_7.5.md A.3.3) rather than re-deriving a
      `HardwareProfile` a second time via `load_cached_detection()`.
      `active_model`/`session_state` are reactive placeholders -- wired
      to real values only once ModelSelectorScreen (8.4) and HarnessPanel
      (8.5) exist to set them.
- [x] `tasker` entry point already pointed to `tasker.tui.app:main`
      (from the Phase 8.1 stub) -- no `pyproject.toml` change needed.
      `tasker-cli` already existed too. Reinstalled with
      `pip install -e .` anyway (venv confirmed via `which python`/
      `which pip` first).
- [x] `tests/unit/test_tui_status_bar.py` (new, 7 tests):
      `refresh_hardware()` against a mocked raw cache -- no-cache
      fallback, GPU/no-GPU formatting, ram_gb rounding (regression for
      the raw-float display bug caught live during manual testing, see
      below), missing-`computed_profile` fallback, `render()` combining
      all three reactive fields.
- [x] `tests/unit/test_tui_welcome_screen.py` (new, 12 tests) and
      `tests/unit/test_tui_app.py` (new, 4 tests, replacing the deleted
      REPL test file of the same name) -- driven headlessly through
      Textual's `App.run_test()`/`Pilot` (no real terminal needed):
      status bar present, correct menu item count/ids, title text, each
      non-Quit item's notice text and phase reference, Quit
      click + `q` binding both exit the app, `TuiApp` pushes
      `WelcomeScreen` on mount, `main()` calls `TuiApp().run()`.
- [x] Full suite green: **659 tests, OK** (was 668 after the REPL
      session; net -9 = -30 deleted REPL tests + 21 new TUI tests).
- [x] **Manual verification, Designlab1** (per B.8's requirement --
      Textual rendering can't be fully unit-tested without a terminal):
      (1) `tasker` launched in a real pty via `script -qc "timeout 3
      tasker" /dev/null` -- ran the full 3s with no crash/traceback
      (`timeout`'s SIGTERM exit code 124, i.e. still running, not a
      failure). (2) Real (unmocked) headless screenshots captured via
      `App.export_screenshot()` against this machine's actual cached
      hardware detection and published as an artifact for visual review
      -- confirmed real values on screen (12-core CPU, GTX 1050 Ti
      4096MB, tier 2, resident) and a real menu-selection notice ("Setup
      Wizard: Coming in Phase 8.4..."). Bug caught live during this step
      and fixed before finalizing: `ram_gb` was displaying as an
      unrounded float (`15.307815551757812`) -- rounded to whole GB, with
      a regression test added.
- [ ] Manual verification, TASKER-P1 (or WSL2) -- not run this session,
      no access to that machine from here; unchanged follow-up note from
      every prior phase that needed it.

**Open decisions / known issues:**
- `active_model`/`session_state` on `HardwareStatusBar` are inert
  placeholders until 8.4 (model selection) and 8.5 (harness session
  state) exist to drive them.
- No dark/light theme decision made explicitly -- Textual's own default
  theme applies; revisit once the addendum's visual direction (if any)
  is specified.

## `tasker-cli shell` bug fixes -- provider wiring + REPL UX (2026-07-20)

Live user testing session (local-only, zero cloud spend). One P1
correctness bug plus two REPL UX papercuts, all found interactively.

- [x] **P1 fix:** `WorkerRegistry.apply_provider_availability(provider_map)`
      (`tasker/workers/registry.py`) -- marks a worker `available=False`
      (never dropped, logged reason, same pattern as
      `apply_gpu_availability`) when its declared `provider` has no
      entry in the active `provider_map`. Root cause: `tasker-cli shell`
      only wires `OllamaProvider`, but `WorkerSelector` had no visibility
      into that -- it could (and live-testing showed it did) select
      `fugu-ultra`, which then failed mid-dispatch with `No provider for
      fugu`, ending the whole run in "No results to synthesize."
      instead of falling back to an available Ollama worker.
- [x] Wired into `tasker/runtime/dispatch.py`'s `_run_task()` and
      `_resume_task()` -- called right after the pipeline (and its
      `provider_map`) is built, before `registry.list_all()` is handed to
      the orchestrator for planning, so an unwired-provider worker is
      excluded from both planning and selection, not just selection.
- [x] REPL UX: unknown-command handler now suggests the nearest command
      (`cli/shell.py:_suggest_command()`). A bare mode name is
      special-cased first (`/chat` -> `did you mean: /mode chat?`,
      matching the actual likely intent) ahead of a generic `difflib`
      fuzzy match for real typos (`/wrkers` -> `/workers?`).
- [x] REPL UX: interactive shell now defaults to quiet logging.
      `main()`'s default level dropped from `WARNING` to `ERROR` so
      plumbing warnings (e.g. the new provider-availability log lines)
      don't interleave with the chat flow; a new `--verbose` flag
      restores `WARNING`; `TASKER_LOG_LEVEL` (when explicitly set) always
      wins over both, unchanged from before.
- [x] Bug fixed in the same pass while adding `--verbose`:
      `_first_positional()` treated every `--flag` token as if it took a
      value, so `--verbose` (a boolean flag) silently swallowed the next
      real token (the task string or a subcommand like `workers`) as its
      "value". Fixed with an explicit `_BOOL_FLAGS` set.
- [x] Tests: `tests/unit/test_worker_registry.py` (+5,
      `TestApplyProviderAvailability`), `tests/unit/test_dispatch_provider_wiring.py`
      (new, 2 tests -- drives the real `_run_task()`/`_resume_task()`
      with a fake orchestrator + fake provider, `CAPABILITY_FIRST` policy
      so the excluded worker would otherwise win selection), 
      `tests/unit/test_cli_shell.py` (new, 11 tests -- `_suggest_command`,
      `_first_positional` boolean-flag handling, `--verbose`/
      `TASKER_LOG_LEVEL` logging-level precedence).
- [x] Full suite green: **677 tests, OK** (was 659; +18 net).
- [x] Live smoke test, Designlab1 (local-only, zero cloud spend --
      slash-command testing only, no chat/tool dispatch): `tasker-cli
      shell`, typed `/chat` -> `Unknown command: /chat  (did you mean:
      /mode chat?)`; typed `/wrkers` -> `Unknown command: /wrkers  (did
      you mean: /workers?)`; confirmed no plumbing warnings appear by
      default.

**Open decisions / known issues:** none new. The provider-wiring gap
this fixes is the same one flagged as an open issue since the Phase 8.1
E2E session ("CLI `provider_map` wires only OllamaProvider; `ANY_CLOUD`
selection can legally pick Anthropic/OpenAI/Fugu workers") -- this
change makes that condition *safe* (excluded up front, never a silent
mid-run failure) but does not itself wire the other three providers;
that remains open if/when Anthropic/OpenAI/Fugu support is needed live.

## Cowork honesty + plan-parse resilience bug fixes (2026-07-20)

Second P1 from Roland's live cowork test (transcript in his shell): task
"create a text file with hello from tasker! and provide the path"
produced NO file, but the answer claimed "verified at example.txt".
Three scoped fixes, all local-only, zero cloud spend.

- [x] **Fix 1 -- plan-parse resilience:** `plan_with_repair()`
      (`tasker/orchestrator/_parse.py`) tries, in order, before falling
      back to NanoOrchestrator: (a) parse the raw response as-is, (b) a
      tolerant text-repair pass for common LFM2.5 quoting damage --
      markdown code fences, trailing commas, single-quoted tokens -- no
      extra model call, (c) exactly one re-ask with the specific parse
      error appended to the original prompt. Returns `None` only if all
      three fail, at which point the caller's existing NanoOrchestrator
      fallback applies unchanged. Wired into all four tiers that call
      `parse_plan()`: `tier1_single.py`, `tier2_dual.py`,
      `tier3_reasoning.py`, `tier4_cloud.py`.
- [x] **Fix 2 -- fallback carries real intent:** `NanoOrchestrator`'s
      templates (`tasker/orchestrator/tier0_rules.py`) now embed the
      actual task text into every step description (`f"{desc}: {task}"`)
      instead of a purely generic label ("Answer the task"). Roland's run
      lost "create a text file" to the generic template; the step
      description itself now carries the real wording, so
      `narrow_bundle_to_step()`'s FIRST keyword match attempt already has
      real signal rather than depending entirely on its `original_task`
      second-chance argument being correctly threaded through by every
      caller.
- [x] **Fix 3 -- honesty guard:** `check_side_effect_honesty()`
      (new `tasker/tools/honesty.py`) -- a dual-signal heuristic (a
      side-effect verb like "created"/"wrote"/"ran" combined with an
      object noun like "file"/"command"/"path", or a filename-shaped
      token) flags a step's output when it claims a side effect but
      `tool_results` is empty (no tool actually ran). The output is
      rewritten to lead with `[unverified] worker claimed side effects
      but used no tools. Original claim: <original>`, never presented to
      synthesis as a plain success. Wired into
      `tasker/runtime/dispatch.py`'s `_execute_steps()` immediately after
      `run_tool_loop()` returns, before the result reaches
      `results`/`completed_records` (so a resumed session's replay also
      sees the honest version).
- [x] Tests: `tests/unit/test_plan_repair.py` (new, 13 tests --
      `_tolerant_repair`, `_plan_parse_error`, `plan_with_repair`'s full
      ladder including "exactly one re-ask, never loops"),
      `tests/unit/test_honesty.py` (new, 9 tests -- flags file/command
      claims with zero tool calls, does not flag a real tool-backed
      claim, does not flag plain chat answers or generic "successfully"
      language alone), `tests/unit/test_orchestrator_nano.py` (+2 --
      fallback step descriptions carry the real task text, single- and
      multi-step templates), `tests/unit/test_orchestrator_single.py`
      (+1 -- a real orchestrator recovers a plan via exactly one re-ask
      before falling back), `tests/unit/test_cli_session_wiring.py`
      (+1 -- `_execute_steps()` rewrites an unverified claim before it
      reaches `results`/`completed_records`).
- [x] Full suite green: **703 tests, OK** (was 677; +26 net -- includes
      one test-file fix during authoring, no regressions).
- [x] **Live re-run of Roland's exact task** (Designlab1, WSL Ollama
      127.0.0.1:11435, `lfm2.5-thinking:latest`, cowork mode, scratch
      cwd, zero cloud spend): `tasker-cli --mode cowork "create a text
      file with hello from tasker! and provide the path"`. This run's
      planner JSON actually parsed on the first attempt (only a harmless
      capability string, `"tasker!"`, got dropped -- misread from the
      task wording, not a parse failure, so Fix 1/2's ladder wasn't
      exercised by this particular run). The tool loop's existing
      non-termination guard correctly stopped a duplicate `file_write`
      call on turn 2, but turn 1's call had already executed for real --
      `text_file.txt` was created on disk with content `hello from
      tasker!`, and the synthesized answer ("The text file has been
      created at text_file.txt.") matched reality. The honesty guard
      correctly left it unflagged, since a tool call really did run.
      **A real file was produced and the answer was truthful** -- the
      exact bar this session's task set. Scratch directory cleaned up
      after verification.

**Open decisions / known issues:** none new. Fix 1's re-ask ladder was
not live-exercised by the H11.2 re-run specifically (that run's planner
JSON parsed on the first try) -- its coverage is unit-level
(`test_plan_repair.py`, `test_orchestrator_single.py`'s re-ask test)
plus the fact that it sits in the exact code path every tier's `plan()`
already calls unconditionally.

## CHAT mode direct dispatch + /model + /effort + honesty-guard gating (2026-07-20)

Third live bug this day, from Roland's own chat-mode test (one dispatch,
three issues). Local only, zero cloud spend.

- [x] **SDD-first:** new SDD 5.3a "CHAT Mode Direct Dispatch" documents
      the bypass rule (CHAT never calls `plan()`/`synthesize()`), the
      conversation-history ownership model (REPL-session-scoped,
      in-memory only, no checkpoint/resume involvement), and the
      `/model`/`/effort` worker-selection contract. SDD 7.6's REPL
      command list updated with `/model`/`/effort` and `/status`'s new
      fields.
- [x] **Fix 1 -- CHAT direct dispatch:** new `_run_chat_task()`
      (`tasker/runtime/dispatch.py`) makes exactly one `run_tool_loop()`
      call to the chat worker with the user's raw message as
      `WorkerTask.instruction` and the REPL session's running
      conversation history as `WorkerTask.context["messages"]` -- no
      orchestrator `plan()`/`synthesize()` calls at all. Root cause
      fixed: the worker was previously receiving a *planner-generated
      step description* instead of the user's actual message (pure
      hallucination artifact of round-tripping a one-line greeting
      through a JSON planning call), and three sequential LLM calls took
      ~56s to first response. `cli/shell.py`'s `_repl()` now owns a
      `chat_history: list[dict]` that accumulates real turns across the
      session and routes chat-mode input through `_run_chat_task()`
      while every other mode is unaffected (still the full
      plan/execute-steps/synthesize pipeline via `_run_task()`). The
      one-shot CLI path (`tasker-cli --mode chat "<msg>"`) also uses
      `_run_chat_task()`, with a fresh empty history per invocation
      (multi-turn only makes sense within one REPL session).
- [x] **Fix 2 -- `/model` and `/effort`:** default chat worker is the
      always-loaded local model (`lfm2.5-local`, `DEFAULT_CHAT_WORKER_ID`
      in `dispatch.py`). `/model <worker_id>` pins an exact worker,
      always winning over everything else. `/effort <low|med|high>` (REPL
      default `med`) re-selects via `WorkerSelector` using
      `SPEED_OPTIMIZED`/`COST_OPTIMIZED`/`CAPABILITY_FIRST` respectively
      when no `/model` is pinned -- reusing existing selection/ranking
      logic instead of hardcoding a "stronger model" id, so it stays
      correct as the registry changes. `/status` now shows
      `chat_model=...` and `chat_effort=...`.
- [x] **Fix 3 -- honesty guard over-firing:** `check_side_effect_honesty()`
      (`tasker/tools/honesty.py`) gained a `*context_texts` gate -- the
      guard now only fires when the *request itself* (task and/or step
      description) implied a side effect, not merely because the
      worker's reply happened to contain file/command-shaped words. Root
      cause of the false positive: a plain "Hello" got a friendly reply
      offering "let me know if you'd like me to run any commands or
      create files" -- an offer, not a claim, but the old heuristic only
      looked at the answer's wording and had no way to tell the
      difference. `_execute_steps()`'s call site now passes both `task`
      and `step.description` as context; `_run_chat_task()` passes
      `task`. No `context_texts` at all disables the guard (safer
      default than firing blind). Also fixed while gating: the verb set
      was missing base/present-tense forms ("create", "write", "run",
      etc. -- only past-tense "created"/"wrote" were present), which
      would have silently defeated the gate on present-tense task
      wording like "create a text file...".
- [x] Tests: `tests/unit/test_chat_dispatch.py` (new, 12 tests --
      `_select_chat_worker`'s full selection ladder, `_run_chat_task`'s
      raw-message/no-orchestrator-calls/history-accumulation/
      failure-doesn't-poison-history behavior), `tests/unit/
      test_cli_shell.py` (+11 -- `/model`, `/effort`, `/status`, and
      chat-vs-other-mode dispatch routing, driven through `_repl()`
      directly with a scripted `input()` sequence), `tests/unit/
      test_honesty.py` (+4 -- the greeting false-positive regression, the
      no-context-disables-the-guard default, falsy-context handling,
      multi-context-text gating).
- [x] Full suite green: **730 tests, OK** (was 703 after the previous
      bug-fix session earlier the same day; +27 net -- includes the
      honesty-guard gating fix's own +4, counted once).
- [x] **Live acceptance** (Designlab1, WSL Ollama 127.0.0.1:11435,
      `lfm2.5-thinking:latest`, zero cloud spend): `tasker-cli --mode
      chat "Hello"` answered conversationally in **4.24s real time**
      (well under the 10s bar) with zero warnings under default quiet
      logging, and none beyond pre-existing unrelated logs even at
      `TASKER_LOG_LEVEL=WARNING` -- no `[unverified]` honesty-guard
      warning. Multi-turn history live-verified through `tasker-cli
      shell`: "My name is Roland." then "What is my name?" produced a
      reply correctly referencing "Roland". `/status` showed
      `chat_model=lfm2.5-local (default)  chat_effort=med`.

**Open decisions / known issues:** none new. CHAT mode's direct-dispatch
path deliberately has no `SessionManager.tick()`/pause/checkpoint
involvement (SDD 5.3a) -- a chat turn is a single instant call, never a
multi-step plan that could need to checkpoint mid-flight; cloud budget
from a chat call routed through a cloud worker (e.g. via `/effort high`
or an explicit `/model`) is still recorded by the shared
`OllamaSessionBudget` on the provider, just never throttle/pause-gated
the way COWORK's step loop is. Worth reconsidering if `/effort high`
chat usage on Ollama Cloud becomes a real budget-exhaustion vector in
practice.

## REPL/TUI UX sprint, part 1 -- `/model` dynamic onboarding (2026-07-20)

New sprint from Roland's live REPL/TUI testing, three parts, one commit
each. Part 1 of 3.

- [x] **SDD-first:** SDD_ADDENDUM_PHASE8.md B.4.7 "Dynamic Model
      Onboarding via `/model`" documents the confirm -> pull -> probe ->
      register -> pin flow, the `name:tag` onboarding-candidate
      heuristic, and the explicit non-scope (re-pulling an already-
      registered model, concurrent onboarding, no change to
      `ReadinessChecker.check()`'s own never-auto-pull contract).
- [x] New `tasker/setup/onboarding.py`: `looks_like_model_tag()` (colon-
      shape heuristic, deliberately narrow to avoid false-positiving on
      a typo'd registry id), `pull_model()` (HTTP `POST /api/pull`,
      streaming NDJSON, injectable `_pull_fn` for testing -- never the
      `ollama` CLI, per CLAUDE.md's binding server rules), `onboard_model()`
      (pull -> `ReadinessChecker.check()` -> `write_manifest_to_registry()`
      + live in-memory `registry.register()` on success).
- [x] `cli/shell.py`: `/model <tag>` for an unregistered, tag-shaped id
      now calls `_onboard_and_pin()` -- prints what will happen and
      where from, confirms with the user, runs the onboarding flow, and
      pins CHAT to the new worker id on success. A de-duplicated pull-
      progress printer (`_pull_progress_printer()`) prints one line per
      distinct status change, not one per byte-progress tick. `/help`
      updated.
- [x] Tests: `tests/unit/test_onboarding.py` (new, 14 tests),
      `tests/unit/test_cli_shell.py` (+4, `TestReplModelOnboarding`).
- [x] Full suite green: **748 tests, OK** (was 730).
- [x] **Live smoke** (Designlab1, WSL Ollama 127.0.0.1:11435, zero cloud
      spend): `/model smollm2:135m` in a real `tasker-cli shell` session
      -> confirmed `y` -> real streamed `/api/pull` progress -> `GET
      /api/tags` confirmed the model actually landed on the server ->
      readiness probe correctly reported it as not tool-capable (a real
      135M model genuinely can't reliably call tools) -> not registered,
      `worker_registry.yaml` untouched, CHAT model unchanged. Cleaned up
      via `/api/delete` (never the `ollama` CLI) -- server restored to
      its original 3-model state.

**Open decisions / known issues:** the success-registration path (pull
+ probe succeed, manifest actually written and pinned) was proven at
the unit level, not live in this pass -- the live smoke deliberately
used a tiny, genuinely-not-tool-capable model to keep the download
small and fast; a future session wanting live success-path evidence
should pull a real tool-capable model instead (e.g. a small
`qwen2.5`/`llama3.1` variant), which will take longer and use more
bandwidth/disk.

## REPL/TUI UX sprint, part 2 -- context controls (2026-07-20)

Part 2 of 3 (see part 1's entry above for the sprint's origin).

- [x] **SDD-first:** new SDD 5.6.1a "Context Window Control (`num_ctx`)"
      documents the precedence order (`num_ctx_override` >
      local-VRAM-ceiling > manifest `context_window`), the cloud
      exemption, the GPU data source (same cached detection
      `apply_gpu_availability()` uses), and the deliberately-rough
      bytes-per-token estimate's rationale. SDD 7.6's REPL command list
      updated with `/models`, `/context`, and `/budget`'s new
      initializes-at-0.0 semantics.
- [x] `tasker/workers/providers/ollama.py`: `resolve_num_ctx(worker,
      gpu)` -- cloud exempt (always full manifest value); local capped
      by remaining VRAM (after the worker's declared `vram_mb`, unified-
      memory reserve applied first) estimated via a documented rough
      bytes-per-token constant; no GPU data means no cap (no basis).
      `OllamaProvider.__init__` gained an optional `gpu: GPUInfo | None`
      (never auto-loaded -- kept out of the constructor to stay
      deterministic in tests; real wiring happens in `_build_pipeline()`
      / `tasker/api/server.py`'s `main()`, both now pass
      `load_cached_gpu_info()`). `execute()` now always sends
      `options.num_ctx` -- previously never sent at all, so Ollama
      silently applied its own 4096 default. `task.context["num_ctx_override"]`
      (the REPL's `/context` lever) wins over everything.
- [x] `cli/shell.py`: new `/context <tokens>` (CHAT-mode-scoped, same
      pattern as `/model`/`/effort`), new `/models` command (+ `/model
      list` alias) listing DEFAULT/LOCAL/CLOUD groups with tool
      protocol, max context, and a VRAM-fit hint via `resolve_num_ctx()`;
      `/budget` now reads a real per-mode pipeline instead of a static
      placeholder. The REPL now builds one pipeline per mode up front
      (`_ensure_pipeline()`, called at startup and on every `/mode`/
      `/secure` switch) and reuses it across turns in that mode -- so
      `/budget` shows real, accumulating (initially zero) numbers from
      the moment a mode is entered, not "not active" until a task
      happens to run, and both CHAT and non-CHAT dispatch calls now pass
      `pipeline=` to reuse it. `_evict_if_paused()` drops a non-CHAT
      mode's cached pipeline once its `SessionManager` reaches `PAUSED`,
      so the next task in that mode starts fresh rather than sitting in
      `PAUSED` forever within the REPL process (CHAT's own direct-
      dispatch path never pauses by design, so it's exempt).
- [x] Tests: `tests/unit/test_provider_ollama.py` (+13 --
      `TestResolveNumCtx`, `TestOllamaProviderNumCtxPayload`),
      `tests/unit/test_cli_shell_context.py` (new, 20 tests).
- [x] Full suite green: **781 tests, OK** (was 748).
- [x] **Live smoke** (Designlab1, WSL Ollama 127.0.0.1:11435, real cached
      GPU detection, zero cloud spend): `/budget` showed real
      `0.0/3000 units (0.0%)` before any task ran; `/models` correctly
      grouped DEFAULT/CLOUD and showed a real, data-driven VRAM-fit hint
      on `lfm2.5-local` (`fits ~32768 of 128000 in VRAM` -- this
      machine's real GTX 1050 Ti 4096MB genuinely caps its 128000-token
      manifest declaration); two chat turns (one before, one after
      `/context 4096`) both answered normally with budget staying 0.0
      throughout (correct -- local calls never consume Ollama Cloud
      budget).

**Open decisions / known issues:** `/context`/`/model`/`/effort` remain
CHAT-mode-scoped only (matching the prior sprint's SDD 5.3a pattern) --
non-CHAT modes' worker selection/context is unaffected by any of these
levers; extending them to COWORK/CODE/RESEARCH's step-based dispatch
would need a different design (per-step, not per-session). A `/policy`
change after a mode's pipeline is already cached does not retroactively
rebuild that pipeline within the same REPL session (documented
limitation, same simplification the prior TUI REPL used for its own
per-mode budget caching).

## REPL/TUI UX sprint, part 3 -- readline REPL + TUI spec addendum (2026-07-20)

Part 3 of 3 -- see part 1's entry above for the sprint's origin.

- [x] `cli/shell.py` gained real GNU readline integration: arrow-key
      line editing and Ctrl-R reverse search come free from `import
      readline` (guarded -- `None` on a platform without it, e.g.
      Windows without pyreadline3); persistent history at
      `~/.tasker_history` (`_load_history()`/`_save_history()`, loaded
      at REPL startup, saved when the loop exits via any path);
      tab-completion (`_make_completer()`) for `/`-prefixed commands at
      the start of a line, mode names after `/mode `, and worker ids
      after `/model `/`/resume `.
- [x] **Bug caught and fixed while writing tests, not shipped:** the
      first pass of `_repl()`-driving tests in `test_cli_shell.py`/
      `test_cli_shell_context.py` silently created and wrote a real
      `~/.tasker_history` file on the machine running the suite --
      `_init_readline()`/`_save_history()` were never mocked. Fixed by
      mocking both in every existing REPL-driving test, plus a dedicated
      regression test (`test_never_touches_real_home_directory_history_file`)
      to guard against it recurring.
- [x] **SDD-first:** new SDD_ADDENDUM_PHASE8.md B.5.5 "Keyboard Bindings
      & Text Selection" -- a requirement list (not an implementation) for
      whoever builds 8.4/8.5: history recall, reverse-search, and
      tab-completion equivalents on every text-input widget; verified
      native terminal text selection (or an explicit copy-to-clipboard
      fallback) on every output/report panel, called out as a
      live/manual verification item like B.8's screenshot-or-transcript
      requirement. B.11's Phase 8.4 and 8.5 checklists each gained a
      line pointing back at B.5.5.
- [x] Tests: `tests/unit/test_cli_shell_readline.py` (new, 12 tests).
- [x] Full suite green: **793 tests, OK** (was 781).
- [x] **Live smoke** (Designlab1, WSL Ollama, real pty via Python's
      `pty.fork()`, scratch `$HOME` so the real `~/.tasker_history` was
      never touched): `/mod` + Tab correctly extended to the longest
      common prefix `/mode` among the three ambiguous
      `/mode`/`/model`/`/models` matches; `/bud` + Tab unambiguously
      completed to `/budget` and executed it, printing real budget
      stats; Up-arrow after clearing the line correctly recalled the
      previous history entry (`/budget`); the scratch history file
      contained the real submitted commands after the session exited.

**Open decisions / known issues:** Ctrl-R reverse search wasn't
separately pty-scripted this session (Tab and Up-arrow already prove
the same underlying GNU readline C library is correctly wired via
`import readline`; Ctrl-R is inherent to that same library, not
additional project code) -- a future session wanting that specific live
evidence could script `\x12` + a search term through the same pty
harness. Tab-completion's candidate set is currently limited to
commands/modes/worker-ids per B.5.5's REPL-only scope this sprint; it
does not complete file paths or arbitrary task text, which was never in
scope.

## REPL/TUI UX sprint addendum -- chat rewind buffer / session transcript (2026-07-20)

Addendum to part 3, from the same live-testing session: text rolling
off screen with no way to recover it.

- [x] **SDD-first:** new SDD 7.6a "Chat Rewind Buffer (Session
      Transcript)" documents the in-memory `Transcript`, the
      auto-write-as-you-go disk behavior (file created with a header at
      REPL start, every `record()` appended immediately -- nothing lost
      even on a crash), the degrade-to-memory-only fallback on an
      unwritable path, `/transcript [n]`'s paged reprint, and the
      `_Tee`-captured "assistant" entry (full dispatch-call stdout for
      that turn, not a synthesized answer string). SDD 7.6's REPL
      command list updated with `/transcript`.
- [x] New `tasker/runtime/transcript.py`: `TranscriptEntry`, `Transcript`
      (`record()`, `exchanges()`, `render_exchanges()`),
      `default_transcript_path()` (`~/.tasker/transcripts/
      <YYYYMMDD-HHMMSS>.md`). No `cli/shell.py`/Textual coupling --
      reusable by a future TUI `HarnessPanel` (8.5).
- [x] `cli/shell.py`: `Transcript` created at REPL startup, path
      mentioned in the startup banner; every slash command recorded as
      an "event" entry; every chat/task turn's user message and full
      captured stdout (via new `_Tee` class mirroring output to both the
      terminal and an in-memory buffer) recorded as "user"/"assistant";
      new `/transcript [n]` command using a new simple terminal pager
      (`_page_lines()`, `-- more --` between terminal-height chunks, `q`
      to stop early); `/help` updated.
- [x] **Bug caught and fixed before shipping** (same class as H15's):
      the first pass of `_repl()`-driving tests across all four
      `test_cli_shell*.py` files silently created a real
      `~/.tasker/transcripts/*.md` file on the machine running the
      suite. Fixed by mocking `default_transcript_path` in every
      existing REPL-driving test (7 call sites across
      `test_cli_shell.py`/`test_cli_shell_context.py`), alongside new
      dedicated tests in `test_cli_shell_transcript.py` that
      deliberately exercise real (tmp-directory) file writes to prove
      the feature actually works, while everything else stays
      in-memory-only.
- [x] Tests: `tests/unit/test_transcript.py` (new, 17 tests),
      `tests/unit/test_cli_shell_transcript.py` (new, 18 tests).
- [x] Full suite green: **828 tests, OK** (was 793).
- [x] **Live smoke** (Designlab1, WSL Ollama, scratch `$HOME` so the
      real `~/.tasker/transcripts` was never touched, zero cloud spend):
      startup banner correctly showed the transcript path; a real chat
      turn completed normally; `/transcript` correctly reprinted it;
      the on-disk markdown file, read back after the session, contained
      the full session in order (`/status` and `/transcript` and
      `/quit` as event lines, the user message and reply as You:/
      Tasker: lines) -- confirming incremental auto-write, not just an
      in-memory feature.

**Open decisions / known issues:** the pager's default page size is
derived from the real terminal height (`shutil.get_terminal_size()`) --
not exercised by the live smoke test's piped-stdin session (which has
no real terminal size, falls back to the 80x24 default); a future
session with a real interactive terminal could confirm the pager
actually adapts to an unusual terminal height. `/transcript`'s paging
uses the REPL's own `input()` for its "-- more --" prompt, which means
it also benefits from (and is subject to) the readline integration from
the base part-3 work -- e.g. Ctrl-C during a pager prompt is handled
explicitly (stops paging cleanly), consistent with the REPL's own
Ctrl-C handling elsewhere.

## RESEARCH mode grounding -- WEB_SEARCH executor + enforcement + honesty guard (2026-07-20)

New sprint from Roland's live research-mode test: RESEARCH mode
fabricated an entire model comparison and a fake benchmark statistic
with ZERO tool calls.

- [x] **SDD-first:** new SDD 5.1a "RESEARCH Mode Grounding Contract"
      documents the root cause (no `WEB_SEARCH`/`RETRIEVE` execution
      implementation at all, AND no `_TOOL_KEYWORDS` entry so
      `narrow_bundle_to_step()` always narrowed research steps to an
      empty tool set) and the four-point enforcement: real tool
      executors, code-level plan-injection backstop, prompt-level
      grounding requirements (plan + synthesize), and a zero-retrieval
      honesty guard. SDD 5.1's Mode Definitions table cross-referenced.
- [x] **Part 1 -- real tool executors:** `tasker/tools/executor.py` gained
      `_exec_web_search()` (Brave Search API, `BRAVE_API_KEY` env var
      only, structured `{"query","results":[{"title","url","snippet"}]}`
      output carrying real source URLs) and `_exec_retrieve()` (HTTP
      fetch + HTML-to-text strip, `{"url","content"}`). Both registered
      in `_DISPATCH`, network reads so never `_LOCAL_ONLY_TOOLS`-gated.
      `tasker/tools/bundles.py`'s `_TOOL_KEYWORDS` gained entries for
      `WEB_SEARCH`/`RETRIEVE`/`PDF_EXTRACT`/`CITATION_TRACKER`/
      `CONTRADICTION_DETECTOR` -- **the actual root-cause fix**; before
      this, no keyword group existed for any of them, so
      `narrow_bundle_to_step()` returned an empty set for every research
      step regardless of content, meaning the model could never have
      called `web_search`/`retrieve` even if it had tried to.
      `tasker/tools/loop.py`'s multi-tool-call turn execution changed
      from sequential `await` to `asyncio.gather()` -- "parallel fetch"
      per the sprint's request, proven via wall-clock timing.
- [x] **Part 2 -- plan/prompt/synthesis enforcement + honesty guard:**
      `build_plan_prompt()`/`build_synthesize_prompt()`
      (`tasker/orchestrator/_parse.py`) gained an optional `mode_name`
      that appends a RESEARCH-specific grounding block to the user
      prompt (plan: forbids factual step descriptions, requires a real
      search/retrieve step; synthesize: requires citing real URLs from
      worker outputs). All four orchestrator tiers
      (`tier1_single.py`…`tier4_cloud.py`) gained an optional `mode_name`
      constructor param, threaded by `factory.py`'s `build_orchestrator()`
      from `config.mode.name`. New `tasker/runtime/dispatch.py`
      functions: `_search_backend_configured()`,
      `_enforce_research_grounding()` (code-level backstop -- prepends a
      real retrieval step, correctly reindexing dependencies, when a
      plan has none and a backend is configured), and
      `_apply_research_synthesis_honesty()` (checks the union of every
      step's tool calls against the final synthesized answer). New
      `tasker/tools/honesty.py`'s `check_research_grounding()` -- no
      output-side keyword gate (unlike the side-effect guard), since any
      research claim with zero retrieval calls is unverifiable by
      construction. Wired into `_execute_steps()` (per step) and both
      `_run_task()`/`_resume_task()` (final synthesis). `cli/shell.py`'s
      `_warn_if_research_ungrounded()` announces a missing
      `BRAVE_API_KEY` at `/mode research`, REPL startup, and the
      one-shot `--mode research` CLI path.
- [x] Tests: `tests/unit/test_tool_executor.py` (+16 -- `TestWebSearch`,
      `TestRetrieve`), `tests/unit/test_tool_bundles.py` (+8 --
      `TestNarrowBundleToStepResearchKeywordMatches`),
      `tests/unit/test_tool_loop.py` (+1 -- parallel-execution timing),
      `tests/unit/test_orchestrator_parse.py` (+8 --
      `TestResearchModeGroundingPrompts`),
      `tests/unit/test_orchestrator_single.py` (+3),
      `tests/unit/test_orchestrator_tier2.py` (+1),
      `tests/unit/test_orchestrator_tier3.py` (+1),
      `tests/unit/test_orchestrator_tier4.py` (+1),
      `tests/unit/test_orchestrator_factory.py` (+5 --
      `TestModeNameThreading`), `tests/unit/test_honesty.py` (+8 --
      `TestCheckResearchGrounding`), `tests/unit/test_research_grounding.py`
      (new, 17 tests -- unit + end-to-end `_run_task()` wiring),
      `tests/unit/test_cli_shell_research.py` (new, 7 tests).
- [x] Full suite green: **903 tests, OK** (was 852).
- [x] **Live smoke -- honest degradation without a search backend**
      (Designlab1, WSL Ollama, `BRAVE_API_KEY` deliberately unset, zero
      cloud spend): `/mode research` printed the no-backend warning; a
      real research task's planner step description itself now says
      "Perform web_search for comparison" (previously step descriptions
      asserted invented facts); with no backend to actually search, the
      worker declined to fabricate ("The comparison cannot be made due
      to lack of relevant data") and the final synthesized answer was
      still correctly prefixed `[unverified -- no sources retrieved]`
      regardless -- concrete proof the reported silent-fabrication bug
      no longer reproduces.

**Open decisions / known issues:** **no live research query with a real
`BRAVE_API_KEY` and real citations was run this session** -- no key is
available in this sandboxed environment. The full tool-execution path
(mocked Brave response shape) and the "guard clears when a real
retrieval call occurred" path are both unit-tested
(`test_tool_executor.py`, `test_research_grounding.py`'s
`test_no_flag_when_a_real_retrieval_call_backs_the_claim`), but a future
session with a real key should run one live end-to-end research query
and confirm the synthesized answer actually cites real URLs, per the
sprint's original acceptance criterion. `PDF_EXTRACT`/
`CITATION_TRACKER`/`CONTRADICTION_DETECTOR` remain schema-only (no
execution implementation) -- out of scope this pass, since
`WEB_SEARCH`+`RETRIEVE` alone already carry the source URLs synthesis
needs; calling one of the other three still returns "no execution
implementation configured", now correctly scoped to just those three.

## Tool-executor fill-in sprint, part 1 -- DELEGATE_AGENT sub-task dispatch (2026-07-20)

Audit found 15 `ToolID`s with schemas but zero execution implementation
-- a model could request one and nothing would happen. Three-part
sprint, one commit each. Part 1 (highest priority, unblocks the planned
concurrency stress test): `DELEGATE_AGENT`.

- [x] **SDD-first:** new SDD 5.7c "DELEGATE_AGENT — Sub-Task Dispatch"
      documents the inherited-pipeline contract (mode/policy/privacy
      tier via config reuse, shared budget/concurrency via pipeline-tuple
      reuse -- a sub-agent cannot bypass the parent's own budget),
      bounded depth (max 2, `DelegationContext.child()`), the per-task
      sub-agent cap (max 3, a single shared counter across the whole
      delegation tree, race-safe under asyncio's cooperative scheduling
      with no `await` between the cap check and the increment), and the
      structured result/error contract. New SDD 5.7d "Tool Executor
      Coverage — Honest Degradation" written as the contract Parts 2/3
      will implement against.
- [x] New `tasker/runtime/delegation.py`: `DelegationContext` (a leaf
      module -- `tasker/tools/executor.py` imports it directly;
      `tasker/runtime/dispatch.py` is imported back from inside
      `_exec_delegate_agent()` only, deferred, to avoid a real import
      cycle with the existing dispatch -> loop -> executor chain).
- [x] `tasker/tools/executor.py`: new `_exec_delegate_agent()`, wired
      into `execute_tool()` ahead of the `_DISPATCH` lookup (delegation
      is a dispatch call, not local execution -- never
      `_LOCAL_ONLY_TOOLS`-gated). `tasker/tools/loop.py`'s
      `run_tool_loop()` gained a `delegation` param threaded through to
      every `execute_tool()` call.
- [x] `tasker/runtime/dispatch.py`: `_execute_steps()` gained a
      `delegation` param forwarded unchanged to `run_tool_loop()` for
      every step (depth only increases when a step's worker actually
      calls `delegate_agent`, via `.child()`, not per step).
      `_run_task()` now **returns the synthesized output string**
      (`str | None`) instead of only printing it -- a backward-compatible
      change (existing callers ignoring the return value are
      unaffected) needed so `_exec_delegate_agent()` can hand a real
      sub-task result back as tool output. Both `_run_task()` and
      `_resume_task()` build a fresh depth-0 `DelegationContext` when
      none is passed in.
- [x] `tasker/tools/bundles.py`'s `_TOOL_KEYWORDS` gained a
      `DELEGATE_AGENT` group -- same lesson as the research-mode sprint:
      no keyword group means the tool can never be offered regardless of
      how real its executor is.
- [x] Tests: `tests/unit/test_delegation.py` (new, 16 tests) --
      `DelegationContext.child()` behavior, `_exec_delegate_agent()`'s
      guard clauses, and the real (non-mocked) recursive `_run_task()`
      path proving shared budget/concurrency, structured result
      passing, spawned-counter increments, and the depth-limit chain.
- [x] Full suite green: **919 tests, OK** (was 903).
- [~] **Live smoke attempted, not achieved this session:** several
      `tasker-cli --mode cowork --policy local` attempts (Designlab1,
      WSL Ollama, zero cloud spend enforced via `--policy local` after
      confirming an unforced attempt did route to a cloud worker) never
      got the local `lfm2.5-thinking` model to actually issue a
      `delegate_agent` tool call -- it either answered trivial sub-tasks
      directly (a previously-documented small-model pattern: skipping
      an offered tool when it believes it can just answer) or, once,
      badly misparsed a prompt containing "pong" as being about the
      video game. Not a defect in this session's code -- the mechanism
      itself is proven at the unit level
      (`TestExecDelegateAgentRecursive` drives the real recursive
      dispatch, not a mock). Flagged as an open follow-up for a future
      session with more time or a stronger local model.

**Open decisions / known issues:** live delegate_agent invocation not
yet demonstrated end-to-end with a real small local model -- see H18.2
in TESTING_GUIDE.md for the full attempt log. Session paused here per
explicit instruction (usage window near limit) -- Parts 2 (TEST_RUNNER/
LINTER/CALCULATOR) and 3 (honest degradation for the remaining
unimplemented tools) are queued for the next window, not started this
session.

## Tool-executor fill-in sprint, part 2 -- TEST_RUNNER, LINTER, CALCULATOR (2026-07-20)

Continuation of the three-part tool-executor fill-in sprint. Implements
real executors for the three most commonly needed CODE/COWORK/CHAT
tools that still had schemas only.

- [x] `tasker/tools/executor.py` gained `_exec_test_runner()`,
      `_exec_linter()`, and `_exec_calculator()`:
  - TEST_RUNNER auto-detects `pytest` (via `shutil.which`) and falls back
    to `python -m unittest discover`; returns structured
    `{framework, passed, failed, skipped, failing_tests}`.
  - LINTER runs `ruff check <path> --output-format json` when ruff is
    available; returns `{tool, findings[], error_count}`; otherwise
    returns an honest "linter not installed" error.
  - CALCULATOR parses the expression with the `ast` module and evaluates
    a whitelist of numeric operators only -- `eval()` is never used.
- [x] `_DISPATCH` updated to register all three tools.
- [x] `tasker/tools/bundles.py` `_TOOL_KEYWORDS` gained a `CALCULATOR`
      group (LINTER/TEST_RUNNER already had groups); without this,
      `narrow_bundle_to_step()` would never offer the tool regardless of
      how real its executor is -- the same root-cause pattern that broke
      RESEARCH mode grounding.
- [x] Tests: `tests/unit/test_tool_executor.py` expanded with
      `TestCalculator`, `TestTestRunner`, and `TestLinter` classes (+19
      tests total for the three tools); `tests/unit/test_tool_bundles.py`
      gained `test_calculator_keyword_matches`.
- [x] Full suite green: **935 tests, OK** (was 919).
- [x] Commit: `feat: tool executors part 2 — TEST_RUNNER, LINTER, CALCULATOR`.

**Next task:** Tool-executor fill-in sprint, part 3 -- honest
"not available in this build" degradation for every remaining
unimplemented `ToolID`, and excluding unavailable tools from offered
bundles (SDD 5.7d). Then SDD_ADDENDUM_PHASE8.md Phase 8.4.

## Tool-executor fill-in sprint, part 3 -- honest degradation for unimplemented tools (2026-07-20)

Final executor sprint: removes the remaining placeholder `ToolID`s from
the bundles offered to workers, and replaces the generic "no execution
implementation configured" message with a structured error that tells the
model exactly which tools are actually available.

- [x] `tasker/tools/executor.py` gained `implemented_tools()` -- a single
      registry-of-truth returning `frozenset[str]` of all keys in
      `_DISPATCH`. New `_make_unavailable_error(tool_name)` builds the
      structured error dict `{tool, error, available_tools}`.
- [x] `execute_tool()` now returns `tool_output=_make_unavailable_error(...)`
      with `error=None` for any unimplemented tool, instead of a plain string
      error -- the multi-turn loop can still feed this structured dict back to
      the model as a tool result.
- [x] `tasker/tools/bundles.py` `get_definitions()` now filters every bundle
      through `_filter_implemented()` before returning `ToolDefinition`s.
      Unimplemented tools are dropped with a WARNING, so workers are never
      tempted to call them. `implemented_tools()` is imported from the
      executor module -- adding a new `_DISPATCH` entry automatically lifts
      it into offered bundles.
- [x] Tests: `TestUnavailableTools` in `tests/unit/test_tool_executor.py`
      (+3 tests) and `TestBundleImplementationFilter` in
      `tests/unit/test_tool_bundles.py` (+4 tests). Both paths use
      `implemented_tools()` as the source of truth.
- [x] Full suite green: **941 tests, OK** (was 935).
- [x] Commit: `feat: tool executors part 3 — honest degradation for unimplemented tools`.

**Next task:** SDD_ADDENDUM_PHASE8.md Phase 8.4 -- SetupWizardScreen +
ModelSelectorScreen. No remaining executor sprint work.

**Open decisions:** Same as Part 2 -- live invocation of any of these
tools with a real model has not been attempted; the executors are proven
at the unit level.

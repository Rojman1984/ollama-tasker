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

### Still out of scope (unchanged from SDD_ADDENDUM_PHASE8.md)
- [ ] Phase 8.3 -- TUI Foundation (real TuiApp, WelcomeScreen, status bar)
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

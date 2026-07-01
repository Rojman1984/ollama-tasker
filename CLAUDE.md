# Ollama Tasker — Project Context

> **Authoritative design reference:** `docs/SDD.md`
> **Cross-platform migration + hardware detection addendum:** `docs/SDD_ADDENDUM_7.5.md`
> **Setup wizard / readiness checker / TUI addendum:** `docs/SDD_ADDENDUM_PHASE8.md`
> **Feature checklist:** `docs/TASKER_CHECKLIST.md`
> **Testing guide:** `docs/TESTING_GUIDE.md`
> **Parity reference:** `docs/PARITY_CHECKLIST.md`

---

## What This Project Is

The **Ollama Tasker** is a provider-agnostic, hardware-aware multi-agent orchestration
system for tool-capable language models. It is a standalone Python project under the
Real Truth AI initiative.

**It is NOT part of HomeWatch, Ztripes, or any MSP product line.**
Do not reference, import, or share infrastructure with those systems.

---

## What This Project Does

- Abstracts local Ollama, Ollama Cloud, Anthropic, OpenAI, and Fugu behind a unified
  worker interface
- Routes tasks to workers via a configurable RoutingPolicy with privacy tier enforcement
- Orchestrates multi-step agent tasks using a swappable tier system (Tier 0–4)
- Implements five modes: CHAT, CODE, COWORK, RESEARCH, SECURE
- Manages Ollama Cloud concurrency slots and 5-hour session budget windows
- Checkpoints long-horizon tasks and resumes after session exhaustion
- Exposes an OpenAI-compatible API and a CLI shell with slash commands

---

## Repository Layout

```
ollama-tasker/
├── docs/
│   ├── SDD.md                    ← READ THIS FIRST on every session
│   ├── TASKER_CHECKLIST.md      ← update on every feature completion
│   ├── TESTING_GUIDE.md          ← add test command for every feature
│   └── PARITY_CHECKLIST.md       ← reference for adopted parity modules
│
├── core/                         ← adopted from Parity Project (do not rewrite)
│   ├── agent_runtime.py
│   ├── query_engine.py
│   ├── openai_compat.py
│   ├── session_store.py
│   ├── plan_runtime.py
│   ├── task_runtime.py
│   ├── agent_manager.py
│   ├── compact.py
│   ├── microcompact.py
│   ├── hook_policy.py
│   ├── mcp_runtime.py
│   ├── bash_security.py
│   └── agent_slash_commands.py
│
├── tasker/
│   ├── modes/
│   │   ├── base.py               ← TaskerMode dataclass, ModeConfigurator
│   │   ├── chat.py
│   │   ├── code.py
│   │   ├── cowork.py
│   │   ├── research.py
│   │   └── secure.py
│   ├── classifier/
│   │   ├── base.py
│   │   ├── rule_based.py
│   │   └── local_llm.py
│   ├── orchestrator/
│   │   ├── base.py               ← OrchestratorBase ABC
│   │   ├── tier0_rules.py
│   │   ├── tier1_single.py
│   │   ├── tier2_dual.py
│   │   ├── tier3_reasoning.py
│   │   └── tier4_cloud.py
│   ├── workers/
│   │   ├── base.py               ← ALL data models and enumerations live here
│   │   ├── registry.py           ← WorkerRegistry, WorkerSelector
│   │   └── providers/
│   │       ├── base.py           ← WorkerProviderBase ABC
│   │       ├── ollama.py
│   │       ├── anthropic.py
│   │       ├── openai_provider.py
│   │       └── fugu.py
│   ├── session/
│   │   ├── manager.py            ← SessionManager state machine
│   │   ├── checkpoint.py         ← Checkpoint dataclass + CheckpointStore
│   │   ├── budget.py             ← OllamaSessionBudget
│   │   ├── concurrency.py        ← OllamaCloudConcurrencyManager
│   │   └── notifier.py           ← NotifierBase + implementations
│   └── tools/
│       ├── bundles.py            ← tool sets per mode
│       └── normalizer.py         ← ToolCallNormalizer
│
├── config/
│   ├── profiles/
│   │   ├── tier0_minimal.yaml
│   │   ├── tier1_tasker.yaml     ← TASKER-P1: Ryzen 5 3500U, 32GB, CPU-only
│   │   └── tier2_designlab.yaml  ← Designlab1: Ryzen 5/7, GTX 1050 Ti 4GB
│   ├── modes/
│   │   ├── chat.yaml
│   │   ├── code.yaml
│   │   ├── cowork.yaml
│   │   ├── research.yaml
│   │   └── secure.yaml
│   └── workers/
│       └── worker_registry.yaml
│
├── cli/
│   └── shell.py                  ← interactive REPL, slash commands
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── fixtures/
│       ├── fake_ollama_server.py
│       ├── fake_anthropic_server.py
│       ├── fake_openai_server.py
│       ├── fake_fugu_server.py
│       └── fake_stdio_mcp.py
│
├── CLAUDE.md                     ← this file
├── pyproject.toml
└── README.md
```

---

## Tech Stack

- **Language:** Python 3.11+
- **Async:** `asyncio` throughout — all provider calls, session management, and
  orchestrator loops are async
- **Foundation:** Parity Project Python runtime (see `core/` — do not rewrite these)
- **Transport:** Ollama `/api/chat` + OpenAI-compat `/v1/chat/completions` for all
  providers (LiteLLM optional, not required)
- **Config:** YAML (PyYAML) for hardware profiles, mode defaults, worker registry
- **Persistence:** JSON files for checkpoints and session state
- **Testing:** `unittest` (stdlib) — same pattern as Parity Project
- **Shell:** Linux/WSL2 (primary, since Phase 7.5.1) — use `python`, `&&` to chain
  commands. PowerShell (Windows, secondary) remains supported — use `python` not
  `python3`, `;` not `&&`. The codebase itself is OS-agnostic (pathlib, asyncio, no
  Windows-only APIs); only shell syntax in docs/commands differs.
- **Venv:** Linux/WSL2: `source .venv/bin/activate`. Windows: `.venv\Scripts\Activate.ps1`
- **dotenv:** use `python-dotenv` for loading `.env` files (never hardcode keys)
- **AMD APU GPU setup (Linux):** see `docs/Ollama_AMD_APU_Install_Guide.md` for the
  general Vulkan/Mesa RADV setup (Vega 8 Mobile through RDNA3). For TASKER-P1
  (Ryzen 5 3500U, gfx902/Raven2) specifically, the general guide's `OLLAMA_VULKAN=1`
  fix alone is **not** sufficient — it causes a silent runner crash via ROCm
  enumeration on hardware below ROCm's supported list. Use
  `docs/ollama-amd-igpu-config-guide.md` instead, which additionally requires
  `ROCR_VISIBLE_DEVICES=-1` and `HIP_VISIBLE_DEVICES=-1` to disable ROCm enumeration.
  Documented as the expected fix for TASKER-P1; live confirmation on real hardware
  is a Phase 7.5.5 task, not yet performed as of 7.5.1.

---

## Non-Negotiable Constraints

These are enforced mechanically, never by convention:

1. **Privacy tier LOCAL_ONLY** — raises `TaskerPolicyError` immediately on any cloud
   call attempt. No silent fallback.

2. **Ollama Cloud concurrency** — Free plan: 1 slot, Pro: 3, Max: 10. Use asyncio
   semaphore. Return `WorkerStatus.DEFERRED` (never block the caller) if no slot
   available. Reject (not queue) when full.

3. **Session budget 5-hour window** — throttle routing at 90%, begin pause flow at
   100%. Always complete the current step before pausing.

4. **Tool-capable models only** — models without `Capability.TOOL_USE` are rejected
   at registration time.

5. **Orchestrator never calls tools** — it plans and synthesizes only. Workers execute.

6. **Sequential load on TASKER-P1** — Tier 0 and 1 load one model at a time. Peak
   RAM = one model resident.

---

## Development Rules

- **SDD first:** Every architectural decision must be reflected in `docs/SDD.md`
  before implementation begins. If you discover a gap in the SDD, update it first.

- **Checklist discipline:** Every completed feature gets a checked item in
  `docs/TASKER_CHECKLIST.md`. Every user-testable feature gets a concrete command
  in `docs/TESTING_GUIDE.md`.

- **Test before next phase:** All unit tests for a phase must pass before moving to
  the next phase. Run: `python -m unittest discover -s tests -v`

- **No HomeWatch bleed-in:** Do not import, reference, or share any code path with
  the HomeWatch or Ztripes codebase.

- **workers/base.py is the contract:** All data models and enumerations are defined
  here. No other module defines WorkerManifest, WorkerResult, WorkerTask, or any
  Capability/RoutingPolicy/PrivacyTier enum. Import from here only. This also includes
  the Phase 5 mode/tool enums (ToolID, InteractionPattern, MemoryScope) — do not look
  for these in tasker/tools/bundles.py or tasker/modes/base.py.

- **Providers are opaque to the orchestrator:** The orchestrator receives only
  `WorkerManifest` and `WorkerResult`. It never imports from `tasker/workers/providers/`.

---

## Phase Tracker

Update this section as phases complete.

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Data models + Worker Registry + Selector | ✅ COMPLETE |
| 2 | Session Layer (Budget, Checkpoint, Manager, Notifier) | ✅ COMPLETE |
| 3 | Orchestrator (Base ABC, Tier 0, Tier 1) | ✅ COMPLETE |
| 4 | Providers (Ollama, Anthropic, OpenAI, Fugu) + ToolNormalizer | ✅ COMPLETE |
| 5 | Modes + CLI Shell | ✅ COMPLETE |
| 6 | Higher Orchestrator Tiers (2, 3, 4) | ✅ COMPLETE |
| 7 | Hardening (Notifiers, MindSeed, OpenAI API server) | ✅ COMPLETE |
| 8 | Orchestrator Factory + Live CLI Wiring | ✅ COMPLETE |
| 7.5.1 | Linux/WSL2 migration audit (see `docs/SDD_ADDENDUM_7.5.md`) | ✅ COMPLETE |
| 7.5.2 | `GPUBackend` ABC + `NoGpuBackend` + `tasker-hardware` applet + cache + 3-source resolution | ✅ COMPLETE |
| 7.5.3 | `NvidiaBackend` — detect + verify (Designlab1) | ✅ COMPLETE |
| 7.5.4–7.5.6 | `AmdApuBackend`, VRAM cross-check, final paired verification | ⬜ NOT STARTED |
| 8.1 | Setup wizard headless logic + `tasker-setup` CLI (see `docs/SDD_ADDENDUM_PHASE8.md`) — **note:** the row above labeled plain "8" is an unrelated, earlier "Orchestrator Factory" milestone from before `SDD_ADDENDUM_PHASE8.md` existed; this is a real naming collision in the project's own history, not a typo — the two are unrelated | ✅ COMPLETE |
| 8.2–8.5 | Readiness checker, TUI foundation, model selector, harness panel | ⬜ NOT STARTED |

---

## Key Design Decisions (Summary)

Full rationale in `docs/SDD.md`. Quick reference:

- **Single OllamaProvider** handles both `LOCAL_HARDWARE` and `OLLAMA_CLOUD` — same
  endpoint, `compute_location` in the manifest distinguishes them.
- **Fugu** registers with `Capability.MULTI_AGENT` and is treated as a high-quality,
  slow, opaque worker — it internally orchestrates its own pool.
- **NanoOrchestrator (Tier 0)** uses no model at all — pure rule-based plan templates.
  This is the fallback that always works on any hardware.
- **Mode + HardwareProfile = ExecutionConfig** — modes never hardcode hardware
  assumptions; profiles never hardcode mode behavior.
- **PrivacyTier** is attached to both the TaskerMode (default) and individual
  WorkerTasks (per-step override in COWORK mode).
- **LFM2.5 models use `ToolProtocol.LFM25`, not `NATIVE`** — Ollama Tasker
  handles the dialect internally (system-prompt JSON injection, JSON/Pythonic
  output parsing). The **LFM2 Skill Translator is a separate project**, scoped
  to the Claude Code → Ollama use case — it is not a dependency of Ollama
  Tasker and is referenced in `docs/SDD_ADDENDUM_7.5.md` A.2b only as a
  design comparison (LFM2's wrapper-token dialect vs. LFM25's plain-JSON one).

---

## Environment Variables

**Linux/WSL2 (session, primary):**
```bash
# Ollama (local)
export OLLAMA_BASE_URL="http://localhost:11434"

# Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."

# OpenAI
export OPENAI_API_KEY="sk-..."

# Fugu (via OpenRouter or direct)
export FUGU_API_KEY="..."
export FUGU_BASE_URL="https://api.sakana.ai/v1"

# Tasker
export TASKER_PROFILE="tier1_tasker"   # hardware profile to load
export TASKER_OLLAMA_PLAN="pro"        # free | pro | max
export TASKER_LOG_LEVEL="INFO"
```

**Persistent (add to `~/.bashrc` / `~/.profile`):**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export TASKER_PROFILE="tier1_tasker"
```

**PowerShell (Windows, secondary):**
```powershell
# Ollama (local)
$env:OLLAMA_BASE_URL    = "http://localhost:11434"

# Anthropic
$env:ANTHROPIC_API_KEY  = "sk-ant-..."

# OpenAI
$env:OPENAI_API_KEY     = "sk-..."

# Fugu (via OpenRouter or direct)
$env:FUGU_API_KEY       = "..."
$env:FUGU_BASE_URL      = "https://api.sakana.ai/v1"

# Tasker
$env:TASKER_PROFILE     = "tier1_tasker"   # hardware profile to load
$env:TASKER_OLLAMA_PLAN = "pro"            # free | pro | max
$env:TASKER_LOG_LEVEL   = "INFO"
```

**Persistent (add to `$PROFILE` or Windows system env):**
```powershell
[System.Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")
[System.Environment]::SetEnvironmentVariable("TASKER_PROFILE", "tier1_tasker", "User")
```

**`.env` file (recommended — load with `python-dotenv`):**
```ini
OLLAMA_BASE_URL=http://localhost:11434
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
TASKER_PROFILE=tier2_designlab
TASKER_OLLAMA_PLAN=pro
TASKER_LOG_LEVEL=INFO
```

---

## Running Tests

Identical command on Linux/WSL2 and Windows/PowerShell — activate the venv first
(`source .venv/bin/activate` or `.venv\Scripts\Activate.ps1`).

```bash
# Full suite
python -m unittest discover -s tests -v

# Phase-specific
python -m unittest tests.unit.test_worker_registry -v
python -m unittest tests.unit.test_routing_policy -v
python -m unittest tests.unit.test_session_budget -v
python -m unittest tests.unit.test_session_manager -v
python -m unittest tests.unit.test_orchestrator_nano -v
```

---

## Current Session Notes

*(Update this section at the end of every Cowork or Code session)*

**Last worked on:** Building the multi-turn tool-execution loop —
closes out the "known open issue, out of scope" note carried since the
LFM25 session (`tool_result_role` unvalidated because nothing ever
re-invoked a worker with a tool result appended). Started as an
investigation into the empty-content flakiness noted last session; that
investigation surfaced a much bigger, pre-existing gap (see below), which
became this session's real focus per explicit user direction.

**What was actually broken (discovered, not assumed):** no tool call
requested by a worker LLM was ever executed anywhere in the codebase.
`ToolCallNormalizer.extract()` parsed a request into a `WorkerToolResult`
with `tool_output=None`, but nothing downstream ran it — `cli/shell.py`
marked a step `[ok]` purely on HTTP status, and `build_synthesize_prompt()`
only read `WorkerResult.output`, never `tool_results`. A worker could
request `bash("ls")` and the system would report success while `ls`
never ran; the synthesizer then produced plausible-sounding prose about
what the command "would" show. Confirmed live before any fix: asking the
CLI to list files via bash never ran `ls` — it just guessed. Also
confirmed: despite `CLAUDE.md` describing `core/` as "adopted from Parity
Project, do not rewrite," every file in `core/` is a literal 6-line stub
with zero implementation — there was no existing execution primitive to
build on; everything below is written fresh.

**The fix — two new modules, both under `tasker/tools/` (not
`tasker/orchestrator/`, since "the orchestrator never calls tools
directly" is a hard rule, constraint #5 above):**

- **`tasker/tools/executor.py`** — `execute_tool()` runs one tool call
  for real (argv-based `asyncio.create_subprocess_exec`, never
  `shell=True`) for `BASH`, `GIT`, `FILE_READ`, `FILE_WRITE`,
  `CODE_SEARCH`. `LINTER`/`TEST_RUNNER` deliberately left unimplemented —
  no linter or test framework is configured anywhere in this project.
  Security posture (this is a local dev CLI, but `COWORK_BUNDLE` pairs
  `bash` with network tools under `privacy_tier: any_cloud`, so a
  cloud-routed worker could otherwise be tricked into driving local
  execution): `BASH`/`FILE_WRITE`/`GIT` are hard-gated to
  `ComputeLocation.LOCAL_HARDWARE`; a small BASH denylist is a documented
  speed bump, not a security boundary; 30s timeout + 8000-char output cap
  on every call; `FILE_READ`/`FILE_WRITE` path-contained under `cwd`.
  Full rationale in `docs/SDD.md` §5.7a.
- **`tasker/tools/loop.py`** — `run_tool_loop()` drives
  `provider.execute()` through turns: execute → run any requested tools
  for real → thread the assistant's own turn (`WorkerResult.
  raw_assistant_message`, new field) and the tool result
  (`format_tool_result_message()`) into history → re-invoke. Terminates
  at `max_turns=5` with a WARNING, never raises. Every turn's *executed*
  tool results survive into the final result (not just the last turn's —
  a design-review-caught bug: the last turn typically requests none,
  since it's the final answer, so returning only it would silently
  discard everything that actually ran). DEFERRED gets bounded retry with
  backoff before giving up. `cli/shell.py` now calls this instead of a
  single `provider.execute()` per step.

**Design review caught three real bugs in the original design before any
code was written** (see the plan file / this conversation's design-review
pass): (1) the loop as first sketched wouldn't have fixed the reported
empty-content case at all, since an empty response parses to zero tool
calls — nothing for the loop to execute; (2) returning only the last
turn's `tool_results` would have silently discarded every tool that
actually ran; (3) naively persisting a `role:"system"` entry into the
running message history would make `ToolCallNormalizer.inject_tools()`
re-append the "List of tools..." suffix onto an already-suffixed system
message every turn, growing unboundedly. All three are fixed and covered
by regression tests — (3) specifically by an integration test using the
real `OllamaProvider` (HTTP mocked only), since a fully-isolated loop or
provider test would each miss the interaction.

**The actual reason live end-to-end proof initially failed (found via
live testing, then fixed):** `ToolCallNormalizer._extract_lfm25()` set
`tool_name=""` whenever the model's JSON call omitted the
`{"name","arguments"}` envelope. Live testing found `lfm2.5-thinking:latest`
does this *consistently* for single-tool tasks — e.g. emitting bare
`{"command": "hostname"}` instead of the spec's wrapped form — reproduced
identically across 3+ separate prompts, not flakiness. Fixed:
`ToolCallNormalizer.extract()`/`extract_tool_calls()` gained an optional
`tools` param (threaded from `task.tools`); `_infer_tool_from_flat_object()`
matches the flat dict's keys against each offered tool's JSON Schema and
infers the name only on a unique match, leaving ambiguous/unmatched cases
as `tool_name=""` (unchanged from before) rather than guessing.

**Live verification, Designlab1:**
- **Real tool execution proven end-to-end:** a direct provider+loop
  script (bypassing the orchestrator's planner) instructed to run
  `hostname` via the `bash` tool got the model's flat-object response
  correctly inferred as `bash`, executed for real, and returned
  `tool_output='Designlab1\n'` — the machine's actual hostname, confirmed
  against a direct `hostname` shell invocation. First confirmed
  non-fabricated tool execution in this project's history.
- **Security gate confirmed live:** an `OLLAMA_CLOUD` worker requesting
  `bash` gets a clear `.error`, never executes.
- **Full `python -m cli.shell` pipeline still not observed completing a
  real tool call in one run** (4/4 attempts this session): the
  orchestrator's own planning step rephrases the task before the worker
  ever sees it, and several of those rephrasings reliably trigger the
  *separate*, pre-existing empty-content bug (unchanged from last
  session) before the loop's (proven-working) code path is reached. Not
  a regression — the loop and inference fix are proven correct in
  isolation; the full pipeline just has one more opportunity to hit the
  other bug first.
- **New minor finding, not investigated further:** after a real tool
  result was fed back, the model sometimes re-issued the identical tool
  call again instead of answering, repeating until `max_turns` cut it
  off gracefully. Likely a small-model multi-turn limitation, not a loop
  bug — the loop's own job (execute + feed back correctly) is separately
  confirmed via mocked unit tests.
- **Empty-content bounded retry (`OllamaProvider._EMPTY_CONTENT_MAX_
  RETRIES=2`, added this session) does not recover the empty-content
  case** — confirmed live, 3/3 identical retries still empty for the same
  prompt. Kept as a safe, tested, no-harm mitigation; not a fix for the
  phrasing-dependent failure. Untried next lever: Ollama's per-request
  `"think": false` control — `done_reason=stop` + non-empty `thinking` +
  empty `content` is exactly the signature that control targets.

**Tests:** 46 new (25 `test_tool_executor.py`, 11 `test_tool_loop.py`
including the system-message-duplication integration test, 7 across
`test_provider_ollama.py`'s new `TestOllamaProviderMultiTurn`/
`TestFormatToolResultMessage`, 3 `TestBuildSynthesizePrompt`, 7
`TestLfm25FlatObjectInference`). Full suite: 437/437 → 494/494.

**Last file modified:** `tasker/tools/executor.py` (new),
`tasker/tools/loop.py` (new), `tasker/tools/normalizer.py`,
`tasker/workers/base.py`, `tasker/workers/providers/ollama.py`,
`cli/shell.py`, `tasker/orchestrator/_parse.py`, `docs/SDD.md`,
`tests/unit/test_tool_executor.py` (new), `tests/unit/test_tool_loop.py`
(new), `tests/unit/test_provider_ollama.py`,
`tests/unit/test_orchestrator_parse.py`, `tests/unit/test_tool_normalizer.py`,
`docs/TASKER_CHECKLIST.md`, `CLAUDE.md`.

**Next task:** Phase 8.2 — Agentic Readiness Checker
(`tasker/setup/readiness.py`, 3 probe rounds NATIVE→LFM25→JSON_EXTRACT,
`tasker-setup --check-model <name>`, worker registry write on
confirmation, `WorkerRole` assignment per B.4.6). Separately, still open:
the empty-content bug itself (try `"think": false`); getting the full
`cli.shell` pipeline to complete one real tool execution end-to-end (not
just the direct provider+loop script); the model-doesn't-conclude-after-
tool-result behavior; Phase 7.5.4 (`AmdApuBackend`, needs TASKER-P1); wire
`ModeConfigurator.resolve_hardware_profile()` into `cli/shell.py`;
generalize `run_tool_loop()` beyond `OllamaProvider` if/when
Anthropic/OpenAI/Fugu need a multi-turn loop of their own.
**Blockers:** None.
**Open decisions:** `tool_result_role="user"` (the documented Ollama
workaround) not separately live-tested — `"tool"` (the default) worked,
so there was no failure forcing the workaround path; revisit if `"tool"`
ever fails against a different model. AMD-APU tier-computation fallthrough
still untested against real hardware — revisit once 7.5.4 lands on
TASKER-P1. `worker_role` is still a schema addition only — no code
assigns it yet; that's Phase 8.2's job per B.4.6's rules.

**Live model config (tier1_tasker):**
- Orchestrator: `lfm2.5-thinking:latest` (local, 1.2B — was `qwen3:1.7b`, not installed)
- Worker: `lfm2.5-thinking:latest` (local, 1.2B — `tool_protocol: lfm25`, was
  incorrectly `native`; was `lfm2.5:latest`, not installed)

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
| 7.5.4–7.5.6 | `AmdApuBackend`, VRAM cross-check, final paired verification | ✅ COMPLETE |
| 8.1 | Setup wizard headless logic + `tasker-setup` CLI (see `docs/SDD_ADDENDUM_PHASE8.md`) — **note:** the row above labeled plain "8" is an unrelated, earlier "Orchestrator Factory" milestone from before `SDD_ADDENDUM_PHASE8.md` existed; this is a real naming collision in the project's own history, not a typo — the two are unrelated | ✅ COMPLETE |
| 8.2 | Agentic Readiness Checker (`tasker/setup/readiness.py`, addendum numbering — the third "8.2" in this table, see the 8.1 note) | ✅ COMPLETE |
| 8.3 | Textual TUI skeleton (`TuiApp`, `WelcomeScreen`, `HardwareStatusBar`) | ✅ COMPLETE |
| 8.4–8.5 | SetupWizardScreen + ModelSelectorScreen, HarnessPanel | ⬜ NOT STARTED |
| E2E 8.1 | Live cloud-path E2E validation (COWORK_PROMPT.md task list — a *third* use of the "8.1" label, distinct from both rows above) | ✅ COMPLETE |
| E2E 8.2 | tier4_cloud.py reachability from current hardware profiles | ✅ COMPLETE |
| E2E 8.3 | Tool-loop non-termination guard | ✅ COMPLETE |

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

**Last worked on:** `tasker-cli shell` bug-fix session, prompted by live
user testing (not a queued addendum phase). Full write-up in
`docs/TASKER_CHECKLIST.md` → "`tasker-cli shell` bug fixes -- provider
wiring + REPL UX (2026-07-20)".

**P1 fix — provider-wiring gap:** live testing hit a real failure: a
chat-mode turn's `WorkerSelector` picked `fugu-ultra`, but `tasker-cli
shell`'s `provider_map` only wires `OllamaProvider` — the step failed
mid-dispatch (`No provider for fugu`) and the whole run ended in "No
results to synthesize." with no clear explanation. This was a known,
previously-flagged gap (open issue since the Phase 8.1 E2E session) that
had never actually been fixed. Fix, mirroring the existing
`apply_gpu_availability` pattern (SDD_ADDENDUM_7.5.md A.3.4): new
`WorkerRegistry.apply_provider_availability(provider_map)`
(`tasker/workers/registry.py`) marks a worker `available=False` (logged
reason, never dropped from `list_all()`) when its provider has no entry
in the active `provider_map`. Wired into
`tasker/runtime/dispatch.py`'s `_run_task()`/`_resume_task()`
immediately after the pipeline (and its `provider_map`) is built, so an
unwired-provider worker is excluded from *both* planning and selection —
not just selection, which would still have let the orchestrator plan a
step around a worker that could never execute it. Regression test
(`tests/unit/test_dispatch_provider_wiring.py`) deliberately uses
`RoutingPolicy.CAPABILITY_FIRST` with the excluded worker scored higher,
so the test proves exclusion happens up front rather than the worker
merely losing a ranking tie-break.

**Two REPL UX fixes, same live-testing session:** (1) unknown-command
handler (`cli/shell.py:_suggest_command()`) now suggests a next step —
a bare mode name is special-cased first (`/chat` → `did you mean: /mode
chat?`, the actual likely intent) ahead of a generic `difflib` fuzzy
match for real typos (`/wrkers` → `/workers?`). (2) the interactive
shell now defaults to quiet logging — `main()`'s default level dropped
`WARNING` → `ERROR` so plumbing warnings (including the new
provider-availability log lines) don't interleave with the chat flow;
new `--verbose` flag restores `WARNING`; `TASKER_LOG_LEVEL` (when
explicitly set) still wins over both. Bug caught while adding
`--verbose`: `_first_positional()` assumed every `--flag` token takes a
value, so a boolean flag like `--verbose` silently swallowed the next
real token (task text or a subcommand) as its "value" — fixed with an
explicit `_BOOL_FLAGS` set.

**Tests:** 659 → 677 (+18: 5 in `test_worker_registry.py`, 2 new in
`test_dispatch_provider_wiring.py`, 11 new in `test_cli_shell.py`). Full
suite green.

**Live smoke test (Designlab1, local-only, zero cloud spend — slash-command
testing only, no chat/tool dispatch run):** `tasker-cli shell`, typed
`/chat` → `Unknown command: /chat  (did you mean: /mode chat?)`; typed
`/wrkers` → `Unknown command: /wrkers  (did you mean: /workers?)`;
confirmed no plumbing warnings print by default.

**Files modified:** `tasker/workers/registry.py`
(`apply_provider_availability`), `tasker/runtime/dispatch.py` (wired
into `_run_task`/`_resume_task`), `cli/shell.py` (`_suggest_command`,
`--verbose`, `_BOOL_FLAGS` fix to `_first_positional`),
`tests/unit/test_worker_registry.py`,
`tests/unit/test_dispatch_provider_wiring.py` (new),
`tests/unit/test_cli_shell.py` (new), `docs/TESTING_GUIDE.md` (new
H10), `docs/TASKER_CHECKLIST.md`, `CLAUDE.md`, `COWORK_PROMPT.md`.

**Next task:** SDD_ADDENDUM_PHASE8.md Phase 8.4 — SetupWizardScreen +
ModelSelectorScreen (still not started; see the Phase 8.3 notes below
for scope). Also still open: wiring Anthropic/OpenAI/Fugu providers into
`provider_map` (this session made the gap *safe*, not *closed* — those
providers are still unreachable, just no longer a silent failure);
budget persistence across process restarts; orchestrator-planned
`ExecutionPlan` in the API path.

**Blockers:** None.

**Open decisions:** None new this session.

---

## Previous Session Notes (Phase 8.3 Textual TUI skeleton, kept for reference)

**Last worked on:** SDD_ADDENDUM_PHASE8.md Phase 8.3 — Textual TUI
skeleton (`TuiApp`, `WelcomeScreen`, `HardwareStatusBar`), superseding
the one-session rudimentary REPL. Full write-up in
`docs/TASKER_CHECKLIST.md` → "Phase 8.3 -- Textual TUI Skeleton
(2026-07-19)".

**SDD-first reconciliation, before any code:** the addendum had three
mutually inconsistent claims about which sub-phase owns SetupWizardScreen/
ModelSelectorScreen (B.5.2's comments, B.8's roadmap table, and B.11's
detailed checklist each disagreed). Asked the user to confirm scope
rather than guess; confirmed B.11 (skeleton-only for 8.3, SetupWizard+
ModelSelector bundled into 8.4) is authoritative, matching this
project's established one-atomic-phase-at-a-time pattern. Corrected B.8
and B.5.2 to match B.11 before writing any code.

**What was built:** `tasker/tui/app.py` now has a real `TuiApp(App)` +
`main()` — the REPL's `_repl()`/`_dispatch()` functions are gone (they
were documented from day one as a deliberate, temporary interim, not
meant to survive this phase). `tasker/tui/screens/welcome.py`:
`WelcomeScreen` renders the full B.5.2 menu (Setup Wizard, Model
Selector, Run Task, View Sessions, Daemon, Quit) up front so 8.4/8.5
don't need a second layout change; only Quit is wired, the rest show an
inert "coming in Phase 8.x" notice pointing at the headless command that
covers the same ground today. `tasker/tui/widgets/status_bar.py`:
`HardwareStatusBar`, a reactive one-line bar per B.5.4's bracketed
format, reading the machine-local hardware cache directly (never a live
subprocess call — same A.3.1 convention as every other entry point),
including its pre-computed `computed_profile` block rather than
re-deriving a profile a second time. `tasker/runtime/dispatch.py`
(actually reusable) is untouched, carried forward as planned for 8.4/8.5
to build on — nothing in this phase duplicates it. For an interactive
CLI session in the meantime, `tasker-cli shell` still works (its own,
separate, longer-standing REPL).

**Manual verification (Designlab1, per B.8's screenshot-or-transcript
requirement since Textual rendering can't be fully unit-tested):**
`tasker` launched in a real pty (`script -qc "timeout 3 tasker"
/dev/null`) and ran the full 3s with no crash. Real (unmocked) headless
screenshots captured via `App.export_screenshot()` against this
machine's actual cached hardware detection, published as an artifact for
visual review — confirmed real values on screen (12-core CPU, GTX 1050
Ti 4096MB, tier 2, resident) and a real menu-selection notice. Caught and
fixed a real bug during this step: `ram_gb` was rendering as an unrounded
float (`15.307815551757812`) — now rounded to whole GB, with a
regression test. TASKER-P1 manual verification not done this session (no
access to that machine), same as every prior phase that needed it.

**Tests:** 668 → 659 (net −9: −30 deleted REPL tests, +21 new TUI tests
across `test_tui_app.py`, new `test_tui_welcome_screen.py`, new
`test_tui_status_bar.py`, all driven headlessly via Textual's
`App.run_test()`/`Pilot` — no real terminal, no live Ollama, no live
hardware detection). Full suite green.

**Files modified:** `tasker/tui/app.py` (rewritten — TuiApp/main(), REPL
removed), `tasker/tui/screens/welcome.py` (new), `tasker/tui/screens/
__init__.py` (new), `tasker/tui/widgets/status_bar.py` (new),
`tasker/tui/widgets/__init__.py` (new), `tests/unit/test_tui_app.py`
(rewritten), `tests/unit/test_tui_welcome_screen.py` (new),
`tests/unit/test_tui_status_bar.py` (new), `docs/SDD_ADDENDUM_PHASE8.md`
(B.8/B.5.2 reconciliation), `docs/TESTING_GUIDE.md` (H8 marked
superseded, new H9), `docs/TASKER_CHECKLIST.md`, CLAUDE.md,
COWORK_PROMPT.md. No `pyproject.toml` change needed (`tasker`/`tasker-cli`
entry points already correct); reinstalled with `pip install -e .`
anyway (venv confirmed via `which python`/`which pip` first).

**Next task:** SDD_ADDENDUM_PHASE8.md Phase 8.4 — SetupWizardScreen
(wraps `tasker/setup/wizard.py`'s `run_wizard()`, live per-step status,
re-run buttons, GPU guidance panel) + ModelSelectorScreen (wraps
`tasker/setup/readiness.py`'s `ReadinessChecker`, two-panel layout,
async "Test Model" with a progress indicator, "Add to Registry" button).
B.11's checklist also calls for the Textual message bus
(`WizardStepCompleted`, `ReadinessCheckCompleted`, `WorkerRegistryUpdated`)
this sub-phase. Then Phase 8.5 (HarnessPanel, built on
`tasker/runtime/dispatch.py`). TASKER-P1 manual verification for 8.3
remains open. Other carried-over candidates unchanged: wire Anthropic/
OpenAI/Fugu providers into the provider_map; budget persistence across
process restarts; orchestrator-planned `ExecutionPlan` in the API path.

**Blockers:** None.

**Open decisions:**
- `active_model`/`session_state` on `HardwareStatusBar` are inert
  placeholders until 8.4/8.5 exist to drive them.
- No explicit dark/light theme decision — Textual's own default theme
  applies; revisit if the addendum ever specifies a visual direction.

---

## Previous Session Notes (Rudimentary TUI REPL, kept for reference)

**Last worked on:** Rudimentary interactive TUI REPL at `tasker/tui/app.py`
(behind the `tasker` console script), replacing the Phase 8.1
"coming in Phase 8.3" stub. Deliberate scoped deviation from
SDD_ADDENDUM_PHASE8.md B.5 (full Textual TUI, still Phase 8.3-8.5, not
started) -- documented SDD-first as new B.5.0. Full write-up in
`docs/TASKER_CHECKLIST.md` → "Rudimentary TUI REPL -- `tasker/tui/app.py`
(2026-07-19)".

**What was built:** Extracted `cli/shell.py`'s pipeline-building/dispatch
logic (`_build_pipeline`, `_build_session`, `_execute_steps`, `_run_task`,
`_resume_task`, serialization helpers, policy resolution) plus two new
helpers (`_load_registry()`, `_print_workers()`/`_print_checkpoints()`)
into a new shared module, `tasker/runtime/dispatch.py`. `cli/shell.py`
re-imports every name unchanged (same names, leading underscore and all)
so its own tests and behavior are untouched -- verified by running the
full suite green immediately after the extraction, before any TUI code
was added. `_run_task()` gained a backward-compatible optional
`pipeline=` kwarg so a caller can reuse a pre-built pipeline instead of
always constructing a fresh one.

`tasker/tui/app.py` is now a real REPL: `/mode [chat|code|cowork|
research|secure]` (get/set, mode shown in the prompt as `tasker
(mode)>`), `/workers`, `/budget`, `/resume <id>|--last`, `/checkpoints`,
`/help`, `/quit`/`/exit`; non-slash input dispatches as a task in the
active mode through the real orchestrator → provider pipeline, same as
`tasker-cli`. The one genuinely new piece of behavior (not just reuse):
each mode lazily builds and caches its own pipeline on first use, reused
across turns in that mode, so `/budget` shows real accumulating usage
instead of resetting every call the way `cli/shell.py`'s CLI and
`tasker/api/server.py`'s API both do. Honestly scoped as per-mode, not
the true single-account budget (SDD 5.10) — documented, not silently
glossed over. A paused pipeline is evicted from the cache so the next
task in that mode starts fresh rather than sitting in `HOLD` forever.

**Live smoke test** (Designlab1 WSL, Ollama 0.30.11 @ 127.0.0.1:11435 —
confirmed reachable first, never started): a scripted stdin session
through the real `tasker` entry point. `/budget` before any task showed
config-only info; a chat-mode task ("Say hello in exactly three words.")
dispatched through a real `SingleLLMOrchestrator` plan → `lfm2.5-local`
worker (7.3s) → synthesis, zero cloud spend; `/budget` after showed real
live usage (`0.0/3000 units`, correctly zero since local calls don't
consume Ollama Cloud budget); `/mode cowork` updated the prompt; a
cowork-mode task ("list files via bash") exercised a real
`run_tool_loop` dispatch and **live-triggered the Phase 8.3 tool-loop
non-termination guard** (identical consecutive tool call on turn 2,
terminated early as designed) after one empty-content retry, then
synthesized a correct answer; final `/budget` showed cowork's own
separate window, correctly demonstrating the per-mode (not global)
scoping; `/quit` exited cleanly. No stray files (the cowork task was
read-only by design).

**Venv discipline:** every python/pip/`tasker-*` command this session
was preceded by `source .venv/bin/activate` + `which python`/`which pip`
confirmation, per the standing instruction from the prior session.

**Tests:** 638 → 668 (30 new in `tests/unit/test_tui_app.py`; the
`tasker/runtime/dispatch.py` extraction itself added none, by design —
it's a pure move). Full suite green throughout, including immediately
after the extraction (before any new TUI code existed) to confirm zero
behavior change to `cli/shell.py`.

**Files modified:** `tasker/runtime/__init__.py` (new),
`tasker/runtime/dispatch.py` (new — extracted from `cli/shell.py`),
`cli/shell.py` (imports from the shared module, no behavior change),
`tasker/tui/app.py` (real REPL, was a stub), `tests/unit/test_tui_app.py`
(new, 30 tests), `docs/SDD_ADDENDUM_PHASE8.md` (new B.5.0),
`docs/TASKER_CHECKLIST.md`, `docs/TESTING_GUIDE.md` (new H8), CLAUDE.md,
COWORK_PROMPT.md. No `pyproject.toml` change needed — `tasker =
"tasker.tui.app:main"` already pointed here from the Phase 8.1 stub;
reinstalled with `pip install -e .` anyway to pick up the new
`tasker/runtime/` package.

**Next task:** SDD_ADDENDUM_PHASE8.md Phase 8.3-8.5 — the full Textual
TUI (WelcomeScreen, HardwareStatusBar, SetupWizardScreen,
ModelSelectorScreen, HarnessPanel) that supersedes this REPL. This
REPL's `_repl()`/`_dispatch()` logic is not expected to carry forward
into the Textual screens (different interaction model); only
`tasker/runtime/dispatch.py` is expected to be reused there too. Other
carried-over candidates: wire Anthropic/OpenAI/Fugu providers into the
CLI/TUI provider_map; budget persistence across process restarts;
orchestrator-planned `ExecutionPlan` in the API path (still
`_stub_plan`); TASKER-P1 live runs of `tasker-setup`/`tasker`.

**Blockers:** None.

**Open decisions (also in TASKER_CHECKLIST.md's Rudimentary TUI REPL
section):**
- Per-mode (not per-account) budget scoping in the REPL — a real
  architectural simplification, should be revisited if/when the true
  SDD 5.10 single-account model needs representing in an interactive
  session.
- No `--mode`/other CLI flags on `tasker` itself (always starts in
  `chat`) — not requested this session, trivial to add later.

---

## Previous Session Notes (API server launchability, kept for reference)

**Last worked on:** Made the OpenAI-compat API server (`tasker/api/server.py`,
built in Phase 7) actually launchable, so a WebUI can connect. Standalone
ops/launch task, not part of the SDD_ADDENDUM_PHASE8 numbering. Full
write-up in `docs/TASKER_CHECKLIST.md` → "API Server Launchability --
`tasker-api` (2026-07-19)".

**What was built:** `server.py:main()` (new `tasker-api` console script)
wired the same way as `cli/shell.py`'s `main()`: `TASKER_PROFILE` env
resolution, `OLLAMA_BASE_URL` env override, a `provider_map` with a
shared `OllamaSessionBudget`/`OllamaCloudConcurrencyManager` on the
`OllamaProvider`, hardware-cache GPU availability cross-check on the
registry. `--host`/`--port` (default `127.0.0.1:8555`) and `--mode`
(restrict to one of the 5 modes) flags. `create_app()` gained optional
`provider_map`/`concurrency_mgr`/`allowed_modes` kwargs (test `_step_fn`
override still wins). New `_make_live_step_fn()` drives a real
`WorkerSelector` → `WorkerTask` → `run_tool_loop()` dispatch for
`CoworkRunner`, and `_handle_completions` now wraps `runner.run()` in
try/except (worker failure → HTTP 500 with reason, was an uncaught
exception before). Bug fixed in the same pass: `_stub_plan()` truncated
its step description to 80 chars — harmless while the server only ever
echoed a stub string, but that description becomes the real worker
instruction once a live `step_fn` is wired, so any prompt over 80 chars
was silently being cut off. Now carries the full task text (regression
test with a 200-char prompt). `pyproject.toml`: added
`tasker-api = "tasker.api.server:main"`.

**Live smoke test** (Designlab1 WSL, Ollama 0.30.11 @ 127.0.0.1:11435 —
confirmed reachable first, never started, per the binding Ollama server
rules above): started `tasker-api` in the background against the real
WSL server. `GET /v1/models` → 200 (all 5 modes), `GET /v1/workers` → 200
(real registry), `POST /v1/chat/completions` with `tasker/chat` and a
real prompt → 200, correct OpenAI `chat.completion` shape, genuine answer
from the local `lfm2.5-thinking` worker via the real dispatch path (not
the stub echo), zero cloud spend, ~44s (thinking-model latency, consistent
with prior sessions). Server stopped cleanly. Fixed the startup banner
print (`flush=True`) after the first run showed it buffering indefinitely
under `nohup`.

**Venv discipline this session:** Roland flagged that a previous session
may have run outside `.venv`. Every python/pip/`tasker-*` command this
session was preceded by `source .venv/bin/activate` and a `which
python`/`which pip` check confirming `.venv/bin/*` before proceeding,
including immediately before `pip install -e .`.

**Tests:** 630 → 638 (12 new/changed in
`tests/integration/test_api_server.py`: live-dispatch success/failure/
no-truncation, stub-fallback-when-unwired, step_fn-override-priority,
`allowed_modes` filtering on both endpoints). Full suite green.

**Files modified:** `tasker/api/server.py` (main() + live dispatch +
allowed_modes + stub-plan truncation fix), `pyproject.toml` (tasker-api
entry), `tests/integration/test_api_server.py` (+12),
`docs/TESTING_GUIDE.md` (new H7 — H6 was already taken by the setup
wizard from the prior session), `docs/TASKER_CHECKLIST.md`, `CLAUDE.md`,
`COWORK_PROMPT.md`.

**Next task:** No orchestrator-planned `ExecutionPlan` in the API path
yet (still `_stub_plan`, one step per request) — wiring the orchestrator
tier into `/v1/chat/completions` was explicitly out of scope this
session. SDD_ADDENDUM_PHASE8.md Phase 8.3 (TUI foundation) remains the
next queued addendum task. No WebUI container/reverse-proxy work done
(explicitly out of scope, per the task's own framing).

**Blockers:** None.

**Open decisions (also in TASKER_CHECKLIST.md's API Server section):**
- `_handle_completions` still builds a fresh per-request
  `OllamaSessionBudget`/`SessionManager`, separate from the provider's
  own shared budget used for GPU-time accounting — pause/resume
  checkpoint snapshots via the API don't reflect real cumulative cloud
  usage. Pre-existing architecture, not touched this session.
- Should `/v1/chat/completions` eventually plan through a real
  orchestrator tier instead of `_stub_plan`'s single step? Needed for
  multi-step COWORK-mode requests through a WebUI to actually behave like
  COWORK; deferred as orchestrator work.

---

## Previous Session Notes (SDD_ADDENDUM_PHASE8.md Phase 8.2, kept for reference)

**Last worked on:** SDD_ADDENDUM_PHASE8.md Phase 8.2 — Agentic Readiness
Checker (`tasker/setup/readiness.py` + `tasker-setup --check-model`), the
*addendum's* 8.2 (third use of that number in this project). Headless
Cowork-supervised session on Designlab1 (WSL, Ollama 0.30.11 @
127.0.0.1:11435). Full write-up in `docs/TASKER_CHECKLIST.md` → "Phase
8.2 -- Agentic Readiness Checker (addendum numbering)".

**What was built:** `ReadinessChecker.check()` runs the B.4.3 3-round
probe (NATIVE → LFM25 → JSON_EXTRACT, later rounds skipped after a
success) through the real `OllamaProvider`, so a passing round exercises
the exact production code path. Success = extracted call names
`get_current_time` with the required `timezone` arg. On success:
suggested `WorkerManifest` (existing registry entry's id/capabilities/
usage-level reused — a re-check never narrows a worker; probe verdict
wins on tool_protocol; `context_window` from `/api/show`'s
`*.context_length`, fallback existing entry then 8192; `latency_class`
from measured probe duration; `worker_role` per B.4.6 `assign_roles()`),
B.4.4 report via `format_report()`, and a [Y/n]-confirmed registry write
(`write_manifest_to_registry()` — text-splicing, preserves the YAML's
hand comments; append for new id, exact-block replace for existing id).
CLI: `tasker-setup --check-model <name>` (+ `--yes`, `--registry PATH`,
`--ollama-url`). SDD-first additions to the addendum: B.4.3 success
criterion, B.4.3a (JSON_EXTRACT injection format — `inject_tools()` now
injects for JSON_EXTRACT, was pass-through; `_extract_json()` gained a
raw_decode fallback so nested `arguments` objects parse), and the B.4.2
cloud-model exception (pull gate applies to LOCAL models only —
live-verified that a signed-in server serves `:cloud` models via
`/api/chat` while they're absent from `/api/tags`).

**Live findings (both smoke tests done on real hardware):**
1. `lfm2.5-thinking:latest` → **NATIVE now SUPPORTED on Ollama 0.30.11**
   — Ollama returned a correct `tool_calls[]` for the probe. A.2b's
   "rejects tools[] for this family" no longer reproduces on this server
   version. Forced Round 2 (LFM25) also passed live (bare-object JSON,
   18.8s). The real registry was deliberately left at `lfm25`
   (known-good, validated E2E 8.1–8.3) — flipping to native is an open
   decision requiring tool-loop revalidation on both machines.
2. `kimi-k2.7-code:cloud` → native, ~1s probe, and `/api/show` reports
   real context 262144 vs the hand-written registry's 128000 (stale).
   Registry writes validated against scratch copies only; real registry
   untouched this session.
3. **Bonus provider fix** (found live by the probe): the empty-content
   retry loop now checks `not msg.get("tool_calls")` — a native tool
   call from a thinking model legitimately has empty content +
   `tool_calls[]`, and the old condition burned 2 extra (budgeted, if
   cloud) calls per native tool call. Regression test added.

**Tests:** 595 → 630 (28 new in `test_readiness.py`, +6 net normalizer
tests incl. JSON_EXTRACT injection + raw_decode fallback scan, +1
provider retry regression), full suite green.

**Files modified:** `tasker/setup/readiness.py` (new),
`tasker/setup/wizard.py` (--check-model implemented, stub removed),
`tasker/tools/normalizer.py` (JSON_EXTRACT injection + `_scan_json_calls`),
`tasker/workers/providers/ollama.py` (retry guard),
`docs/SDD_ADDENDUM_PHASE8.md` (B.4.2 exception, B.4.3 criterion, B.4.3a),
`tests/unit/test_readiness.py` (new), `tests/unit/test_tool_normalizer.py`,
`tests/unit/test_provider_ollama.py`, `docs/TASKER_CHECKLIST.md`,
`docs/TESTING_GUIDE.md` (new H6), `CLAUDE.md`, `COWORK_PROMPT.md`.

**Next task:** Addendum Phase 8.3 — TUI foundation (real `TuiApp`,
`WelcomeScreen`, `HardwareStatusBar`; `tasker/tui/app.py` is currently a
stub). Then 8.4 (SetupWizardScreen + ModelSelectorScreen wired to the
readiness checker) and 8.5 (HarnessPanel). Carried-over candidates: wire
Anthropic/OpenAI/Fugu providers into the CLI provider_map (or pre-filter
unroutable workers); budget persistence across restarts (SDD 5.10);
TASKER-P1 live runs of `tasker-setup` (wizard + readiness) — this
session had no access to that machine.

**Blockers:** None.

**Open decisions (also in TASKER_CHECKLIST.md Phase 8.2 section):**
- Flip `lfm2.5-local` to `tool_protocol: native`? Probe says 0.30.11
  supports it natively; requires end-to-end tool-loop revalidation first.
- Update `kimi-k2.7-code-cloud` context_window 128000 → 262144 and
  latency medium → fast (probe-derived)? Both change live selection
  behavior; a 1-token probe's latency is not necessarily representative.
- Unchanged from before: LFM2.5 empty-content bug (parked; the retry
  path itself got safer this session but the root cause is still
  unconfirmed); Tier 2 same-model-for-both-roles bug;
  `resolve_hardware_profile()` still not wired into `_run_task()`.

---

## Previous Session Notes (COWORK_PROMPT tasks 8.1–8.3, kept for reference)

**Last worked on:** COWORK_PROMPT tasks 8.1 (live cloud-path E2E
validation), 8.2 (tier4_cloud.py reachability), and 8.3 (tool-loop
non-termination guard) — the full PHASE 8 TASK LIST — on Designlab1
(headless Cowork-supervised session). Full write-ups in
`docs/TASKER_CHECKLIST.md` → "Phase 8.1"/"Phase 8.2"/"Phase 8.3"
sections (COWORK_PROMPT numbering).

**Task 8.3 summary:** SDD 5.7a updated first, then `run_tool_loop`
(`tasker/tools/loop.py`) gained the second guard condition. Hard cap:
verified already correct — `max_turns=5` strictly bounds provider calls
(existing exactness test kept, updated to vary its commands per turn).
New: repeated-identical-call detection — a turn requesting the identical
tool-call set (names + arguments, order-sensitive, sorted-key-JSON
compared) as the immediately preceding turn terminates the loop at that
turn with a WARNING, without executing the duplicates or spending
another provider call (on a cloud worker every wasted turn is a budgeted
call — this exact stuck pattern was observed live in the 7.5.4–7.5.6
session, where lfm2.5-thinking burned all 5 turns). Non-consecutive
repeats stay allowed (ls → pwd → ls is legitimate re-checking). 4 new
tests in `test_tool_loop.py` (early termination at 2 calls, same-tool/
different-args negative, non-consecutive negative, multi-call-set
positive). Suite 591 → 595, green.

**Task 8.2 summary:** Tier 4 was unreachable through three independent
gates: (1) machine profiles cap tier_max at 2/1 — by design, kept;
(2) no mode allowed tier 4 (max was cowork/research at 3) — a genuine SDD
gap (the ladder defined Tier 4 but nothing could select it), fixed
SDD-first: SDD 5.1 COWORK now "2–4", new SDD 5.3 "Tier 4 activation"
paragraph (explicit config opt-in, never hardware detection; local
orchestrator location degrades to Tier 3 per 10.3), cowork.yaml
tier_max 3→4 (effective tier unchanged on both standard machines);
(3) `build_orchestrator()` never constructed CloudOrchestrator — fixed:
tier ≥ 4 + `orchestrator.compute_location: ollama_cloud` →
`CloudOrchestrator` (which routes through `provider.execute()`, so 8.1's
slot/budget wiring applies to Tier 4 orchestration calls automatically);
local location degrades to Tier 3 with a WARNING. New opt-in profile
`config/profiles/tier4_cloud_hybrid.yaml` (kimi-k2.7-code:cloud planner).
Live-confirmed: `Planning with CloudOrchestrator...`, cloud plan (+3.4u),
reasoning step on nemotron cloud, writing step on LOCAL lfm2.5, correct
synthesis — the exact SDD 5.3 hybrid. +5 net factory tests incl.
`TestTier4Reachability` driving the real shipped YAMLs
(designlab×cowork→2, tasker-p1×cowork→1, tier4_cloud_hybrid×cowork→4,
tier4_cloud_hybrid×chat→1). Suite 586 → 591, green.

**Summary:** the unit-tested session layer was genuinely NOT wired into
the live CLI path (exactly what 8.1 suspected): `OllamaSessionBudget` had
zero production `record_usage()` callers, `SessionManager.tick()` was
never called, no checkpoint was ever written during a run, `tasker
resume` was a stub, `WorkerSelector` got hardcoded `slots_available=1,
should_throttle=False`, and tiers 2/3/4 returned NanoOrchestrator
fallback plans without setting `used_fallback` (only tier 1 did — and
tier 2 is the live tier on Designlab1). All fixed with regression tests:

1. `used_fallback = True` on fallback in tier2/3/4 `plan()` (+3 tests).
2. `OllamaProvider(base_url, concurrency_mgr, budget)` — new optional
   budget records `compute_usage_units(elapsed_s, usage_level)` (wall
   clock × level, None billed as 1) on every successful OLLAMA_CLOUD
   call, covering worker AND orchestrator cloud calls since both share
   the one provider instance (+7 tests).
3. `cli/shell.py` restructured: `_build_pipeline()` (config + budget +
   SessionManager + concurrency + provider + orchestrator, shared by run
   and resume), `_execute_steps()` (tick() before every dispatch; PAUSE →
   Checkpoint.new with plan/completed-records/budget-snapshot →
   `SessionManager.pause()` → banner with resume command; throttle
   directive → `should_throttle=True` into selector; live
   `concurrency_mgr.slots_available` threaded in), `_resume_task()` (real
   SDD 9.4 flow: fresh budget window, `SessionManager.resume()`, continue
   from `current_step_index`, synthesize prior+new results).
   `--policy` flag now actually applied (was parsed and ignored);
   `OLLAMA_BASE_URL` env now overrides profile YAML (Designlab1 serves on
   127.0.0.1:11435 via systemd port.conf — the YAML's 11434 could never
   connect); `TASKER_LOG_LEVEL` wired to `logging.basicConfig`;
   `TASKER_BUDGET_PRELOAD` env (float units) pre-loads the budget so
   throttle/pause paths can be validated live without burning ~45min of
   real cloud GPU-time (+9 tests in `test_cli_session_wiring.py`).
4. `tier2_designlab.yaml`: added `orchestrator.model:
   lfm2.5-thinking:latest` — the factory's default (qwen3:1.7b) isn't
   installed on Designlab1, so live tier-2 planning had never actually
   been possible on the machine this profile is for. New
   `tier2_designlab_cloud.yaml` variant (orchestrator
   `kimi-k2.7-code:cloud`, `compute_location: ollama_cloud`) for the
   cloud-path runs.
5. INFO logs for slot acquire/DENIED/release (concurrency.py) and per-call
   budget increments (provider) — this is the live observability the
   evidence rests on.

**Live evidence highlights (Ollama 0.30.11, signed in as Rojman1984):**
multi-step COWORK run planned by kimi cloud, step 0 routed to
`nemotron-3-ultra-cloud` via the `reasoning` capability (+46.4 units =
15.5s × level 3), step 1 local, cloud synthesis — budget 0 → 59.1/3000
visibly accumulating; FREE-plan saturation demo: 2 truly concurrent real
cloud calls → one `success`, one immediate `deferred` ("slot DENIED — all
1 slot(s) in use"); preloaded-exhaustion run paused with a real
checkpoint, and `tasker resume --last` in a fresh process completed both
steps + synthesis correctly (`3^6 = 729 > 6! = 720`).

**Small planner caveat found live:** `lfm2.5-thinking` as tier-2 planner
invents off-vocabulary capability names (`calculation`, `summarization`)
which `parse_plan()` correctly drops → steps degrade to `{tool_use}` →
always route local. The kimi cloud planner follows the vocabulary. Not a
bug (parse behaves as designed), but it means local-planner runs rarely
route steps to cloud workers on their own.

**Tests:** 567 → 586 (task 8.1) → 591 (task 8.2) → 595 (task 8.3), full
suite green throughout (also re-verified after every live-run-driven fix).

**Last files modified:** task 8.1 — `cli/shell.py` (major),
`tasker/workers/providers/ollama.py`, `tasker/session/concurrency.py`,
`tasker/orchestrator/tier2_dual.py`, `tier3_reasoning.py`,
`tier4_cloud.py`, `config/profiles/tier2_designlab.yaml`,
`config/profiles/tier2_designlab_cloud.yaml` (new),
`tests/unit/test_cli_session_wiring.py` (new),
`tests/unit/test_provider_ollama.py`, `tests/unit/test_orchestrator_tier{2,3,4}.py`.
Task 8.2 — `docs/SDD.md` (5.1 + 5.3 Tier 4 activation),
`config/modes/cowork.yaml` (tier_max 4),
`tasker/orchestrator/factory.py` (tier ≥ 4 → CloudOrchestrator),
`config/profiles/tier4_cloud_hybrid.yaml` (new),
`tests/unit/test_orchestrator_factory.py`. Task 8.3 — `docs/SDD.md`
(5.7a guard), `tasker/tools/loop.py`, `tests/unit/test_tool_loop.py`.
All — `docs/TASKER_CHECKLIST.md`, `docs/TESTING_GUIDE.md`, `CLAUDE.md`,
`COWORK_PROMPT.md`.

**Next task:** COWORK_PROMPT's PHASE 8 TASK LIST (8.1–8.3) is complete.
Next up is `SDD_ADDENDUM_PHASE8.md` Phase 8.2 — Agentic Readiness
Checker (`tasker/setup/readiness.py`, 3 probe rounds
NATIVE→LFM25→JSON_EXTRACT, `tasker-setup --check-model <name>`, worker
registry write on confirmation, `WorkerRole` assignment per B.4.6) —
note this "8.2" is the *addendum's* numbering, not COWORK_PROMPT's
just-completed task 8.2. Then addendum 8.3–8.5 (TUI foundation, model
selector, harness panel). Also worth considering: the Known Open Issues
from E2E 8.1 (CLI provider_map only wires Ollama; budget persistence).

**Blockers:** None.

**Open decisions / new known issues (also in TASKER_CHECKLIST.md):**
- CLI `provider_map` wires only OllamaProvider; ANY_CLOUD selection can
  legally pick Anthropic/OpenAI/Fugu workers (observed live under
  throttle: `claude-haiku-4-5` selected → "No provider for anthropic").
  Wire the other providers or pre-filter unroutable workers.
- Cloud-orchestrator plan/synthesize calls are not tick()-gated — an
  exhausted budget still permits the planning call (deliberate: a
  checkpoint without a plan cannot resume; observed +3.1u at 101.8%).
- Budget state doesn't persist across process restarts (SDD 5.10 says it
  should) — only the checkpoint's BudgetSnapshot persists.
- Under throttle, the heavy-cloud filter runs before the capability
  filter (SDD 5.5 order), so `{reasoning, thinking}` steps can end up
  with no eligible worker and fail selection cleanly — by design, but
  surprising live.
- Unchanged from before: LFM2.5 empty-content bug (parked, hypotheses 1–3
  ruled out — do not re-test); Tier 2 same-model-for-both-roles bug
  (`planner_model`/`synthesizer_model` YAML keys still unread);
  `resolve_hardware_profile()` still not wired into `_run_task()` (still
  env-var/`load_profile()` based).

---

## Previous Session Notes (Phase 7.5.4–7.5.6, kept for reference)

**Last worked on:** Phase 7.5.4–7.5.6 (`AmdApuBackend` + worker VRAM
cross-check + final paired live verification), followed by an
unplanned-but-user-approved expansion into fixing 4 real pipeline bugs
discovered while actually running the full CLI smoke test end-to-end on
both machines for the first time this thoroughly.

**SSH-based remote verification workflow (reusable pattern for future
TASKER-P1 sessions):** this session ran entirely from Designlab1, reaching
TASKER-P1 over SSH rather than physically switching machines. No
`~/.ssh/config` entry existed yet for `tasker-p1` — the bare hostname
resolves on the network but auth as user `tasker` failed; the correct
user is `tasker0`. Added a permanent `~/.ssh/config` entry (`Host
tasker-p1` → `User tasker0`) so `ssh tasker-p1 '...'` works verbatim
going forward. Pattern used throughout: implement + unit-test locally,
commit + push, `ssh tasker-p1 'cd ~/projects/ollama-tasker && git pull &&
source .venv/bin/activate && ...'` to pull and re-verify remotely — never
edited files directly over SSH. TASKER-P1 needed a fresh `git clone` and
`python3 -m venv .venv && pip install -e ".[dev]"` this session (first
time this repo was checked out there); Ollama itself (v0.20.2) was
already installed and running as a systemd service.

**Phase 7.5.4/7.5.5 — `AmdApuBackend`:** implemented in
`tasker/config/gpu_backends.py` alongside `NvidiaBackend`/`NoGpuBackend`
(not a separate module), mirroring `NvidiaBackend`'s detect()/verify_live()
shape. `detect()`: lspci -nn presence check (Windows: Get-CimInstance),
vulkaninfo informational check (never gates), 3-env-var check
(`OLLAMA_VULKAN`, `ROCR_VISIBLE_DEVICES`, `HIP_VISIBLE_DEVICES`) with a
gfx902-specific crash warning when Vulkan is on but ROCm isn't disabled,
video/render group check via the `grp` module (no subprocess),
`memory_mb` = total system RAM (never a sysfs VRAM figure — see
`GPUInfo`'s docstring). `verify_live()`: `/api/ps` `size_vram` primary
check + `journalctl -u ollama -n 200` supplementary parsing, priority-
ordered per A.4.4 (crash signature → `verified=False`; "offloaded N/M" →
`offload_status` full/partial). Wired into `detect_gpu()`'s chain and the
`tasker-hardware verify` subcommand. Also added
`_apply_unified_memory_tier_override()` (`tasker/config/detect.py`) — a
dedicated tier-computation path for unified-memory GPUs, gated on
`is_unified_memory` not a vendor string (future-proofs for e.g. Apple
Silicon), that layers `tier_max`/`load_strategy` onto the existing
`tier1_tasker.yaml` base profile rather than switching to
`tier2_designlab.yaml` the way the NVIDIA branch does — that file's
`qwen3` orchestrator models aren't installed on an AMD APU machine, so
reusing it for a tier-2-eligible AMD box would have resolved to a broken
orchestrator model even though the tier_max number was right.
23 new tests (`test_gpu_backends.py`), 4 tier-computation tests
(`test_hardware_detect.py`), no real hardware needed.

**Live verification, TASKER-P1 (real Ryzen 5 3500U, Raven2/gfx902,
confirmed via `lspci`):** the systemd `override.conf` already had all 4
required env vars set (`OLLAMA_VULKAN=1`, `ROCR_VISIBLE_DEVICES=-1`,
`HIP_VISIBLE_DEVICES=-1`, `OLLAMA_FLASH_ATTENTION=1`) from a prior
session, and the `ollama` service account was already in `video`+`render`
groups — no fix needed, no sudo required this session (confirmed
passwordless sudo was NOT available, so this was fortunate rather than
assumed). `tasker-hardware detect` correctly resolved `gpu_vendor=
amd_apu`, `gpu_memory_mb=29013` (total system RAM), `is_unified_memory=
true`. Loaded `lfm2.5-thinking:latest` (confirmed 100% GPU via `ollama
ps`), `tasker-hardware verify` correctly parsed real journalctl output:
**"journalctl confirms full GPU offload: 17/17 layers"** →
`gpu_verified_offload_status="full"`. Note: the *interactive SSH login
user* (`tasker0`) is NOT in video/render (only the `ollama` service
account is) — `detect()`'s `group_warning` correctly flagged this as
expected/documented behavior (advisory, doesn't affect the service's
actual access).

**Phase 7.5.6 — worker VRAM cross-check:**
`WorkerRegistry.apply_gpu_availability(gpu, reserve_mb=6144)` marks
`requires_gpu=true` workers unavailable (logged reason, never silently
dropped from `list_all()`/`tasker workers`) when they don't fit: NVIDIA
discrete checked directly against `gpu.memory_mb`; AMD APU unified memory
checked against `gpu.memory_mb - reserve_mb` (6GB, within A.3.4's 4-8GB
range). Wired into `cli/shell.py`'s `main()` via the machine-local cache
(`load_cached_detection()`/new `load_cached_gpu_info()` sibling), not a
fresh `detect_gpu()` call, to avoid adding subprocess latency to every
CLI invocation — skipped entirely when no cache exists yet, preserving
pre-7.5.6 behavior. 13 new tests, mocked `GPUInfo` throughout.

**Unplanned expansion — 4 pipeline bugs found + fixed while pursuing the
final 3-stage smoke-test verification (user-approved, one bug at a time,
via explicit check-ins):**
1. `narrow_bundle_to_step()`'s no-keyword-match fallback offered the FULL
   tool bundle (a deliberate prior-session choice) — live evidence showed
   this caused `lfm2.5-thinking` to hallucinate a nonsensical tool call
   (`calculator(expression="hello")` for "say hello in exactly five
   words") instead of answering directly, then never conclude across
   repeated turns, exhausting `run_tool_loop`'s `max_turns=5`. Now falls
   back to an **empty** tool set instead (`tasker/tools/bundles.py`).
   Also added an `original_task` second-chance keyword match (new 3rd
   param, threaded through from `cli/shell.py`) for when the planner's
   step description is too garbled to match on its own — e.g. "Listing
   available workers" for what should have been "list files in current
   directory".
2. Orchestrator/worker call `timeout_s` defaulted to 120.0s
   (`factory.py`, `ollama.py`) — live-measured a single `plan()` call
   against `lfm2.5-thinking:latest` at **94.5s real time** (17417-char
   thinking block, 3922 eval tokens) for a trivial prompt, and a second
   attempt exceeded 120s outright and raised `TimeoutError`. This
   "thinking" model is just slow, not broken. Raised the default to
   240.0s in both places.
3. `parse_plan()` (`tasker/orchestrator/_parse.py`) silently corrupted
   step descriptions when the model emitted a JSON object with a
   duplicated `"description"` key — observed live: a 4-intent
   "create/verify/read/confirm" task collapsed into 2 objects each with
   2 `"description"` values; plain `json.loads()` kept only the LAST
   value per key (JSON spec's implementation-defined handling), silently
   losing the step's real first-mentioned intent with no error — the
   worker then acted on the wrong instruction and never wrote the file.
   Added a custom `object_pairs_hook`
   (`_split_duplicate_description_objects`) that splits such objects
   into multiple correctly-formed steps, recovering all originally-
   intended steps.
4. `parse_plan()` raised an uncaught `AttributeError` when a plan array
   element wasn't itself a JSON object (e.g. a bare string) — only saved
   from a hard crash by `cli/shell.py`'s outer `try/except`. Now
   validated and returns `None` (NanoOrchestrator fallback) per its
   documented contract, matching every other malformed-structure case.
   `AttributeError` also added to the except tuple as defense in depth.

Also found and fixed a **test-isolation bug** live on TASKER-P1:
`test_falls_through_to_no_gpu_when_nvidia_absent` only mocked
`NvidiaBackend.detect`, so real AMD hardware broke its "no GPU at all"
assumption — passed on Designlab1 (nothing for the unmocked
`AmdApuBackend.detect()` to find) but failed running the suite on
TASKER-P1 itself, where it genuinely found the real Vega 8 Mobile iGPU.

**Final smoke-test results:** Designlab1 — all 3 stages pass with
*correct* output: CHAT → "One, two, three, four, five." (5 words), CODE →
correctly listed real directory contents via bash (needed all 5 tool-loop
turns, but synthesis still recovered the right answer from accumulated
results), COWORK → genuinely created `hello.txt` with content "hello"
(verified on disk, then cleaned up). TASKER-P1 (via SSH) — CHAT passes
("A, B, C, D, E.", fast ~4s worker call); CODE completed without hanging
but surfaced a **5th, distinct, NOT yet fixed** bug — a flat-object tool
call (`{"command": "ls"}`, no `name`/`arguments` wrapper) wasn't correctly
inferred/executed, so the raw JSON leaked into the final synthesized
answer instead of a real directory listing; COWORK not re-tested on
TASKER-P1 this session (stopped by explicit user decision after the 5th
bug, to avoid an open-ended chain of tiny-model reliability fixes beyond
this phase's actual scope). `TestLfm25FlatObjectInference` in
`test_tool_normalizer.py` already covers this exact shape and passes, so
this is either an edge case slipping past that logic's matching rules or
a different code path entirely — not yet root-caused. See
`docs/TASKER_CHECKLIST.md`'s "Known Open Issues" section for the
reproduction command.

**Tests:** 565 → 567 (Phase A: 21 new for AmdApuBackend/tier computation;
worker-VRAM-cross-check + pipeline-fix commit: 25 new/changed net; +2 more
for the AttributeError fix; +1 test-isolation fix, no net count change).
Full suite green on both machines throughout.

**Last file modified:** `tasker/config/gpu_backends.py`,
`tasker/config/detect.py`, `tasker/workers/registry.py`, `cli/shell.py`,
`tasker/tools/bundles.py`, `tasker/orchestrator/factory.py`,
`tasker/orchestrator/_parse.py`, `tasker/workers/providers/ollama.py`,
`tests/unit/test_gpu_backends.py`, `tests/unit/test_hardware_detect.py`,
`tests/unit/test_worker_availability_vram.py` (new),
`tests/unit/test_tool_bundles.py`, `tests/unit/test_orchestrator_parse.py`,
`docs/TASKER_CHECKLIST.md`, `CLAUDE.md`.

**Next task:** Investigate the flat-object tool call inference gap found
on TASKER-P1 (5th bug above — reproduction command in
`docs/TASKER_CHECKLIST.md`). Separately, Phase 8.2 — Agentic Readiness
Checker (`tasker/setup/readiness.py`, 3 probe rounds NATIVE→LFM25→
JSON_EXTRACT, `tasker-setup --check-model <name>`, worker registry write
on confirmation, `WorkerRole` assignment per B.4.6). Still open,
**unchanged from before this session**: the original empty-content bug
itself (distinct from the tool-loop-hallucination issue fixed this
session — quantization and `think:false` were both ruled out in an
earlier session, still no confirmed lever, though it no longer causes
hangs since the 240s timeout + tool-bundle fixes); Tier 2's
same-model-for-both-roles bug (`factory.py`, tier==2 branch) plus
`tier2_designlab.yaml`'s unread `planner_model`/`synthesizer_model` keys;
wire `ModeConfigurator.resolve_hardware_profile()` into `cli/shell.py`
(still not done — `_run_task()` still calls `configurator.load_profile()`
directly with a hardcoded/env-var profile name, not the dynamic 3-source
resolution this whole phase built).
**Blockers:** None.
**Open decisions:** Whether `_UNIFIED_MEMORY_RESERVE_MB=6144` (6GB) is
the right default reserve for AMD APU VRAM cross-check, or whether it
should scale with total RAM — not stress-tested under actual multi-model
concurrent load yet. Whether the 240s orchestrator/worker timeout is
generous enough for worse-case thinking-model output on TASKER-P1
specifically (only Designlab1's 94.5s worst case was directly measured;
TASKER-P1's chat-mode worker call was fast at ~4s, but that's not
necessarily representative of its plan()/synthesize() latency under the
same heavy-thinking conditions).

---

## Diagnostic session — empty-content bug, num_predict + warmup hypotheses (Designlab1)

**Scope:** targeted diagnostic only, per explicit instruction — test two
specific hypotheses for the still-open empty-content bug (num_predict
generation-budget starvation; cold-model warmup), fix only if confirmed.
No other change was in scope.

**Step 1 — code audit (read-only):** `tasker/workers/providers/ollama.py`'s
request payload (`execute()`, ~line 190) is `{"model", "messages",
"stream": False}` plus optional `tools` — **no `options` dict is ever
constructed**, so `num_predict` is never sent; Ollama's own default
applies. **`num_ctx` is also never set.** `HardwareProfile.context_limit`
(parsed from `tier1_tasker.yaml`, e.g. `4096`) is parsed but **never
threaded into any request** — confirmed via grep, a dead config value.
Empirically (`ollama show lfm2.5-thinking:latest`): the model's own
Modelfile only sets `temperature=0.05`/`top_k=50`, no `num_predict`/
`num_ctx` override; real max context is 128,000 tokens, but `ollama ps`
shows it actually loaded with **`CONTEXT 4096`** (the effective Ollama
server default) — a real gap given `<think>` blocks routinely run
4,000–14,000+ chars. Neither `WorkerManifest` nor `WorkerTask` has any
existing field for this (`max_tokens`/`num_predict`/`options`) — grep on
`tasker/workers/base.py`, zero matches. Confirms Ollama Tasker really is
missing an equivalent of the two reference MCP scripts'
`num_predict: 32000`.

**Steps 2–4 — reproduction attempts (28 total raw `/api/chat` calls
against `lfm2.5-thinking:latest`, Designlab1, real GPU, via a standalone
script bypassing the harness to see full raw JSON incl. `thinking`):**
covered every previously-documented trigger combination —
  - Full user-wording prompt, no tools/system prompt: 3 + 8 = 11 runs, **0
    empty**. `eval_count` 1661–2260, `done_reason` always `"stop"`.
  - Terse single-word instruction ("Hello", matching the exact
    orchestrator step-description wording that triggered the bug live
    earlier in this same overall session — see the 7.5.4-7.5.6 notes
    above), no tools: 4 runs, **0 empty**. Notably fast (~3.6-4s) and
    byte-identical output across all 4 (temperature=0.05 makes this
    model highly deterministic for short prompts).
  - Terse instruction + LFM25 tool-list system prompt (matching the
    actual system-prompt shape a CODE/COWORK-mode worker call gets —
    the condition present in every earlier live observation of this
    bug): 6 runs, **0 empty**.
  - Same tool-prompt condition but with the model force-unloaded
    (`ollama stop`) immediately before the call, i.e. genuinely cold
    (Step 4, warmup hypothesis): 4 runs, **0 empty**.
  - Same tool-prompt condition with an explicit `options.num_predict:
    32000` override (Step 3, the num_predict hypothesis): 3 runs, **0
    empty**.

**Critical cross-cutting observation:** across all 28 calls, `done_reason`
was `"stop"` every single time — **never `"length"`**. `"length"` is what
Ollama reports when a response is cut off by `num_predict` (or context)
exhaustion; every one of these 28 responses completed naturally, with
`eval_count` ranging ~200 (short "Hello", no tools) to ~2260 (long
constraint-satisfaction reasoning). This is direct evidence against
generation-budget starvation being the mechanism, at least under every
condition this session could exercise — if `num_predict` (or the
effective 4096 `num_ctx`) were actually truncating responses, at least
some fraction of 28 calls with `thinking_len` up to ~9,251 chars should
have shown `done_reason="length"`. None did.

**Conclusion (Step 5): neither hypothesis could be confirmed, because
the bug could not be reproduced at all this session** — not "tested and
ruled out via a fix that didn't help," but a genuine failure to
reproduce despite exhaustively covering every condition previously
observed to trigger it live (terse wording, tool-list system prompt,
cold model). Per explicit instruction, **no fix was implemented** — a
speculative `num_predict`/warmup change would be unjustified without
evidence it addresses the actual failure mode, and could mask the real
cause for a future session that DOES catch it. **No code was changed,
nothing was committed.**

**What this session adds to the evidence trail (for whoever picks this
up next):** the bug's base rate under current conditions on Designlab1
appears low enough that 28 isolated attempts weren't enough to catch it,
despite earlier live sessions hitting it repeatedly within a handful of
full-CLI runs. Plausible explanations, none tested this session: (a) the
harness's real call path (`aiohttp`, real async concurrency, potentially
overlapping orchestrator+worker+synthesize calls) differs from this
session's serial `urllib` script in a way that matters — e.g. GPU
contention from a near-simultaneous second request; (b) the bug's
frequency is itself state-dependent on something not controlled here
(server uptime, thermal state, driver state); (c) true low-probability
sampling rarity and 28 attempts is simply not enough. **Two hypotheses
now ruled out as sole/primary causes and should not be re-tested from
scratch:** num_predict/generation-budget starvation (Step 1 confirms the
gap exists but Steps 2-4's 28/28 `done_reason="stop"` argues against it
being why), and simple cold-vs-warm model state (Step 4: 4/4 clean on a
freshly-reloaded model). The most promising untried lever, based on this
session's process-of-elimination: **reproduce via the actual harness
under real async/concurrent load** (e.g. a scripted multi-turn
`run_tool_loop()` invocation, or genuinely concurrent overlapping
requests) rather than isolated sequential raw calls, since that's the
one dimension this session's methodology could not exercise.

---

## Follow-up diagnostic session — context-window ceiling + concurrency hypotheses (Designlab1)

Two more hypotheses tested, both prompted directly by the prior session's
"untried next lever" note above. Per instruction, did not re-test
num_predict or cold/warm (both already confirmed ruled out).

### Priority 1 — context-window (`num_ctx`) ceiling

**Confirmed the underlying gap for real:** `OllamaProvider` never sets
`num_ctx` anywhere (same audit as the prior session, re-verified).
`worker_registry.yaml`'s `lfm2.5-local` entry declares
`context_window: 128000`, but that field is purely descriptive — never
threaded into any request. This part of the hypothesis was correct.

**But the reproduction test ruled it out as the empty-content bug's
cause.** Built a realistic large-context case: COWORK mode's full
14-tool bundle (LFM25-formatted tool-list system prompt) + a synthetic
multi-turn history (bash listing + file-read tool result, matching what
`run_tool_loop()` actually accumulates) + the terse "Hello" instruction.
Real tokenizer count (`prompt_eval_count`) was **3508** — notably higher
than a naive chars/4 estimate (2304), a useful calibration note for
future token-budget reasoning in this repo. Combined with generation,
`total_tokens` (`prompt_eval_count + eval_count`) actually **exceeded the
supposed 4096 default ceiling in most runs**:

  - Baseline (`num_ctx` unset, current behavior), 5 runs: **0/5 empty**.
    `total_tokens` = 4553, 4360, 4653, 4604, 4102 — i.e. 3 of 5 runs were
    *already over* 4096, with clean, complete, non-truncated answers
    every time (`done_reason: "stop"`, never `"length"`).
  - `num_ctx=32768` explicitly set, 5 runs: **0/5 empty**. `total_tokens`
    = 4548, 4753, 5342, 4409, 3723 — one run 30% over 4096. Still clean.

10/10 clean across both conditions, spanning 3723–5342 total tokens, is
strong evidence the model is not actually being hard-capped at 4096 in
practice (contrary to what `ollama ps`'s `CONTEXT 4096` column implies),
or that overflow doesn't manifest as this specific empty-content
signature. **Conclusion: `num_ctx`/context-window ceiling ruled out as
the empty-content bug's cause.** No fix applied — wiring
`WorkerManifest.context_window` through to `num_ctx` would still be a
reasonable correctness improvement on its own merits (the field is
genuinely dead today), but it does not address this bug, so it was not
implemented this session per the "fix only if confirmed" instruction.

### Priority 2 — concurrency (local calls unguarded)

**Confirmed via code read:** `tasker/session/concurrency.py`'s
`OllamaCloudConcurrencyManager` is gated by `is_cloud = worker.
compute_location == ComputeLocation.OLLAMA_CLOUD` in `OllamaProvider.
execute()` (line ~162) — for `LOCAL_HARDWARE` (every worker call on
TASKER-P1/Designlab1 today), `is_cloud` is `False` and the concurrency
manager is never consulted at all. Confirmed via grep across `cli/
shell.py`, `tasker/tools/loop.py`, and `concurrency.py` itself: there is
no semaphore, lock, or any other guard anywhere in the codebase for
local calls. This part of the hypothesis is also correct as stated —
local calls truly have zero concurrency guarding today.

**Reproduction:** fired 3 truly concurrent (`asyncio.gather` + `aiohttp`)
requests against `lfm2.5-thinking:latest`, same terse "Hello" + tool-list
prompt, across 3 batches (9 total calls). **0/9 empty or errored.**
Per-request elapsed times within a batch were staggered (e.g. batch 1:
18.9s / 39.7s / 64.4s) — confirming Ollama's server serializes GPU
inference even when requests arrive simultaneously at the HTTP layer —
and did so *cleanly*: every response had a distinct, plausible `content`
for the shared prompt (no signs of one request's output leaking into
another), all `status: 200`, all `done_reason: "stop"`.

**Conclusion: concurrency hypothesis also ruled out under the tested
conditions** (3-way concurrency, 9 total calls). The absence of any
guard is still a real, confirmed gap in the provider layer worth fixing
on its own architectural merits (silently relying on the Ollama server
to serialize correctly is fragile, and `is_cloud`-gating a manager named
`OllamaCloudConcurrencyManager` for LOCAL_HARDWARE calls was never going
to work by design) — but since it didn't reproduce the empty-content bug
here, no fix was implemented this session; a local-hardware concurrency
guard is a nontrivial provider-layer addition explicitly deferred
pending direct confirmation with the user before implementing, per this
session's instructions.

**Net result of both follow-up priorities: still no reproduction of the
empty-content bug this session** (0/10 Priority 1 + 0/9 Priority 2, on
top of the prior session's 0/28 — 47 total attempts across every
hypothesis tested so far). No code changed, nothing committed. Remaining
untested lever from the prior session's note — genuinely concurrent
*multi-turn* load specifically through `run_tool_loop()`'s history-
accumulation path (as opposed to this session's single-turn concurrent
calls) — is still open for a future session, though the base rate now
looks low enough that a much larger sample size (dozens to hundreds of
attempts) may be needed to catch it at all.

## Ollama server rules — DO NOT VIOLATE (Roland directive, 2026-07-19)

- NEVER start, restart, or launch Ollama. Do not run `ollama serve`,
  `Start-Process "ollama app.exe"`, or any command that spawns a server.
  The Windows Ollama app owns the server lifecycle on this machine.
- The API is at http://127.0.0.1:11434 (Windows app). WSL Ollama is at
  127.0.0.1:11435 — inside WSL, set OLLAMA_HOST=127.0.0.1:11435.
- If the API doesn't respond, STOP and tell Roland. Do not attempt recovery
  by starting Ollama; a second instance causes port conflicts and freezes
  the app UI. The only approved fix (run ONLY if Roland explicitly asks):
  Stop-Process -Name 'ollama app','ollama' -Force; Start-Sleep 3;
  Start-Process "$env:LOCALAPPDATA\Programs\Ollama\ollama app.exe"
- Prefer HTTP calls to /api/* over the `ollama` CLI — the CLI auto-spawns
  a server if it can't reach one, which is exactly the failure mode.
- Set OLLAMA_HOST=127.0.0.1:11434 explicitly in any environment where the
  CLI must run (11435 inside WSL), so it targets the running server instead
  of spawning one.

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

**Last worked on:** Phase 8.1 — headless setup wizard (`tasker/setup/`)
and the `tasker-setup` CLI entry point, per `docs/SDD_ADDENDUM_PHASE8.md`.
Explicitly did **not** start Phase 8.2 (readiness checker) or any TUI code
this session — `tasker/tui/app.py` is a one-line stub only.

**Mid-session detour, done first per an explicit interrupt:** appended two
new sections to `docs/SDD_ADDENDUM_PHASE8.md` — B.4.6 (Role Assignment in
Readiness Report: a new `WorkerRole` enum distinct from `AgentRole`) and a
new B.6 (Model-Agnostic Design Principle, including a preview of a future
DAEMON mode). Existing B.6–B.10 renumbered to B.7–B.11 (headings only, no
other content touched). Added `WorkerRole` enum
(`BACKGROUND_AGENT`/`EXECUTION_WORKER`/`REASONING_WORKER`/`ORCHESTRATOR`)
and `WorkerManifest.worker_role: list[WorkerRole]` (defaults to `[]`) to
`tasker/workers/base.py`, serialized in `to_dict()`/`from_dict()`, with new
round-trip tests. This field is unused by anything yet — the Phase 8.2
readiness checker is what will populate it.

**Provenance note on `docs/SDD_ADDENDUM_PHASE8.md` itself:** the file
arrived owned by `root` with a Windows `Zone.Identifier` (`ZoneId=3`,
i.e. downloaded from the internet) — unusual provenance for a repo file.
Content was verified content-coherent with the actual current codebase
(correct field names, correct existing function references matching real
code) before treating it as legitimate reference material; most likely the
user drafted/generated it in a browser session elsewhere and copied it in.
Flagged to the user at the time; no injection-style content found.

**New: `tasker/setup/environment.py`** — `is_wsl2()` (`/proc/version`
contains "microsoft"/"wsl"), `check_python()`, `check_venv()` (warns, never
blocks), `check_ollama_binary()`, `check_ollama_version()`,
`check_ollama_service()` (WSL2 vs systemd vs no-systemd remediation
messages, never auto-starts Ollama).

**New: `tasker/setup/wizard.py`** — `StepStatus`/`WizardStepResult` (per
B.3.3), `run_wizard()` (7 steps), `cli_main()`. Steps never abort early —
even an ERROR/`can_continue=False` step (e.g. Ollama unreachable) still
lets every later step run and report, so the user sees the full picture in
one pass. Step 4 (GPU verification) is `SKIPPED`, not `ERROR`, for both
"no GPU" and "no model loaded" — reuses `NvidiaBackend.verify_live()`
directly rather than re-implementing `/api/ps` parsing. Step 5 deliberately
reaches into `tasker.config.detect`'s private cache-writing helpers
(`_CACHE_PATH`, `_build_cache_dict`, `_run_live_detection`) rather than
duplicating the A.3.3 schema a second time. Step 6 flags
`tool_protocol: native` workers whose `model_id` contains "lfm2.5" as
needing `lfm25` instead (A.2b) — the *current* real registry already has
none (already fixed in the LFM25 session), so this only fires on
hypothetically-misconfigured entries; a lightweight VRAM-cross-check note
also fires for `requires_gpu=true` workers, explicitly deferring the full
A.3.4 margin-subtraction algorithm to Phase 7.5.6 rather than
reimplementing it here.

**Step 7 deliberately diverges from the addendum's own B.3.2 text:** B.3.2
defines wizard Step 7 as "Model selector + agentic readiness" (→ B.4), but
that's Phase 8.2 scope, explicitly excluded this session. This session's
task instructions directly redefined Step 7 as a Summary step instead — implemented that way, documented as an intentional deviation (not a
transcription error) in `wizard.py`'s module docstring.

`pyproject.toml`: added `textual>=0.70.0`; `tasker` entry point now points
to `tasker.tui.app:main` (stub) instead of `cli.shell:main`; added
`tasker-cli` (→ `cli.shell:main`, preserves the old default entry point
under a new name — nothing about `cli/shell.py` itself changed);
`tasker-setup` added.

400/428 → 428/428: 28 new unit tests this session (13 in
`test_environment.py`, 13 in `test_setup_wizard.py`, 2 new
`WorkerManifest.worker_role` round-trip tests). All mocked — no live
Ollama/subprocess/network calls, no writes to the real `.tasker/` cache
during tests (confirmed via a temp-path-swap test and by checking the real
cache file's mtime was untouched after the run).

**Live headless run on Designlab1 (this machine), exactly as requested:**
all 7 steps ran and printed cleanly, no unhandled exceptions. GPU step
correctly showed `nvidia (NVIDIA GeForce GTX 1050 Ti, 4096MB)`. Worker
registry step listed all 9 registered workers with protocol/availability.
Step 4 correctly `SKIPPED` (no model loaded at run time). Full output
recorded in `docs/TASKER_CHECKLIST.md`. **Did not** run on TASKER-P1 — no
access to that machine from this session; left unchecked in the checklist
rather than fabricated.

**Last file modified:** `docs/SDD_ADDENDUM_PHASE8.md`,
`tasker/workers/base.py`, `tasker/setup/__init__.py` (new),
`tasker/setup/environment.py` (new), `tasker/setup/wizard.py` (new),
`tasker/tui/__init__.py` (new), `tasker/tui/app.py` (new),
`pyproject.toml`, `docs/TASKER_CHECKLIST.md`, `CLAUDE.md`,
`tests/unit/test_environment.py` (new), `tests/unit/test_setup_wizard.py`
(new), `tests/unit/test_worker_manifest.py`.  
**Next task:** Phase 8.2 — Agentic Readiness Checker
(`tasker/setup/readiness.py`, 3 probe rounds NATIVE→LFM25→JSON_EXTRACT,
`tasker-setup --check-model <name>`, worker registry write on
confirmation, `WorkerRole` assignment per B.4.6). Separately, still open
from prior sessions: Phase 7.5.4 (`AmdApuBackend`, needs TASKER-P1); wire
`ModeConfigurator.resolve_hardware_profile()` into `cli/shell.py`; harden
`parse_plan()`'s capability-string handling; build the multi-turn
tool-result loop to unblock `tool_result_role` testing.  
**Blockers:** None.  
**Open decisions:** `tool_result_role` default (`"tool"`) still unvalidated
— needs the multi-turn loop. AMD-APU tier-computation fallthrough still
untested against real hardware — revisit once 7.5.4 lands on TASKER-P1.
`worker_role` is a schema addition only this session — no code assigns it
yet; that's Phase 8.2's job per B.4.6's rules.  

**Live model config (tier1_tasker):**  
- Orchestrator: `lfm2.5-thinking:latest` (local, 1.2B — was `qwen3:1.7b`, not installed)  
- Worker: `lfm2.5-thinking:latest` (local, 1.2B — `tool_protocol: lfm25`, was
  incorrectly `native`; was `lfm2.5:latest`, not installed)

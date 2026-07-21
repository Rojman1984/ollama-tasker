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
| 8.4 | SetupWizardScreen + ModelSelectorScreen | ✅ COMPLETE |
| 8.5 | HarnessPanel | ⬜ NOT STARTED |
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

**Last worked on:** Phase 8.4 — SetupWizardScreen + ModelSelectorScreen +
HistoryInput widget, per SDD_ADDENDUM_PHASE8.md B.3-B.5. One commit, full
suite green before push.

**What was implemented:**
- `tasker/tui/messages.py`: WizardStepCompleted, ReadinessCheckCompleted,
  WorkerRegistryUpdated Textual message classes.
- `tasker/tui/widgets/history_input.py`: reusable Input subclass with
  persistent `~/.tasker_history` (same file the REPL uses), Up/Down recall,
  Ctrl+R reverse-search overlay, and Tab-completion cycling.
- `tasker/tui/widgets/step_row.py`: WizardStepRow with status icon,
  collapsible detail, copyable action command, and per-step Re-run button.
- `tasker/tui/screens/setup_wizard.py`: SetupWizardScreen running the same
  headless `run_wizard()` in a Textual worker, with Re-run All, per-step
  Re-run, and a GPU guidance panel.
- `tasker/tui/widgets/readiness_panel.py`: ReadinessReportPanel with
  formatted report and Copy report fallback button.
- `tasker/tui/screens/model_selector.py`: two-panel ModelSelectorScreen
  (model list + readiness report), Test Model async worker, and Add to
  Registry write.
- `tasker/tui/screens/welcome.py`: Setup Wizard and Model Selector menu
  items now push real screens; Run Task / View Sessions / Daemon remain
  placeholders for 8.5/future.

**Headless TUI transcript:** captured at
`docs/transcripts/phase_8_4_tui_transcript.txt` using Textual's
`App.run_test()` driver. It demonstrates the wizard producing 7 live
step rows, the model selector listing candidates, running a probe, and
writing a new worker entry to a scratch registry.

**Manual-only item (not verified):** B.5.5's native terminal-emulator
click-drag text selection on the readiness report panel. Implemented with
an explicit Copy report fallback, but the actual eyes-on check in a real
terminal can only be done by Roland.

**Files modified:** `tasker/tui/messages.py`,
`tasker/tui/widgets/history_input.py`,
`tasker/tui/widgets/step_row.py`,
`tasker/tui/widgets/readiness_panel.py`,
`tasker/tui/screens/setup_wizard.py`,
`tasker/tui/screens/model_selector.py`,
`tasker/tui/screens/welcome.py`,
`tests/unit/test_tui_history_input.py` (new),
`tests/unit/test_tui_setup_wizard.py` (new),
`tests/unit/test_tui_model_selector.py` (new),
`tests/unit/test_tui_welcome_screen.py` (updated for real navigation),
`docs/TASKER_CHECKLIST.md` (Phase 8.4 items),
`docs/TESTING_GUIDE.md` (H8 TUI test commands),
`docs/transcripts/phase_8_4_tui_transcript.txt` (new),
`scripts/phase_8_4_transcript.py` (new),
`CLAUDE.md` (Phase Tracker + this note).

**Tests:** 943 → 985 (+42 tests). Full suite green:
`python -m unittest discover -s tests` → OK.

**Next task:** SDD_ADDENDUM_PHASE8.md Phase 8.5 — HarnessPanel.

**Blockers:** None.

**Open decisions:** None new.


---

## Session Archive Index

Full historical session notes archived at: `/mnt/f/tasker-p1/memory/projects/ollama-tasker/archive/CLAUDE_ARCHIVE_2026-07-20.md`

| Date | Sprint / Session |
|------|------------------|
| 2026-07-20 | Tool-executor fill-in sprint, Part 2 — TEST_RUNNER, LINTER, CALCULATOR, kept for reference |
| 2026-07-20 | Tool-executor fill-in sprint, Part 1 — DELEGATE_AGENT, kept for reference |
| 2026-07-20 | RESEARCH mode grounding sprint, kept for reference |
| 2026-07-20 | REPL/TUI UX sprint + transcript addendum, kept for reference |
| 2026-07-20 | CHAT mode direct dispatch + /model + /effort + honesty-guard gating, kept for reference |
| 2026-07-20 | Cowork honesty + plan-parse resilience bug fixes, kept for reference |
| 2026-07-20 | `tasker-cli shell` provider-wiring + REPL UX fixes, kept for reference |
| 2026-07-20 | Phase 8.3 Textual TUI skeleton, kept for reference |
| 2026-07-20 | Rudimentary TUI REPL, kept for reference |
| 2026-07-20 | API server launchability, kept for reference |
| 2026-07-20 | SDD_ADDENDUM_PHASE8.md Phase 8.2, kept for reference |
| 2026-07-20 | COWORK_PROMPT tasks 8.1–8.3, kept for reference |
| 2026-07-20 | Phase 7.5.4–7.5.6, kept for reference |
| 2026-07-20 | empty-content bug, num_predict + warmup hypotheses (Designlab1) |
| 2026-07-20 | context-window ceiling + concurrency hypotheses (Designlab1) |

---

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

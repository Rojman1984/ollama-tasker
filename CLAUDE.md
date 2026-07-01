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

**Last worked on:** Investigating why the multi-turn tool loop (previous
session) still couldn't demonstrate real end-to-end CLI execution led to
a live quantization/prompt-complexity investigation, which then became
two concrete fixes: **step-aware tool subsetting** and an **Ollama-Cloud-
routed orchestrator (planner) model**. Both implemented, tested, and
live-verified this session.

**Quantization investigation (diagnostic, no code changes from this
part):** pulled and live-tested `lfm2.5-thinking` at Q8_0 and full bf16
against the exact prompt that reliably failed at Q4. Finding: **quantization
was never the bottleneck.** All three precisions failed identically once
offered the full 7-tool `CODE_BUNDLE` — even bf16 (the best this model can
do) hit the same empty-content signature. `"think": false` was also tried
live and made things *worse* (11/12 attempts across both models had the
model's entire response budget consumed by reasoning with nothing after
`</think>`, vs. 1/12 with default think behavior). The one thing that was
100% reliable in every test, across every precision, was offering just the
1 tool a step actually needed — that became this session's real fix.

**Fix 1 — step-aware tool subsetting
(`tasker/tools/bundles.py::narrow_bundle_to_step()`):** deterministic,
keyword-group-based narrowing of the tools offered per step, following
the existing `secure_bundle()` pattern. Explicitly NOT LLM-classified —
proven unreliable for this same small model (see `_infer_tool_from_flat_object`
from last session). `PlanStep` only carries `description` (free text) and
`required_capabilities` (too coarse — `Capability.CODE` doesn't distinguish
"run tests" from "read a file"), so matching is keyword-group-based on
`description`: a match requires ALL of a group's substrings present (any
order), not a fixed phrase — needed after live testing showed the planner
paraphrases the same real intent multiple ways per run ("List files in
current directory" / "Listing files" / "List current directory files").
No match → falls back to the full bundle (today's behavior) + logs a
WARNING, so unmatched phrasing stays visible/improvable rather than
silently guessing wrong. Wired into `cli/shell.py::_run_task()`'s step
loop (was: tools computed once, constant, before the loop).

**Fix 2 — Ollama-Cloud-routed orchestrator model:** lets the *planning*
role use a stronger model via Ollama's own cloud
(`ComputeLocation.OLLAMA_CLOUD`, same `OllamaProvider`/endpoint as local
calls) while the *worker* role stays on the local Q4 model, per explicit
user preference. **Explicitly rejected a third-party OpenAI-compatible
router (OpenRouter) after the user corrected that direction** — see
memory `feedback_cloud_models_via_ollama`. Real gaps found and fixed in
`tasker/orchestrator/factory.py`: `_build_orchestrator_manifest()` and
`_make_call_model()` were hardcoded to `ComputeLocation.LOCAL_HARDWARE`/
`PrivacyTier.LOCAL_ONLY` — both would have hard-blocked a cloud call via
the project's own privacy-tier enforcement even though `OllamaProvider`
itself already supports `OLLAMA_CLOUD`. Now both accept params, and
`build_orchestrator()` branches on a new `HardwareProfile.
orchestrator_compute_location` field (`"local"` default, `"ollama_cloud"`
opt-in). No new provider class needed — still only ever resolves
`provider_registry[ProviderType.OLLAMA]`. New additive profile
`config/profiles/tier1_cloud_planner.yaml`: local Q4 worker unchanged,
orchestrator routed to `gpt-oss:120b-cloud` (OpenAI's actual open-weight
120B release, hosted on Ollama Cloud — confirmed live via `ollama show`
to have a real 131072-token context window; `context_limit` set to match
rather than copying the local profile's 4096 CPU-RAM-driven value, per
explicit user request to "open up the context frame for cloud models").

**Live verification, Designlab1:**
- **Tool subsetting:** the exact prompt that reliably failed last session
  (`"Use the bash tool to list the files in the current directory"`), on
  Q4, through the full CLI pipeline: 0 of 3 completed runs hit the
  no-keyword-match fallback across 3 different planner paraphrases; one
  run completed with the exact real directory listing as the final
  answer. The other two hit `max_turns` (the already-documented "model
  doesn't conclude after a real tool result" quirk from last session, not
  a narrowing failure — both still executed real tools throughout).
- **Cloud planner:** this machine had no active Ollama Cloud session at
  session start (confirmed via a direct `:cloud` API call returning
  `"Unauthorized"`) — user completed `ollama signin`'s browser flow mid-
  session (same pattern as the earlier `gh auth login` step). Confirmed
  `gpt-oss:20b-cloud` and `gpt-oss:120b-cloud` both reachable with real
  responses. A real planning call through `SingleLLMOrchestrator` wired
  to `tier1_cloud_planner` produced a clean, valid 3-step plan
  (`used_fallback=False`, no unrecognized capability strings) — visibly
  better structured than typical local Q4 planning output. A full
  `python -m cli.shell --mode code` run using this profile (cloud
  planner + local Q4 worker) completed with the correct, real directory
  listing as its final answer.
- **New, real, pre-existing bug found (not introduced or fixed this
  session):** the cloud planner's richer plans assign `REASONING`/
  `THINKING` capabilities the local worker doesn't declare, so
  `WorkerSelector` falls through to `nemotron-3-ultra-cloud` for those
  steps — which fails instantly, because `worker_registry.yaml`'s
  `model_id: "nemotron-3-ultra"` is missing the `:cloud` suffix Ollama
  Cloud's actual tags require (confirmed: bare `nemotron-3-ultra` returns
  `"model 'nemotron-3-ultra' not found"`). Likely affects other
  cloud-routed registry entries too (glm-5.2, glm-5.1, minimax-m3,
  kimi-k2.7-code) — not individually verified, out of scope this session.

**Tests:** 26 new (18 `test_tool_bundles.py`, 4 `TestBuildOrchestratorCloudRouting`
in `test_orchestrator_factory.py`, plus 2 existing `HardwareProfile` test
fixtures updated for the new required field). Full suite: 494/494 → 516/516.

**Last file modified:** `tasker/tools/bundles.py`, `cli/shell.py`,
`tasker/modes/base.py`, `tasker/orchestrator/factory.py`,
`config/profiles/tier1_cloud_planner.yaml` (new),
`tests/unit/test_tool_bundles.py` (new),
`tests/unit/test_orchestrator_factory.py`, `tests/unit/test_setup_wizard.py`,
`docs/TASKER_CHECKLIST.md`, `CLAUDE.md`.

**Next task:** Phase 8.2 — Agentic Readiness Checker
(`tasker/setup/readiness.py`, 3 probe rounds NATIVE→LFM25→JSON_EXTRACT,
`tasker-setup --check-model <name>`, worker registry write on
confirmation, `WorkerRole` assignment per B.4.6). Separately, still open:
fix `worker_registry.yaml`'s missing `:cloud` suffixes (nemotron-3-ultra
confirmed broken, others unverified); the empty-content bug itself remains
unfixed (quantization and `think:false` both ruled out this session —
still no confirmed lever); the model-doesn't-conclude-after-tool-result
behavior; Tier 2's same-model-for-both-roles bug (`factory.py`, tier==2
branch) plus `tier2_designlab.yaml`'s unread `planner_model`/
`synthesizer_model` keys — the `orchestrator_compute_location` plumbing
added this session would make this easier to fix now; wiring
`OllamaCloudConcurrencyManager` to the orchestrator's `OllamaProvider`
(cloud orchestrator calls currently proceed without slot-limiting); Phase
7.5.4 (`AmdApuBackend`, needs TASKER-P1); wire
`ModeConfigurator.resolve_hardware_profile()` into `cli/shell.py`.
**Blockers:** None.
**Open decisions:** Whether to make `tier1_cloud_planner` the default
profile going forward, or keep it opt-in alongside `tier1_tasker` — not
decided this session, both configs exist and work. `tool_result_role="user"`
still not separately live-tested. AMD-APU tier-computation fallthrough
still untested against real hardware.

**Live model config:**
- `tier1_tasker` (default): orchestrator + worker both
  `lfm2.5-thinking:latest` (local Q4, 1.2B).
- `tier1_cloud_planner` (new, opt-in): orchestrator `gpt-oss:120b-cloud`
  (Ollama Cloud), worker `lfm2.5-thinking:latest` (local Q4, unchanged).
  Requires `ollama signin`.

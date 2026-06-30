# Ollama Tasker — Project Context

> **Authoritative design reference:** `docs/SDD.md`
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
| 7.5.2–7.5.6 | Dynamic hardware detection (`tasker-hardware` applet, GPU backends) | ⬜ NOT STARTED |

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

**Last worked on:** LFM25 tool protocol. The official LiquidAI LFM2.5 docs
corrected two wrong assumptions: `lfm2.5-thinking:latest` was registered with
`tool_protocol: native`, but Ollama reports `capability: completion` for this
model family and rejects `tools[]`; and LFM2.5 doesn't use LFM2's
`<|tool_list_start|>`/`<|tool_list_end|>` wrapper tokens (plain JSON injection
instead). Added `ToolProtocol.LFM25`, `WorkerManifest.tool_result_role`,
`ToolCallNormalizer.inject_tools()`/`extract_tool_calls()`, and protocol-aware
routing in `OllamaProvider` (NATIVE sends `tools[]`; everything else injects
into the system message and never sends `tools[]` — this also fixes a second,
independent latent bug where `OllamaProvider` sent `tools[]` unconditionally
for every protocol). Full details and rationale in `docs/SDD_ADDENDUM_7.5.md`
A.2b. 356/356 unit tests passing.

**Live test result (lfm2.5-thinking:latest, Ollama 0.30.11):** the spec's
literal instruction — append only "Output function calls as JSON" to the
system message — was **not sufficient**: the model reasoned to the correct
call inside its thinking trace but then emitted empty `content`. Fix: append
an explicit "Respond with ONLY the JSON array function call and no other
text." instruction too (now baked into `inject_tools()`). Even with that fix,
real output varied run to run — sometimes a clean JSON array, sometimes a
single (non-array) JSON object, sometimes wrapped in a ` ```json ` fence
despite being told not to — so `_extract_lfm25()` was hardened to accept all
three shapes. 3/3 manual runs parsed correctly after hardening.
**`tool_result_role` confirmed working:** not yet — no multi-turn
tool-execution loop exists anywhere in the codebase yet (`WorkerResult.
tool_results` is produced but nothing re-invokes a worker with results
appended), so this field has no live test to run yet. Default `"tool"` is
untested in practice; flagged in SDD_ADDENDUM_7.5.md A.2b as a follow-up.

**Git history reconciled (this session):** `origin/master` turned out to have
a complete, unrelated git history (initial scaffold → Phases 1–7 →
orchestrator factory → a Phase 7.5 SDD addendum commit) — this working copy
had been `git init`'d fresh in the 7.5.1 session without realizing the GitHub
repo already had history, so the two diverged with zero common ancestor.
File content was almost entirely identical (most files showed 0 diff); real
differences were this session's actual new work layered on top of what was
already on origin. Merged with `--allow-unrelated-histories`; restored two
files that existed only on origin (`.claude/settings.json`, root-level
`OLLAMA_TASKER_SDD.md`). The bulk of the apparent conflict set (103 files)
was a spurious executable-bit difference with byte-identical content, not a
real disagreement. 356/356 tests passing post-merge. **Push still blocked** —
no GitHub credentials configured in this environment (no credential helper,
no `gh` CLI). Needs a PAT via `gh auth login` or an SSH remote from the user.

**`cli/shell.py` tools=[] gap fixed:** `_run_task()` previously hardcoded
`tools=[]` on every `WorkerTask`, for every mode — no mode's tool bundle
(`tasker/tools/bundles.py`) ever reached a live model call. Fixed: resolves
`config.mode.tool_bundle` via `get_definitions()` and passes the real
`list[ToolDefinition]` into `WorkerTask`. SECURE's network-tool stripping
was already baked into its bundle at the data level (`tasker/modes/secure.py`
already assigns `SECURE_BUNDLE`, and `secure.yaml`'s `tool_bundle` already
lists only the stripped set) — no extra code needed there, just reaching it.
Confirmed live: CODE mode's `task.tools` had 7 entries (bash, code_search,
file_read, file_write, git, linter, test_runner), correctly reaching
`OllamaProvider`.

**Bigger, separate, pre-existing bug found while live-testing the fix:**
`SingleLLMOrchestrator.plan()` asks `lfm2.5-thinking:latest` for a JSON plan,
then falls back to `NanoOrchestrator`'s hardcoded single-step "Answer the
task" template whenever `parse_plan()` fails to parse the response.
`lfm2.5-thinking:latest` sometimes returns a `capabilities` value outside the
`Capability` enum (observed: `"bash"` instead of `"tool_use"`), which makes
`Capability(c)` raise inside `parse_plan()`, silently triggering the
fallback — **the worker never sees the real task text when this happens**.
Reproduced directly by hand-sending the planning prompt to the model.
`python -m cli.shell --mode code "Use the bash tool to list the files in the
current directory"` hit this fallback in **4/4** runs — never fired a real
tool call through the literal requested command. When the planning step
*does* succeed (confirmed once via a direct orchestrator→provider script,
same pipeline, no CLI print wrapper), the real task reached the worker and
LFM25 fired a genuine, correctly-parsed tool call end-to-end (wrong tool
picked — `test_runner` instead of `bash` — but `inject_tools` → JSON
response → `extract_tool_calls` → `WorkerResult.tool_results` all worked).
So: **LFM25 itself is validated working; the harness-level "first real tool
call" milestone is blocked on `parse_plan()` silently discarding the task on
a capability mismatch, not on anything in this session's changes.** See
`docs/TASKER_CHECKLIST.md` LFM25 section for full detail.

**`tool_result_role` still unconfirmed:** fixing the `tools=[]` gap does
**not** unblock this — a single-turn tool call never produces a "next turn,"
so the field still has nothing to exercise it against. Needs the multi-turn
loop itself built first (explicitly out of scope this session).

**Last file modified:** `cli/shell.py`, `.gitignore`, `.gitattributes`,
`docs/TASKER_CHECKLIST.md`, `CLAUDE.md` — plus the merge commit touching the
full tree (file-mode normalization + restoring origin-only files).  
**Next task:** Harden `tasker/orchestrator/_parse.py`'s `parse_plan()` (or
the `PLAN_SYSTEM` prompt) so an invalid/unknown capability string doesn't
discard the entire plan — e.g. skip the unrecognized capability instead of
raising, or validate against the enum's value set explicitly in the prompt.
That's the real prerequisite for a CLI-level "first real tool call" smoke
test (LFM25 or otherwise), not the `tools=[]` wiring (already fixed). Then
build the multi-turn tool-result loop to finally unblock `tool_result_role`.
Then Phase 7.5.2 — `GPUBackend` ABC, `GPUInfo` dataclass, `NoGpuBackend`,
`tasker-hardware` applet scaffold.  
**Blockers:** GitHub push needs credentials (see above).  
**Open decisions:** `tool_result_role` default (`"tool"`) is unvalidated —
test "tool" vs "user" once a multi-turn loop exists.  

**Live model config (tier1_tasker):**  
- Orchestrator: `lfm2.5-thinking:latest` (local, 1.2B — was `qwen3:1.7b`, not installed)  
- Worker: `lfm2.5-thinking:latest` (local, 1.2B — `tool_protocol: lfm25`, was
  incorrectly `native`; was `lfm2.5:latest`, not installed)

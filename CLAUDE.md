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

# Ollama Tasker — Cowork Session Bootstrap Prompt

> Copy the content below the divider into a new Cowork session to resume
> development. Update the STATUS BLOCK before each new session.

---

## HOW TO USE THIS PROMPT

1. Open a new Cowork session.
2. Upload `docs/SDD.md` and `CLAUDE.md` as attachments, OR paste their content.
3. Paste the SESSION PROMPT below as your first message.
4. Update the STATUS BLOCK to reflect current progress before each session.

---

## FIRST-TIME REPO SETUP (Windows / PowerShell)

Run once to scaffold the repo on Designlab1 or TASKER-P1:

```powershell
# Create and enter repo
mkdir ollama-tasker; cd ollama-tasker
git init

# Scaffold all directories
$dirs = @(
    "docs",
    "core",
    "tasker\modes",
    "tasker\classifier",
    "tasker\orchestrator",
    "tasker\workers\providers",
    "tasker\session",
    "tasker\tools",
    "config\profiles",
    "config\modes",
    "config\workers",
    "cli",
    "tests\unit",
    "tests\integration",
    "tests\e2e",
    "tests\fixtures"
)
foreach ($d in $dirs) { New-Item -ItemType Directory -Force -Path $d | Out-Null }

# Copy project documents into repo
Copy-Item .\CLAUDE.md .
Copy-Item .\OLLAMA_TASKER_SDD.md docs\SDD.md
Copy-Item .\COWORK_PROMPT.md docs\COWORK_PROMPT.md

# Python virtual environment (Python 3.11+ required)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install pyyaml aiohttp python-dotenv

# Verify Python version
python --version   # must be 3.11+

# Initial commit
git add -A; git commit -m "chore: initial scaffold"
```

> **Note for Claude Code:** PowerShell is the shell on Windows.
> Chain commands with `;` not `&&`.
> Activate the venv before running any `python` commands.

---

## SESSION PROMPT

```
You are continuing development of the Ollama Tasker project.

## Your first actions

1. Read CLAUDE.md — it is the project context file and contains the repository
   layout, tech stack, non-negotiable constraints, and development rules.
2. Read docs/SDD.md — it is the authoritative design specification. Every
   implementation decision must align with it. If you find a gap or contradiction,
   update the SDD before writing code.
3. Read the STATUS BLOCK below — it tells you exactly where to start.

Do not write any code until you have read both documents.

---

## STATUS BLOCK

**Project:** Ollama Tasker (standalone — not HomeWatch, not Ztripes)
**SDD Version:** 0.1.0-draft (docs/SDD.md)
**Current Phase:** 1 — Data Models + Worker Registry + Worker Selector

**Phase completion state:**

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Data models + Worker Registry + Selector | ⬜ NOT STARTED |
| 2 | Session Layer | ⬜ NOT STARTED |
| 3 | Orchestrator (Base, Tier 0, Tier 1) | ⬜ NOT STARTED |
| 4 | Providers + ToolNormalizer | ⬜ NOT STARTED |
| 5 | Modes + CLI Shell | ⬜ NOT STARTED |
| 6 | Higher Orchestrator Tiers | ⬜ NOT STARTED |
| 7 | Hardening | ⬜ NOT STARTED |

**Last completed task:** None — first session.

**Next task:** Create `tasker/workers/base.py` — all data models and enumerations
per SDD Section 6. This file is the contract that every other module imports from.
Nothing else is written until this file is complete and its unit tests pass.

**Files modified this session:** None yet.

**Open decisions / blockers:** None. All design decisions are captured in SDD.

---

## PHASE 1 TASK LIST (in order — do not skip ahead)

### 1.1 — tasker/workers/base.py

Create all data models and enumerations defined in SDD Sections 6 and a subset of
Section 5. This is the single source of truth — no other file defines these types.

Required contents:

Enumerations (SDD 6.8):
  - ProviderType
  - ComputeLocation
  - Capability
  - ToolProtocol
  - RoutingPolicy
  - PrivacyTier
  - AgentRole
  - SessionState
  - SessionDirective
  - WorkerStatus
  - OllamaPlan
  - OllamaUsageLevel (IntEnum)
  - LatencyClass
  - FallbackHint

Dataclasses (SDD 6.1–6.4):
  - WorkerManifest
  - WorkerTask
  - WorkerResult
  - WorkerToolResult
  - ModelUsage
  - ToolDefinition
  - RetryDecision
  - ClassifierResult

Supporting types:
  - TaskerPolicyError(Exception) — raised on privacy tier violation
  - TaskerConfigError(Exception) — raised on invalid configuration

Validation:
  - WorkerManifest.__post_init__ must reject any manifest missing Capability.TOOL_USE

### 1.2 — tests/unit/test_worker_manifest.py

Unit tests for WorkerManifest:
  - valid manifest with TOOL_USE passes
  - manifest without TOOL_USE raises TaskerPolicyError
  - serialization round-trip (to_dict / from_dict)
  - capability subset checks
  - ollama_usage_level only set when provider is OLLAMA

### 1.3 — tasker/workers/registry.py

Implement WorkerRegistry and WorkerSelector per SDD Section 5.4 and 5.5.

WorkerRegistry:
  - register(manifest: WorkerManifest) → validates, stores
  - deregister(worker_id: str) → removes
  - filter(capabilities: set[Capability]) → list[WorkerManifest]
  - health_check(worker_id: str) → bool (stub: always True until providers exist)
  - list_all() → list[WorkerManifest]
  - get(worker_id: str) → WorkerManifest | None

WorkerSelector:
  - select(required_capabilities, policy, privacy_tier, slots_available,
           should_throttle) → WorkerManifest
  - Implement the full selection decision tree from SDD Section 5.5:
      1. Privacy check (hard block on LOCAL_ONLY)
      2. Concurrency check (exclude OLLAMA_CLOUD if slots_available == 0)
      3. Budget check (penalize usage_level 3-4 when should_throttle)
      4. Capability filter
      5. Policy rank (COST_OPTIMIZED / CAPABILITY_FIRST / SPEED_OPTIMIZED / HYBRID / PRIVATE)
  - select() raises TaskerPolicyError if LOCAL_ONLY and no local worker available

### 1.4 — tests/unit/test_worker_registry.py

  - register adds to registry
  - deregister removes from registry
  - filter returns correct capability matches
  - filter returns empty list when no match
  - list_all returns all registered workers

### 1.5 — tests/unit/test_worker_selector.py

  - COST_OPTIMIZED prefers LOCAL_HARDWARE over OLLAMA_CLOUD over DIRECT_CLOUD
  - CAPABILITY_FIRST selects highest-scored worker
  - LOCAL_ONLY with local worker available → selects local worker
  - LOCAL_ONLY with NO local workers → raises TaskerPolicyError
  - OLLAMA_CLOUD excluded when slots_available == 0
  - Usage level 3-4 penalized when should_throttle is True
  - No candidates after all filters → raises appropriate error

### 1.6 — config/workers/worker_registry.yaml

Create the initial worker registry YAML with these workers (from SDD Section 8.3):
  - lfm2.5-local (LOCAL_HARDWARE, ollama)
  - nemotron-3-ultra-cloud (OLLAMA_CLOUD, ollama, usage_level 3)
  - minimax-m3-cloud (OLLAMA_CLOUD, ollama, usage_level 3, long_context)
  - glm-5.1-cloud (OLLAMA_CLOUD, ollama, usage_level 3, code specialist)
  - kimi-k2.7-code-cloud (OLLAMA_CLOUD, ollama, usage_level 2, code + vision)
  - claude-haiku-4-5 (DIRECT_CLOUD, anthropic)
  - claude-sonnet-4-6 (DIRECT_CLOUD, anthropic)
  - fugu-ultra (DIRECT_CLOUD, fugu, multi_agent)

### 1.7 — tasker/workers/__init__.py

Expose the public surface cleanly.

### 1.8 — docs/TASKER_CHECKLIST.md

Create the checklist. Add checked items for every task completed in Phase 1.

---

## DEVELOPMENT RULES (enforce these — do not deviate)

1. Read SDD.md Section 6 before writing any data model. Implement exactly what is
   specified. If the SDD is wrong or incomplete, fix the SDD first.

2. Run tests after each numbered task (1.2, 1.4, 1.5). Do not proceed to the next
   task until all tests pass.

3. workers/base.py is the contract. No other file redefines these types. Every other
   harness module imports from it.

4. Use Python 3.11+ features: dataclasses with field(), match/case for state machines,
   IntEnum for OllamaUsageLevel, ABC for all base classes, asyncio throughout.

5. All provider calls will be async. Anticipate this in the data models — use
   Awaitable return types in stubs where providers are not yet implemented.

6. Do not import or reference anything from HomeWatch, Ztripes, or any MSP product.

7. Update CLAUDE.md Phase Tracker and "Current Session Notes" at the end of each
   session before stopping.

---

## SESSION END PROTOCOL

Before ending each session:

1. Run the full test suite: `python -m unittest discover -s tests -v`
2. Update CLAUDE.md:
   - Phase Tracker (mark completed phases with ✅)
   - "Current Session Notes" section (last file modified, next task, blockers)
3. Update docs/TASKER_CHECKLIST.md with all completed items checked.
4. Update the STATUS BLOCK in this prompt file to reflect current state.
5. Commit: `git add -A; git commit -m "phase-1: <what was completed>"`

---

## QUICK REFERENCE — KEY SDD SECTIONS

| What you need | SDD Section |
|---------------|-------------|
| Architecture diagram | 4.1, 4.2 |
| Mode definitions | 5.1 (table) |
| Classifier spec | 5.2 |
| Orchestrator tiers | 5.3 (table) |
| Worker Registry spec | 5.4 |
| Worker Selector decision tree | 5.5 |
| Provider specs | 5.6 |
| Tool normalizer protocols | 5.7 |
| Session manager | 5.8, Section 9 |
| Concurrency manager | 5.9 |
| Session budget | 5.10 |
| WorkerManifest | 6.1 |
| WorkerTask | 6.2 |
| WorkerResult | 6.3 |
| ExecutionPlan | 6.4 |
| Checkpoint | 6.5 |
| OllamaSessionBudget | 6.6 |
| TaskerMode | 6.7 |
| All enumerations | 6.8 |
| OrchestratorBase ABC | 7.1 |
| WorkerProviderBase ABC | 7.2 |
| ClassifierBase ABC | 7.3 |
| NotifierBase ABC | 7.4 |
| OpenAI-compat API surface | 7.5 |
| CLI slash commands | 7.6 |
| Hardware profile YAML schema | 8.2 |
| Worker registry YAML schema | 8.3 |
| Session state machine | 9.1 |
| Pause flow | 9.2 |
| Fallback ladder | 9.3 |
| Resume flow | 9.4 |
| Error classification | 10.1 |
| Privacy tier enforcement | 11.1 |
| Phase roadmap | 13 |

---

## HARDWARE CONTEXT

**TASKER-P1** — Ryzen 5 3500U, 32GB RAM, no GPU  
→ Use hardware profile: `config/profiles/tier1_tasker.yaml`  
→ Max orchestrator tier: 1  
→ Sequential model loading only  
→ Peak RAM: one model at a time  

**Designlab1** — Ryzen 5/7, 32GB RAM, GTX 1050 Ti (4GB VRAM)  
→ Use hardware profile: `config/profiles/tier2_designlab.yaml`  
→ Max orchestrator tier: 2  
→ Resident planner + 1 worker concurrent  

---

Begin by reading CLAUDE.md and docs/SDD.md. Then start Phase 1, Task 1.1.
```

---

## TEMPLATE: STATUS BLOCK FOR FUTURE SESSIONS

When updating the STATUS BLOCK for a future session, replace the Phase 1
task list section with the appropriate phase task list from SDD Section 13,
and update the phase table to reflect current completion state using:

- ⬜ NOT STARTED
- 🔄 IN PROGRESS  
- ✅ COMPLETE

Example for a session starting Phase 2:

```
**Current Phase:** 2 — Session Layer

**Phase completion state:**

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Data models + Worker Registry + Selector | ✅ COMPLETE |
| 2 | Session Layer | 🔄 IN PROGRESS |
| 3 | Orchestrator (Base, Tier 0, Tier 1) | ⬜ NOT STARTED |
...

**Last completed task:** Phase 1 — all unit tests passing, TASKER_CHECKLIST.md
updated, committed as "phase-1: workers/base.py, registry, selector, yaml config".

**Next task:** Create tasker/session/budget.py — OllamaSessionBudget per SDD 6.6.
```

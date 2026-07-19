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
**Current Phase:** Cloud-path E2E validation (post-Phase-7.5 — Ollama server +
Ollama Cloud models first; local models and frontier APIs deferred)

**Phase completion state:**

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Data models + Worker Registry + Selector | ✅ COMPLETE |
| 2 | Session Layer | ✅ COMPLETE |
| 3 | Orchestrator (Base, Tier 0, Tier 1) | ✅ COMPLETE |
| 4 | Providers + ToolNormalizer | ✅ COMPLETE |
| 5 | Modes + CLI Shell | ✅ COMPLETE |
| 6 | Higher Orchestrator Tiers | ✅ COMPLETE |
| 7 | Hardening (+ Addenda A/B, 7.5.x hardware detection) | ✅ COMPLETE |
| 8 | Cloud-path E2E validation | 🔄 IN PROGRESS |

**Last completed task:** Task 8.2 — tier4_cloud.py reachability, ✅
COMPLETE (same session as 8.1, also ✅). Tier 4 was unreachable via three
gates: profile ceilings (2/1 — by design, kept), mode ceilings (max 3 —
SDD gap, fixed SDD-first: 5.1 COWORK "2–4" + new 5.3 "Tier 4 activation";
cowork.yaml tier_max→4, effective tier unchanged on standard machines),
and the factory never constructing CloudOrchestrator (fixed: tier ≥ 4 +
orchestrator compute_location ollama_cloud → CloudOrchestrator, local
location degrades to Tier 3 per SDD 10.3). New opt-in profile
tier4_cloud_hybrid.yaml; live-confirmed on Designlab1 ("Planning with
CloudOrchestrator...", cloud plan/synthesize with slot+budget logs,
reasoning step on nemotron cloud, writing step on local lfm2.5). Suite
567 → 586 (8.1) → 591 (8.2), green. Evidence:
docs/TASKER_CHECKLIST.md → "Phase 8.1"/"Phase 8.2" sections; full detail
in CLAUDE.md Current Session Notes.

**Next task:** Task 8.3 — tool-loop non-termination guard in
`tasker/tools/loop.py`: hard iteration cap (max_turns=5 exists — verify
it is truly hard) + repeated-identical-call detection (worker re-issuing
the same tool call with the same arguments → terminate early rather than
burn turns/budget). Unit tests for both guard conditions.

**Files modified this session:** 8.1 — cli/shell.py (session wiring,
resume, --policy, OLLAMA_BASE_URL/TASKER_BUDGET_PRELOAD/TASKER_LOG_LEVEL),
tasker/workers/providers/ollama.py (budget recording),
tasker/session/concurrency.py (slot logging), orchestrator tier2/3/4
(used_fallback), config/profiles/tier2_designlab.yaml (+orchestrator
model), config/profiles/tier2_designlab_cloud.yaml (new), tests (+19).
8.2 — docs/SDD.md, config/modes/cowork.yaml,
tasker/orchestrator/factory.py, config/profiles/tier4_cloud_hybrid.yaml
(new), tests/unit/test_orchestrator_factory.py (+5 net). Both —
docs/TASKER_CHECKLIST.md, docs/TESTING_GUIDE.md, CLAUDE.md,
COWORK_PROMPT.md.

**Open decisions / blockers:**
- CLI provider_map wires only OllamaProvider — ANY_CLOUD selection can
  legally pick Anthropic/OpenAI/Fugu workers and then fail with "No
  provider for <x>" (observed live under throttle). Wire the remaining
  providers or pre-filter unroutable workers.
- Cloud-orchestrator planning is not tick()-gated (deliberate — a
  checkpoint without a plan cannot resume); budget state does not persist
  across process restarts (only the checkpoint's BudgetSnapshot does).
- LFM2.5 empty-content bug PARKED for local-model phase; next lever is
  reproduction under real async/concurrent harness load (see CLAUDE.md
  diagnostic notes — hypotheses 1–3 ruled out, do not re-test).
- Cowork now drives headless Claude Code runs via shared tmux session
  (`tmux attach -t tasker -r` to observe).

---

## PHASE 8 TASK LIST (in order — do not skip ahead)

### 8.1 — Live cloud-path E2E validation  ✅ COMPLETE (2026-07-19)

Run a real multi-step orchestration through Ollama Cloud workers (not unit
tests — the live CLI path; unit tests previously passed while the live path
was broken). Confirm live:
  - Concurrency slot management (OllamaCloudConcurrencyManager constructed
    and enforcing in the CLI path)
  - Session budget tracking increments and throttle behavior
  - Pause/resume checkpoints survive a real pause
  - used_fallback reported correctly on ExecutionPlan
Document evidence (commands + output) in docs/TASKER_CHECKLIST.md.

### 8.2 — tier4_cloud.py reachability  ✅ COMPLETE (2026-07-19)

Verify hardware-profile → tier resolution can actually route to Tier 4 from
the Designlab1 and TASKER-P1 profiles. If unreachable by design, fix the
resolution chain or document why. Add a regression test.

### 8.3 — Tool-loop non-termination guard

Hard iteration cap + repeated-identical-call detection in the tool loop,
so a runaway loop cannot burn Ollama Cloud budget. Unit tests for both
guard conditions.

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

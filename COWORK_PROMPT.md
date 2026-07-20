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
**Current Phase:** SDD_ADDENDUM_PHASE8 (setup wizard / readiness checker /
TUI). Cloud-path E2E validation (COWORK_PROMPT task list 8.1–8.3) and
addendum 8.1–8.3 are complete. `tasker` now launches a real Textual app
(skeleton only — Setup Wizard/Model Selector/Run Task are inert
placeholders until 8.4/8.5). One standalone launch/ops task (API server
launchability, not addendum-numbered) was completed in between; the
interim REPL from the session before this one has been superseded.

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
| 8 | Cloud-path E2E validation (task list 8.1–8.3) | ✅ COMPLETE |
| A8.1–8.2 | Addendum: setup wizard + readiness checker | ✅ COMPLETE |
| A8.3 | Addendum: Textual TUI skeleton (TuiApp, WelcomeScreen, status bar) | ✅ COMPLETE |
| A8.4–8.5 | Addendum: SetupWizardScreen + ModelSelectorScreen, HarnessPanel | ⬜ NOT STARTED |

**Last completed task:** Textual TUI skeleton, ✅ COMPLETE (2026-07-19;
the addendum's real Phase 8.3). SDD-first: the addendum had three
mutually inconsistent claims about which sub-phase owns SetupWizardScreen/
ModelSelectorScreen (B.5.2's comments, B.8's table, B.11's checklist all
disagreed) — asked the user to confirm scope before writing code;
confirmed B.11 (skeleton-only 8.3, wizard+selector bundled into 8.4) is
authoritative, and corrected B.8/B.5.2 to match. `tasker/tui/app.py` now
has a real `TuiApp(App)` + `main()`, replacing both the Phase 8.1 stub
and the prior session's interim REPL (whose `_repl()`/`_dispatch()` are
now gone — documented from day one as temporary; `tasker-cli shell`
remains available for an interactive CLI session).
`tasker/tui/screens/welcome.py`: `WelcomeScreen` renders the full B.5.2
menu up front (Setup Wizard, Model Selector, Run Task, View Sessions,
Daemon, Quit) so 8.4/8.5 don't need a second layout change; only Quit is
wired, the rest show an inert "coming in Phase 8.x" notice.
`tasker/tui/widgets/status_bar.py`: `HardwareStatusBar`, a reactive
bracketed status line (B.5.4) reading the machine-local hardware cache
directly (never live detection). `tasker/runtime/dispatch.py` — the
actually-reusable piece — untouched, carried forward as planned.
Live-verified on Designlab1: `tasker` booted in a real pty with no crash
(3s run under `timeout`, killed as expected); real (unmocked) headless
screenshots captured via Textual's `export_screenshot()` against this
machine's actual cached hardware and published for visual review,
confirming real values on screen. Caught + fixed a real bug during that
step: `ram_gb` was displaying as an unrounded float, now rounded to
whole GB with a regression test. Suite 668 → 659 (−30 deleted REPL
tests, +21 new TUI tests, all headless via Textual's `Pilot`). Evidence:
docs/TASKER_CHECKLIST.md → "Phase 8.3 -- Textual TUI Skeleton
(2026-07-19)".

**Next task:** SDD_ADDENDUM_PHASE8.md Phase 8.4 — SetupWizardScreen
(wraps `tasker/setup/wizard.py`'s `run_wizard()`) + ModelSelectorScreen
(wraps `tasker/setup/readiness.py`'s `ReadinessChecker`), plus the
Textual message bus (`WizardStepCompleted`, `ReadinessCheckCompleted`,
`WorkerRegistryUpdated`) per B.11. Then Phase 8.5 (HarnessPanel, built on
`tasker/runtime/dispatch.py`). TASKER-P1 manual verification for 8.3
still open (no access this session, same as every prior phase that
needed it). Carried-over candidates: wire Anthropic/OpenAI/Fugu
providers into the CLI/TUI provider_map (or pre-filter unroutable
workers); budget persistence across process restarts; orchestrator-
planned ExecutionPlan in the API path (still _stub_plan).

**Files modified this session:** tasker/tui/app.py (rewritten —
TuiApp/main(), REPL removed), tasker/tui/screens/welcome.py (new),
tasker/tui/screens/__init__.py (new), tasker/tui/widgets/status_bar.py
(new), tasker/tui/widgets/__init__.py (new), tests/unit/test_tui_app.py
(rewritten), tests/unit/test_tui_welcome_screen.py (new),
tests/unit/test_tui_status_bar.py (new), docs/SDD_ADDENDUM_PHASE8.md
(B.8/B.5.2 reconciliation), docs/TESTING_GUIDE.md (H8 superseded, new
H9), docs/TASKER_CHECKLIST.md, CLAUDE.md, COWORK_PROMPT.md. No
pyproject.toml change needed (`tasker`/`tasker-cli` entry points already
correct); reinstalled with `pip install -e .` anyway.

**Open decisions / blockers:**
- `active_model`/`session_state` on `HardwareStatusBar` are inert
  placeholders until 8.4/8.5 exist to drive them.
- No explicit dark/light theme decision — Textual's own default theme
  applies; revisit if the addendum ever specifies a visual direction.
- `_handle_completions` (API server) still builds a fresh per-request
  OllamaSessionBudget/SessionManager, separate from the provider's own
  shared budget used for GPU-time accounting — pause/resume checkpoint
  snapshots via the API don't reflect real cumulative cloud usage.
  Pre-existing, not touched this session.
- Should /v1/chat/completions eventually plan through a real
  orchestrator tier instead of _stub_plan's single step? Needed for
  multi-step COWORK-mode requests through a WebUI to behave like real
  COWORK — deferred as orchestrator work.
- Unchanged from before: flip lfm2.5-local to tool_protocol: native
  (probe-confirmed on 0.30.11, needs tool-loop revalidation first);
  update kimi-k2.7-code-cloud context_window/latency from probe data;
  CLI provider_map wires only OllamaProvider — ANY_CLOUD selection can
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

### 8.3 — Tool-loop non-termination guard  ✅ COMPLETE (2026-07-19)

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

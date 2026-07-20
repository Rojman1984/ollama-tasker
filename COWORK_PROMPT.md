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

**Last completed task:** CHAT mode direct dispatch + `/model` + `/effort`
+ honesty-guard gating, ✅ COMPLETE (2026-07-20; third live bug from
Roland the same day, this time from his own chat-mode test — one
dispatch, three issues). Bug: a plain "Hello" was routed through the
full orchestrator pipeline; the worker received the *planner's generated
step description* ("Processing available workers...") instead of the
user's actual message, and three sequential LLM calls took ~56s to first
response. SDD-first: new SDD 5.3a documents CHAT's plan/synthesize
bypass, REPL-owned conversation history, and the `/model`/`/effort`
worker-selection contract; SDD 7.6's REPL command list updated. Fix 1:
new `_run_chat_task()` (`tasker/runtime/dispatch.py`) — exactly one
`run_tool_loop()` call with the raw message as `instruction` and the
REPL's running history as `context["messages"]`, no plan()/synthesize()
at all; `cli/shell.py`'s `_repl()` owns `chat_history` and routes
chat-mode input through it, every other mode unaffected. Fix 2: default
chat worker is the always-loaded `lfm2.5-local`; `/model <worker_id>`
pins an exact worker (always wins); `/effort <low|med|high>` (default
`med`) re-selects via `SPEED_OPTIMIZED`/`COST_OPTIMIZED`/
`CAPABILITY_FIRST` when no `/model` is pinned, reusing existing
`WorkerSelector` ranking rather than hardcoding a "stronger model" id;
`/status` now shows `chat_model`/`chat_effort`. Fix 3:
`check_side_effect_honesty()` gained a `*context_texts` gate — only
fires when the request itself implied a side effect, fixing a false
positive where a "Hello" reply's friendly offer to "run commands or
create files" tripped the guard even though nothing was actually
claimed; also fixed the verb set's missing present-tense forms
("create"/"write"/"run") that would have silently defeated the gate.
Suite 703 → 730 (+27). Live acceptance (Designlab1, zero cloud spend):
`tasker-cli --mode chat "Hello"` → 4.24s real time, conversational
reply, zero warnings, no `[unverified]` warning; multi-turn history
live-verified via `tasker-cli shell` ("My name is Roland." → "What is my
name?" correctly referenced "Roland"). Evidence:
docs/TASKER_CHECKLIST.md → "CHAT mode direct dispatch + `/model` +
`/effort` + honesty-guard gating (2026-07-20)".

---

## Previous completed task (kept for reference)

Cowork honesty + plan-parse resilience bug-fix
session, ✅ COMPLETE (2026-07-20; second P1 from Roland's live cowork
testing the same day, queued right after the provider-selection fix
below). Bug: "create a text file with hello from tasker! and provide the
path" produced NO file, but the answer claimed "verified at
example.txt". Three scoped fixes: (1) `plan_with_repair()`
(`tasker/orchestrator/_parse.py`) — a tolerant text-repair pass (no
extra model call) plus exactly one re-ask with the parse error appended,
tried before any of the four orchestrator tiers falls back to
NanoOrchestrator; (2) `NanoOrchestrator`'s fallback templates
(`tasker/orchestrator/tier0_rules.py`) now embed the real task text into
every step description instead of a purely generic label, so
`narrow_bundle_to_step()` has real signal on its first match attempt;
(3) new `tasker/tools/honesty.py`: `check_side_effect_honesty()` flags a
step's output when it claims a side effect (creation/write/run verb +
file/command/path object, or a filename-shaped token) but `tool_results`
is empty, rewriting it to lead with `[unverified] worker claimed side
effects but used no tools.` — wired into `_execute_steps()` before a
result reaches `results`/`completed_records`. Live re-run of Roland's
exact task (Designlab1, scratch cwd, zero cloud spend): a real
`text_file.txt` was created with the correct content and the synthesized
answer matched reality — honesty guard correctly left it unflagged since
a tool call really did run this time. Suite 677 → 703 (+26). Evidence:
docs/TASKER_CHECKLIST.md → "Cowork honesty + plan-parse resilience bug
fixes (2026-07-20)".

---

## Previous completed task (kept for reference)

`tasker-cli shell` bug-fix session, ✅ COMPLETE
(2026-07-20; live user testing, not a queued addendum phase). P1 fix: a
chat-mode turn's `WorkerSelector` picked `fugu-ultra` even though
`tasker-cli shell`'s `provider_map` only wires `OllamaProvider` — the
step failed mid-dispatch (`No provider for fugu`), ending the run in "No
results to synthesize." with no clear cause. This was the exact
long-flagged "CLI provider_map wires only OllamaProvider" open issue
below, finally fixed rather than just documented: new
`WorkerRegistry.apply_provider_availability(provider_map)`
(`tasker/workers/registry.py`, same never-drop/logged-reason pattern as
`apply_gpu_availability`) marks a worker unavailable when its provider
has no entry in the active `provider_map`; wired into
`tasker/runtime/dispatch.py`'s `_run_task()`/`_resume_task()` right
after `provider_map` is built, so the worker is excluded from planning
*and* selection, not just selection. Regression test uses
`RoutingPolicy.CAPABILITY_FIRST` with the excluded worker scored higher,
proving up-front exclusion rather than a ranking loss. Two REPL UX
fixes in the same session: unknown-command handler suggests a next step
(`/chat` → `did you mean: /mode chat?`; `/wrkers` → `/workers?` via
`difflib`); interactive shell now defaults to `ERROR`-level logging
(was `WARNING`, cluttering the chat flow) with a new `--verbose` flag to
restore it — caught and fixed a real bug while adding the flag:
`_first_positional()` assumed every `--flag` took a value, so
`--verbose` silently swallowed the next real token. Suite 659 → 677
(+18). Evidence: docs/TASKER_CHECKLIST.md → "`tasker-cli shell` bug
fixes -- provider wiring + REPL UX (2026-07-20)".

---

## Previous completed task (kept for reference)

Textual TUI skeleton, ✅ COMPLETE (2026-07-19; the addendum's real Phase
8.3). SDD-first: the addendum had three
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

(That session's own "Next task" pointed at Phase 8.4 — still accurate,
see below; its "Files modified" and "Open decisions" are folded into
this section's lists.)

---

**Next task (current):** SDD_ADDENDUM_PHASE8.md Phase 8.4 —
SetupWizardScreen (wraps `tasker/setup/wizard.py`'s `run_wizard()`) +
ModelSelectorScreen (wraps `tasker/setup/readiness.py`'s
`ReadinessChecker`), plus the Textual message bus
(`WizardStepCompleted`, `ReadinessCheckCompleted`,
`WorkerRegistryUpdated`) per B.11. Then Phase 8.5 (HarnessPanel, built
on `tasker/runtime/dispatch.py`). TASKER-P1 manual verification for 8.3
still open (no access this session, same as every prior phase that
needed it). All three of today's bug-fix sessions were interrupt-driven
by live testing, not a step in the addendum sequence — this queue is
otherwise unchanged.

**Files modified this session (2026-07-20, third bug-fix pass —
CHAT mode direct dispatch):** `docs/SDD.md` (new 5.3a, 7.6 REPL
commands), `tasker/runtime/dispatch.py` (`_run_chat_task`,
`_select_chat_worker`, `DEFAULT_CHAT_WORKER_ID`, `_EFFORT_LEVELS`, and
the `_execute_steps()` honesty-guard call site updated to pass
`task`/`step.description` as context), `cli/shell.py` (`/model`,
`/effort`, `/status`, chat-mode dispatch routing, `chat_history` state),
`tasker/tools/honesty.py` (`*context_texts` gate, expanded verb set),
`tests/unit/test_chat_dispatch.py` (new, 12 tests),
`tests/unit/test_cli_shell.py` (+11), `tests/unit/test_honesty.py` (+4),
`docs/TESTING_GUIDE.md` (new H12), `docs/TASKER_CHECKLIST.md`,
`CLAUDE.md`, `COWORK_PROMPT.md`.

**Files modified this session (2026-07-20, second bug-fix pass):**
`tasker/orchestrator/_parse.py` (`_tolerant_repair`, `_plan_parse_error`,
`plan_with_repair`), `tasker/orchestrator/tier1_single.py`,
`tier2_dual.py`, `tier3_reasoning.py`, `tier4_cloud.py` (wired to
`plan_with_repair`), `tasker/orchestrator/tier0_rules.py`
(task-embedded step descriptions), `tasker/tools/honesty.py` (new),
`tasker/runtime/dispatch.py` (honesty guard wired into
`_execute_steps`), `tests/unit/test_plan_repair.py` (new, 13 tests),
`tests/unit/test_honesty.py` (new, 9 tests),
`tests/unit/test_orchestrator_nano.py` (+2),
`tests/unit/test_orchestrator_single.py` (+1),
`tests/unit/test_cli_session_wiring.py` (+1), `docs/TESTING_GUIDE.md`
(new H11), `docs/TASKER_CHECKLIST.md`, `CLAUDE.md`, `COWORK_PROMPT.md`.

*(First bug-fix pass this same day, provider-wiring + REPL UX:*
`tasker/workers/registry.py` (`apply_provider_availability`),
`tasker/runtime/dispatch.py` (wired into `_run_task`/`_resume_task`),
`cli/shell.py` (`_suggest_command`, `--verbose`, `_BOOL_FLAGS` fix to
`_first_positional`), `tests/unit/test_worker_registry.py` (+5),
`tests/unit/test_dispatch_provider_wiring.py` (new, 2 tests),
`tests/unit/test_cli_shell.py` (new, 11 tests), `docs/TESTING_GUIDE.md`
(new H10)*.)*

**Open decisions / blockers:**
- CHAT's direct-dispatch path has no `SessionManager.tick()`/pause/
  checkpoint involvement by design (a chat turn is a single instant
  call); cloud budget from a chat call routed to a cloud worker (via
  `/effort high` or an explicit `/model`) is still recorded on the
  shared budget but never throttle/pause-gated the way COWORK's step
  loop is — worth reconsidering if that becomes a real
  budget-exhaustion vector in practice.
- Fix 1's re-ask ladder (`plan_with_repair`) wasn't live-exercised by
  the H11.2 re-run specifically — that run's planner JSON parsed on the
  first try. Coverage is unit-level today; worth confirming end-to-end
  with an intentionally-malformed live prompt if a future session wants
  that specific evidence.
- Provider-wiring gap is now *safe* (excluded up front, logged, never a
  silent mid-run failure) but not *closed* — Anthropic/OpenAI/Fugu are
  still unreachable from `tasker-cli shell`/`tasker`'s `provider_map`.
  Wiring them in (or intentionally deciding not to) remains open.
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
  update kimi-k2.7-code-cloud context_window/latency from probe data.
  (The "CLI provider_map wires only OllamaProvider" item that used to be
  here is now the safe-but-not-closed bullet at the top of this list —
  fixed 2026-07-20, see above.)
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

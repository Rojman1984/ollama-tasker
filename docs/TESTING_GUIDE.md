# Ollama Tasker -- Testing Guide

Tests are organized by runtime surface, not source file.
Every feature must have at least one concrete command listed here.

## Setup

```powershell
cd ollama-tasker
.\.venv\Scripts\Activate.ps1

# Full suite
python -m unittest discover -s tests -v

# Phase 1 suite
python -m unittest tests.unit.test_worker_manifest -v
python -m unittest tests.unit.test_worker_registry -v
python -m unittest tests.unit.test_worker_selector -v
```

## H1. Worker Registry

### H1.1 Register local worker
```powershell
python -m unittest tests.unit.test_worker_registry.TestWorkerRegistry.test_register_local_worker -v
```

### H1.2 Register Ollama Cloud worker
```powershell
python -m unittest tests.unit.test_worker_registry.TestWorkerRegistry.test_register_ollama_cloud_worker -v
```

### H1.3 Filter by capability
```powershell
python -m unittest tests.unit.test_worker_registry.TestWorkerRegistry.test_filter_by_capability -v
```

## H2. Routing Policy

### H2.1 COST_OPTIMIZED prefers local
```powershell
python -m unittest tests.unit.test_worker_selector.TestWorkerSelector.test_cost_optimized_prefers_local -v
```

### H2.4 PRIVATE hard block
```powershell
python -m unittest tests.unit.test_worker_selector.TestWorkerSelector.test_private_hard_block_no_local_raises -v
```

## H3. Concurrency Manager
*(add commands when Phase 2 complete)*

## H4. Session Budget + Lifecycle
*(add commands when Phase 2 complete)*
## H5. Live Cloud-Path E2E (Phase 8.1, COWORK_PROMPT numbering)

Requires: Ollama running + signed in to Ollama Cloud (`ollama signin`).
On Designlab1 the server listens on 127.0.0.1:11435 (systemd port.conf).

### H5.1 Unit: CLI session wiring (tick/pause/checkpoint/resume helpers)
```bash
python -m unittest tests.unit.test_cli_session_wiring -v
```

### H5.2 Unit: provider budget recording + used_fallback regressions
```bash
python -m unittest tests.unit.test_provider_ollama.TestOllamaProviderBudgetRecording -v
python -m unittest tests.unit.test_orchestrator_tier2 tests.unit.test_orchestrator_tier3 tests.unit.test_orchestrator_tier4 -v
```

### H5.3 Live: multi-step cloud orchestration with slot + budget logs
```bash
export TASKER_PROFILE=tier2_designlab_cloud
export OLLAMA_BASE_URL=http://127.0.0.1:11435
export TASKER_LOG_LEVEL=INFO
tasker-cli --mode cowork "Plan two steps. Step 1: a reasoning specialist reasons about which is bigger, 6 factorial or 3 to the 6th power. Step 2: a writer states the answer in one sentence."
# Expect: INFO slot acquired/released around each cloud call, INFO budget
# "+N units ... x/3000 session", "used_fallback=False" after planning.
```

### H5.4 Live: throttle, pause -> checkpoint -> resume
```bash
# Throttle (90%+): expect "[throttle] budget at ..% — routing local-biased"
TASKER_BUDGET_PRELOAD=2750 tasker-cli --mode cowork "<same task as H5.3>"

# Pause (100%+): expect PAUSED banner + checkpoint id, then resume it:
TASKER_BUDGET_PRELOAD=3050 tasker-cli --mode cowork "<same task as H5.3>"
tasker-cli resume --last   # fresh process, preload unset -> completes plan
```

### H5.5 Tier 4 reachability (Phase 8.2, COWORK_PROMPT numbering)
```bash
# Unit: resolution from real YAMLs + factory tier-4 construction/degrade
python -m unittest tests.unit.test_orchestrator_factory.TestTier4Reachability -v
python -m unittest tests.unit.test_orchestrator_factory.TestBuildOrchestratorTierSelection -v

# Live: CloudOrchestrator plans via Ollama Cloud, workers hybrid local/cloud
export TASKER_PROFILE=tier4_cloud_hybrid
export OLLAMA_BASE_URL=http://127.0.0.1:11435
export TASKER_LOG_LEVEL=INFO
tasker-cli --mode cowork "Plan two steps. Step 1: a reasoning specialist reasons about whether 91 is prime. Step 2: a writer states the answer in one sentence."
# Expect: "[cowork] Planning with CloudOrchestrator..." + slot/budget INFO
# logs on the plan and synthesize calls themselves.
```

### H5.6 Tool-loop non-termination guard (Phase 8.3, COWORK_PROMPT numbering)
```bash
python -m unittest tests.unit.test_tool_loop -v
# Guard-specific:
python -m unittest tests.unit.test_tool_loop.TestRunToolLoop.test_identical_consecutive_calls_terminate_early -v
python -m unittest tests.unit.test_tool_loop.TestRunToolLoop.test_max_turns_exhaustion_returns_last_result_with_warning -v
```

## H6. Setup Wizard + Agentic Readiness Checker (SDD_ADDENDUM_PHASE8 8.1/8.2)

### H6.1 Headless setup wizard (addendum Phase 8.1)
```bash
python -m unittest tests.unit.test_environment tests.unit.test_setup_wizard -v
# Live (never starts Ollama itself -- reports ERROR with the command to run):
tasker-setup --verbose                       # default http://localhost:11434
tasker-setup --ollama-url http://127.0.0.1:11435 --verbose   # WSL server
```

### H6.2 Agentic readiness checker (addendum Phase 8.2)
```bash
python -m unittest tests.unit.test_readiness -v
# Live: 3-round probe (NATIVE -> LFM25 -> JSON_EXTRACT), report, and
# [Y/n]-confirmed registry write. --yes skips the prompt; --registry PATH
# targets a scratch copy instead of the real registry.
tasker-setup --check-model lfm2.5-thinking:latest --ollama-url http://127.0.0.1:11435
tasker-setup --check-model kimi-k2.7-code:cloud --ollama-url http://127.0.0.1:11435 \
    --registry /tmp/registry_scratch.yaml --yes
# Expect (0.30.11, live-verified 2026-07-19): both confirm NATIVE in Round 1;
# an un-pulled LOCAL model instead prints "Run: ollama pull <name>" and
# probes nothing; an un-pulled :cloud model IS probed (pull not required).
```

## H7. OpenAI-Compat API Server (`tasker-api`)

> Numbering note: the launch task that produced this section originally
> asked for "H6", but H6 (Setup Wizard + Readiness Checker) already exists
> above from an earlier session -- this is H7 to avoid colliding with it,
> same convention as the COWORK_PROMPT-numbering notes elsewhere in this
> file.

`tasker-api` (`tasker/api/server.py:main()`) is wired the same way as
`cli/shell.py`'s `main()`: `TASKER_PROFILE` env (default `tier1_tasker`),
`OLLAMA_BASE_URL` env override of the profile's Ollama URL, a
`provider_map` with a shared `OllamaSessionBudget` +
`OllamaCloudConcurrencyManager` on the `OllamaProvider`, and a
hardware-cache GPU availability cross-check on the worker registry
(skipped if `tasker-hardware detect` has never run on this machine).
Binds `127.0.0.1:8555` by default.

### H7.1 Unit + integration tests
```bash
python -m unittest tests.integration.test_api_server -v
```
Covers: OpenAI-shaped `/v1/models` and `/v1/chat/completions` responses,
the documented no-worker stub fallback, `allowed_modes` (`--mode`)
restricting both endpoints, a mocked-provider live-dispatch path (worker
selection -> `run_tool_loop` -> response, full untruncated prompt reaches
the worker instruction -- regression test for a truncation bug fixed
while wiring this), and a worker failure surfacing as HTTP 500 instead of
crashing the server.

### H7.2 Live: start the server, exercise it as a WebUI client would
```bash
# Never starts Ollama itself (see CLAUDE.md's binding server rules) --
# point at whichever server is already running. WSL: 127.0.0.1:11435.
OLLAMA_BASE_URL=http://127.0.0.1:11435 tasker-api --host 127.0.0.1 --port 8555
# Restrict to one mode (rejects tasker/<other> with 400):
tasker-api --mode chat

# In another terminal:
curl http://127.0.0.1:8555/v1/models
curl http://127.0.0.1:8555/v1/workers
curl -X POST http://127.0.0.1:8555/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "tasker/chat", "messages": [{"role": "user", "content": "Say hello in exactly three words."}]}'
```
Expect (live-verified 2026-07-19, Designlab1 WSL, Ollama 0.30.11 @
127.0.0.1:11435, `tier1_tasker` profile -> local `lfm2.5-local` worker,
zero cloud spend): `/v1/models` lists all 5 `tasker/<mode>` ids;
`/v1/chat/completions` returns a `chat.completion` object with a real
assistant answer dispatched through `WorkerSelector` ->
`OllamaProvider.execute()` via `run_tool_loop` (not the stub echo) --
`lfm2.5-thinking` took ~44s end-to-end for a trivial prompt (thinking
model, see CLAUDE.md's latency notes). Stop the server with the normal
signal (`Ctrl-C` interactively, or `kill <pid>` if backgrounded) --
`web.run_app` shuts down cleanly.

## H8. [SUPERSEDED] Rudimentary TUI REPL

The stdlib-only REPL this section documented (`/mode`, `/budget`, etc.
typed at a `tasker (mode)>` prompt) was a deliberate one-session interim
ahead of the Textual TUI, and is now gone -- `tasker` launches the real
Textual app described in H9 below. Its production-dispatch logic lives
on in `tasker/runtime/dispatch.py` (see H9). For an interactive
multi-turn CLI session today, use `tasker-cli shell`, which has its own
REPL (`/mode`, `/workers`, `/policy`, `/secure`, `/budget`,
`/checkpoint`, `/resume`, `/status`, `/help`) -- a different,
longer-standing implementation, unaffected by the TUI work.

## H9. Textual TUI Skeleton (`tasker`) -- SDD_ADDENDUM_PHASE8 Phase 8.3

`tasker` (`tasker/tui/app.py:main()`) now launches `TuiApp`, a real
full-screen Textual application. Phase 8.3 scope (see the addendum's
2026-07-19 reconciliation note in B.8): `TuiApp` + `WelcomeScreen` +
`HardwareStatusBar` only. Setup Wizard and Model Selector screens are
Phase 8.4; the task-running harness panel is Phase 8.5 -- until then,
every non-Quit menu item shows an inert notice pointing at the headless
command that covers the same ground today (`tasker-setup`,
`tasker-setup --check-model`, `tasker-cli`).

### H9.1 Unit tests
```bash
python -m unittest tests.unit.test_tui_app tests.unit.test_tui_welcome_screen tests.unit.test_tui_status_bar -v
```
Driven headlessly through Textual's own `App.run_test()`/`Pilot` test
driver -- no real terminal needed, no live Ollama calls, no live
hardware detection (`tasker.config.detect._read_matching_cache` is
mocked). Covers: `TuiApp` pushes `WelcomeScreen` on mount; the menu has
all 5 B.5.2 items plus Quit with correct ids; each non-Quit item's
notice text and phase reference; Quit (click and the `q` binding) exits
the app; `HardwareStatusBar.refresh_hardware()` against a mocked cache
(present/absent, with/without GPU, `computed_profile` missing, `ram_gb`
rounding).

### H9.2 Live: launch the real TUI
```bash
tasker
```
Arrow keys / mouse to navigate the menu, Enter or click to select, `q`
or the Quit item to exit. The status bar at the top reads this machine's
real cached hardware detection (`tasker-hardware detect` must have been
run at least once, same as every other entry point that shows it) --
run `tasker-hardware detect` first if it shows "hardware: not detected".

For automated/headless verification without a real terminal (e.g. CI,
or capturing evidence for a phase-completion writeup), drive it the same
way the test suite does:
```python
import asyncio
from tasker.tui.app import TuiApp

async def main():
    app = TuiApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        svg = app.export_screenshot(title="WelcomeScreen")
        open("welcome.svg", "w").write(svg)

asyncio.run(main())
```
Expect (live-verified 2026-07-19, Designlab1 WSL, Textual 8.2.8): boots
straight into the status bar + menu; the bracketed status line reflects
real detected hardware (this machine: 12-core CPU, GTX 1050 Ti 4096MB,
tier 2, resident); selecting Setup Wizard / Model Selector / Run Task /
View Sessions shows the expected "coming in Phase 8.x" notice without
navigating; selecting Daemon cites the B.6 reserved-placeholder note;
`tasker` also confirmed to boot without crashing in a real pty
(`script -qc "timeout 3 tasker" /dev/null` -- ran the full 3s, killed by
the timeout, not a crash).

## H10. `tasker-cli shell` fixes -- provider wiring + unknown-command UX (2026-07-20)

Live user testing found a P1 bug: a chat-mode turn selected `fugu-ultra`
even though `provider_map` only wires `OllamaProvider`, so the step failed
mid-dispatch (`No provider for fugu`) and the run ended in "No results to
synthesize." instead of falling back to an available local worker. Two
smaller REPL UX issues were found in the same session.

### H10.1 Unit tests
```bash
python -m unittest tests.unit.test_worker_registry tests.unit.test_dispatch_provider_wiring tests.unit.test_cli_shell -v
```
Covers: `WorkerRegistry.apply_provider_availability()` marks a worker
unavailable (never dropped from `list_all()`) when its declared provider
has no entry in the active `provider_map`, same pattern as
`apply_gpu_availability`; `_run_task()`/`_resume_task()` exclude such a
worker *before* planning/selection even when it would otherwise win on
routing policy (`CAPABILITY_FIRST`, higher capability score) --
`test_dispatch_provider_wiring.py` proves the wired fallback worker
executes instead of the run failing; `_suggest_command()` special-cases a
bare mode name (`/chat` -> `did you mean: /mode chat?`) ahead of a
generic `difflib` typo match (`/wrkers` -> `/workers`); `_first_positional()`
no longer swallows the token after a boolean flag (`--verbose`, `--last`)
as if it were that flag's value; `main()` defaults interactive-shell
logging to `ERROR` (was `WARNING`, cluttering the chat flow with plumbing
lines), `--verbose` restores `WARNING`, and `TASKER_LOG_LEVEL` (when set)
always wins over both.

### H10.2 Live: unknown-command suggestions + quiet-by-default logging
```bash
tasker-cli shell
```
```
tasker> /chat
Unknown command: /chat  (did you mean: /mode chat?)
tasker> /wrkers
Unknown command: /wrkers  (did you mean: /workers?)
```
No plumbing warnings appear by default; `tasker-cli shell --verbose`
restores them. Live-verified 2026-07-20 (Designlab1), local-only, zero
cloud spend -- slash-command testing only, no chat/tool dispatch run.

## H11. Plan-parse resilience + fallback intent + honesty guard (2026-07-20)

Live cowork test (Roland's own shell) found a P1 bug: "create a text file
with hello from tasker! and provide the path" produced NO file, but the
synthesized answer claimed "verified at example.txt". Three scoped fixes.

### H11.1 Unit tests
```bash
python -m unittest tests.unit.test_plan_repair tests.unit.test_honesty tests.unit.test_orchestrator_nano tests.unit.test_orchestrator_single tests.unit.test_cli_session_wiring -v
```
Covers: `plan_with_repair()` (`tasker/orchestrator/_parse.py`) -- parses
as-is first, then a tolerant text-repair pass (markdown fences, trailing
commas, single-quoted tokens) with zero extra model calls, then exactly
one re-ask with the parse error appended, before returning `None` for
the caller's existing NanoOrchestrator fallback; wired into all four
tiers (`tier1_single.py`, `tier2_dual.py`, `tier3_reasoning.py`,
`tier4_cloud.py`). `NanoOrchestrator`'s fallback templates now embed the
real task text into every step description (`tasker/orchestrator/
tier0_rules.py`), not just a generic label. `check_side_effect_honesty()`
(`tasker/tools/honesty.py`) -- a dual-signal heuristic (a side-effect verb
+ an object noun or filename-shaped token) rewrites a step's output to
lead with `[unverified] worker claimed side effects but used no tools.`
when `tool_results` is empty; wired into `tasker/runtime/dispatch.py`'s
`_execute_steps()` right after `run_tool_loop()` returns, before the
result is appended to `results`/`completed_records`.

### H11.2 Live: Roland's exact cowork task
```bash
cd /some/scratch/dir
OLLAMA_BASE_URL=http://127.0.0.1:11435 TASKER_PROFILE=tier2_designlab \
  tasker-cli --mode cowork "create a text file with hello from tasker! and provide the path"
```
Live-verified 2026-07-20 (Designlab1, WSL Ollama, `lfm2.5-thinking:latest`):
planner JSON parsed on the first attempt this run (only a harmless
capability string got dropped -- `"tasker!"` misread from the task
wording, not a parse failure); the tool loop's non-termination guard
correctly stopped a duplicate `file_write` call on turn 2, but turn 1's
call had already executed for real -- `text_file.txt` was created on
disk with content `hello from tasker!`, and the synthesized answer ("The
text file has been created at text_file.txt.") matched reality, so the
honesty guard correctly left it unflagged (a tool call really did run).
Confirms the fix end-to-end: a real file was produced and the answer was
truthful. Local only, zero cloud spend.

## H12. CHAT mode direct dispatch + /model + /effort + honesty-guard gating (2026-07-20)

Third live bug this day, from Roland's own chat-mode test: CHAT was
routed through the full orchestrator pipeline like every other mode. The
worker received the planner's generated step description ("Processing
available workers...") instead of the user's actual "Hello" -- a pure
hallucination artifact -- and three sequential LLM calls (plan, worker
turn, synthesize) took ~56s to first response. Same session also fixed
the honesty guard over-firing on a plain greeting.

### H12.1 Unit tests
```bash
python -m unittest tests.unit.test_chat_dispatch tests.unit.test_cli_shell tests.unit.test_honesty -v
```
Covers: `_select_chat_worker()` (`tasker/runtime/dispatch.py`) -- `/model`
always wins; default is the always-loaded local worker
(`lfm2.5-local`) at effort `med`; `low`/`high` effort re-select via
`SPEED_OPTIMIZED`/`CAPABILITY_FIRST` when no `/model` is pinned; an
unknown or unavailable `/model` id raises cleanly.  `_run_chat_task()`
-- the worker receives the user's raw message as `instruction`, never a
planner artifact; exactly one provider call (no plan/synthesize calls --
proven by passing a pipeline whose orchestrator slot is `None` and
confirming no `AttributeError`); conversation history accumulates across
turns and is threaded to the next call; a failed turn does not poison
history with an unanswered user message.  `cli/shell.py`'s `_repl()` --
`/model`, `/effort`, `/status` (now showing `chat_model`/`chat_effort`),
and that chat-mode input dispatches through `_run_chat_task()` while
every other mode still dispatches through the full `_run_task()`
pipeline, unaffected.  `tasker/tools/honesty.py`'s gating fix -- the
guard now only fires when the *task or step text itself* implies a side
effect (a regression test reproduces the exact false positive: a
friendly greeting reply that merely offers "let me know if you'd like me
to run any commands or create files" no longer trips the guard, since
nothing about a plain "Hello" implied one).

### H12.2 Live acceptance: a chat greeting answers fast, cleanly, no warnings
```bash
OLLAMA_BASE_URL=http://127.0.0.1:11435 TASKER_PROFILE=tier2_designlab \
  tasker-cli --mode chat "Hello"
```
Live-verified 2026-07-20 (Designlab1, WSL Ollama,
`lfm2.5-thinking:latest`): **4.24s real time** (well under the 10s bar),
a genuinely conversational reply, zero warnings printed (default quiet
logging) and none present even at `TASKER_LOG_LEVEL=WARNING` beyond
pre-existing, unrelated provider-wiring/tool-narrowing logs -- no
`[unverified]` honesty-guard warning. Multi-turn history also
live-verified through `tasker-cli shell`: "My name is Roland." followed
by "What is my name?" produced a reply that correctly referenced
"Roland", confirming `WorkerTask.context["messages"]` carried real
conversation history across REPL turns. `/status` showed
`chat_model=lfm2.5-local (default)  chat_effort=med` as expected. Local
only, zero cloud spend.

## H13. `/model` dynamic onboarding (2026-07-20)

New sprint (REPL/TUI UX package), part 1 of 3. An unregistered `/model
<tag>` that looks like a genuine Ollama model reference (`name:tag`)
offers to pull it, probe it for tool-calling readiness, and register it
-- rather than a flat "Unknown worker id" rejection.

### H13.1 Unit tests
```bash
python -m unittest tests.unit.test_onboarding tests.unit.test_cli_shell.TestReplModelOnboarding -v
```
Covers: `looks_like_model_tag()` (accepts `name:tag` shapes, rejects
colon-less registry-style ids so a typo of a known id is never treated
as a download candidate); `pull_model()` -- success on final
`{"status": "success"}`, failure on non-200/`{"error": ...}`/unexpected
final status/transport exception, progress callback invoked per NDJSON
line (all via an injected `_pull_fn`, no real HTTP); `onboard_model()`
-- pull failure never probes or registers, probe failure (not
tool-capable) never registers despite a successful pull, success writes
the manifest to the registry file *and* the live in-memory registry and
returns it. `cli/shell.py`'s `_onboard_and_pin()` -- the REPL's
confirm/decline flow, and that a colon-less unregistered id never offers
onboarding (falls through to the plain "Unknown worker id" message).

### H13.2 Live: real pull + probe against the WSL Ollama server
```bash
OLLAMA_BASE_URL=http://127.0.0.1:11435 TASKER_PROFILE=tier2_designlab tasker-cli shell
tasker> /model smollm2:135m
Download and onboard 'smollm2:135m'? [y/N] y
```
Live-verified 2026-07-20 (Designlab1, WSL Ollama): real `POST
/api/pull` streamed real progress lines (`pulling manifest` ->
`pulling <digest>` x6 -> `verifying sha256 digest` -> `writing
manifest` -> `success`), confirmed via `GET /api/tags` showing
`smollm2:135m` actually present on the server afterward. The probe then
correctly reported the tiny 135M model as NOT tool-capable (expected --
proves the failure path honestly: pulled but not registered,
`worker_registry.yaml` untouched, CHAT model selection unchanged).
Cleaned up afterward via `DELETE /api/pull`'s counterpart `/api/delete`
(never the `ollama` CLI, per the binding server rules) -- server back to
its original 3-model state. The success-registration path itself is
unit-tested (`test_onboarding.py`'s
`test_pull_and_probe_success_registers_and_returns_manifest`) rather
than forcing a second, larger tool-capable download live. Local only;
zero Ollama Cloud spend (the one live `/api/pull` was against a local,
not `:cloud`-tagged, tag).

## H14. Context controls -- num_ctx wiring, /context, /models, /budget init (2026-07-20)

New sprint (REPL/TUI UX package), part 2 of 3.

### H14.1 Unit tests
```bash
python -m unittest tests.unit.test_provider_ollama.TestResolveNumCtx tests.unit.test_provider_ollama.TestOllamaProviderNumCtxPayload tests.unit.test_cli_shell_context -v
```
Covers: `resolve_num_ctx()` (`tasker/workers/providers/ollama.py`) --
cloud workers always get the manifest's full `context_window` regardless
of GPU data; local workers with no GPU data are left uncapped (no basis
to cap on); local workers get capped when the VRAM estimate is lower
than the manifest's value, including the unified-memory reserve applied
first; `OllamaProvider.execute()` actually sends the resolved value in
`options.num_ctx` (was never sent at all before), and
`task.context["num_ctx_override"]` wins over everything, including the
VRAM cap. `cli/shell.py`: `_print_budget()` (initializes at 0.0, shows
accumulated usage, handles a failed-to-build pipeline gracefully),
`_print_models()` (DEFAULT/LOCAL/CLOUD grouping, tool protocol + max
context columns, the VRAM-fit hint), `/context <tokens>` (set/get/reject
non-positive), `/models` and its `/model list` alias, and the REPL's
per-mode pipeline caching (`_ensure_pipeline`/`_evict_if_paused`) -- one
`_build_pipeline()` call per mode for the whole session (not per turn),
the same pipeline object reused across chat turns so budget genuinely
accumulates, and a pipeline whose session went `PAUSED` is evicted so
the next task in that mode rebuilds fresh.

### H14.2 Live: real VRAM ceiling + budget + context override
```bash
OLLAMA_BASE_URL=http://127.0.0.1:11435 TASKER_PROFILE=tier2_designlab tasker-cli shell
tasker> /budget
tasker> /models
tasker> Hello
tasker> /budget
tasker> /context 4096
tasker> Hi again
```
Live-verified 2026-07-20 (Designlab1, WSL Ollama, real cached GPU
detection -- GTX 1050 Ti 4096MB): `/budget` showed `budget=0.0/3000
units (0.0%)` *before* any task ran, not the old "not active" message.
`/models` correctly grouped `lfm2.5-local` under DEFAULT and all 8
`:cloud`/`direct_cloud` workers under CLOUD, and showed a real,
data-driven VRAM-fit hint on `lfm2.5-local`: `(fits ~32768 of 128000 in
VRAM)` -- its manifest declares a 128000 context window, but this
machine's real GPU cache correctly capped the estimate to 32768. Both
chat turns answered normally (budget stayed 0.0 -- correct, local calls
never consume Ollama Cloud budget), including the second turn after
`/context 4096` was set, confirming the override was accepted and sent
without breaking the call. Local only, zero cloud spend.

## H15. readline REPL -- arrow-key editing, history, Ctrl-R, tab-completion (2026-07-20)

New sprint (REPL/TUI UX package), part 3 of 3. Roland's live session
showed raw escape codes on arrow keys -- the REPL's `input()` had no
line-editing support at all.

### H15.1 Unit tests
```bash
python -m unittest tests.unit.test_cli_shell_readline -v
```
Covers: `_make_completer()`'s candidate logic (slash commands at the
start of a line, mode names after `/mode `, worker ids after `/model `
or `/resume `, no candidates for a plain chat message, exhausted-state
returns `None`) via an injectable line-buffer callable -- no real
terminal needed; `_load_history()`/`_save_history()` roundtrip through a
real (but tmp-directory) history file, missing-file is a silent no-op,
parent directories are created on save; `_init_readline()` configures
the completer/delims/tab-binding and returns `True` when `readline` is
available, `False` (safe no-op) when it isn't (`cli.shell.readline`
patched to `None`, covering the Windows-without-pyreadline3 case per
CLAUDE.md's PowerShell-secondary note). A dedicated regression test
(`test_never_touches_real_home_directory_history_file`) guards against
the exact mistake caught while writing these tests: every REPL-driving
test in `test_cli_shell.py`/`test_cli_shell_context.py` now mocks
`_init_readline`/`_save_history`, since without that they were silently
creating/writing a real `~/.tasker_history` file on the machine running
the suite.

### H15.2 Live: real pty, tab-completion + arrow-key history recall + persisted history
```python
# scripted via Python's pty module -- input() only gets real line editing
# through an actual pseudo-terminal, not a piped stdin
import os, pty
pid, fd = pty.fork()
if pid == 0:
    os.execvpe("tasker-cli", ["tasker-cli", "shell"], env)  # env: OLLAMA_BASE_URL, TASKER_PROFILE, HOME=<scratch>
# ...then os.write(fd, b"/bud"); os.write(fd, b"\t"); os.write(fd, b"\n")
```
Live-verified 2026-07-20 (Designlab1, WSL Ollama, real pty via
`os.pty.fork()`, scratch `$HOME` so nothing touched the real
`~/.tasker_history`): typing `/mod` + Tab extended to the longest common
prefix `/mode` among the three ambiguous `/mode`/`/model`/`/models`
matches (correct GNU readline ambiguous-completion behavior); typing
`/bud` + Tab unambiguously completed to `/budget` and executed it,
printing real budget stats (`mode=chat  budget=0.0/3000 units (0.0%)
plan=pro  window_remaining=4:59:56`); after clearing the line and
pressing Up-arrow, readline correctly recalled the previous history
entry `/budget`. The scratch `~/.tasker_history` file was confirmed to
contain the real submitted commands (`/budget`, `/quit`) after the
session exited. Ctrl-R reverse search was not separately scripted (it's
the same GNU readline C library already exercised live by Tab and
Up-arrow, not additional code this project wrote) but is enabled by the
same `import readline`. Local only, zero cloud spend (no chat/tool
dispatch beyond `/budget`, which makes no worker call).

## SDD_ADDENDUM_PHASE8.md B.5.5 -- Keyboard Bindings & Text Selection (spec only)

New requirement section added to the TUI addendum (no TUI code changed
this sprint): every 8.4/8.5 screen with a text input needs a Textual
equivalent of the REPL's arrow-key history recall, Ctrl-R-equivalent
reverse search, and tab-completion; every output/report panel needs
verified native terminal text selection (or an explicit in-app
copy-to-clipboard fallback if Textual's own mouse capture defeats native
selection for that widget). See B.5.5 for the full requirement list.
Checked off nothing (spec only) -- B.11's Phase 8.4/8.5 checklists
gained a line each pointing back at B.5.5.

## H16. Chat rewind buffer -- session transcript, /transcript, auto-save (2026-07-20)

Addendum to part 3 of the REPL/TUI UX sprint, from the same live-testing
session: REPL output scrolls off the terminal and, until this, was
simply gone once it left scrollback.

### H16.1 Unit tests
```bash
python -m unittest tests.unit.test_transcript tests.unit.test_cli_shell_transcript -v
```
Covers: `Transcript` (`tasker/runtime/transcript.py`) -- `record()`
appends entries in memory and (when a path is set) to disk immediately,
not only at some later flush; `exchanges()` groups a "user" entry with
everything logged until the next "user" entry (event entries in between
stay in the same exchange; leading events before the first user entry
form their own group); `render_exchanges(n)` returns the full session or
just the last `n` exchanges; a path whose parent can't be created (e.g.
blocked by a file where a directory is expected) degrades to
in-memory-only rather than crashing. `cli/shell.py`: `_Tee` mirrors
stdout to multiple streams; `_page_lines()` (the terminal pager) prints
short output with no pause, paginates longer output with `-- more --`
prompts, stops early on `q`, and doesn't crash on Ctrl-C during the
prompt; `_print_transcript()`; the REPL's startup banner mentions the
transcript path when disk writing is active (and omits the line when
it's degraded to in-memory-only); every slash command is recorded as an
"event", every chat/task turn as "user"+"assistant" (captured via the
Tee, so warnings/budget lines printed alongside the answer are captured
too, not just a synthesized "final answer" string); `/transcript [n]`
reprints and accepts/rejects arguments correctly. Every REPL-driving
test in this file and the three existing `test_cli_shell*.py` files now
mocks `default_transcript_path` (to a tmp path or `None`) alongside the
existing `_init_readline`/`_save_history` mocks -- same discipline as
H15's history-file fix, guarding against a real
`~/.tasker/transcripts/*.md` file being silently created during test
runs (caught live while writing these tests, fixed before it shipped).

### H16.2 Live: real chat turn, transcript file, /transcript reprint
```bash
export HOME=<scratch dir>   # keep the real ~/.tasker/transcripts untouched
export OLLAMA_BASE_URL=http://127.0.0.1:11435
export TASKER_PROFILE=tier2_designlab
tasker-cli shell
tasker> /status
tasker> Hello
tasker> /transcript
tasker> /quit
```
Live-verified 2026-07-20 (Designlab1, WSL Ollama, scratch `$HOME`, zero
cloud spend): startup banner printed `Transcript:  <scratch>/.tasker/
transcripts/20260720-133025.md`; a real chat turn ("Hello" -> a genuine
conversational reply) completed normally; `/transcript` reprinted the
exchange correctly; the on-disk file, read back after the session,
contained the full session in the expected markdown shape --
`/status` and `/transcript` and `/quit` as italic event lines, the user
message and assistant reply as bold You:/Tasker: lines, in the correct
order -- confirming the transcript really is written incrementally as
the session runs, not just held in memory. The real `~/.tasker/
transcripts` was confirmed untouched throughout (scratch `$HOME` used
for the whole live test).

## H17. RESEARCH mode grounding -- WEB_SEARCH executor + plan/prompt/synthesis enforcement + honesty guard (2026-07-20)

New sprint from Roland's live research-mode test: RESEARCH mode
fabricated an entire model comparison and a fake benchmark statistic
with ZERO tool calls. Root cause: `WEB_SEARCH`/`RETRIEVE`/etc had no
execution implementation at all, AND no `_TOOL_KEYWORDS` entry, so
`narrow_bundle_to_step()` narrowed every research step to an empty tool
set regardless of content -- the model could never have called these
tools even if it tried.

### H17.1 Unit tests
```bash
python -m unittest tests.unit.test_tool_executor tests.unit.test_tool_bundles tests.unit.test_tool_loop tests.unit.test_orchestrator_parse tests.unit.test_orchestrator_single tests.unit.test_orchestrator_tier2 tests.unit.test_orchestrator_tier3 tests.unit.test_orchestrator_tier4 tests.unit.test_orchestrator_factory tests.unit.test_honesty tests.unit.test_research_grounding tests.unit.test_cli_shell_research -v
```
Covers: `_exec_web_search()`/`_exec_retrieve()` (`tasker/tools/executor.py`)
-- Brave Search API call (HTTP mocked via `_search_get_fn`/`_page_get_fn`
module-level swap points, never real network), missing `BRAVE_API_KEY`
reported cleanly, results capped and URL-less results dropped, HTML
stripped to readable text with script/style blocks removed, both work
from a cloud worker (network reads, never `_LOCAL_ONLY_TOOLS`-gated);
`narrow_bundle_to_step()` now offers `WEB_SEARCH`/`RETRIEVE`/`PDF_EXTRACT`/
`CITATION_TRACKER`/`CONTRADICTION_DETECTOR` for realistic research step
text (previously always empty -- the actual root-cause fix);
`run_tool_loop()`'s multiple-tool-calls-in-one-turn now execute in
parallel (proven via wall-clock timing, not just call-count);
`build_plan_prompt()`/`build_synthesize_prompt()` append a grounding
requirement only for `mode_name="research"`; all four orchestrator tiers
accept and thread an optional `mode_name` constructor param into both
prompt builders; `factory.py`'s `build_orchestrator()` threads
`config.mode.name` into every tier; `check_research_grounding()`
(`tasker/tools/honesty.py`) flags zero-retrieval factual output, no
output-side keyword gate (unlike the side-effect guard) since any
research claim with zero retrieval is unverifiable by construction;
`_enforce_research_grounding()` (`tasker/runtime/dispatch.py`) injects a
real retrieval step (correctly reindexed, dependencies shifted) when a
plan has none and a search backend is configured, a no-op otherwise;
`_apply_research_synthesis_honesty()` checks the union of every step's
tool calls against the final synthesized answer; an end-to-end test
drives the real `_run_task()` with a fake orchestrator + fake provider
proving the injected step actually executes and the final answer gets
flagged/not-flagged correctly; `cli/shell.py`'s
`_warn_if_research_ungrounded()` announces a missing `BRAVE_API_KEY` at
`/mode research` (REPL), REPL startup (when starting directly in
research mode), and the one-shot `--mode research` CLI path.

### H17.2 Live: no-backend honest degradation (real Ollama, no Brave key)
```bash
OLLAMA_BASE_URL=http://127.0.0.1:11435 TASKER_PROFILE=tier2_designlab tasker-cli shell
tasker> /mode research
tasker> compare the speed of a cheetah and a greyhound
```
Live-verified 2026-07-20 (Designlab1, WSL Ollama, `BRAVE_API_KEY`
deliberately unset): `/mode research` printed the no-backend warning;
the planner's own step description now says "Perform web_search for
comparison" (previously step descriptions themselves asserted invented
facts); with no real search backend to call, the worker did **not**
fabricate a comparison -- it answered "The comparison cannot be made due
to lack of relevant data," and the honesty guard still correctly
prefixed the final synthesized answer with `[unverified -- no sources
retrieved]` regardless. This is the concrete behavior change from the
reported bug: previously silent fabrication, now either an honest
non-answer or an explicitly marked unverified one -- never presented as
plain fact. Local only, zero cloud spend.

**Not live-verified this session: a real research query with real
citations from an actual Brave Search API call.** No `BRAVE_API_KEY` is
available in this sandboxed environment. The `WEB_SEARCH`/`RETRIEVE`
executors are fully unit-tested against a mocked Brave API response
shape (`tests/unit/test_tool_executor.py`), and the honest-degradation
path above proves the rest of the pipeline (planning, tool offering,
honesty guard) works correctly when a step *does* get real tool results
-- see `test_research_grounding.py`'s
`test_no_flag_when_a_real_retrieval_call_backs_the_claim`, which proves
the guard clears when a real `web_search`/`retrieve` call occurred. A
future session with a real `BRAVE_API_KEY` should run one live research
query end-to-end and confirm the synthesized answer cites real URLs.

### H17.3 Search-query rewrite step (SDD 5.1a.5)

```bash
python -m unittest tests.unit.test_query_rewrite -v
```

Covers: `rewrite_search_query()` (`tasker/tools/query_rewrite.py`) rewrites
a natural-language research step description plus the model's optional
draft query into a concise, keyword-focused Brave Search query, strips
a single pair of surrounding quotes if the model adds them, and falls
back to the draft query (or the step description itself if no draft
exists) on empty response or exception. `build_query_rewriter()` reuses
the same worker/provider via `tasker.orchestrator.factory.make_call_model()`
with a 30-second timeout and the correct privacy tier derived from the
worker's `compute_location`. `run_tool_loop()` applies the rewriter only
to `web_search` tool inputs, leaving `retrieve` and all other tools
untouched; RESEARCH mode wiring in `tasker/runtime/dispatch.py` builds
the rewriter only when `BRAVE_API_KEY` is configured.

## H18. DELEGATE_AGENT -- sub-task dispatch (2026-07-20)

New sprint from a tool-executor audit: 15 `ToolID`s had no execution
implementation at all -- a model could request one and nothing would
happen. Part 1 of 3 (highest priority): `DELEGATE_AGENT`, which unblocks
the planned concurrency stress test.

### H18.1 Unit tests
```bash
python -m unittest tests.unit.test_delegation -v
```
Covers: `DelegationContext.child()` (`tasker/runtime/delegation.py`) --
increments depth, shares the `spawned` counter object (not a copy,
across the whole delegation tree), preserves the pipeline and limits;
`_exec_delegate_agent()`'s guard clauses (missing `task`, no delegation
context, depth limit, sub-agent cap -- cap check does not increment past
itself); the real recursive path -- a fake orchestrator + fake provider
prove a delegated sub-task actually dispatches through
`tasker.runtime.dispatch._run_task()`, returns `{"task", "result"}` as
structured tool output, consumes the SAME shared pipeline (provider
called, not a separate one), increments the spawned counter, and that a
three-deep delegation chain (depth 0 -> 1 -> 2 -> refused at what would
be depth 3) hits the depth limit correctly; `execute_tool()` itself
correctly routes `delegate_agent` to the new handler and is not
`LOCAL_ONLY_TOOLS`-gated (a dispatch call, not local execution).

### H18.2 Live: cowork task attempting delegation (local only)
```bash
OLLAMA_BASE_URL=http://127.0.0.1:11435 TASKER_PROFILE=tier2_designlab \
  tasker-cli --mode cowork --policy local "Call the delegate_agent tool with task='say hi'. Report exactly what the tool returns."
```
Attempted live 2026-07-20 (Designlab1, WSL Ollama, `--policy local` to
guarantee zero cloud spend) several times with varied phrasing. Two
concrete findings, neither a defect in this session's own code: (1) an
early attempt without `--policy local` routed the step to a *cloud*
worker (`nemotron-3-ultra-cloud`, +1.6% budget) and answered directly
without delegating -- confirms `--policy local` is required for a
zero-cloud-spend attempt, not optional; (2) with `--policy local`
enforced, `lfm2.5-thinking` (the local planner/worker on this machine)
never actually issued a `delegate_agent` tool call across several
phrasings -- it either answered trivial sub-tasks directly (consistent
with this project's established finding that small local models
routinely skip an offered tool in favor of answering directly when they
believe they can), or, in one case, badly misparsed a prompt containing
the word "pong" as being about the video game and planned around that
instead. No run produced a real live `delegate_agent` invocation within
the time available. The mechanism itself -- shared budget/concurrency,
bounded depth, the per-task cap, and the actual recursive dispatch and
result-passing -- is proven at the unit level instead
(`test_delegation.py`'s `TestExecDelegateAgentRecursive` class drives
the real, non-mocked `_run_task()` recursion). A future session with
more time (or a stronger local model, or a cloud model with an explicit
zero-spend guard) should retry the live invocation specifically. Zero
cloud spend was maintained throughout every attempt after the first.

## H19. TEST_RUNNER, LINTER, CALCULATOR executors -- tool-executor fill-in part 2 (2026-07-20)

Part 2 of the tool-executor fill-in sprint. Replaces the previous
"no execution implementation configured" placeholders for `TEST_RUNNER`,
`LINTER`, and `CALCULATOR` with real executors and the `_TOOL_KEYWORDS`
groups needed for `narrow_bundle_to_step()` to offer them.

### H19.1 Unit tests
```bash
python -m unittest tests.unit.test_tool_executor.TestCalculator -v
python -m unittest tests.unit.test_tool_executor.TestTestRunner -v
python -m unittest tests.unit.test_tool_executor.TestLinter -v
python -m unittest tests.unit.test_tool_bundles.TestNarrowBundleToStepKeywordMatches.test_calculator_keyword_matches -v
```
Covers: CALCULATOR AST-whitelist arithmetic, missing-expression handling,
eval/function-call blocking, and no `LOCAL_HARDWARE` gating; TEST_RUNNER
pytest and unittest output parsing, pytest-vs-unittest detection,
failing-test-name extraction, and real unittest-discover fallback;
LINTER ruff JSON output parsing and honest "not installed" error when
ruff is absent; CALCULATOR keyword registration in
`narrow_bundle_to_step()`.

### H19.2 Full suite
```bash
python -m unittest discover -s tests
```
Expected: all tests pass (935 total after this commit).

### H19.3 Live: calculator from CHAT mode
```bash
OLLAMA_BASE_URL=http://127.0.0.1:11435 TASKER_PROFILE=tier1_tasker \
  tasker-cli --mode chat "What is 12345 * 6789?"
```
Expected: the model is offered the `calculator` tool for this arithmetic
step and returns a numeric answer (exact interaction depends on the
local model's tool-use reliability; the executor itself is unit-tested).

## H20. Honest degradation for unimplemented tools -- tool-executor fill-in part 3 (2026-07-20)

Part 3 of the tool-executor fill-in sprint. Remaining placeholder tools
(`CHECKPOINT_WRITE`, `CITATION_TRACKER`, `CONTRADICTION_DETECTOR`,
`LOCAL_MEMORY`, `LOCAL_SEARCH`, `MCP_CALL_TOOL`, `MEMORY_READ`, `PDF_EXTRACT`,
`PROGRESS_REPORT`, `SEARCH`, `TASK_STATE`) are now excluded from the
bundles offered to workers. If a model ever still requests one,
`execute_tool()` returns a structured error carrying the tool name,
"not available in this build", and the list of tools that ARE available.

### H20.1 Unit tests
```bash
python -m unittest tests.unit.test_tool_executor.TestUnavailableTools -v
python -m unittest tests.unit.test_tool_bundles.TestBundleImplementationFilter -v
```
Covers: unavailable-tool request returns `{tool, error, available_tools}`
with the correct tool name and the full implemented-tools list; unknown
tool names get the same shape; `get_definitions()` drops every
unimplemented tool from the offered bundle; `narrow_bundle_to_step()`
never returns an unimplemented tool; `implemented_tools()` equals
`_DISPATCH` keys.

### H20.2 Full suite
```bash
python -m unittest discover -s tests
```
Expected: all tests pass (941 total after this commit).

### H20.3 Registry-of-truth invariant
Adding a new executor to `tasker/tools/executor.py` `_DISPATCH` will:
1. automatically include it in `implemented_tools()`;
2. automatically allow `get_definitions()` to offer it if the mode bundle
   includes it;
3. automatically include it in the structured error's `available_tools`.
No separate allow-list needs to be maintained.

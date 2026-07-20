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

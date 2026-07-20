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

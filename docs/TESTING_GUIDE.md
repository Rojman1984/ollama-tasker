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

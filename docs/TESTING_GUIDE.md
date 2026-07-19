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

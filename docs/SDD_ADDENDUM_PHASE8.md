# Ollama Tasker — SDD Addendum: Phase 8
# Setup Wizard, Agentic Readiness Checker, and TUI

**Addendum version:** 1.0.0
**Extends:** SDD.md v0.1.0-draft + SDD_ADDENDUM_7.5.md
**Status:** Draft — pending Phase 8 implementation
**Date:** 2026-06-30

---

## B.1 Purpose and Scope

This addendum introduces three new subsystems not present in the original
7-phase roadmap or the 7.5 hardware-detection addendum:

1. **Setup Wizard** (`tasker/setup/wizard.py`) — a re-runnable, headless
   setup pipeline that detects hardware, verifies the Ollama environment,
   guides the user through GPU acceleration configuration, and writes a
   validated machine-local config. Callable from the TUI or from the
   command line. No UI dependency.

2. **Agentic Readiness Checker** (`tasker/setup/readiness.py`) — probes a
   user-selected Ollama model with live tool-call test prompts, detects
   which `ToolProtocol` it actually uses, and reports whether it is
   compatible with the harness. No UI dependency. Writes a confirmed
   `WorkerManifest` entry to `config/workers/worker_registry.yaml` on
   success.

3. **TUI** (`tasker/tui/`) — a Textual-based full-screen terminal
   application that provides an interactive interface to the setup wizard,
   model selector, readiness checker, and (in later sub-phases) the harness
   control panel. The TUI calls the headless subsystems above; it does not
   contain any logic of its own. This separation ensures the same wizard
   and readiness logic runs identically whether invoked from the TUI, from
   the CLI, or headlessly.

**Target environments:** Native Linux and WSL2 on Windows. No OS-level
driver installs — Python, Ollama, and environment variable configuration
only.

**Not in this phase:**
- Web dashboard (future)
- Dispatch/Tag-style WebSocket event integration (future — Textual's own
  message bus is the bridge point)
- Windows native (PowerShell/cmd) TUI support (future)
- Automated model pulling (guided only — user must confirm `ollama pull`)

---

## B.2 New Entry Points

```toml
# pyproject.toml additions
[project.scripts]
tasker          = "tasker.tui.app:main"     # replaces cli/shell.py as default
tasker-cli      = "cli.shell:main"          # existing CLI, renamed for clarity
tasker-hardware = "tasker.config.detect:cli_main"   # unchanged
tasker-setup    = "tasker.setup.wizard:cli_main"    # headless wizard path
```

`tasker` with no arguments launches the TUI. The existing CLI task-runner
behavior moves to `tasker-cli` — all existing scripts and tests using
`python -m cli.shell` continue to work unchanged; only the console script
entry point changes.

---

## B.3 Setup Wizard Architecture

### B.3.1 Design Principles

- **Re-runnable:** The wizard detects current state on every run and shows
  current status, not just initial setup state. Running it on an already-
  configured machine shows green checkmarks, not re-prompts to re-configure.
- **Non-destructive:** The wizard never overwrites a config file without
  showing the user what it will change and asking for confirmation.
- **Headless-capable:** Every check and action in the wizard is a Python
  function returning a structured result. The TUI renders these results;
  the headless CLI prints them. The logic is identical.
- **WSL2-aware:** The wizard detects whether it is running inside WSL2
  (`/proc/version` contains "Microsoft" or "WSL") and adjusts Ollama
  service detection accordingly (systemctl may not be available in WSL2
  depending on the distro and init configuration).

### B.3.2 Wizard Steps

The wizard runs these steps in order. Each step returns a `WizardStepResult`
with a status (`OK`, `WARNING`, `ERROR`, `SKIPPED`) and a message. The TUI
renders each step as a live status row; the CLI prints each result as it
completes.

```
Step 1 — Environment detection
  1.1  Python version check (>= 3.11 required)
  1.2  Virtual environment detection (warn if not in venv)
  1.3  WSL2 vs native Linux detection
  1.4  Harness package install check (pip show ollama-tasker)

Step 2 — Ollama presence and service
  2.1  Ollama binary detection (shutil.which("ollama"))
  2.2  Ollama version check (ollama --version)
  2.3  Ollama service reachability (GET http://localhost:11434/api/tags)
       -- on WSL2: direct HTTP check (systemctl unreliable)
       -- on native Linux: both systemctl status and HTTP check
  2.4  If not reachable: display "Run: ollama serve" and wait for user
       to start it, then re-check (do not auto-start -- user decision)

Step 3 — Hardware detection
  3.1  Run detect_hardware_profile() (from tasker.config.detect)
       -- uses the full NvidiaBackend → AmdApuBackend → NoGpuBackend chain
  3.2  Display detected profile (CPU cores, RAM, GPU vendor/VRAM, tier)
  3.3  GPU-specific guidance per vendor:
       NVIDIA: display nvidia-smi output, confirm WSL2 passthrough
       AMD APU: display OLLAMA_VULKAN / ROCR_VISIBLE_DEVICES /
                HIP_VISIBLE_DEVICES status, provide set commands if missing
                (do not auto-set -- display the commands, let user run them)
       None: display "No GPU detected -- CPU inference only"

Step 4 — GPU acceleration verification (requires Ollama running + model)
  4.1  Skip if no GPU detected (Step 3 returned NoGpuBackend)
  4.2  Check if any model is currently loaded (GET /api/ps)
  4.3  If model loaded: run AmdApuBackend.verify_live() or
       NvidiaBackend.verify_live() depending on vendor
  4.4  If no model loaded: display "Load a model (ollama run <model>)
       in another terminal, then press R to re-run this step"
  4.5  Display result: GPU OFFLOAD CONFIRMED / GPU OFFLOAD NOT CONFIRMED
       with specific remediation if not confirmed

Step 5 — Hardware profile cache
  5.1  Show current cache contents (.tasker/hardware_profile.json)
       if it exists, or "No cache -- will be written"
  5.2  Run tasker-hardware detect (equivalent -- calls detect_hardware_profile()
       and writes the cache)
  5.3  Confirm cache written and hostname-scoped correctly

Step 6 — Worker registry status
  6.1  Load config/workers/worker_registry.yaml
  6.2  Show registered workers, their protocols, and availability status
       (cross-checked against detected GPU profile per SDD_ADDENDUM_7.5 A.3.4)
  6.3  Flag any workers with tool_protocol: native that may need updating
       (e.g. LFM2.5 models that should be lfm25)
  6.4  Offer to launch the Model Selector (Step 7) to add/update workers

Step 7 — Model selector + agentic readiness (optional, user-initiated)
  See Section B.4
```

### B.3.3 WizardStepResult Data Model

```python
@dataclass
class WizardStepResult:
    step_id: str                       # e.g. "2.3"
    step_name: str                     # e.g. "Ollama service reachability"
    status: StepStatus                 # OK | WARNING | ERROR | SKIPPED
    message: str                       # human-readable result
    detail: str | None                 # extended detail (collapsible in TUI)
    action_required: str | None        # command to run if user action needed
    can_continue: bool                 # False blocks wizard from proceeding

class StepStatus(Enum):
    OK      = "ok"
    WARNING = "warning"
    ERROR   = "error"
    SKIPPED = "skipped"
```

### B.3.4 Re-run Behavior

When the wizard is re-run on an already-configured machine:
- Steps with cached results (hardware profile) show the cached value
  alongside a "Re-detect" option
- Steps that require Ollama to be running re-check live on every run
- GPU verification (Step 4) always re-runs live (never cached)
- The wizard remembers nothing between runs except what is written to
  `.tasker/hardware_profile.json` and `config/workers/worker_registry.yaml`

---

## B.4 Agentic Readiness Checker

### B.4.1 Purpose

The readiness checker answers one question: "Can this specific Ollama model
handle tool-calling as a harness worker?" It does this empirically, not by
trusting Ollama's capability flags (which are wrong for LFM2.5-family models
as established in SDD_ADDENDUM_7.5.md A.2b).

### B.4.2 Model Discovery

The user selects from a list populated by:
1. `ollama list` — models already pulled locally
2. Ollama Cloud models listed in `config/workers/worker_registry.yaml`
   (not yet pulled)
3. Manual entry (user types a model name not in either list)

For un-pulled models, the checker displays the model name and estimated size
(from worker_registry.yaml if registered, otherwise "unknown") and asks the
user to confirm `ollama pull <model>` before testing. It does not auto-pull.

**Cloud-model exception (live-verified, Ollama 0.30.11, Phase 8.2):** the
pull gate applies to LOCAL models only. A signed-in Ollama server serves
`:cloud`-tagged models via `/api/chat` even when they are absent from
`/api/tags` — no pull (and no download) is required, so the checker probes
cloud models directly and reports their absence from the local tag list as
informational, not blocking.

### B.4.3 Readiness Test Protocol

The checker runs a structured 3-round probe against the model:

**Round 1 — Native tool API probe**
  Send a standard Anthropic-format tool call request via `OllamaProvider`
  with `ToolProtocol.NATIVE`. Check whether Ollama returns a `tool_calls[]`
  array in the response (not empty content, not plain text).
  Result: NATIVE_SUPPORTED or NATIVE_REJECTED

**Round 2 — LFM25 probe (if Round 1 failed or was rejected)**
  Send the same request via `ToolCallNormalizer.inject_tools()` with
  `ToolProtocol.LFM25` (injects "List of tools: [json]\nOutput function
  calls as JSON. Respond with ONLY the JSON array...").
  Run `ToolCallNormalizer.extract_tool_calls()` on the response.
  Result: LFM25_SUPPORTED or LFM25_REJECTED

**Round 3 — JSON_EXTRACT probe (if Round 2 failed)**
  Send the request with `ToolProtocol.JSON_EXTRACT` injection.
  Check for extractable JSON tool call in the response.
  Result: JSON_EXTRACT_SUPPORTED or JSON_EXTRACT_REJECTED

The test tool used in all three rounds is a simple, unambiguous function:
```json
{
  "name": "get_current_time",
  "description": "Returns the current time in the specified timezone.",
  "input_schema": {
    "type": "object",
    "properties": {
      "timezone": {
        "type": "string",
        "description": "IANA timezone string e.g. America/Chicago"
      }
    },
    "required": ["timezone"]
  }
}
```
The user prompt is: "What time is it in Chicago?"

This tool is chosen because:
- It is unambiguous (the model cannot answer without calling the tool)
- It has a single required string parameter (tests basic argument parsing)
- It does not require actual execution to test the format

**Probe success criterion (all three rounds):** the round succeeds iff the
extraction path for its protocol yields at least one call whose tool name is
`get_current_time` and whose arguments include a `timezone` key. Anything
else — plain text, empty content, a hallucinated tool, missing required
argument — is a rejection for that round.

### B.4.3a JSON_EXTRACT injection format (defined for Round 3)

Round 3 requires `ToolCallNormalizer.inject_tools()` to actually inject for
`ToolProtocol.JSON_EXTRACT`; before Phase 8.2 that protocol passed messages
through unchanged (no registered worker needed it). Defined now:

- **Injection:** append to the system message (creating one if absent):
  `List of tools: <json>` followed by an instruction to respond with ONLY a
  JSON array of `{"name": ..., "arguments": {...}}` objects, optionally
  inside a ```json fence. Deliberately mirrors the LFM25 injection shape —
  same tool-list serialization, different output-format instruction — so
  the two dialects stay comparable.
- **Extraction:** `_extract_json()` gains a `raw_decode`-based fallback scan
  (same standard-library scanner `_extract_lfm25` already uses) so that
  nested `arguments` objects parse correctly. The pre-existing fenced-block
  and bare-object regex paths are unchanged and tried first; the fallback
  only runs when they fail. Rationale: the prior regexes could not match a
  call whose arguments contained `{}` nesting, which would make Round 3
  reject models that complied exactly with the instruction.

### B.4.4 Readiness Report

```
MODEL READINESS REPORT
──────────────────────────────────────────────────────────────
Model:          lfm2.5-thinking:latest
Pulled locally: YES (1.2B, Q8_0)

ROUND 1 — Native API (tools[])
  Result:   REJECTED (Ollama reports capability: completion only)

ROUND 2 — LFM25 (system prompt injection, JSON output)
  Result:   SUPPORTED
  Response: [{"name": "get_current_time", "arguments": {"timezone": "America/Chicago"}}]
  Parsed:   get_current_time(timezone="America/Chicago") ✓

Recommended protocol:  lfm25
Recommended role:      worker (tool execution)
Suitable as:           WORKER, THINKER (reasoning also confirmed)

WORKER REGISTRY ENTRY
──────────────────────────────────────────────────────────────
  id: lfm2.5-thinking-local
  provider: ollama
  model_id: lfm2.5-thinking:latest
  compute_location: local_hardware
  capabilities: [tool_use, code, reasoning]
  tool_protocol: lfm25
  tool_result_role: tool
  context_window: 128000
  cost_input: 0.0
  cost_output: 0.0
  ollama_usage_level: null
  latency_class: medium
  requires_gpu: false

Write this entry to config/workers/worker_registry.yaml? [Y/n]
```

### B.4.5 ReadinessResult Data Model

```python
@dataclass
class ReadinessResult:
    model_id: str
    ollama_model: str
    pulled_locally: bool

    # Per-round results
    native_result: ProbeResult
    lfm25_result: ProbeResult
    json_extract_result: ProbeResult

    # Final verdict
    supported: bool
    recommended_protocol: ToolProtocol | None
    recommended_capabilities: set[Capability]
    raw_response: str                   # for display in TUI
    parsed_tool_call: dict | None       # what the winning round extracted
    suggested_manifest: WorkerManifest | None

@dataclass
class ProbeResult:
    protocol: ToolProtocol
    attempted: bool
    succeeded: bool
    raw_response: str | None
    parsed: dict | None
    error: str | None
```

---

## B.4.6 Role Assignment in Readiness Report

After the three probe rounds, the readiness checker assigns one or
more recommended roles based on model characteristics, not just tool
capability. A model can hold multiple roles.

Important: Do NOT extend the existing AgentRole enum
(THINKER/WORKER/VERIFIER in tasker/workers/base.py). Those are
orchestration-internal step roles assigned per plan step. The roles
below are a separate concept -- what a model is suited for across
sessions. Add a new WorkerRole enum to tasker/workers/base.py
alongside AgentRole, and add worker_role: list[WorkerRole] as an
optional field on WorkerManifest (defaults to empty list).

WorkerRole values:
  BACKGROUND_AGENT  -- daemon tasks, heartbeat, health monitoring,
                       housekeeping, agentic task spawning from queue,
                       scheduled maintenance. LOCAL models only. Must
                       run continuously without burning cloud API budget
                       or blocking on rate limits.
  EXECUTION_WORKER  -- tool use, code execution, search, file ops.
                       Local preferred, cloud capable.
  REASONING_WORKER  -- complex analysis, code generation, CODE mode.
                       Cloud preferred (CAPABILITY_FIRST routing).
  ORCHESTRATOR      -- planning, synthesis, multi-step delegation.
                       Cloud or large local model.

Role assignment rules applied by ReadinessChecker after probing:
  local + context_window < 32768
    -> [BACKGROUND_AGENT, EXECUTION_WORKER]
  local + context_window >= 32768
    -> [BACKGROUND_AGENT, EXECUTION_WORKER, REASONING_WORKER eligible]
  ollama_cloud or direct_cloud + context_window >= 32768
    -> [REASONING_WORKER, ORCHESTRATOR eligible]
  any location + context_window >= 128000
    -> add ORCHESTRATOR regardless of location
  tool_protocol == lfm25 or json_extract
    -> EXECUTION_WORKER confirmed; ORCHESTRATOR not recommended
       (planning requires reliable structured output across turns)

Add to ReadinessResult: recommended_roles: list[WorkerRole]
Add to WorkerManifest: worker_role: list[WorkerRole] = field(
    default_factory=list)
Add WorkerRole to WorkerManifest.to_dict() / from_dict() serialization.

---

## B.5 TUI Architecture

### B.5.1 Framework: Textual

Textual (https://textual.textualize.io) is the correct choice for this phase:
- Async-native, works directly with `asyncio` (the harness's runtime)
- Full-screen terminal application with CSS-based layout
- Message/event system (`on_button_pressed`, `@on(Button.Pressed, "#tag")`)
  that naturally maps to future Dispatch/Tag-style event integration
- Works on Linux, macOS, and Windows terminal
- No browser or desktop dependency

Add to `pyproject.toml` dependencies: `textual>=0.70.0`

### B.5.2 Screen Structure

```
TuiApp (App)
│
├── WelcomeScreen          ← default/home
│   Status bar: [hardware profile] [active model] [session state]
│   Menu: Setup Wizard | Model Selector | Run Task | View Sessions | Quit
│
├── SetupWizardScreen      ← Phase 8.2
│   Runs wizard steps live, shows status per step
│   Re-runnable: "Re-run All" and "Re-run Step N" buttons
│   GPU guidance panel: shows commands to run if env vars missing
│
├── ModelSelectorScreen    ← Phase 8.3
│   Two-panel: available models (left) | readiness report (right)
│   "Test Model" button launches ReadinessChecker async
│   Progress indicator during test (model inference can be slow)
│   "Add to Registry" button on confirmed compatible model
│
└── HarnessPanel           ← Phase 8.4 (basic in this phase)
    Mode selector (CHAT / CODE / COWORK / RESEARCH / SECURE)
    Task input field
    Output display (streaming)
    Session status (budget, checkpoint if COWORK)
```

### B.5.3 Message Protocol (Textual-Native)

The TUI uses Textual's built-in message system for all internal events.
This is the "Dispatch/Tag style" integration point documented here so the
future web dashboard knows where to hook in:

```python
# Messages emitted by wizard steps -- TUI screens react to these
class WizardStepCompleted(Message):
    result: WizardStepResult

class ReadinessCheckCompleted(Message):
    result: ReadinessResult

class WorkerRegistryUpdated(Message):
    manifest: WorkerManifest

class HarnessTaskCompleted(Message):
    worker_result: WorkerResult
```

Future web dashboard: replace Textual's `.post_message()` with a WebSocket
`broadcast()` using the same message class names as event types. The logic
layer does not change.

### B.5.4 Status Bar (persistent across screens)

A status bar widget visible on all screens displays:

```
[CPU: 4c/32GB] [GPU: NVIDIA GTX 1050 Ti / 4GB] [Tier: 2 / resident]
[Model: lfm2.5-thinking:latest / lfm25] [Session: READY]
```

Updated automatically when:
- Setup wizard completes hardware detection
- A model is confirmed in the model selector
- A harness task starts/completes

---

## B.6 Model-Agnostic Design Principle

Ollama Tasker is model-agnostic. All providers (local Ollama, Ollama
Cloud, Anthropic, OpenAI, Fugu) are first-class. No mode, wizard step,
or TUI screen should assume a specific model or prefer a specific
provider in its logic. Provider preference is expressed through
RoutingPolicy only.

Intended operational model by WorkerRole:

  BACKGROUND_AGENT
    Local models only. Run continuously, autonomously, without user
    initiation. Examples: heartbeat/health monitoring, checkpoint
    maintenance, log rotation, task queue processing, scheduled
    housekeeping. Must not consume cloud API budget or block on rate
    limits. TASKER-P1's lfm2.5-thinking:latest is the reference
    implementation for this role.

  EXECUTION_WORKER
    Local preferred for cost and privacy. Cloud capable when larger
    context or higher capability is needed. RoutingPolicy.HYBRID
    handles the split automatically.

  REASONING_WORKER / CODE mode
    Cloud preferred. Higher-end models (claude-sonnet-4-6,
    nemotron-3-ultra, glm-5.2 via Ollama Cloud, gpt-4o) are the
    intended workers. The harness never hardcodes which cloud model --
    worker registry and routing policy determine it at runtime.

  ORCHESTRATOR
    Cloud or large local. Fugu, Claude, or a large Ollama Cloud model.
    Tier 3-4 orchestrators target this role.

DAEMON as a future sixth mode (not implemented in Phase 8):
  Joins CHAT / CODE / COWORK / RESEARCH / SECURE.
  Always LOCAL_ONLY privacy tier. Always BACKGROUND_AGENT workers.
  Runs on schedule or event trigger, not user initiation.
  Phase 8 TUI must reserve a "Daemon" menu item (visible but
  disabled / "coming soon") so navigation anticipates it without
  implementing it. Do not implement DAEMON mode behavior in Phase 8.

---

## B.7 WSL2 Detection

The wizard must behave correctly on both native Linux and WSL2. Detection:

```python
def is_wsl2() -> bool:
    try:
        version = Path("/proc/version").read_text().lower()
        return "microsoft" in version or "wsl" in version
    except (FileNotFoundError, PermissionError):
        return False
```

WSL2-specific behavior differences:

| Check | Native Linux | WSL2 |
|---|---|---|
| Ollama service status | `systemctl status ollama` + HTTP | HTTP only (systemctl may fail) |
| journalctl for verify | Available | May be unavailable (no systemd) |
| GPU type | nvidia-smi or amdgpu | nvidia-smi (NVIDIA via passthrough); AMD iGPU passthrough limited |
| Ollama serve needed | Optional (systemd) | Usually: `ollama serve` in background terminal |

---

## B.8 Phase 8 Roadmap

| Sub-phase | Description | Entry point |
|---|---|---|
| 8.1 | Setup wizard headless logic (wizard.py, all 7 steps) + CLI (`tasker-setup`) | `tasker-setup` |
| 8.2 | Agentic readiness checker (readiness.py) + CLI probe mode | `tasker-setup --check-model <name>` |
| 8.3 | Textual TUI skeleton (TuiApp, WelcomeScreen, status bar, SetupWizardScreen) | `tasker` |
| 8.4 | ModelSelectorScreen wired to readiness checker | `tasker` → Model Selector |
| 8.5 | HarnessPanel (mode select, task input, output display, session status) | `tasker` → Run Task |

Each sub-phase must have passing unit tests before the next begins.
Sub-phases 8.3–8.5 require manual TUI verification (screenshot or
session transcript) in addition to unit tests, since Textual rendering
cannot be fully tested without a terminal.

---

## B.9 New File Structure

```
ollama-tasker/
│
├── tasker/
│   ├── setup/                      ← NEW (Phase 8.1, 8.2)
│   │   ├── __init__.py
│   │   ├── wizard.py               ← WizardStep, WizardStepResult, run_wizard()
│   │   ├── readiness.py            ← ReadinessChecker, ReadinessResult, ProbeResult
│   │   └── environment.py          ← is_wsl2(), check_python(), check_ollama()
│   │
│   └── tui/                        ← NEW (Phase 8.3-8.5)
│       ├── __init__.py
│       ├── app.py                  ← TuiApp, main()
│       ├── screens/
│       │   ├── __init__.py
│       │   ├── welcome.py          ← WelcomeScreen
│       │   ├── setup_wizard.py     ← SetupWizardScreen
│       │   ├── model_selector.py   ← ModelSelectorScreen
│       │   └── harness_panel.py    ← HarnessPanel (Phase 8.5)
│       └── widgets/
│           ├── __init__.py
│           ├── status_bar.py       ← persistent HardwareStatusBar
│           ├── step_row.py         ← WizardStepRow (one row per step)
│           └── readiness_panel.py  ← ReadinessReportPanel
│
├── cli/
│   └── shell.py                    ← unchanged (now `tasker-cli`)
│
└── tests/
    ├── unit/
    │   ├── test_setup_wizard.py    ← Phase 8.1 tests
    │   ├── test_readiness.py       ← Phase 8.2 tests
    │   └── test_environment.py     ← WSL2 detection, Ollama checks
    └── (integration tests deferred -- TUI requires terminal)
```

---

## B.10 Testing Strategy

The headless wizard and readiness checker are fully unit-testable with mocks.
The TUI screens are tested manually (Textual does provide a `Pilot` test
driver for automated UI testing, but it requires a real terminal environment
and is deferred to after Phase 8.5).

**Unit test coverage targets:**

| Module | What to mock | Key cases |
|---|---|---|
| `environment.py` | `/proc/version`, `shutil.which`, `subprocess.run` | is_wsl2 True/False, Ollama found/not found, service reachable/not |
| `wizard.py` | All environment checks, `detect_hardware_profile()` | Each step OK / WARNING / ERROR; re-run idempotency |
| `readiness.py` | `OllamaProvider.execute()`, `ToolCallNormalizer` | All 3 rounds; first-round success skips remaining; all rejected; partial |

No live Ollama calls in unit tests. Live readiness testing is a manual
smoke test step at the end of Phase 8.2, mirroring the pattern established
in Phases 7.5.3 and 7.5.4.

---

## B.11 Checklist Additions (`docs/TASKER_CHECKLIST.md`)

```
## Phase 8 -- Setup Wizard, Readiness Checker, TUI

### Phase 8.1 -- Setup Wizard (headless)
- [ ] tasker/setup/environment.py (is_wsl2, check_python, check_ollama)
- [ ] tasker/setup/wizard.py (WizardStepResult, all 7 steps, run_wizard())
- [ ] tasker-setup CLI entry point (headless, prints step results)
- [ ] tests/unit/test_environment.py passing
- [ ] tests/unit/test_setup_wizard.py passing
- [ ] Live headless run on TASKER-P1 (native Linux or WSL2)
- [ ] Live headless run on Designlab1

### Phase 8.2 -- Agentic Readiness Checker
- [ ] tasker/setup/readiness.py (ProbeResult, ReadinessResult,
      ReadinessChecker)
- [ ] All 3 probe rounds implemented (NATIVE, LFM25, JSON_EXTRACT)
- [ ] Suggested WorkerManifest generation on success
- [ ] Worker registry write on user confirmation
- [ ] tasker-setup --check-model <name> CLI command
- [ ] tests/unit/test_readiness.py passing
- [ ] Live smoke test: lfm2.5-thinking:latest -> confirmed lfm25 protocol
- [ ] Live smoke test: a cloud model via Ollama -> confirmed native or other

### Phase 8.3 -- TUI Foundation
- [ ] textual added to pyproject.toml dependencies
- [ ] tasker/tui/app.py (TuiApp, main())
- [ ] tasker/tui/screens/welcome.py (WelcomeScreen, main menu)
- [ ] tasker/tui/widgets/status_bar.py (HardwareStatusBar)
- [ ] tasker entry point changed to tui/app.py:main
- [ ] tasker-cli entry point added for existing CLI
- [ ] Manual verification: `tasker` launches TUI on Designlab1
- [ ] Manual verification: `tasker` launches TUI on TASKER-P1 (or WSL2)

### Phase 8.4 -- SetupWizardScreen + ModelSelectorScreen
- [ ] tasker/tui/screens/setup_wizard.py (SetupWizardScreen)
- [ ] tasker/tui/widgets/step_row.py (WizardStepRow)
- [ ] tasker/tui/screens/model_selector.py (ModelSelectorScreen)
- [ ] tasker/tui/widgets/readiness_panel.py (ReadinessReportPanel)
- [ ] Textual message bus wired (WizardStepCompleted,
      ReadinessCheckCompleted, WorkerRegistryUpdated)
- [ ] Manual verification: full setup wizard runs through TUI
- [ ] Manual verification: model test + registry write through TUI

### Phase 8.5 -- HarnessPanel (basic)
- [ ] tasker/tui/screens/harness_panel.py
- [ ] Mode selector widget
- [ ] Task input + async execution
- [ ] Output streaming display
- [ ] Session status (budget, checkpoint indicator for COWORK)
- [ ] Manual verification: CHAT task through TUI
- [ ] Manual verification: COWORK task with checkpoint through TUI
```

---

*This addendum should be added to docs/ as SDD_ADDENDUM_PHASE8.md and
referenced in CLAUDE.md alongside SDD_ADDENDUM_7.5.md. Merge into SDD.md
proper once all Phase 8 sub-phases are verified.*

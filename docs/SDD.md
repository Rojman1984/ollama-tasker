# Ollama Tasker — Software Design Document

**Version:** 0.1.0-draft  
**Status:** Draft  
**Author:** Roland Ortiz / Real Truth AI  
**Date:** 2026-06-29  

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [System Overview](#2-system-overview)
3. [Design Constraints](#3-design-constraints)
4. [Architecture](#4-architecture)
5. [Component Specifications](#5-component-specifications)
6. [Data Models](#6-data-models)
7. [Interface Contracts](#7-interface-contracts)
8. [Configuration System](#8-configuration-system)
9. [Session Lifecycle](#9-session-lifecycle)
10. [Error Handling and Resilience](#10-error-handling-and-resilience)
11. [Security and Privacy](#11-security-and-privacy)
12. [Testing Strategy](#12-testing-strategy)
13. [Development Roadmap](#13-development-roadmap)
14. [Glossary](#14-glossary)
15. [References](#15-references)

---

## 1. Introduction

### 1.1 Purpose

This Software Design Document (SDD) specifies the architecture, components, interfaces, and data models for the **Ollama Tasker** — a provider-agnostic, hardware-aware multi-agent orchestration system for tool-capable language models. It serves as the authoritative design reference for all implementation work.

### 1.2 Scope

The Ollama Tasker is a standalone Python system that:

- Abstracts local (Ollama) and cloud (Anthropic, OpenAI, Fugu, Ollama Cloud) model providers behind a unified worker interface.
- Provides a swappable orchestrator tier system that scales from rule-based execution on minimal hardware to full multi-agent coordination on capable hardware.
- Implements five interaction modes emulating Claude Code and Claude Cowork behavior patterns.
- Manages Ollama Cloud concurrency slots, session budget windows, and graceful pause/resume lifecycle.
- Enforces privacy tiers that prevent sensitive data from leaving local hardware.

The Ollama Tasker is **not** part of the HomeWatch/Ztripes product line. It is an independent project under the Real Truth AI initiative.

### 1.3 Intended Audience

- Primary developer: Roland Ortiz
- Future contributors to the Real Truth AI project
- Reviewers evaluating architectural decisions

### 1.4 Definitions and Acronyms

| Term | Definition |
|------|------------|
| SDD | Software Design Document |
| MCP | Model Context Protocol |
| TRINITY | Thinker/Worker/Verifier multi-agent coordination pattern (Sakana AI ICLR 2026) |
| Ollama Cloud | Cloud inference hosted by Ollama Inc., accessed via the same local API endpoint |
| Worker | Any tool-capable model instance registered in the harness |
| Orchestrator | The component responsible for task planning, role assignment, and synthesis |
| Classifier | Lightweight intake component that routes tasks by type and complexity |
| Mode | A named pre-configuration of orchestrator tier, tool bundle, routing policy, and interaction pattern |
| Hardware Profile | YAML configuration describing available compute and corresponding orchestrator tier |
| Privacy Tier | A classification of data sensitivity that constrains which compute locations are permitted |
| Checkpoint | A serialized snapshot of execution state enabling pause and resume |
| Session Budget | Ollama Cloud's usage tracking window (5-hour reset, plan-based limits) |
| LFM | Liquid Foundation Model (primary local worker model) |

---

## 2. System Overview

### 2.1 Product Perspective

The Ollama Tasker addresses a gap not covered by existing tools: a unified orchestration layer that treats local Ollama models, Ollama Cloud models, and direct cloud APIs (Anthropic, OpenAI, Fugu) as interchangeable workers behind a common interface, with hardware-aware orchestration tiers that degrade gracefully on low-end hardware and scale automatically on better hardware.

It draws design inspiration from:

- **Claude Code** — agentic coding mode with file system and shell tool integration
- **Claude Cowork** — long-horizon async task execution with checkpointing
- **Sakana AI Fugu** — learned multi-agent coordination (TRINITY pattern: Thinker/Worker/Verifier roles; Conductor: RL-trained natural language coordination)
- **Parity Project** — Python runtime that mirrors the Claude Code npm runtime, providing a proven foundation for core agent loop, session management, and tool execution

### 2.2 Primary Functions

- Multi-provider worker pool management
- Task classification and intelligent routing
- Swappable orchestrator tiers (Tier 0–4)
- Five operating modes: CHAT, CODE, COWORK, RESEARCH, SECURE
- Ollama concurrency and session budget management with pause/resume
- Privacy-tier enforcement (LOCAL_ONLY, OLLAMA_CLOUD_OK, ANY_CLOUD)
- Tool call protocol normalization across model families
- Checkpoint-driven long-horizon task execution
- CLI shell with slash command interface

### 2.3 User Characteristics

Primary user is an IT systems analyst and generative AI engineering student operating on mixed hardware (Ryzen 5 mini PC, Ryzen 5/7 desktop with discrete GPU). The system must be operational and useful at minimum hardware configuration and progressively more capable as hardware improves.

### 2.4 Operating Environment

| Machine | Role | Constraints |
|---------|------|-------------|
| TASKER-P1 (Ryzen 5 3500U, 32GB, no GPU) | Primary agent host | CPU-only inference, 1 model at a time |
| Designlab1 (Ryzen 5/7, 32GB, GTX 1050 Ti 4GB) | Secondary host | GPU-accelerated inference, parallel workers possible |
| Ollama Cloud | Remote compute | Concurrency limits, 5-hour session windows |
| Anthropic API | Remote cloud | Token-based billing |
| OpenAI API | Remote cloud | Token-based billing |
| Sakana Fugu | Remote cloud | Per-token billing, proprietary agent pool |

---

## 3. Design Constraints

### 3.1 Ollama Cloud Constraints

These constraints directly shape the architecture and must be respected at the infrastructure level:

| Constraint | Value | Architectural Response |
|------------|-------|------------------------|
| Concurrency (Free plan) | 1 simultaneous model | Sequential-only orchestration |
| Concurrency (Pro plan) | 3 simultaneous models | Limited parallel: orchestrator + 2 workers |
| Concurrency (Max plan) | 10 simultaneous models | Full parallel TRINITY execution |
| Session window | 5-hour rolling reset | SessionBudget tracks usage; triggers pause at 100% |
| Warning threshold | 90% of plan limit | Routing shifts to local-biased at 90% |
| Queue full behavior | Reject (not queue) | Immediate fallback, never block caller |
| Usage unit | GPU-time × model level (1–4) | WorkerManifest.ollama_usage_level informs cost estimation |
| Privacy | No logging, no training, zero retention | Permits OLLAMA_CLOUD_OK privacy tier |

### 3.2 Hardware Constraints

- TASKER-P1: Sequential model loading only (RAM constraint). Peak RAM = one model at a time.
- Designlab1 GTX 1050 Ti: 4GB VRAM limits simultaneous GPU-resident model size.
- Local inference is always unlimited by plan; billing and concurrency constraints apply only to Ollama Cloud.

### 3.3 Functional Constraints

- Only tool-capable models are eligible for the worker pool. Models without tool support are excluded at registration time.
- The Ollama Tasker is architecturally independent of HomeWatch, Ztripes, and any Ztripes infrastructure. No shared code, notifiers, or data paths.
- The harness presents an OpenAI-compatible API surface to external callers.
- Privacy tier LOCAL_ONLY is a hard block — cloud calls in this mode must throw, not fall back silently.

### 3.4 Design Principles

- **Separation of concerns:** Mode configures the stack; orchestrator plans; workers execute; harness normalizes.
- **Orchestrator transparency:** The orchestrator never knows which provider a worker uses — it sees only WorkerManifest and WorkerResult.
- **Single model at a time on low-end hardware:** Sequential load strategy avoids OOM on TASKER-P1.
- **Graceful degradation:** Every component has a fallback path. Pause before fail.
- **Verification over trust:** Hardware profiles, privacy tiers, and concurrency slots are enforced mechanically, not by convention.

---

## 4. Architecture

### 4.1 Layered Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  INTERFACE LAYER                                                │
│  CLI Shell (slash commands) │ OpenAI-compat API endpoint        │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  MODE LAYER                                                     │
│  ModeConfigurator → TaskerMode                                 │
│  CHAT │ CODE │ COWORK │ RESEARCH │ SECURE                       │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  ORCHESTRATION LAYER                                            │
│  Classifier → Orchestrator (Tier 0–4)                           │
│  plan() │ synthesize() │ should_retry()                         │
└──────────┬──────────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────────┐
│  SESSION LAYER                                                  │
│  SessionManager │ CheckpointStore │ OllamaSessionBudget         │
│  OllamaCloudConcurrencyManager │ Notifier                       │
└──────────┬──────────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────────┐
│  WORKER LAYER                                                   │
│  WorkerRegistry │ WorkerSelector │ RoutingPolicy                │
│  PrivacyTier enforcement                                        │
└──────────┬──────────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────────┐
│  PROVIDER LAYER                                                 │
│  OllamaProvider (local + cloud) │ AnthropicProvider             │
│  OpenAIProvider │ FuguProvider                                  │
└──────────┬──────────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────────┐
│  NORMALIZATION LAYER                                            │
│  ToolCallNormalizer │ ResponseNormalizer │ PromptNormalizer      │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Component Interaction — Request Flow

```
User input
    │
    ▼
[CLI / API Interface]
    │
    ▼
[ModeConfigurator]
  loads HardwareProfile × TaskerMode → ExecutionConfig
    │
    ▼
[Classifier]
  task_type, complexity_score, required_capabilities
    │
    ▼
[SessionManager.tick()]
  check SessionState → RUNNING / THROTTLING / PAUSED
    │ (RUNNING or THROTTLING)
    ▼
[Orchestrator.plan()]
  produces ExecutionPlan with ordered Steps and RoleAssignments
    │
    ▼  (for each step)
[WorkerSelector.select()]
  privacy check → concurrency check → budget check → capability filter → policy rank
    │
    ▼
[Provider.execute()]
  PromptNormalizer → model call → ToolCallNormalizer → ResponseNormalizer
    │
    ▼
[Orchestrator.synthesize()]
  merges WorkerResults → final response
    │
    ▼
Output stream / Checkpoint
```

### 4.3 Foundation Layer

The harness is built on top of the proven Python runtime from the Parity Project. Core modules adopted as-is:

| Parity Module | Harness Role |
|---------------|--------------|
| `agent_runtime.py` | Core agent loop backbone |
| `query_engine.py` | Execution facade |
| `openai_compat.py` | Transport layer |
| `session_store.py` | Checkpoint persistence backend |
| `plan_runtime.py` | Execution plan management |
| `task_runtime.py` | Task state tracking |
| `agent_manager.py` | Nested agent lineage tracking |
| `compact.py` / `microcompact.py` | Context window management |
| `hook_policy.py` | Policy enforcement (SECURE mode) |
| `mcp_runtime.py` | MCP tool integration |
| `bash_security.py` | CODE mode tool safety |
| `agent_slash_commands.py` | CLI shell slash commands |

New modules unique to the harness are listed in Section 5.

---

## 5. Component Specifications

### 5.1 ModeConfigurator

**Responsibility:** Combines a HardwareProfile and a TaskerMode into a resolved ExecutionConfig that governs all downstream components.

**Inputs:** Hardware profile YAML path, mode name string  
**Outputs:** ExecutionConfig  
**Location:** `tasker/modes/configurator.py`

**Behavior:**

- Reads hardware profile YAML to determine available orchestrator tier and concurrent slot count.
- Merges mode defaults with hardware constraints.
- Applies plan-level mode constraint overrides (e.g., Free plan forces `sequential_only` in COWORK mode).
- Validates that the resolved config is internally consistent before returning.

**Mode Definitions:**

| Mode | Orchestrator Tier | Tool Bundle | Routing Policy | Interaction | Memory Scope |
|------|------------------|-------------|----------------|-------------|--------------|
| CHAT | 0 (rule-based) or 1 | search, calculator, memory_read | COST_OPTIMIZED | sync stream | session |
| CODE | 1 (single LLM) | bash, file_read, file_write, git, linter, test_runner, code_search | CAPABILITY_FIRST | CLI/REPL + diffs | project-aware |
| COWORK | 2–4 (dual/reasoning/cloud) | ALL + checkpoint_write, task_state, progress_report | HYBRID | async + checkpoints | project + episodic |
| RESEARCH | 2+ | web_search, retrieve, pdf_extract, citation_tracker | CAPABILITY_FIRST, long-ctx preferred | async + section streaming | research session |
| SECURE | 0–1 (local only) | file ops, local search, local memory (no web) | PRIVATE (hard block) | mirrors base mode | local filesystem only |

---

### 5.1a RESEARCH Mode Grounding Contract

**Status:** Added after a live bug report (Roland): a RESEARCH-mode task
fabricated an entire model comparison, including an invented benchmark
statistic, with **zero tool calls**. Root cause, confirmed by code
audit: `WEB_SEARCH`/`RETRIEVE`/`PDF_EXTRACT`/`CITATION_TRACKER`/
`CONTRADICTION_DETECTOR` had schema definitions but (a) no execution
implementation at all in `tasker/tools/executor.py` (calling any of them
always errored "no execution implementation configured"), and (b) no
`_TOOL_KEYWORDS` entry in `tasker/tools/bundles.py`, so
`narrow_bundle_to_step()` narrowed *every* research step to an **empty**
tool set regardless of content — the model could never have called these
tools even if it had tried. Both are now fixed (5.1a.1), but grounding
also needed enforcement beyond "the tool now works if invoked" — a model
that never calls it produces the same fabrication either way.

**Rule:** RESEARCH mode is the one mode with an explicit **grounding
requirement**, enforced across four points, not merely hoped-for via
prompt wording:

1. **Tool executors are real.** `WEB_SEARCH` calls the Brave Search API
   (`BRAVE_API_KEY` env var, never hardcoded); `RETRIEVE` fetches a URL
   and strips it to text. Both return structured output carrying real
   source URLs (`{"query", "results": [{"title","url","snippet"}]}` /
   `{"url", "content"}`) — see `tasker/tools/executor.py`. `PDF_EXTRACT`/
   `CITATION_TRACKER`/`CONTRADICTION_DETECTOR` remain schema-only
   (out of scope this pass — `WEB_SEARCH`+`RETRIEVE` alone already carry
   the URLs synthesis needs to cite); calling one still returns the
   existing "no execution implementation configured" error, now
   correctly scoped to only those three rather than all five.
   `narrow_bundle_to_step()` gained keyword groups for all five, so a
   research step can actually be offered these tools in the first place
   (5.1a.1's root-cause fix).

2. **Plans must include a retrieval step.** After `orchestrator.plan()`
   returns (any tier), `tasker/runtime/dispatch.py`'s
   `_enforce_research_grounding()` checks whether any step's
   `required_capabilities` includes `Capability.SEARCH`. If not — and a
   search backend is actually configured (see point 4) — a retrieval
   step is prepended: `"Search for and retrieve real, current sources
   relevant to: <task>"`, `required_capabilities={TOOL_USE, SEARCH}`,
   and every other step's index/`depends_on` shifts by one. This is a
   code-level backstop, not just prompt engineering — a plan is
   corrected even if the model ignored the planning prompt's own
   grounding instructions (below).

3. **Worker prompts and plans are told not to fabricate.**
   `build_plan_prompt()`/`build_synthesize_prompt()`
   (`tasker/orchestrator/_parse.py`) accept an optional `mode_name`; when
   `"research"`, both append an explicit grounding block: the plan
   prompt requires step descriptions to describe *actions* ("search for
   X"), never assert factual conclusions or invented statistics
   themselves (the second root cause Roland found — the step
   description itself contained fabricated claims); the synthesize
   prompt requires every factual claim to cite a real URL from the
   worker outputs, and requires stating explicitly what wasn't found
   rather than filling the gap. All four orchestrator tiers
   (`tier1_single.py`…`tier4_cloud.py`) accept an optional `mode_name`
   constructor parameter, threaded in by `factory.py`'s
   `build_orchestrator()` from `config.mode.name`, and pass it through to
   both prompt builders.

4. **Zero-retrieval factual output is marked, never presented as fact.**
   `tasker/tools/honesty.py`'s `check_research_grounding()` — a sibling
   of the side-effect honesty guard, same "never silently pass through
   an unverifiable claim" philosophy — prefixes a step's output (and
   separately, the final synthesized answer) with `[unverified -- no
   sources retrieved]` when `mode_name == "research"` and no
   `web_search`/`retrieve` tool call occurred anywhere in that
   output's provenance. Wired into `_execute_steps()` (per step) and
   `_run_task()` (final synthesis, checked against the union of every
   step's tool calls).

**No search backend configured:** rather than silently producing
ungrounded (and now honesty-guard-flagged) output, entering RESEARCH
mode announces the gap up front. `cli/shell.py`'s `/mode research` (and
the one-shot `--mode research` CLI path) prints a warning when
`BRAVE_API_KEY` is unset: research tasks will proceed but any factual
claims will carry the `[unverified]` marker. This is advisory, not a
hard block — SECURE mode's `LOCAL_ONLY` privacy tier already covers the
"must not reach the network" case; RESEARCH without a key is a degraded
but still honest mode, not a disabled one.

---

### 5.2 Classifier

**Responsibility:** Lightweight intake routing. Produces a ClassifierResult that seeds orchestrator planning.

**Inputs:** Raw task string, active TaskerMode  
**Outputs:** ClassifierResult  
**Location:** `tasker/classifier/`

**Classifier Providers:**

| Provider | When Used | Cost |
|----------|-----------|------|
| `RuleBasedClassifier` | Free plan, TASKER-P1 under pressure | Zero (no model) |
| `LocalLLMClassifier` | Pro/Max plan, Designlab1 | Small local model call |
| `OrchestratorClassifier` | Ambiguous tasks, escalation path | Orchestrator model call |

**ClassifierResult fields:**
- `task_type`: CODING, RESEARCH, REASONING, TOOL_EXECUTION, CONVERSATIONAL
- `complexity_score`: 0.0–1.0
- `required_capabilities`: set[Capability]
- `suggested_workers`: list[str] (worker IDs, optional hint)
- `estimated_duration_s`: float

---

### 5.3 Orchestrator (Tiered)

**Responsibility:** Decomposes tasks into ordered steps, assigns roles, manages the feedback loop, and synthesizes results. Never executes tools directly.

**Location:** `tasker/orchestrator/`

**Tier Ladder:**

| Tier | Class | Orchestrator Model | When Active |
|------|-------|--------------------|-------------|
| 0 | `NanoOrchestrator` | None (rule-based templates) | TASKER-P1 under pressure, Free plan |
| 1 | `SingleLLMOrchestrator` | qwen3:1.7b or llama3.2:3b | TASKER-P1 normal, sequential |
| 2 | `DualLLMOrchestrator` | Planner: qwen3:7b, Synthesizer: qwen3:4b | Designlab1 (GPU) |
| 3 | `ReasoningOrchestrator` | Full reasoning model resident | GPU server or future upgrade |
| 4 | `CloudOrchestrator` | Ollama Cloud model / Fugu / Claude / OpenAI | Hybrid: cloud orchestrator, local workers |

**Tier 4 activation (added for COWORK_PROMPT task 8.2):** Tier 4 is an
explicit configuration opt-in, never a hardware-detection outcome. Because the
Tier 4 orchestrator model runs remotely, the local hardware ceiling that
justifies `tier_max` 0–3 does not physically constrain it — but the resolution
rule stays uniform: `effective_tier = min(mode.orchestrator_tier_max,
profile.orchestrator_tier_max)`. To reach Tier 4 a hardware profile must
declare `orchestrator.tier_max: 4` **and** route the orchestrator model to the
cloud (`orchestrator.compute_location: ollama_cloud` in the current
Ollama-Cloud-first phase; direct-cloud providers once they are wired into the
CLI provider map). A tier ≥ 4 request whose orchestrator compute location is
local degrades to Tier 3 per the Section 10.3 chain. COWORK is the only mode
that may rise to Tier 4 (`orchestrator_tier_max: 4`); the standard machine
profiles (`tier1_tasker`, `tier2_designlab`) deliberately stay capped at 1/2,
so Tier 4 is reached only via a purpose-built profile such as
`config/profiles/tier4_cloud_hybrid.yaml`.

**TRINITY Role Assignments (Tiers 2+):**

| Role | Responsibility |
|------|---------------|
| Thinker | Reasons about the problem space, identifies approach |
| Worker | Executes tool calls, writes code, retrieves data |
| Verifier | Validates Worker output, checks correctness, flags retry |

**Load Strategy per Tier:**

| Tier | Strategy | RAM Behavior |
|------|----------|--------------|
| 0–1 (TASKER-P1) | Sequential: load → plan → unload → worker runs | Peak = 1 model at a time |
| 2 (Designlab1) | Resident planner: stays loaded, workers hot-swap | Peak = planner + 1 worker |
| 3–4 | Concurrent: all roles may load simultaneously | Peak = N models |

---

### 5.3a CHAT Mode Direct Dispatch

**Status:** Added after a live bug report (Roland's cowork/chat test
session): a CHAT-mode "Hello" was routed through the full orchestrator
pipeline (`plan()` → step dispatch → `synthesize()`) like every other
mode. Three problems observed live: (1) the worker's instruction was the
*planner's generated step description* ("Processing available
workers..."), not the user's actual message — a pure hallucination
artifact of round-tripping a one-line greeting through a JSON planning
call; (2) three sequential LLM calls (plan, worker turn, synthesize) took
~56s to first response for what should be an instant reply; (3) CHAT's
multi-turn nature (a REPL conversation) had no representation in the
pipeline at all — every turn was dispatched as an independent, context-
free task.

**Rule:** CHAT mode never calls `OrchestratorBase.plan()` or
`synthesize()`. It is the one mode that bypasses the orchestrator tier
entirely — a single direct call to a chat worker via the same
`run_tool_loop()` machinery every other mode's step dispatch uses, with
the user's raw message as `WorkerTask.instruction` and the running REPL
conversation as `WorkerTask.context["messages"]`. CODE, COWORK, RESEARCH,
and SECURE are unaffected — they still plan/execute-steps/synthesize as
before; this bypass is CHAT-specific because CHAT is the only mode
defined as a single-turn conversational exchange with no multi-step
decomposition to plan in the first place (see 5.1's Mode Definitions
table: CHAT's own tier is 0/1, meaning even its "orchestrator" is either
no model at all or a single small model — round-tripping through it to
plan a one-step "answer the question" plan was pure overhead).

**Conversation history:** owned by the REPL session (`cli/shell.py`'s
`_repl()`), not by any persisted session/checkpoint state — a chat
history list accumulates `{"role": "user"|"assistant", "content": ...}`
turns across the interactive session and is passed to the worker every
turn via `WorkerTask.context["messages"]`, matching the existing
non-chat convention (`_build_messages()` in
`tasker/workers/providers/ollama.py` already prefers `context["messages"]`
over re-appending `instruction` when history is present — chat dispatch
needed no provider changes). History is in-memory only, cleared when the
REPL process exits; SDD 9's checkpoint/resume machinery is a COWORK-mode
concern and does not apply here — a chat turn is never checkpointed or
paused mid-flight.

**Worker selection:** default is the always-loaded local worker
(`lfm2.5-local`) so a plain greeting never needs a cold model load or a
cloud call. Two REPL levers redirect it, both scoped to the current
session only (not persisted):
  - `/model <worker_id>` — pin an exact worker by registry id. Always
    wins over the default and over `/effort`.
  - `/effort <low|med|high>` — when no `/model` is pinned, `med` (the
    REPL default) keeps the always-loaded local default; `low` re-selects
    via `RoutingPolicy.SPEED_OPTIMIZED`, `high` via
    `RoutingPolicy.CAPABILITY_FIRST` — reusing `WorkerSelector`'s
    existing ranking logic rather than hardcoding a specific "stronger"
    model id, so it stays correct as the worker registry changes.
    `high` may select a cloud worker if one ranks highest by capability
    score; this is intentional (the whole point of the lever is letting
    the user redirect to a stronger model), not a bug — a user choosing
    `/effort high` is choosing to potentially spend cloud budget.

Both are shown in `/status`. See Section 7.6 for the exact REPL command
syntax.

---

### 5.4 Worker Registry

**Responsibility:** Maintains the catalog of all registered workers. Supports capability filtering, liveness checks, and manifest serialization.

**Location:** `tasker/workers/registry.py`

**Key Operations:**

- `register(manifest: WorkerManifest)` — adds a worker to the registry
- `deregister(worker_id: str)` — removes a worker
- `filter(capabilities: set[Capability]) -> list[WorkerManifest]` — capability query
- `health_check(worker_id: str) -> bool` — liveness probe
- `list_all() -> list[WorkerManifest]` — full registry dump

---

### 5.5 Worker Selector

**Responsibility:** Given required capabilities and a routing policy, selects the optimal worker. Applies privacy enforcement, concurrency checks, and session budget throttling before capability ranking.

**Location:** `tasker/workers/registry.py`

**Selection Decision Tree:**

```
required_capabilities + RoutingPolicy
    │
    ├─ [Privacy check]
    │   LOCAL_ONLY → filter to local_hardware only (hard block)
    │   OLLAMA_CLOUD_OK → permit local + ollama_cloud, block direct_cloud
    │   ANY_CLOUD → all locations permitted
    │
    ├─ [Concurrency check]
    │   ollama_cloud_slots_available == 0 → exclude OLLAMA_CLOUD candidates
    │
    ├─ [Budget check]
    │   should_throttle → penalize OLLAMA_CLOUD usage_level 3 and 4
    │
    ├─ [Capability filter]
    │   filter candidates by required_capabilities
    │
    └─ [Policy rank]
        COST_OPTIMIZED   → LOCAL → OLLAMA_CLOUD_L1 → OLLAMA_CLOUD_L2 → DIRECT_CLOUD
        CAPABILITY_FIRST → rank by capability_score (model benchmark data)
        SPEED_OPTIMIZED  → rank by latency_class (FAST < MEDIUM < SLOW)
        HYBRID           → local for tool execution, cloud for reasoning steps
        PRIVATE          → LOCAL_HARDWARE only (same as LOCAL_ONLY tier)
```

---

### 5.6 Providers

All providers implement `WorkerProviderBase`. The harness never calls provider-specific APIs directly — all access is through the provider abstraction.

**Location:** `tasker/workers/providers/`

#### 5.6.1 OllamaProvider

Handles both `LOCAL_HARDWARE` and `OLLAMA_CLOUD` compute locations. The Ollama API endpoint is the same for both; `compute_location` in the manifest distinguishes them for routing and concurrency management.

- Acquires a concurrency slot before every OLLAMA_CLOUD call
- Returns `WorkerResult(status=DEFERRED)` immediately if no slot available (never blocks)
- Raises `OllamaQueueFullError` on HTTP 429; harness catches and triggers fallback

#### 5.6.1a Context Window Control (`num_ctx`)

**Status:** Added after live REPL/TUI UX testing found `num_ctx` was
never sent at all — Ollama silently applied its own server default
(observed live: 4096), regardless of a worker's declared
`context_window`, sometimes far below it.

`OllamaProvider.execute()` now always sends `options.num_ctx`, resolved
by `resolve_num_ctx(worker, gpu)`:

- **Precedence:** `WorkerTask.context["num_ctx_override"]` (the REPL's
  `/context <tokens>` lever) always wins when set.
- **Cloud workers** (any `compute_location` other than
  `LOCAL_HARDWARE`) are exempt from any ceiling — always use the
  manifest's full `context_window`. There's no local GPU constraint to
  reason about for a remote model.
- **Local workers** are capped to what the resolved `GPUInfo`'s
  remaining VRAM (after the worker's own declared `vram_mb`) is
  estimated to fit, via a deliberately rough
  bytes-per-context-token constant — *not* a precise memory model, just
  enough to avoid requesting a context window that cannot possibly fit
  and OOM mid-response. With no GPU data available (no cache, or the
  cache reports no `memory_mb`), the manifest's value is used as-is —
  no cap without a basis for one. The same unified-memory reserve as
  `WorkerRegistry.apply_gpu_availability()` (`SDD_ADDENDUM_7.5.md`
  A.3.4) is applied before capping.
- **GPU data source:** the same machine-local hardware-detection cache
  every other GPU-aware code path uses
  (`tasker.config.detect.load_cached_gpu_info()`) — read once at
  provider construction (`_build_pipeline()` in
  `tasker/runtime/dispatch.py`), never a live subprocess call per
  request. `OllamaProvider` itself never auto-loads this — its
  constructor takes an optional `gpu: GPUInfo | None` so the provider
  stays fully deterministic in tests; production wiring supplies the
  real cached value.

`resolve_num_ctx()` returns `(num_ctx, capped)` — `capped` is a "fits in
VRAM" hint surfaced in the REPL's `/models` listing (Section 7.6) for
local workers whose full manifest `context_window` doesn't fit.

#### 5.6.2 AnthropicProvider

Wraps the Anthropic Messages API. Uses native tool_calls protocol. Handles streaming and non-streaming responses uniformly.

#### 5.6.3 OpenAIProvider

Wraps the OpenAI Chat Completions API. Native tool_calls protocol. Response format identical to Anthropic after normalization.

#### 5.6.4 FuguProvider

Wraps the Sakana Fugu OpenAI-compatible endpoint (via OpenRouter or direct). Fugu is registered with `Capability.MULTI_AGENT` — when assigned a subtask, it internally orchestrates its own agent pool and returns a synthesized result. The harness treats it as an opaque, high-quality, slow worker.

---

### 5.7 Tool Normalizer

**Responsibility:** Translates tool call outputs from model-specific formats into the standard WorkerToolResult format. Also translates tool definitions into the format each model expects on input.

**Location:** `tasker/tools/normalizer.py`

**Protocols Supported:**

| Protocol | Description | Models |
|----------|-------------|--------|
| `NATIVE` | Standard `tool_calls[]` in response | Most modern models |
| `JSON_EXTRACT` | Tool call embedded in JSON text block | Some Mistral variants |
| `XML_EXTRACT` | Tool call in `<tool_call>` XML tags | Some older models |
| `FEW_SHOT` | No native support; few-shot examples injected | Zero-shot models |

**Normalization Contract:** Regardless of input protocol, output is always:

```python
@dataclass
class WorkerToolResult:
    tool_name: str
    tool_input: dict
    tool_output: str | dict | None
    error: str | None
    duration_ms: int
```

---

### 5.7a Multi-turn Tool Loop and Tool Executor

**Status:** Added mid-project, after ToolCallNormalizer (5.7) existed for
several sessions without anything that actually ran a requested tool call.
Numbered `5.7a` rather than renumbering 5.8–5.12 onward, since those are
cross-referenced by exact section number from several modules
(`tasker/session/concurrency.py`, `episodic.py`, `notifier.py`).

**Problem this closes:** `ToolCallNormalizer.extract()` parses a model's
requested tool call into a `WorkerToolResult` with `tool_output=None`, but
nothing downstream ever executed it, and `build_synthesize_prompt()`
(5.3) only read `WorkerResult.output` — never `tool_results`. A worker
could request `bash("ls")` and the system would report success while
`ls` never ran; the synthesizer would then produce plausible-sounding
prose about what the command "would" show. Confirmed live against
`lfm2.5-thinking:latest`. See `CLAUDE.md`'s Current Session Notes for the
investigation.

**Responsibility split (two modules, both under `tasker/tools/`, not
`tasker/orchestrator/` — the orchestrator ABC's hard rule, "never calls
tools directly," rules that out; see 7.1):**

- **`tasker/tools/executor.py`** — `execute_tool(tool_result, *, worker,
  cwd, timeout_s=30.0) -> WorkerToolResult`. Runs one tool call for real
  and returns a *new* `WorkerToolResult` with `tool_output`/`error`/
  `duration_ms` populated. Never raises. Dispatches `BASH`, `GIT`,
  `FILE_READ`, `FILE_WRITE`, `CODE_SEARCH` (all via `asyncio.create_
  subprocess_exec`, argv-based, never `shell=True`). `LINTER`/
  `TEST_RUNNER` are deliberately unimplemented — no linter or test
  framework is configured anywhere in this project, so guessing which
  one to invoke would be worse than a clear `.error`.

- **`tasker/tools/loop.py`** — `run_tool_loop(task, worker, provider, *,
  max_turns=5, cwd=None) -> WorkerResult`. Drives `provider.execute()`
  through as many turns as needed: execute → if the result requests
  tool calls, run them for real via `execute_tool()`, thread the
  assistant's own turn (`WorkerResult.raw_assistant_message`, new field
  on the 5.6 contract) and the tool result
  (`format_tool_result_message()`, `tasker/workers/providers/ollama.py`)
  into a running message history, re-invoke. Terminates when a turn
  requests no more tools, or `max_turns` is hit (returns the last result
  and logs a WARNING rather than raising), or — non-termination guard,
  COWORK_PROMPT task 8.3 — when a turn requests an **identical tool-call
  set** (same tool names and arguments, order-sensitive) as the
  immediately preceding turn: a model that ignores its tool results and
  re-issues the same call is stuck, and every additional turn may be a
  budgeted Ollama Cloud call, so the loop stops at the second identical
  request without executing it (WARNING logged, last result returned —
  same contract as the `max_turns` exit). Non-consecutive repeats are
  deliberately allowed (re-running `git status` later in a task is
  legitimate); only consecutive identical requests trigger the guard.
  Usage/cost/duration accumulate
  across all turns; every turn's *executed* `WorkerToolResult`s survive
  into the final `WorkerResult.tool_results` (not just the last turn's,
  which typically has none since it's the final answer).
  `cli/shell.py`'s `_run_task()` calls this in place of a single
  `provider.execute()` per step.

**Security posture** (this is a local dev CLI, but `COWORK_BUNDLE`
pairs `bash` with network tools under `privacy_tier: any_cloud` — a
cloud-routed worker with web-fetched content in context could otherwise
be tricked into driving local execution):

1. `BASH`, `FILE_WRITE`, `GIT` are hard-gated in `execute_tool()` to
   `worker.compute_location == ComputeLocation.LOCAL_HARDWARE`,
   regardless of what a mode's `privacy_tier` allowed at planning time.
   `FILE_READ`/`CODE_SEARCH` (read-only) are ungated — governed by the
   existing `PrivacyTier`/`RoutingPolicy` system (11.1).
2. A small BASH denylist (substring/regex on the command before
   execution — `rm -rf`, `sudo`, `mkfs`, `dd if=`, fork-bomb pattern,
   `curl|sh`-style pipes, writes to `/dev/`, `chmod -R 777 /`) is a
   speed bump against obviously catastrophic commands, **not** a
   security boundary. Real safety rests on the `LOCAL_HARDWARE` gate and
   the user's own trust in their local model/machine.
3. Every tool call has a 30s timeout and an 8000-char output cap
   (truncated with a marker), to bound cost and avoid flooding the
   model's context.
4. `FILE_READ`/`FILE_WRITE` resolve their `path` under `cwd` and reject
   any resolved path that escapes it. `BASH`/`GIT` cannot be
   path-contained this way (shell commands can `cd`/use absolute paths
   freely) — an accepted, documented limitation.

**Known limitation, not closed by this section:** the loop only helps
tool calls that are *successfully parsed*. If a model's response is
fully empty (nothing parses into any tool call — confirmed live for
`lfm2.5-thinking:latest` under `ToolProtocol.LFM25` on some prompts, even
after `OllamaProvider`'s bounded empty-content retry, 5.6.1), there is
nothing for this loop to execute. That remains open; see `CLAUDE.md`.

---

### 5.8 Session Manager

**Responsibility:** Owns the full session lifecycle state machine. Arbitrates between RUNNING, THROTTLING, PAUSING, CHECKPOINTING, PAUSED, RESUMING states. Called before every worker dispatch.

**Location:** `tasker/session/manager.py`

See Section 9 for full state machine specification.

---

### 5.9 Concurrency Manager

**Responsibility:** Enforces Ollama Cloud concurrency slot limits using an asyncio semaphore. Non-blocking by design — callers receive DEFERRED rather than waiting.

**Location:** `tasker/session/concurrency.py`

**Plan-to-slot mapping:**

| Plan | Max Concurrent Slots | COWORK Behavior |
|------|---------------------|-----------------|
| Free | 1 | Sequential only |
| Pro | 3 | Orchestrator + 2 workers |
| Max | 10 | Full TRINITY parallel |

---

### 5.10 Session Budget

**Responsibility:** Tracks GPU-time usage within the current 5-hour Ollama Cloud window. Computes throttle signals. Persists state across process restarts.

**Location:** `tasker/session/budget.py`

**Key thresholds:**

| Threshold | Value | Action |
|-----------|-------|--------|
| Warning | 90% of plan limit | Shift routing to COST_OPTIMIZED, prefer local |
| Pause trigger | 100% of plan limit | Begin graceful pause flow |
| Weekly warning | 85% of weekly limit | Log warning, notify user |
| Weekly exhausted | 100% of weekly limit | Same as session exhausted |

---

### 5.11 Checkpoint Store

**Responsibility:** Persists and retrieves Checkpoint objects. Supports targeted resume by checkpoint ID and most-recent resume.

**Location:** `tasker/session/checkpoint.py`

**Storage backend:** Local filesystem (JSON), path: `.harness/checkpoints/<checkpoint_id>.json`

---

### 5.12 Notifier

**Responsibility:** Delivers pause/resume/status events to the user through configured channels. Harness-internal only — no external service dependencies assumed.

**Location:** `tasker/session/notifier.py`

**Implementations:**

| Notifier | When Used |
|----------|-----------|
| `TerminalNotifier` | CLI mode — countdown display, keypress handler |
| `DesktopNotifier` | OS notification (cross-platform) |
| `WebhookNotifier` | User-configured POST endpoint |
| `LogNotifier` | Silent — writes to harness log only (daemon/background mode) |
| `CompositeNotifier` | Fires all registered notifiers |

---

## 6. Data Models

### 6.1 WorkerManifest

```python
@dataclass
class WorkerManifest:
    id: str                              # unique identifier, e.g. "lfm2.5-local"
    provider: ProviderType               # OLLAMA | ANTHROPIC | OPENAI | FUGU
    model_id: str                        # provider-specific model string
    compute_location: ComputeLocation    # LOCAL_HARDWARE | OLLAMA_CLOUD | DIRECT_CLOUD
    
    # Capability profile
    capabilities: set[Capability]        # TOOL_USE | CODE | REASONING | SEARCH |
                                         # VISION | THINKING | LONG_CONTEXT | MULTI_AGENT
    tool_protocol: ToolProtocol          # NATIVE | JSON_EXTRACT | XML_EXTRACT | FEW_SHOT
    context_window: int                  # max tokens
    
    # Cost profile (per 1M tokens; 0.0 for local)
    cost_input: float
    cost_output: float
    
    # Ollama-specific
    ollama_usage_level: OllamaUsageLevel | None   # LIGHT(1) | MEDIUM(2) | HEAVY(3) | EXTRA_HEAVY(4)
    
    # Runtime profile
    latency_class: LatencyClass          # FAST(<2s) | MEDIUM(<10s) | SLOW(<60s)
    available: bool                      # liveness from health check
    
    # Hardware constraint (local only)
    requires_gpu: bool
    vram_mb: int | None
    
    # Capability score (optional, for CAPABILITY_FIRST ranking)
    capability_scores: dict[str, float]  # benchmark_name → score
```

### 6.2 WorkerTask

```python
@dataclass
class WorkerTask:
    task_id: str
    step_index: int
    role: AgentRole                      # THINKER | WORKER | VERIFIER
    instruction: str
    tools: list[ToolDefinition]
    context: dict                        # orchestrator-assembled context
    routing_policy: RoutingPolicy
    privacy_tier: PrivacyTier
    timeout_s: float | None
```

### 6.3 WorkerResult

```python
@dataclass
class WorkerResult:
    task_id: str
    worker_id: str
    status: WorkerStatus                 # SUCCESS | FAILED | DEFERRED | REJECTED | TIMEOUT
    output: str | None
    tool_results: list[WorkerToolResult]
    usage: ModelUsage                    # input_tokens, output_tokens, cost_usd
    duration_ms: int
    reason: str | None                   # failure/deferral reason
    fallback_hint: FallbackHint | None
```

### 6.4 ExecutionPlan

```python
@dataclass
class ExecutionPlan:
    plan_id: str
    original_task: str
    steps: list[PlanStep]
    dependency_graph: dict[int, list[int]]   # step_index → [blocking step indices]
    
@dataclass
class PlanStep:
    index: int
    description: str
    role: AgentRole
    required_capabilities: set[Capability]
    depends_on: list[int]
    status: StepStatus               # PENDING | ACTIVE | COMPLETED | FAILED | SKIPPED
    result: WorkerResult | None
```

### 6.5 Checkpoint

```python
@dataclass
class Checkpoint:
    id: str                          # uuid4
    created_at: datetime
    mode: str                        # mode name
    hardware_profile: str            # profile name
    
    # Orchestration state
    original_task: str
    plan: ExecutionPlan
    completed_steps: list[WorkerResult]
    current_step_index: int
    session_context: dict            # accumulated orchestrator variables
    
    # Memory state
    episodic_log_position: int
    
    # Budget state at pause time
    budget_snapshot: BudgetSnapshot
    
    # Resume config
    resume_at: datetime | None       # None = manual only
    auto_resume: bool
```

### 6.6 OllamaSessionBudget

> **NOTE — Placeholder limits:** Exact session/weekly unit limits are placeholders
> pending real Ollama Cloud telemetry. Current values live in
> `tasker/session/budget.py` (`_SESSION_LIMIT`, `_WEEKLY_LIMIT`) — do not silently
> change them without updating both the code and this note.

```python
@dataclass
class OllamaSessionBudget:
    plan: OllamaPlan                 # FREE | PRO | MAX
    window_start: datetime
    window_duration: timedelta       # 5 hours
    usage_consumed: float            # GPU-time units
    weekly_usage_consumed: float
    
    # Derived
    @property
    def usage_pct(self) -> float: ...
    @property
    def weekly_usage_pct(self) -> float: ...
    @property
    def window_remaining(self) -> timedelta: ...
    @property
    def should_throttle(self) -> bool: ...  # usage_pct >= 0.90
    @property
    def is_exhausted(self) -> bool: ...    # usage_pct >= 1.0

@dataclass
class BudgetSnapshot:
    captured_at: datetime
    usage_pct: float
    weekly_usage_pct: float
    window_remaining_s: float
    plan: str
```

### 6.7 TaskerMode

```python
@dataclass
class TaskerMode:
    name: str                            # CHAT | CODE | COWORK | RESEARCH | SECURE
    orchestrator_tier_max: int           # maximum tier this mode permits (0–4)
    tool_bundle: set[ToolID]
    routing_policy: RoutingPolicy
    interaction_pattern: InteractionPattern
    memory_scope: MemoryScope
    worker_preference_order: list[Capability]
    private_hard_block: bool             # True only for SECURE mode
    privacy_tier: PrivacyTier
```

### 6.8 Enumerations

```python
class ProviderType(Enum):
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    FUGU = "fugu"

class ComputeLocation(Enum):
    LOCAL_HARDWARE  = "local"
    OLLAMA_CLOUD    = "ollama_cloud"
    DIRECT_CLOUD    = "direct_cloud"

class Capability(Enum):
    TOOL_USE     = "tool_use"
    CODE         = "code"
    REASONING    = "reasoning"
    SEARCH       = "search"
    VISION       = "vision"
    THINKING     = "thinking"
    LONG_CONTEXT = "long_context"
    MULTI_AGENT  = "multi_agent"     # Fugu only

class ToolProtocol(Enum):
    NATIVE       = "native"
    JSON_EXTRACT = "json_extract"
    XML_EXTRACT  = "xml_extract"
    FEW_SHOT     = "few_shot"

class RoutingPolicy(Enum):
    COST_OPTIMIZED   = "cost_optimized"
    CAPABILITY_FIRST = "capability_first"
    SPEED_OPTIMIZED  = "speed_optimized"
    HYBRID           = "hybrid"
    PRIVATE          = "private"

class PrivacyTier(Enum):
    LOCAL_ONLY       = 0
    OLLAMA_CLOUD_OK  = 1
    ANY_CLOUD        = 2

class AgentRole(Enum):
    THINKER  = "thinker"
    WORKER   = "worker"
    VERIFIER = "verifier"

class SessionState(Enum):
    RUNNING       = "running"
    THROTTLING    = "throttling"
    PAUSING       = "pausing"
    CHECKPOINTING = "checkpointing"
    PAUSED        = "paused"
    RESUMING      = "resuming"

class SessionDirective(Enum):
    CONTINUE            = "continue"
    CONTINUE_LOCAL_ONLY = "continue_local_only"
    PAUSE               = "pause"
    HOLD                = "hold"

class WorkerStatus(Enum):
    SUCCESS  = "success"
    FAILED   = "failed"
    DEFERRED = "deferred"      # no slots available
    REJECTED = "rejected"      # queue full
    TIMEOUT  = "timeout"

class OllamaPlan(Enum):
    FREE = "free"
    PRO  = "pro"
    MAX  = "max"

class OllamaUsageLevel(IntEnum):
    LIGHT       = 1
    MEDIUM      = 2
    HEAVY       = 3
    EXTRA_HEAVY = 4

class LatencyClass(Enum):
    FAST   = "fast"     # < 2s
    MEDIUM = "medium"   # < 10s
    SLOW   = "slow"     # < 60s

class FallbackHint(Enum):
    USE_LOCAL_OR_DIRECT_CLOUD = "use_local_or_direct_cloud"
    RETRY_OR_ESCALATE         = "retry_or_escalate"
    NO_FALLBACK_AVAILABLE     = "no_fallback_available"
```

---

## 7. Interface Contracts

### 7.1 OrchestratorBase

```python
class OrchestratorBase(ABC):

    @abstractmethod
    async def plan(
        self,
        task: str,
        classifier_output: ClassifierResult,
        available_workers: list[WorkerManifest]
    ) -> ExecutionPlan:
        """Decompose task into ordered steps with role assignments."""

    @abstractmethod
    async def synthesize(
        self,
        original_task: str,
        results: list[WorkerResult]
    ) -> str:
        """Merge worker outputs into a final response."""

    @abstractmethod
    async def should_retry(
        self,
        plan: ExecutionPlan,
        failed_step: WorkerResult
    ) -> RetryDecision:
        """Decide: retry same worker, reassign to different worker, or fail."""
```

### 7.2 WorkerProviderBase

```python
class WorkerProviderBase(ABC):

    @abstractmethod
    async def execute(
        self,
        task: WorkerTask,
        worker: WorkerManifest
    ) -> WorkerResult:
        """Execute a task on the specified worker. Returns result or status."""

    @abstractmethod
    async def health_check(
        self,
        worker: WorkerManifest
    ) -> bool:
        """Return True if the worker is reachable and ready."""

    @abstractmethod
    def supports(
        self,
        worker: WorkerManifest
    ) -> bool:
        """Return True if this provider can handle the given manifest."""
```

### 7.3 ClassifierBase

```python
class ClassifierBase(ABC):

    @abstractmethod
    async def classify(
        self,
        task: str,
        mode: TaskerMode
    ) -> ClassifierResult:
        """Classify the task and return routing metadata."""
```

### 7.4 NotifierBase

```python
class NotifierBase(ABC):

    @abstractmethod
    async def send(self, event: SessionEvent) -> None:
        """Deliver a session lifecycle event to the user."""
```

### 7.5 OpenAI-Compatible API Surface

The harness exposes a standard endpoint for external callers:

```
POST /v1/chat/completions
  - model field: "tasker/<mode>" e.g. "tasker/cowork", "tasker/code"
  - tools: standard OpenAI tool definitions
  - stream: boolean, supported

GET  /v1/models
  - returns registered harness modes as model entries

GET  /v1/workers
  - harness extension: returns worker registry status
```

### 7.6 CLI Shell Interface

```
tasker --mode <mode> "<task>"          # single task, specified mode
tasker --mode <mode> --policy <policy> "<task>"
tasker resume <checkpoint_id>          # resume from checkpoint
tasker resume --last                   # resume most recent checkpoint
tasker resume --last --policy local    # resume with policy override
tasker checkpoints                     # list all checkpoints
tasker workers                         # show worker registry
tasker shell                           # enter interactive REPL

# Interactive REPL slash commands
/mode <mode>          switch mode
/workers              show active worker pool with status
/models               list workers by DEFAULT/LOCAL/CLOUD group, with
                       tool protocol, max context, and a "fits in VRAM"
                       hint for local workers (alias: /model list; 5.6.1a)
/policy <policy>      change routing policy
/secure [on|off]      toggle SECURE mode
/budget               show current session budget -- initializes at 0.0
                       the moment a mode is entered (one pipeline built
                       per mode up front, not lazily on first task; 5.6.1a)
/checkpoint           manually checkpoint current session
/resume <id>          resume from checkpoint
/model <worker_id>    pin CHAT mode to an exact worker (see 5.3a); an
                       unregistered but Ollama-tag-shaped id offers
                       dynamic onboarding (pull + probe + register,
                       SDD_ADDENDUM_PHASE8.md B.4.7)
/effort <low|med|high> redirect CHAT mode's default worker selection
/context <tokens>     override CHAT mode's num_ctx for this REPL
                       session (5.6.1a); precedes the VRAM ceiling and
                       the manifest's own context_window
/transcript [n]       reprint last n exchanges, paged (full session if
                       omitted); auto-saved to ~/.tasker/transcripts/ (7.6a)
/status               show full session status (CHAT's current model,
                       effort, and context override)
/help                 list all slash commands
```

### 7.6a Chat Rewind Buffer (Session Transcript)

**Status:** Added after live REPL testing (Roland) — REPL output scrolls
off the terminal on a long session and, until this, was simply gone
once it left scrollback.

**Rule:** the REPL maintains one `Transcript` (`tasker/runtime/
transcript.py`) for the whole session — every user prompt, every
assistant response, and every slash command ("key event") is recorded
in memory as a `TranscriptEntry(timestamp, kind, mode, text)`, `kind`
one of `"user" | "assistant" | "event"`.

- **Auto-write to disk as the session runs**, not only at exit: the
  transcript file is created (with a header) the moment the REPL
  starts, at `~/.tasker/transcripts/<YYYYMMDD-HHMMSS>.md`, and every
  `record()` call appends immediately — a crash or a closed terminal
  loses nothing already recorded. If the path can't be created/written
  (unwritable home directory, full disk), the `Transcript` degrades to
  in-memory-only rather than crashing the REPL; `/transcript` still
  works for the rest of that session, it just won't survive the process
  exiting.
- **Startup banner** prints the transcript's file path (when disk
  writing is active) so the user knows where to find it without asking.
- **`/transcript [n]`** reprints the last `n` *exchanges* (a user prompt
  plus everything logged until the next user prompt — the reply and any
  event entries in between) — the full session if `n` is omitted —
  through a simple terminal pager (chunks sized to the terminal height,
  `-- more --` between chunks, `q` to stop).
- **What gets captured for the "assistant" entry** is the dispatch
  call's entire stdout for that turn (via a small `_Tee` in
  `cli/shell.py`, mirroring stdout into both the real terminal and an
  in-memory buffer), not a synthesized "final answer" string — this
  matches the rewind buffer's purpose: recovering exactly what scrolled
  past, including any warnings/budget lines printed alongside the answer.

Reusable by a future TUI `HarnessPanel` (8.5) the same way
`tasker/runtime/dispatch.py` is shared today — `tasker/runtime/
transcript.py` has no `cli/shell.py` or Textual import coupling.

---

## 8. Configuration System

### 8.1 Configuration Hierarchy

```
Hardware Profile (YAML)
    ×
Mode Default (YAML)
    ×
Worker Registry (YAML)
    ×
Runtime overrides (CLI flags / slash commands)
    =
Active ExecutionConfig
```

### 8.2 Hardware Profile Schema

```yaml
# config/profiles/tier1_tasker.yaml
hardware_profile: tier1_local_minimal
description: "TASKER-P1 — Ryzen 5 3500U, 32GB RAM, CPU-only"

orchestrator:
  tier_max: 1
  provider: single_llm
  model: qwen3:1.7b
  load_strategy: sequential       # load → plan → unload → worker runs
  context_limit: 4096

classifier:
  provider: rule_based
  fallback: orchestrator

worker_pool:
  max_concurrent_local: 1
  max_concurrent_ollama_cloud: 1  # overridden by Ollama plan
  unload_between_tasks: true

ollama:
  plan: pro                       # free | pro | max
  base_url: "http://localhost:11434"
  session_throttle_at: 0.90
  weekly_throttle_at: 0.85
  fallback_on_exhaustion: local_then_direct_cloud

mode_constraints:
  cowork:
    behavior: sequential_only
  research:
    behavior: single_worker
```

```yaml
# config/profiles/tier2_designlab.yaml
hardware_profile: tier2_local_standard
description: "Designlab1 — Ryzen 5/7, 32GB RAM, GTX 1050 Ti 4GB"

orchestrator:
  tier_max: 2
  provider: dual_llm
  planner_model: qwen3:7b
  synthesizer_model: qwen3:4b
  load_strategy: resident         # planner stays loaded
  context_limit: 8192

classifier:
  provider: local_llm
  model: qwen3:1.7b

worker_pool:
  max_concurrent_local: 2
  max_concurrent_ollama_cloud: 3  # Pro plan
  unload_between_tasks: false

mode_constraints:
  cowork:
    behavior: limited_parallel    # orchestrator + 2 workers
  research:
    behavior: parallel_fetch
```

### 8.3 Worker Registry Schema

```yaml
# config/workers/worker_registry.yaml
workers:
  - id: lfm2.5-local
    provider: ollama
    model_id: "lfm2.5:latest"
    compute_location: local_hardware
    capabilities: [tool_use, code, search]
    tool_protocol: native
    context_window: 32768
    cost_input: 0.0
    cost_output: 0.0
    ollama_usage_level: null
    latency_class: medium
    requires_gpu: false

  - id: nemotron-3-ultra-cloud
    provider: ollama
    model_id: "nemotron-3-ultra"
    compute_location: ollama_cloud
    capabilities: [tool_use, reasoning, thinking, code]
    tool_protocol: native
    context_window: 128000
    cost_input: 0.0
    cost_output: 0.0
    ollama_usage_level: 3
    latency_class: slow

  - id: minimax-m3-cloud
    provider: ollama
    model_id: "minimax-m3"
    compute_location: ollama_cloud
    capabilities: [tool_use, vision, thinking, long_context]
    tool_protocol: native
    context_window: 1000000
    cost_input: 0.0
    cost_output: 0.0
    ollama_usage_level: 3
    latency_class: slow

  - id: claude-haiku-4-5
    provider: anthropic
    model_id: "claude-haiku-4-5"
    compute_location: direct_cloud
    capabilities: [tool_use, code, reasoning]
    tool_protocol: native
    context_window: 200000
    cost_input: 0.80
    cost_output: 4.00
    ollama_usage_level: null
    latency_class: fast

  - id: fugu-ultra
    provider: fugu
    model_id: "fugu-ultra-20260615"
    compute_location: direct_cloud
    capabilities: [tool_use, code, reasoning, multi_agent]
    tool_protocol: native
    context_window: 272000
    cost_input: 5.00
    cost_output: 30.00
    ollama_usage_level: null
    latency_class: slow
```

### 8.4 Mode Default Schema

```yaml
# config/modes/cowork.yaml
name: COWORK
orchestrator_tier_max: 3
routing_policy: hybrid
interaction_pattern: async_checkpoint
memory_scope: project_plus_episodic
private_hard_block: false
privacy_tier: any_cloud

tool_bundle:
  - bash
  - file_read
  - file_write
  - git
  - web_search
  - retrieve
  - code_search
  - checkpoint_write
  - task_state
  - progress_report
  - mcp_call_tool
  - delegate_agent
```

---

## 9. Session Lifecycle

### 9.1 State Machine

```
RUNNING
    │ usage >= 90%
    ▼
THROTTLING ──────────── usage < 90% ──────────────── RUNNING
    │ usage >= 100%                                    ▲
    │                                                  │ budget refreshes
    ▼                                                  │
PAUSING                                               │
    │ await current step completion                    │
    ▼                                                  │
CHECKPOINTING                                         │
    │ checkpoint written                               │
    ▼                                                  │
PAUSED ──── timer fires OR manual resume ───────── RESUMING
                                                       │
                                                   validate budget
                                                   reload checkpoint
                                                       │
                                                       └──────────────────►
```

### 9.2 Pause Flow (Detailed)

```
usage == 100%
    │
    ▼
1.  SessionState = PAUSING
2.  Let current step complete (do not kill in-flight calls)
3.  Acquire checkpoint lock
4.  Serialize ExecutionContext → Checkpoint
5.  Persist Checkpoint to CheckpointStore
6.  Calculate resume_at = window_start + 5h
7.  Compute wait_seconds = (resume_at - now).total_seconds()
8.  Fire PauseNotification via Notifier
9.  If auto_resume and wait_seconds > 0:
        schedule asyncio timer → self.resume()
10. SessionState = PAUSED
11. Set _pause_event (blocks orchestrator loop)
```

### 9.3 Fallback Ladder Before Pause

```
usage == 100% on Ollama Cloud
    │
    ▼
Local hardware available? ──YES──► CONTINUE_LOCAL_ONLY
    │ NO
    ▼
Direct cloud keys configured? ──YES──► CONTINUE_DIRECT_CLOUD (log cost)
    │ NO
    ▼
Task tolerates delay? ──YES──► CHECKPOINT + PAUSE + TIMER
    │ NO (interactive / time-sensitive)
    ▼
GRACEFUL_EXIT: complete current step, return partial result + checkpoint ID
```

### 9.4 Resume Flow

```
Timer fires OR `tasker resume <id>`
    │
    ▼
1.  SessionState = RESUMING
2.  Load Checkpoint from CheckpointStore
3.  Refresh OllamaSessionBudget (new window may have opened)
4.  Validate budget is non-zero
5.  Reconstruct ExecutionContext from Checkpoint
6.  Fire ResumeNotification
7.  SessionState = RUNNING
8.  Set _pause_event → unblocks orchestrator loop
9.  Continue from current_step_index
```

### 9.5 Pause Notification Content

```
⏸  HARNESS PAUSED
──────────────────────────────────────────────────────
Mode       : <mode>
Task       : "<original_task>"
Progress   : <n>/<total> steps completed
Paused at  : <timestamp>
Resumes at : <timestamp>  (<wait_duration> window reset)
Checkpoint : <checkpoint_id>

Completed:
  ✓ <step description>
  ...

Remaining:
  → <step description>
  ...

Auto-resume: ON | OFF
Manual:      tasker resume <checkpoint_id>
──────────────────────────────────────────────────────
```

---

## 10. Error Handling and Resilience

### 10.1 Error Classification

| Error Class | Examples | Response |
|-------------|----------|----------|
| Provider transient | HTTP 429, 503, timeout | Retry with backoff (max 3) |
| Provider permanent | Auth failure, model not found | Fail step, try fallback worker |
| Concurrency | No slots, queue full | Immediate DEFERRED, fallback worker |
| Budget exhausted | 100% session usage | Begin pause flow |
| Privacy violation | Cloud call in LOCAL_ONLY mode | Raise TaskerPolicyError immediately |
| Orchestrator failure | Plan generation failed | Downgrade to next lower tier |
| Tool execution error | Bash error, file not found | Return error in WorkerResult, let orchestrator decide retry |
| Checkpoint failure | Disk write error | Log + warn + attempt retry, do not lose plan state |

### 10.2 Retry Policy

```python
@dataclass
class RetryPolicy:
    max_retries: int = 3
    backoff_base_s: float = 1.0
    backoff_multiplier: float = 2.0
    jitter: bool = True
    fallback_to_different_worker: bool = True
```

### 10.3 Graceful Degradation Chain

```
Tier 4 (Cloud Orchestrator) unavailable
    → Tier 3 (Reasoning)
    → Tier 2 (Dual LLM)
    → Tier 1 (Single LLM)
    → Tier 0 (Rule-based)
    → Return best-effort partial result with explanation
```

---

## 11. Security and Privacy

### 11.1 Privacy Tier Enforcement

| Tier | Permitted Locations | Enforcement |
|------|---------------------|-------------|
| LOCAL_ONLY (0) | LOCAL_HARDWARE only | Hard block — raises TaskerPolicyError on violation |
| OLLAMA_CLOUD_OK (1) | LOCAL_HARDWARE + OLLAMA_CLOUD | Blocks DIRECT_CLOUD providers |
| ANY_CLOUD (2) | All locations | No restriction |

Privacy tier is set at the Mode level but can be overridden per-task by the orchestrator for sensitive steps within a COWORK session.

### 11.2 SECURE Mode

SECURE mode sets `private_hard_block: True` and `privacy_tier: LOCAL_ONLY`. Additional constraints:

- Tool bundle excludes all web-fetch and remote tools
- No cloud provider calls are permitted at any layer
- A banner is shown on every response: `[SECURE MODE — LOCAL ONLY]`
- Slash command `/secure off` requires explicit confirmation

### 11.3 Data Handling

- Checkpoints are stored on local filesystem only
- Checkpoint content is not transmitted to any provider
- Session context passed to cloud workers contains only the task and tool results, not full checkpoint state
- API keys are read from environment variables only — never written to checkpoint files

---

## 12. Testing Strategy

### 12.1 Principles

Adopted from the Parity Project Testing Guide:

- Tests are organized by runtime surface, not by source file
- Every implemented feature has at least one concrete test command
- Every new feature adds a checked item to `TASKER_CHECKLIST.md`
- Every user-testable feature adds a concrete command to `TESTING_GUIDE.md`
- Full unit test suite runs on every commit: `python3 -m unittest discover -s tests -v`

### 12.2 Test Suite Structure

```
tests/
├── unit/
│   ├── test_worker_manifest.py        # serialization, validation
│   ├── test_worker_registry.py        # register, filter, health_check
│   ├── test_worker_selector.py        # routing policy, privacy enforcement
│   ├── test_routing_policy.py         # all policy variants
│   ├── test_concurrency_manager.py    # slot acquisition, DEFERRED, REJECTED
│   ├── test_session_budget.py         # tracking, throttle, exhaustion
│   ├── test_session_manager.py        # state machine transitions
│   ├── test_checkpoint.py             # serialize, persist, load, resume
│   ├── test_tool_normalizer.py        # all protocol variants
│   ├── test_orchestrator_nano.py      # Tier 0 plan generation
│   ├── test_orchestrator_single.py    # Tier 1 plan + synthesize
│   ├── test_harness_modes.py          # mode configurator, all 5 modes
│   └── test_privacy_enforcement.py    # hard blocks, tier escalation
│
├── integration/
│   ├── test_ollama_local.py           # requires: ollama serve + local model
│   ├── test_ollama_cloud.py           # requires: ollama account + cloud model
│   ├── test_anthropic.py              # requires: ANTHROPIC_API_KEY
│   ├── test_openai.py                 # requires: OPENAI_API_KEY
│   ├── test_fugu.py                   # requires: FUGU_API_KEY
│   ├── test_cowork_flow.py            # full COWORK mode end-to-end
│   ├── test_pause_resume.py           # session budget exhaustion + resume
│   └── test_secure_mode.py            # privacy hard block end-to-end
│
├── fixtures/
│   ├── fake_ollama_server.py          # mock Ollama API (local + cloud)
│   ├── fake_anthropic_server.py       # mock Anthropic Messages API
│   ├── fake_openai_server.py          # mock OpenAI Chat API
│   ├── fake_fugu_server.py            # mock Fugu OpenAI-compat endpoint
│   ├── fake_stdio_mcp.py              # mock MCP server (from Parity Project)
│   └── worker_registry_fixture.yaml   # test worker registry
│
└── e2e/
    ├── test_chat_mode.py
    ├── test_code_mode.py
    ├── test_cowork_mode.py
    ├── test_research_mode.py
    └── test_secure_mode.py
```

### 12.3 Test Coverage Areas

| Surface | Unit | Integration | E2E |
|---------|------|-------------|-----|
| Worker Registry + Selector | ✓ | ✓ | |
| Routing Policy (all variants) | ✓ | ✓ | |
| Privacy Tier enforcement | ✓ | ✓ | ✓ |
| Concurrency Manager (all plans) | ✓ | ✓ | |
| Session Budget + Throttling | ✓ | ✓ | |
| Pause / Checkpoint / Resume | ✓ | ✓ | ✓ |
| Orchestrator Tier 0 | ✓ | | |
| Orchestrator Tier 1 | ✓ | ✓ | |
| Tool Normalizer (all protocols) | ✓ | ✓ | |
| CHAT mode | | | ✓ |
| CODE mode | | | ✓ |
| COWORK mode | | ✓ | ✓ |
| RESEARCH mode | | | ✓ |
| SECURE mode | ✓ | ✓ | ✓ |
| CLI slash commands | ✓ | | ✓ |
| OpenAI-compat API | ✓ | ✓ | |

### 12.4 Fixture Test Workspace Setup

```bash
mkdir -p ./test_cases/{.harness,workers,sessions,budgets,modes,secure}

# Worker registry fixture
cp config/workers/worker_registry.yaml ./test_cases/.harness/

# Ollama plan fixture (Pro plan for most tests)
cat > ./test_cases/.harness/ollama_plan.yaml <<'EOF'
plan: pro
concurrent_slots: 3
session_throttle_at: 0.90
weekly_throttle_at: 0.85
fallback_on_exhaustion: local_then_direct_cloud
EOF

# SECURE mode policy fixture
cat > ./test_cases/secure/.harness/policy.yaml <<'EOF'
privacy_tier: local_only
cloud_call_action: throw
allowed_providers: [ollama_local]
EOF
```

---

## 13. Development Roadmap

### Phase 1 — Foundation (Week 1–2)

Core contracts that all other components depend on:

| Task | File | Notes |
|------|------|-------|
| Data models + enumerations | `tasker/workers/base.py` | WorkerManifest, WorkerTask, WorkerResult, all enums |
| Worker Registry | `tasker/workers/registry.py` | register, filter, health_check |
| Worker Selector | `tasker/workers/registry.py` | routing policy, privacy check, concurrency guard |
| Concurrency Manager | `tasker/session/concurrency.py` | semaphore, DEFERRED on exhaustion |
| Unit tests: Phase 1 | `tests/unit/test_worker_*.py` | Full coverage before Phase 2 |

### Phase 2 — Session Layer (Week 2–3)

| Task | File | Notes |
|------|------|-------|
| Session Budget | `tasker/session/budget.py` | Usage tracking, throttle/exhaustion signals |
| Checkpoint Store | `tasker/session/checkpoint.py` | Serialize, persist, load |
| Session Manager | `tasker/session/manager.py` | Full state machine |
| Notifier | `tasker/session/notifier.py` | Terminal + LogNotifier first |
| Unit tests: Phase 2 | `tests/unit/test_session_*.py` | |

### Phase 3 — Orchestrator (Week 3–4)

| Task | File | Notes |
|------|------|-------|
| OrchestratorBase ABC | `tasker/orchestrator/base.py` | |
| NanoOrchestrator (Tier 0) | `tasker/orchestrator/tier0_rules.py` | Operational on TASKER-P1 day one |
| SingleLLMOrchestrator (Tier 1) | `tasker/orchestrator/tier1_single.py` | Requires local model |
| Unit tests: Phase 3 | `tests/unit/test_orchestrator_*.py` | |

### Phase 4 — Providers (Week 4–5)

| Task | File | Notes |
|------|------|-------|
| WorkerProviderBase ABC | `tasker/workers/providers/base.py` | |
| OllamaProvider | `tasker/workers/providers/ollama.py` | Local + cloud unified |
| AnthropicProvider | `tasker/workers/providers/anthropic.py` | |
| OpenAIProvider | `tasker/workers/providers/openai.py` | |
| FuguProvider | `tasker/workers/providers/fugu.py` | |
| ToolNormalizer | `tasker/tools/normalizer.py` | All 4 protocols |
| Integration tests: Phase 4 | `tests/integration/test_*_provider.py` | Uses fake servers |

### Phase 5 — Modes + CLI (Week 5–6)

| Task | File | Notes |
|------|------|-------|
| TaskerMode dataclass | `tasker/modes/base.py` | |
| ModeConfigurator | `tasker/modes/configurator.py` | Profile × mode resolution |
| CHAT mode | `tasker/modes/chat.py` | |
| CODE mode | `tasker/modes/code.py` | |
| COWORK mode | `tasker/modes/cowork.py` | Full checkpoint loop |
| RESEARCH mode | `tasker/modes/research.py` | |
| SECURE mode | `tasker/modes/secure.py` | Hard block enforcement |
| CLI Shell | `cli/shell.py` | Slash commands, countdown display |
| E2E tests: Phase 5 | `tests/e2e/` | All 5 modes |

### Phase 6 — Higher Orchestrator Tiers (Week 7+)

| Task | File | Notes |
|------|------|-------|
| DualLLMOrchestrator (Tier 2) | `tasker/orchestrator/tier2_dual.py` | Designlab1 target |
| ReasoningOrchestrator (Tier 3) | `tasker/orchestrator/tier3_reasoning.py` | GPU server target |
| CloudOrchestrator (Tier 4) | `tasker/orchestrator/tier4_cloud.py` | Fugu / Claude as planner |

### Phase 7 — Hardening

- Desktop and Webhook notifiers
- MindSeed episodic memory integration (COWORK mode)
- OpenAI-compat API server
- Hardware profile auto-detection
- Performance profiling on TASKER-P1

---

## 14. Glossary

| Term | Definition |
|------|------------|
| Agent | A model instance executing a task within an orchestrated session |
| Checkpoint | Serialized execution state enabling pause and resume |
| Classifier | Lightweight component that categorizes tasks by type and complexity |
| COWORK | Long-horizon async orchestration mode with checkpointing |
| Executor | A worker dispatched with a specific role by the orchestrator |
| Fugu | Sakana AI's multi-agent system exposed as a single OpenAI-compatible API |
| Harness | This system — the Ollama Tasker |
| Hardware Profile | YAML config describing the target machine and its orchestrator tier ceiling |
| LFM | Liquid Foundation Model — primary local worker model |
| Mesa-optimizer | An optimizer that emerges within an outer optimization process |
| Mode | A named pre-configuration of the harness stack for a specific interaction style |
| MCP | Model Context Protocol — standard for tool exposure to models |
| Ollama Cloud | Remote GPU inference run by Ollama Inc., accessed at the same local API endpoint |
| Orchestrator | The planning and synthesis component that never executes tools directly |
| Plan | An ordered sequence of steps with role assignments and dependency edges |
| Privacy Tier | A constraint on which compute locations may handle a given task |
| Provider | An implementation of WorkerProviderBase for a specific API backend |
| SECURE mode | Harness mode that hard-blocks all cloud compute |
| Session Budget | Ollama Cloud's rolling 5-hour GPU-time usage window |
| TRINITY | Thinker/Worker/Verifier coordination pattern from Sakana AI ICLR 2026 paper |
| Worker | Any tool-capable model registered in the harness worker pool |
| Worker Selector | Component that picks the optimal worker given capabilities and routing policy |

---

## 15. References

| Reference | Description |
|-----------|-------------|
| PARITY_CHECKLIST.md | Feature parity tracking for the Python Claude Code runtime |
| TESTING_GUIDE.md | Concrete test commands organized by runtime surface |
| Sakana AI Fugu — https://sakana.ai/fugu/ | Multi-agent system as a model; TRINITY and Conductor papers |
| Ollama Cloud documentation | Concurrency limits, usage levels, plan constraints |
| Anthropic Messages API | claude-haiku-4-5, claude-sonnet-4-6 tool calling |
| OpenAI Chat Completions API | gpt-4o tool calling |
| LiteLLM documentation | Optional unified transport layer reference |
| TASKER_CHECKLIST.md | (To be created) Feature checklist for this project |

---

*This document is a living specification. Update version and date on every revision. All architectural decisions made after this draft must be reflected here before implementation begins.*

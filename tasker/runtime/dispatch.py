"""
tasker.runtime.dispatch
------------------------
Shared production wiring for driving a task through the orchestrator ->
provider pipeline: profile resolution, session/budget construction, the
per-step dispatch loop (SessionManager.tick() before every step, checkpoint
+ pause on PAUSE/HOLD), and checkpoint resume.

Originally lived in cli/shell.py. Moved here so cli/shell.py's REPL/CLI
frontend and tasker/tui/app.py's REPL frontend can both drive the exact
same production path -- no behavior fork between the two entry points.
cli/shell.py re-imports every name below unchanged (including the leading
underscore) so its own tests and its own module namespace are unaffected
by this move.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from tasker.session.checkpoint import CheckpointStore
from tasker.workers.registry import WorkerRegistry

_DEFAULT_STORE_DIR = Path(".tasker") / "checkpoints"
_REGISTRY_YAML = Path(__file__).parent.parent.parent / "config" / "workers" / "worker_registry.yaml"

_POLICY_ALIASES: dict[str, str] = {
    "local":      "private",
    "cost":       "cost_optimized",
    "capability": "capability_first",
    "speed":      "speed_optimized",
    "hybrid":     "hybrid",
    "private":    "private",
}


# --------------------------------------------------------------------------- #
# Registry loading (shared by cli/shell.py's and tasker/tui/app.py's main())
# --------------------------------------------------------------------------- #

def _print_workers(registry: WorkerRegistry) -> None:
    """Shared table-formatting for `tasker workers` (cli/shell.py) and
    `/workers` (tasker/tui/app.py's REPL)."""
    workers = registry.list_all()
    if not workers:
        print("No workers registered.")
        return
    print(f"{'ID':<30}  {'MODEL':<25}  {'LOCATION':<14}  STATUS")
    print("-" * 80)
    for w in workers:
        status = "available" if w.available else "unavailable"
        print(f"{w.id:<30}  {w.model_id:<25}  {w.compute_location.value:<14}  {status}")


def _print_checkpoints(store: CheckpointStore) -> None:
    """Shared table-formatting for `tasker checkpoints` (cli/shell.py) and
    `/checkpoints` (tasker/tui/app.py's REPL)."""
    checkpoints = store.list_all()
    if not checkpoints:
        print("No checkpoints found.")
        return
    print(f"{'ID':<38}  {'MODE':<10}  {'CREATED':<18}  TASK")
    print("-" * 90)
    for cp in checkpoints:
        ts = cp.created_at.strftime("%Y-%m-%d %H:%M")
        print(f"{cp.id:<38}  {cp.mode:<10}  {ts:<18}  {cp.original_task[:30]}")


def _load_registry(registry_yaml: Path = _REGISTRY_YAML) -> WorkerRegistry:
    """
    Load the worker registry from YAML, cross-checked against cached
    hardware detection GPU availability if a cache exists for this machine
    (SDD_ADDENDUM_7.5.md A.3.4: requires_gpu workers that don't fit are
    marked unavailable, never dropped). Uses the cache, never a fresh
    detect_gpu() call, to avoid adding subprocess cost to every launch --
    skipped entirely if `tasker-hardware detect` has never been run.
    """
    if registry_yaml.exists():
        registry = WorkerRegistry.load_from_yaml(registry_yaml)
        from tasker.config.detect import load_cached_detection, load_cached_gpu_info

        if load_cached_detection() is not None:
            registry.apply_gpu_availability(load_cached_gpu_info())
    else:
        registry = WorkerRegistry()
    return registry


# --------------------------------------------------------------------------- #
# Task execution
# --------------------------------------------------------------------------- #

def _resolve_policy_override(policy_str: str | None):
    """Map a CLI/REPL policy string (or alias) to a RoutingPolicy, or None."""
    if not policy_str:
        return None
    from tasker.modes.base import _POLICY_MAP

    return _POLICY_MAP.get(_POLICY_ALIASES.get(policy_str.lower(), policy_str.lower()))


def _build_session(profile, store: CheckpointStore):
    """
    Construct the per-run session stack: budget + SessionManager.

    TASKER_BUDGET_PRELOAD (float GPU-time units) pre-loads usage_consumed so
    throttle (90%) and pause (100%) behaviour can be exercised live without
    burning hours of real Ollama Cloud GPU time -- the code path from there
    on (tick(), pause flow, checkpoint write) is the real one. Unset in
    normal operation.
    """
    from datetime import datetime

    from tasker.session.budget import OllamaSessionBudget
    from tasker.session.manager import SessionManager
    from tasker.session.notifier import TerminalNotifier

    budget = OllamaSessionBudget(
        plan=profile.ollama_plan,
        window_start=datetime.now().astimezone(),
    )
    preload = os.environ.get("TASKER_BUDGET_PRELOAD")
    if preload:
        try:
            budget.usage_consumed = float(preload)
            budget.weekly_usage_consumed = float(preload)
        except ValueError:
            print(f"Ignoring non-numeric TASKER_BUDGET_PRELOAD={preload!r}")
    # auto_resume=False: the one-shot CLI/REPL process exits after a pause,
    # so an in-process asyncio resume timer could never fire. Resume is
    # manual: `tasker resume <id>` / `tasker resume --last` / `/resume --last`.
    session_mgr = SessionManager(budget, store, TerminalNotifier(), auto_resume=False)
    return budget, session_mgr


def _build_config(mode_name: str, policy_override=None):
    """
    Shared profile + mode resolution. Returns the resolved ExecutionConfig
    or None on config failure. Kept separate from _build_pipeline() so the
    API server can reuse the same resolution logic while building its own
    per-request session/budget stack around the shared provider_map.
    """
    import dataclasses

    from tasker.modes.base import ModeConfigurator

    profile_name = os.environ.get("TASKER_PROFILE", "tier1_tasker")
    configurator = ModeConfigurator()
    try:
        profile = configurator.load_profile(profile_name)
        mode_cfg = configurator.load_mode(mode_name)
    except Exception as exc:
        print(f"Config error: {exc}")
        return None

    if policy_override is not None:
        mode_cfg = dataclasses.replace(mode_cfg, routing_policy=policy_override)

    return profile_name, configurator.resolve(profile, mode_cfg)


def _build_pipeline(mode_name: str, store: CheckpointStore, policy_override=None):
    """
    Shared construction for fresh runs and resumes: config, budget,
    SessionManager, concurrency manager, provider map, orchestrator.
    Returns None (after printing the error) on config failure.
    """
    config_result = _build_config(mode_name, policy_override)
    if config_result is None:
        return None
    profile_name, config = config_result

    # config.mode.tool_bundle is already the correct per-mode set -- SECURE's
    # bundle is pre-stripped of network tools at the YAML/TaskerMode level
    # (see tasker/tools/bundles.py secure_bundle()/SECURE_BUNDLE), so no
    # extra stripping is needed here. Per-step narrowing (see
    # narrow_bundle_to_step()) happens inside the step loop, once each
    # step's description is known.
    budget, session_mgr = _build_session(config.profile, store)

    # One shared concurrency manager for the whole run -- covers both
    # regular worker dispatch (via WorkerSelector/run_tool_loop) and
    # orchestrator-level plan/synthesize/retry calls (via
    # build_orchestrator()'s call_model closures), since both paths route
    # through this same OllamaProvider instance. The shared budget is
    # threaded into the same provider so *every* OLLAMA_CLOUD call
    # (worker or orchestrator) records GPU-time units.
    #
    # OLLAMA_BASE_URL overrides the profile YAML -- the YAML records the
    # standard port, but a machine may run Ollama elsewhere (Designlab1
    # serves on 127.0.0.1:11435 via a systemd port.conf drop-in).
    base_url = os.environ.get("OLLAMA_BASE_URL") or config.profile.ollama_base_url
    from tasker.session.concurrency import OllamaCloudConcurrencyManager
    from tasker.workers.base import ProviderType
    from tasker.workers.providers.ollama import OllamaProvider

    concurrency_mgr = OllamaCloudConcurrencyManager(config.profile.ollama_plan)
    # Cached GPU detection (same source WorkerRegistry.apply_gpu_availability()
    # uses via _load_registry()) -- lets OllamaProvider apply its local-only
    # num_ctx VRAM ceiling (SDD 5.6.1a) without a live subprocess call.
    from tasker.config.detect import load_cached_gpu_info

    ollama_provider = OllamaProvider(base_url, concurrency_mgr, budget, gpu=load_cached_gpu_info())
    provider_map = {ProviderType.OLLAMA: ollama_provider}
    from tasker.orchestrator.factory import build_orchestrator

    orchestrator = build_orchestrator(config, provider_map)

    return profile_name, config, budget, session_mgr, concurrency_mgr, provider_map, orchestrator


def _serialize_step_result(step_index: int, result) -> dict:
    """Minimal WorkerResult record stored in Checkpoint.completed_steps."""
    return {
        "step_index": step_index,
        "task_id": result.task_id,
        "worker_id": result.worker_id,
        "status": result.status.value,
        "output": result.output,
        "duration_ms": result.duration_ms,
    }


def _deserialize_step_result(record: dict):
    """Rebuild a synthesis-grade WorkerResult from a checkpoint record."""
    from tasker.workers.base import ModelUsage, WorkerResult, WorkerStatus

    return WorkerResult(
        task_id=record["task_id"],
        worker_id=record["worker_id"],
        status=WorkerStatus(record["status"]),
        output=record["output"],
        tool_results=[],
        usage=ModelUsage(0, 0, 0.0),
        duration_ms=record["duration_ms"],
    )


async def _execute_steps(
    task: str,
    plan,
    start_index: int,
    completed_records: list[dict],
    *,
    workers: list,
    mode_name: str,
    profile_name: str,
    config,
    budget,
    session_mgr,
    concurrency_mgr,
    provider_map,
    delegation=None,
) -> tuple[list, bool]:
    """
    Drive plan steps from start_index, calling SessionManager.tick() before
    every dispatch (SDD 9.1). On a PAUSE/HOLD directive: checkpoint the
    in-progress plan, run the full pause flow, and return (results, True).
    completed_records is mutated in place so the checkpoint carries every
    finished step, including ones completed before a resume.

    *delegation* (SDD 5.7c) is threaded into every step's run_tool_loop()
    call unchanged -- depth only increases when a step's worker actually
    calls DELEGATE_AGENT (see DelegationContext.child()), not per step.
    """
    from datetime import datetime

    from tasker.session.checkpoint import Checkpoint
    from tasker.tools.bundles import get_definitions, narrow_bundle_to_step
    from tasker.tools.honesty import check_research_grounding, check_side_effect_honesty
    from tasker.tools.loop import run_tool_loop
    from tasker.workers.base import SessionDirective, WorkerStatus, WorkerTask
    from tasker.workers.registry import WorkerSelector

    results = []
    for step in plan.steps:
        if step.index < start_index:
            continue

        directive = session_mgr.tick()
        if directive in (SessionDirective.PAUSE, SessionDirective.HOLD):
            cp = Checkpoint.new(
                mode=mode_name,
                hardware_profile=profile_name,
                original_task=task,
                budget_snapshot=budget.snapshot(),
                plan=plan,
                completed_steps=list(completed_records),
                current_step_index=step.index,
                resume_at=budget.window_start + budget.window_duration,
                auto_resume=False,
            )
            await session_mgr.pause(cp)
            print(
                f"\n⏸  Session budget exhausted ({budget.usage_pct:.1%}) — paused "
                f"before step {step.index}.\n"
                f"   Checkpoint: {cp.id}\n"
                f"   Resume:     tasker resume {cp.id}   (or: tasker resume --last)"
            )
            return results, True

        throttled = directive == SessionDirective.CONTINUE_LOCAL_ONLY
        if throttled:
            print(f"  [throttle] budget at {budget.usage_pct:.1%} — routing local-biased")

        print(f"  Step {step.index}: {step.description[:70]}...")
        try:
            worker = WorkerSelector.select(
                workers,
                step.required_capabilities,
                config.mode.routing_policy,
                config.mode.privacy_tier,
                slots_available=concurrency_mgr.slots_available,
                should_throttle=throttled,
            )
        except Exception as exc:
            print(f"  Worker selection failed: {exc}")
            continue

        step_tools = get_definitions(
            narrow_bundle_to_step(config.mode.tool_bundle, step.description, task)
        )
        wt = WorkerTask(
            task_id=str(uuid.uuid4()),
            step_index=step.index,
            role=step.role,
            instruction=step.description,
            tools=step_tools,
            context={},
            routing_policy=config.mode.routing_policy,
            privacy_tier=config.mode.privacy_tier,
        )
        provider = provider_map.get(worker.provider)
        if provider is None:
            print(f"  No provider for {worker.provider.value}")
            continue
        try:
            result = await run_tool_loop(wt, worker, provider, cwd=Path.cwd(), delegation=delegation)
            before = result.output
            result = check_side_effect_honesty(result, task, step.description)
            if result.output != before:
                print(f"  [warn] step {step.index}: unverified side-effect claim (no tool calls)")
            if mode_name == "research":
                before = result.output
                result.output = check_research_grounding(result.output, result.tool_results)
                if result.output != before:
                    print(f"  [warn] step {step.index}: unverified -- no sources retrieved")
            status_str = "ok" if result.status == WorkerStatus.SUCCESS else result.status.value
            print(
                f"  [{status_str}] {worker.id} ({result.duration_ms}ms, "
                f"budget {budget.usage_pct:.1%})"
            )
            results.append(result)
            completed_records.append(_serialize_step_result(step.index, result))
        except Exception as exc:
            print(f"  Execution error: {exc}")

    return results, False


def _search_backend_configured() -> bool:
    """RESEARCH mode grounding (SDD 5.1a): whether WEB_SEARCH can actually
    do anything. Checked live, not cached -- BRAVE_API_KEY could be set
    or unset between REPL commands in the same process."""
    return bool(os.environ.get("BRAVE_API_KEY"))


def _enforce_research_grounding(plan, mode_name: str, search_configured: bool):
    """
    RESEARCH mode grounding (SDD 5.1a), point 2: if no step in *plan*
    requires Capability.SEARCH, prepend a real retrieval step rather than
    trusting the planning prompt's own grounding instructions to have
    been followed -- a code-level backstop, not just prompt engineering.
    A missing search backend makes this a no-op (nothing to force a
    retrieval step toward); every other mode is untouched.
    """
    if mode_name != "research" or not search_configured:
        return plan

    from tasker.workers.base import Capability
    if any(Capability.SEARCH in s.required_capabilities for s in plan.steps):
        return plan

    import dataclasses as _dc

    from tasker.workers.base import AgentRole, PlanStep, StepStatus

    retrieval_step = PlanStep(
        index=0,
        description=f"Search for and retrieve real, current sources relevant to: {plan.original_task}",
        role=AgentRole.WORKER,
        required_capabilities={Capability.TOOL_USE, Capability.SEARCH},
        depends_on=[],
        status=StepStatus.PENDING,
    )
    shifted = [
        _dc.replace(s, index=s.index + 1, depends_on=[d + 1 for d in s.depends_on])
        for s in plan.steps
    ]
    new_steps = [retrieval_step] + shifted
    new_graph = {s.index: s.depends_on for s in new_steps}
    return _dc.replace(plan, steps=new_steps, dependency_graph=new_graph)


def _apply_research_synthesis_honesty(output: str, mode_name: str, results: list) -> str:
    """RESEARCH mode grounding (SDD 5.1a), point 4, applied to the FINAL
    synthesized answer -- checked against the union of every step's tool
    calls, since a claim in the synthesized text may draw on sources
    retrieved in an earlier step than the one that stated the claim."""
    if mode_name != "research":
        return output
    from tasker.tools.honesty import check_research_grounding

    all_tool_results = [tr for r in results for tr in r.tool_results]
    return check_research_grounding(output, all_tool_results)


async def _run_task(
    task: str,
    mode_name: str,
    registry: WorkerRegistry,
    store: CheckpointStore,
    policy_override=None,
    *,
    pipeline=None,
    delegation=None,
) -> str | None:
    """
    Dispatch a task through the orchestrator → provider pipeline. Returns
    the synthesized output string on success, None otherwise (planning
    failure, pause, no results, or a synthesis error) -- callers that
    only care about the printed transcript (cli/shell.py's REPL/CLI) can
    ignore the return value; DELEGATE_AGENT's executor (SDD 5.7c) is the
    one caller that needs it, to hand a sub-task's real result back to
    the parent worker as tool output.

    pipeline: optional pre-built _build_pipeline() tuple. cli/shell.py's
    one-shot CLI/REPL always leaves this None (fresh budget/session per
    call, unchanged behavior). tasker/tui/app.py's REPL passes in a
    per-mode cached pipeline so budget usage accumulates across turns
    within the same mode, closer to how a real interactive session should
    read -- see that module's docstring for the caching/eviction contract.

    delegation: optional DelegationContext (SDD 5.7c). None (the top-level
    call from a REPL/CLI dispatch) means a fresh depth-0 context is built
    here so this task's own steps can delegate; a sub-agent's own
    recursive _run_task() call passes its child() context instead, so
    depth/spawn-count/pipeline all carry through correctly.
    """
    from tasker.workers.base import Capability, ClassifierResult, TaskType

    if pipeline is None:
        pipeline = _build_pipeline(mode_name, store, policy_override)
        if pipeline is None:
            return None
    profile_name, config, budget, session_mgr, concurrency_mgr, provider_map, orchestrator = pipeline

    if delegation is None:
        from tasker.runtime.delegation import DelegationContext
        delegation = DelegationContext(
            registry=registry, store=store, mode_name=mode_name, pipeline=pipeline,
        )

    # Exclude workers whose provider has no wired implementation in this
    # pipeline's provider_map -- e.g. a Fugu/Anthropic/OpenAI worker when
    # only OllamaProvider is wired -- *before* planning/selection, not
    # after a step has already been planned around one (SDD 5.5 gap found
    # live: selection picked fugu-ultra, provider_map.get() returned None,
    # the step silently failed with "No provider for fugu" and the whole
    # run ended in "No results to synthesize.").
    registry.apply_provider_availability(provider_map)

    all_workers = registry.list_all()
    classifier_output = ClassifierResult(
        task_type=TaskType.CONVERSATIONAL,
        complexity_score=0.3,
        required_capabilities={Capability.TOOL_USE},
        suggested_workers=[],
        estimated_duration_s=15.0,
    )

    print(f"[{mode_name}] Planning with {type(orchestrator).__name__}...")
    try:
        plan = await orchestrator.plan(task, classifier_output, all_workers)
    except Exception as exc:
        print(f"Planning failed: {type(exc).__name__}: {exc}")
        return None
    plan = _enforce_research_grounding(plan, mode_name, _search_backend_configured())

    fallback_note = "  (fallback: NanoOrchestrator template — model plan unparseable)" \
        if plan.used_fallback else ""
    print(f"  {len(plan.steps)} step(s), used_fallback={plan.used_fallback}{fallback_note}")

    completed_records: list[dict] = []
    results, paused = await _execute_steps(
        task, plan, 0, completed_records,
        workers=all_workers,
        mode_name=mode_name, profile_name=profile_name, config=config,
        budget=budget, session_mgr=session_mgr,
        concurrency_mgr=concurrency_mgr, provider_map=provider_map,
        delegation=delegation,
    )
    if paused:
        return None

    if not results:
        print("No results to synthesize.")
        return None

    print("\nSynthesizing...")
    try:
        output = await orchestrator.synthesize(task, results)
        output = _apply_research_synthesis_honesty(output, mode_name, results)
        print(f"\n{output}")
        return output
    except Exception as exc:
        print(f"Synthesis error: {exc}")
        return None


async def _resume_task(
    checkpoint_id: str,
    registry: WorkerRegistry,
    store: CheckpointStore,
    policy_override=None,
) -> None:
    """
    Real resume flow (SDD 9.4): load the checkpoint, rebuild the pipeline for
    the checkpointed mode (fresh 5-hour budget window — a resume normally
    happens after the window reset that caused the pause), replay completed
    step results, and continue from current_step_index.
    """
    cp = store.load(checkpoint_id)
    if cp is None:
        print(f"Checkpoint not found: {checkpoint_id}")
        return

    print(
        f"Resuming checkpoint {cp.id}  [{cp.mode}]  task={cp.original_task!r}\n"
        f"  paused with budget at {cp.budget_snapshot.usage_pct:.0%} "
        f"({cp.budget_snapshot.plan} plan), "
        f"{len(cp.completed_steps)}/{len(cp.plan.steps)} step(s) completed"
    )

    # Checkpoints store the profile *file* name so the resumed process can
    # reload the exact same hardware profile regardless of this process's
    # TASKER_PROFILE. Override the env var for _build_pipeline's benefit.
    os.environ["TASKER_PROFILE"] = cp.hardware_profile
    pipeline = _build_pipeline(cp.mode, store, policy_override)
    if pipeline is None:
        return
    profile_name, config, budget, session_mgr, concurrency_mgr, provider_map, orchestrator = pipeline
    registry.apply_provider_availability(provider_map)

    from tasker.runtime.delegation import DelegationContext
    delegation = DelegationContext(registry=registry, store=store, mode_name=cp.mode, pipeline=pipeline)

    # Run the real SessionManager resume flow (notifier event, budget window
    # validation, PAUSED -> RESUMING -> RUNNING) against the loaded checkpoint.
    resumed = await session_mgr.resume(cp.id)
    if resumed is None:
        print(f"SessionManager could not load checkpoint {cp.id}")
        return

    prior_results = [_deserialize_step_result(r) for r in cp.completed_steps]
    completed_records: list[dict] = list(cp.completed_steps)

    new_results, paused = await _execute_steps(
        cp.original_task, cp.plan, cp.current_step_index, completed_records,
        workers=registry.list_all(),
        mode_name=cp.mode, profile_name=cp.hardware_profile, config=config,
        budget=budget, session_mgr=session_mgr,
        concurrency_mgr=concurrency_mgr, provider_map=provider_map,
        delegation=delegation,
    )
    if paused:
        return

    results = prior_results + new_results
    if not results:
        print("No results to synthesize.")
        return

    print("\nSynthesizing...")
    try:
        output = await orchestrator.synthesize(cp.original_task, results)
        output = _apply_research_synthesis_honesty(output, cp.mode, results)
        print(f"\n{output}")
    except Exception as exc:
        print(f"Synthesis error: {exc}")


# --------------------------------------------------------------------------- #
# CHAT mode direct dispatch (SDD 5.3a)
# --------------------------------------------------------------------------- #

DEFAULT_CHAT_WORKER_ID = "lfm2.5-local"

_EFFORT_LEVELS = ("low", "med", "high")
_DEFAULT_EFFORT = "med"


def _effort_policy(effort: str):
    from tasker.workers.base import RoutingPolicy

    return {
        "low":  RoutingPolicy.SPEED_OPTIMIZED,
        "med":  RoutingPolicy.COST_OPTIMIZED,
        "high": RoutingPolicy.CAPABILITY_FIRST,
    }.get(effort, RoutingPolicy.COST_OPTIMIZED)


def _select_chat_worker(
    registry: WorkerRegistry,
    config,
    concurrency_mgr,
    model_override: str | None,
    effort: str,
):
    """
    CHAT mode's worker choice (SDD 5.3a). /model always wins when set.
    Otherwise the default is the always-loaded local worker as long as
    effort is "med" (the REPL default) -- redirecting to a different,
    often costlier, worker only happens on explicit user intent, either
    /model or a non-default /effort.
    """
    from tasker.workers.base import Capability, TaskerPolicyError
    from tasker.workers.registry import WorkerSelector

    if model_override:
        worker = registry.get(model_override)
        if worker is None or not worker.available:
            raise TaskerPolicyError(
                f"Model '{model_override}' not found or unavailable — "
                f"use /workers to see registered worker ids."
            )
        return worker

    default = registry.get(DEFAULT_CHAT_WORKER_ID)
    if effort == _DEFAULT_EFFORT and default is not None and default.available:
        return default

    return WorkerSelector.select(
        registry.list_all(), {Capability.TOOL_USE}, _effort_policy(effort),
        config.mode.privacy_tier, slots_available=concurrency_mgr.slots_available,
        should_throttle=False,
    )


async def _run_chat_task(
    task: str,
    registry: WorkerRegistry,
    store: CheckpointStore,
    history: list[dict],
    policy_override=None,
    *,
    pipeline=None,
    model_override: str | None = None,
    effort: str = _DEFAULT_EFFORT,
    context_override: int | None = None,
) -> None:
    """
    CHAT mode direct dispatch (SDD 5.3a): one call to the chat worker with
    the user's raw message and the running REPL conversation history --
    no orchestrator plan()/synthesize() calls. Root cause fixed: those
    two extra LLM calls added ~tens of seconds on top of the worker's own
    turn, and the worker was receiving a planner-generated step
    description instead of the user's actual message.

    *history* is mutated in place (user turn appended before dispatch,
    assistant turn appended after a successful reply) so the caller's
    REPL session accumulates real multi-turn context across calls.

    *context_override* -- the REPL's /context <tokens> lever (SDD
    5.6.1a) -- is threaded into WorkerTask.context["num_ctx_override"],
    which OllamaProvider.execute() honors ahead of its own VRAM-ceiling
    resolution.
    """
    from tasker.tools.bundles import get_definitions, narrow_bundle_to_step
    from tasker.tools.honesty import check_side_effect_honesty
    from tasker.tools.loop import run_tool_loop
    from tasker.workers.base import AgentRole, WorkerStatus, WorkerTask

    if pipeline is None:
        pipeline = _build_pipeline("chat", store, policy_override)
        if pipeline is None:
            return
    profile_name, config, budget, session_mgr, concurrency_mgr, provider_map, orchestrator = pipeline
    registry.apply_provider_availability(provider_map)

    try:
        worker = _select_chat_worker(registry, config, concurrency_mgr, model_override, effort)
    except Exception as exc:
        print(f"Worker selection failed: {exc}")
        return

    provider = provider_map.get(worker.provider)
    if provider is None:
        print(f"No provider for {worker.provider.value}")
        return

    history.append({"role": "user", "content": task})
    step_tools = get_definitions(narrow_bundle_to_step(config.mode.tool_bundle, task))
    wt_context: dict = {"messages": list(history)}
    if context_override:
        wt_context["num_ctx_override"] = context_override
    wt = WorkerTask(
        task_id=str(uuid.uuid4()),
        step_index=0,
        role=AgentRole.WORKER,
        instruction=task,
        tools=step_tools,
        context=wt_context,
        routing_policy=config.mode.routing_policy,
        privacy_tier=config.mode.privacy_tier,
    )
    try:
        result = await run_tool_loop(wt, worker, provider, cwd=Path.cwd())
    except Exception as exc:
        print(f"Execution error: {exc}")
        history.pop()   # the user turn never got a reply -- don't poison future context
        return

    result = check_side_effect_honesty(result, task)
    if result.status != WorkerStatus.SUCCESS:
        print(f"[{result.status.value}] {result.reason or '(no reason given)'}")
        history.pop()
        return

    answer = result.output or "(no output)"
    print(f"\n{answer}")
    history.append({"role": "assistant", "content": answer})

"""
tasker.api.server
------------------
OpenAI-compatible HTTP API surface for the Ollama Tasker.
Uses aiohttp.web (already a project dependency for client calls).

Endpoints:
  POST /v1/chat/completions
      model field: "tasker/<mode>"  e.g. "tasker/cowork", "tasker/chat"
      tools: standard OpenAI tool definitions
      stream: bool (non-streaming response returned; streaming flagged as TODO)

  GET  /v1/models
      Returns the 5 registered TaskerMode instances as OpenAI model entries.

  GET  /v1/workers
      Harness extension: returns WorkerRegistry.list_all() as JSON.

The API layer is request/response translation only.  Actual execution is
delegated to mode runners (CoworkRunner etc.) and the orchestrator tier
selected by ModeConfigurator.  When no live workers are registered the
endpoint returns a structured stub response so callers can exercise the
routing logic without real API keys.

`main()` (the `tasker-api` console script) wires a real, single-step
worker dispatch into every request the same way cli/shell.py's main()
wires _run_task()'s dispatch loop: profile resolution (TASKER_PROFILE,
default tier1_tasker), OLLAMA_BASE_URL env override, a provider_map keyed
by ProviderType, a shared OllamaSessionBudget/OllamaCloudConcurrencyManager
on the OllamaProvider, and hardware-cache GPU availability cross-check on
the worker registry (SDD_ADDENDUM_7.5.md A.3.4). See B.2 in
SDD_ADDENDUM_PHASE8.md for the console-script convention this follows.

Not yet wired to a real ExecutionPlan from an orchestrator tier (still
`_stub_plan` -- a single step covering the whole request) -- that is
orchestrator work, out of scope for making the server launchable.
See SDD Section 7.5.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web

from tasker.modes.base import TaskerMode
from tasker.modes.chat import CHAT_MODE
from tasker.modes.code import CODE_MODE
from tasker.modes.cowork import COWORK_MODE, CoworkRunner
from tasker.modes.research import RESEARCH_MODE
from tasker.modes.secure import SECURE_MODE
from tasker.session.budget import OllamaSessionBudget
from tasker.session.checkpoint import CheckpointStore
from tasker.session.manager import SessionManager
from tasker.session.notifier import LogNotifier
from tasker.workers.base import (
    AgentRole,
    Capability,
    ExecutionPlan,
    OllamaPlan,
    PlanStep,
    StepStatus,
    WorkerStatus,
    WorkerTask,
)
from tasker.workers.registry import WorkerRegistry, WorkerSelector

_DEFAULT_REGISTRY_YAML = (
    Path(__file__).parent.parent.parent / "config" / "workers" / "worker_registry.yaml"
)

_MODES: dict[str, TaskerMode] = {
    "chat":     CHAT_MODE,
    "code":     CODE_MODE,
    "cowork":   COWORK_MODE,
    "research": RESEARCH_MODE,
    "secure":   SECURE_MODE,
}

_STUB_PLAN_STEPS = 1   # how many stub steps to create for no-worker execution


# --------------------------------------------------------------------------- #
# Request / response helpers
# --------------------------------------------------------------------------- #

def _openai_model_entry(mode: TaskerMode) -> dict:
    return {
        "id": f"tasker/{mode.name}",
        "object": "model",
        "created": 0,
        "owned_by": "ollama-tasker",
    }


def _openai_completion(model: str, content: str, finish_reason: str = "stop") -> dict:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _error_response(status: int, message: str) -> web.Response:
    return web.Response(
        status=status,
        content_type="application/json",
        body=json.dumps({"error": {"message": message, "type": "invalid_request_error"}}).encode(),
    )


def _parse_task(messages: list[dict]) -> str:
    """Extract the task string from the last user message."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                parts = [c.get("text", "") for c in content if isinstance(c, dict)]
                return " ".join(parts).strip()
            return str(content).strip()
    return ""


def _stub_plan(task: str) -> ExecutionPlan:
    """
    Minimal single-step plan used when no live orchestrator is available.

    description carries the FULL task text (not truncated) -- when a real
    step_fn is wired (see _make_live_step_fn), this description becomes the
    worker's actual instruction, so truncating it would silently cut off
    the user's real prompt.
    """
    step = PlanStep(
        index=0,
        description=task,
        role=AgentRole.WORKER,
        required_capabilities={Capability.TOOL_USE},
        depends_on=[],
        status=StepStatus.PENDING,
    )
    plan_id = str(uuid.uuid4())
    return ExecutionPlan(
        plan_id=plan_id,
        original_task=task,
        steps=[step],
        dependency_graph={0: []},
    )


def _make_live_step_fn(mode: TaskerMode, workers: list, provider_map: dict, concurrency_mgr):
    """
    Build a real async (PlanStep) -> str dispatcher for CoworkRunner,
    covering the same WorkerSelector -> WorkerTask -> run_tool_loop path
    cli/shell.py's _execute_steps() drives for the CLI. Used by
    _handle_completions() in production (main()-launched servers); tests
    override with their own _step_fn via create_app().
    """
    from tasker.tools.bundles import get_definitions, narrow_bundle_to_step
    from tasker.tools.loop import run_tool_loop

    async def step_fn(step: PlanStep) -> str:
        worker = WorkerSelector.select(
            workers,
            step.required_capabilities,
            mode.routing_policy,
            mode.privacy_tier,
            slots_available=concurrency_mgr.slots_available,
            should_throttle=False,
        )
        step_tools = get_definitions(
            narrow_bundle_to_step(mode.tool_bundle, step.description, step.description)
        )
        wt = WorkerTask(
            task_id=str(uuid.uuid4()),
            step_index=step.index,
            role=step.role,
            instruction=step.description,
            tools=step_tools,
            context={},
            routing_policy=mode.routing_policy,
            privacy_tier=mode.privacy_tier,
        )
        provider = provider_map.get(worker.provider)
        if provider is None:
            raise RuntimeError(f"No provider registered for {worker.provider.value!r}")

        result = await run_tool_loop(wt, worker, provider, cwd=Path.cwd())
        if result.status != WorkerStatus.SUCCESS:
            reason = f": {result.reason}" if result.reason else ""
            raise RuntimeError(f"Worker {worker.id!r} returned {result.status.value}{reason}")
        return result.output or ""

    return step_fn


# --------------------------------------------------------------------------- #
# Route handlers
# --------------------------------------------------------------------------- #

async def _handle_models(request: web.Request) -> web.Response:
    allowed = request.app.get("allowed_modes")
    modes = (
        [m for name, m in _MODES.items() if name in allowed]
        if allowed is not None else list(_MODES.values())
    )
    data = {"object": "list", "data": [_openai_model_entry(m) for m in modes]}
    return web.json_response(data)


async def _handle_workers(request: web.Request) -> web.Response:
    registry: WorkerRegistry = request.app["registry"]
    workers = registry.list_all()
    data = [
        {
            "id": w.id,
            "model_id": w.model_id,
            "compute_location": w.compute_location.value,
            "capabilities": [c.value for c in w.capabilities],
            "available": w.available,
        }
        for w in workers
    ]
    return web.json_response({"object": "list", "data": data})


async def _handle_completions(request: web.Request) -> web.Response:
    try:
        body: dict = await request.json()
    except Exception:
        return _error_response(400, "Request body must be valid JSON.")

    model_field: str = body.get("model", "")
    if not model_field.startswith("tasker/"):
        return _error_response(400, f"model must be 'tasker/<mode>', got: {model_field!r}")

    mode_name = model_field[len("tasker/"):]
    if mode_name not in _MODES:
        return _error_response(
            400,
            f"Unknown mode {mode_name!r}. Valid modes: {list(_MODES.keys())}",
        )
    allowed = request.app.get("allowed_modes")
    if allowed is not None and mode_name not in allowed:
        return _error_response(
            400,
            f"Mode {mode_name!r} not enabled on this server instance "
            f"(started with --mode {next(iter(allowed))!r}).",
        )

    messages: list[dict] = body.get("messages", [])
    task = _parse_task(messages)
    if not task:
        return _error_response(400, "No user message found in messages array.")

    store: CheckpointStore     = request.app["store"]
    registry: WorkerRegistry   = request.app["registry"]
    step_fn                    = request.app.get("_step_fn")   # injectable for tests

    budget = OllamaSessionBudget(
        plan=OllamaPlan.PRO,
        window_start=datetime.now(tz=timezone.utc),
    )
    session_mgr = SessionManager(
        budget=budget,
        store=store,
        notifier=LogNotifier("tasker.api"),
    )
    mode = _MODES[mode_name]

    # Test override (create_app(_step_fn=...)) always wins. Otherwise, if
    # main() wired a real provider_map/concurrency_mgr into app state,
    # dispatch through the same WorkerSelector -> run_tool_loop path
    # cli/shell.py uses. With neither, fall back to the documented stub
    # response (no live workers registered).
    if step_fn is None:
        provider_map    = request.app.get("provider_map")
        concurrency_mgr = request.app.get("concurrency_mgr")
        if provider_map is not None and concurrency_mgr is not None:
            step_fn = _make_live_step_fn(mode, registry.list_all(), provider_map, concurrency_mgr)

    # For COWORK mode, use CoworkRunner for proper checkpoint/session lifecycle.
    # Other modes: run through the same step loop via a minimal CoworkRunner-like
    # wrapper — this keeps the API layer thin and avoids reimplementing dispatch.
    runner = CoworkRunner(
        mode=mode,
        session_mgr=session_mgr,
        store=store,
        hardware_profile="api",
        _step_fn=step_fn,
    )

    plan = _stub_plan(task)
    try:
        result = await runner.run(task, plan)
    except Exception as exc:
        return _error_response(500, f"{type(exc).__name__}: {exc}")

    if result is None:
        content = f"[{mode_name}] Session paused — checkpoint saved."
    else:
        content = result

    return web.json_response(_openai_completion(model_field, content))


# --------------------------------------------------------------------------- #
# App factory
# --------------------------------------------------------------------------- #

def create_app(
    registry: WorkerRegistry | None = None,
    store: CheckpointStore | None = None,
    *,
    provider_map: dict | None = None,
    concurrency_mgr=None,
    allowed_modes: set[str] | None = None,
    _step_fn=None,
) -> web.Application:
    """
    Build and return the aiohttp Application.

    registry        — WorkerRegistry to expose via GET /v1/workers.
    store           — CheckpointStore passed to CoworkRunner for pause/resume.
    provider_map    — ProviderType -> WorkerProviderBase, for real worker
                       dispatch (see _make_live_step_fn). Set by main(); tests
                       normally leave this None and pass _step_fn instead.
    concurrency_mgr — OllamaCloudConcurrencyManager shared across requests,
                       required alongside provider_map for real dispatch.
    allowed_modes   — restrict GET /v1/models and POST /v1/chat/completions
                       to this subset of mode names (main()'s --mode flag).
                       None (default) accepts/lists all 5 modes.
    _step_fn        — optional async (PlanStep) -> str injected into
                       CoworkRunner; used by integration tests to control
                       per-step behaviour without requiring live workers.
                       Takes priority over provider_map-based dispatch.
    """
    app = web.Application()
    app["registry"] = registry or WorkerRegistry()
    app["store"]    = store    or CheckpointStore()
    if provider_map is not None:
        app["provider_map"] = provider_map
    if concurrency_mgr is not None:
        app["concurrency_mgr"] = concurrency_mgr
    if allowed_modes is not None:
        app["allowed_modes"] = allowed_modes
    if _step_fn is not None:
        app["_step_fn"] = _step_fn

    app.router.add_get("/v1/models",              _handle_models)
    app.router.add_get("/v1/workers",             _handle_workers)
    app.router.add_post("/v1/chat/completions",   _handle_completions)

    return app


# --------------------------------------------------------------------------- #
# tasker-api CLI entry point
# --------------------------------------------------------------------------- #

def main() -> None:
    """
    Entry point for the `tasker-api` console script. Wired the same way as
    cli/shell.py's main()/_build_pipeline(): profile resolution
    (TASKER_PROFILE env, default tier1_tasker), OLLAMA_BASE_URL env
    override of the profile's ollama_base_url, a provider_map keyed by
    ProviderType with a shared OllamaSessionBudget + concurrency manager on
    the OllamaProvider, and a hardware-cache GPU availability cross-check
    on the worker registry (SDD_ADDENDUM_7.5.md A.3.4) -- skipped if
    `tasker-hardware detect` has never been run on this machine, same as
    cli/shell.py.
    """
    import argparse
    import logging
    import os

    from tasker.modes.base import ModeConfigurator
    from tasker.session.concurrency import OllamaCloudConcurrencyManager
    from tasker.workers.base import ProviderType
    from tasker.workers.providers.ollama import OllamaProvider

    logging.basicConfig(
        level=os.environ.get("TASKER_LOG_LEVEL", "WARNING").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        prog="tasker-api",
        description="Ollama Tasker OpenAI-compatible API server.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8555, help="Bind port (default: 8555)")
    parser.add_argument(
        "--mode", default=None, choices=sorted(_MODES.keys()),
        help="Restrict the server to a single mode (default: all 5 modes, "
             "selected per-request via the model field 'tasker/<mode>').",
    )
    args = parser.parse_args()

    profile_name = os.environ.get("TASKER_PROFILE", "tier1_tasker")
    configurator = ModeConfigurator()
    try:
        profile = configurator.load_profile(profile_name)
    except Exception as exc:
        print(f"Config error: {exc}")
        raise SystemExit(1)

    # OLLAMA_BASE_URL overrides the profile YAML -- same rule as
    # cli/shell.py's _build_pipeline (a machine may run Ollama elsewhere,
    # e.g. Designlab1's WSL server on 127.0.0.1:11435).
    base_url = os.environ.get("OLLAMA_BASE_URL") or profile.ollama_base_url
    budget = OllamaSessionBudget(plan=profile.ollama_plan, window_start=datetime.now(tz=timezone.utc))
    concurrency_mgr = OllamaCloudConcurrencyManager(profile.ollama_plan)
    provider_map = {ProviderType.OLLAMA: OllamaProvider(base_url, concurrency_mgr, budget)}

    if _DEFAULT_REGISTRY_YAML.exists():
        registry = WorkerRegistry.load_from_yaml(_DEFAULT_REGISTRY_YAML)
        # Phase 7.5.6 (SDD_ADDENDUM_7.5.md A.3.4): cross-check requires_gpu
        # workers against cached hardware detection, if any exists for this
        # machine -- mirrors cli/shell.py's main(). Uses the cache, never a
        # fresh detect_gpu() call, to avoid subprocess cost on every launch.
        from tasker.config.detect import load_cached_detection, load_cached_gpu_info

        if load_cached_detection() is not None:
            registry.apply_gpu_availability(load_cached_gpu_info())
    else:
        registry = WorkerRegistry()

    allowed_modes = {args.mode} if args.mode else None
    app = create_app(
        registry=registry,
        store=CheckpointStore(),
        provider_map=provider_map,
        concurrency_mgr=concurrency_mgr,
        allowed_modes=allowed_modes,
    )

    print(
        f"tasker-api: profile={profile_name!r} ollama_base_url={base_url!r} "
        f"plan={profile.ollama_plan.value} mode={args.mode or 'all'} "
        f"-> http://{args.host}:{args.port}",
        flush=True,
    )
    web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

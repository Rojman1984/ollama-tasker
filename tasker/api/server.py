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
See SDD Section 7.5.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone

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
)
from tasker.workers.registry import WorkerRegistry

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
    """Minimal single-step plan used when no live orchestrator is available."""
    step = PlanStep(
        index=0,
        description=f"Execute: {task[:80]}",
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


# --------------------------------------------------------------------------- #
# Route handlers
# --------------------------------------------------------------------------- #

async def _handle_models(request: web.Request) -> web.Response:
    data = {"object": "list", "data": [_openai_model_entry(m) for m in _MODES.values()]}
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
    result = await runner.run(task, plan)

    if result is None:
        content = f"[{mode_name}] Session paused — checkpoint saved."
        finish_reason = "stop"
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
    _step_fn=None,
) -> web.Application:
    """
    Build and return the aiohttp Application.

    registry  — WorkerRegistry to expose via GET /v1/workers.
    store     — CheckpointStore passed to CoworkRunner for pause/resume.
    _step_fn  — optional async (PlanStep) -> str injected into CoworkRunner;
                used by integration tests to control per-step behaviour without
                requiring live workers.
    """
    app = web.Application()
    app["registry"] = registry or WorkerRegistry()
    app["store"]    = store    or CheckpointStore()
    if _step_fn is not None:
        app["_step_fn"] = _step_fn

    app.router.add_get("/v1/models",              _handle_models)
    app.router.add_get("/v1/workers",             _handle_workers)
    app.router.add_post("/v1/chat/completions",   _handle_completions)

    return app

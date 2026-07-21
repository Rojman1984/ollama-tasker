"""
Integration tests -- OpenAI-compatible API server (tasker/api/server.py)
Phase 7 -- SDD Section 7.5

Uses aiohttp.test_utils to spin up a real in-process server.
A _step_fn is injected so tests don't require live workers.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from tasker.api.server import create_app
from tasker.session.checkpoint import CheckpointStore
from tasker.session.concurrency import OllamaCloudConcurrencyManager
from tasker.workers.base import (
    Capability,
    ComputeLocation,
    LatencyClass,
    ModelUsage,
    OllamaPlan,
    PlanStep,
    ProviderType,
    ToolProtocol,
    WorkerManifest,
    WorkerResult,
    WorkerStatus,
)
from tasker.workers.registry import WorkerRegistry


# ------------------------------------------------------------------ #
# Shared step function: echoes step description as output
# ------------------------------------------------------------------ #

async def _echo_step(step: PlanStep) -> str:
    return f"completed: {step.description}"


# ------------------------------------------------------------------ #
# Base test case
# ------------------------------------------------------------------ #

class ApiServerTestCase(AioHTTPTestCase):

    async def get_application(self) -> web.Application:
        self._tmp = tempfile.TemporaryDirectory()
        store = CheckpointStore(store_dir=Path(self._tmp.name))
        registry = WorkerRegistry()
        return create_app(registry=registry, store=store, _step_fn=_echo_step)

    async def asyncTearDown(self):
        await super().asyncTearDown()
        self._tmp.cleanup()


# ------------------------------------------------------------------ #
# GET /v1/models
# ------------------------------------------------------------------ #

class TestGetModels(ApiServerTestCase):

    async def test_returns_200(self):
        resp = await self.client.get("/v1/models")
        self.assertEqual(resp.status, 200)

    async def test_returns_all_five_modes(self):
        resp = await self.client.get("/v1/models")
        body = await resp.json()
        self.assertEqual(body["object"], "list")
        ids = {m["id"] for m in body["data"]}
        for mode in ("tasker/chat", "tasker/code", "tasker/cowork", "tasker/research", "tasker/secure"):
            self.assertIn(mode, ids)
        self.assertEqual(len(body["data"]), 5)

    async def test_model_entry_shape(self):
        resp = await self.client.get("/v1/models")
        body = await resp.json()
        entry = body["data"][0]
        self.assertIn("id", entry)
        self.assertIn("object", entry)
        self.assertEqual(entry["object"], "model")
        self.assertEqual(entry["owned_by"], "ollama-tasker")


# ------------------------------------------------------------------ #
# GET /v1/workers
# ------------------------------------------------------------------ #

class TestGetWorkers(ApiServerTestCase):

    async def test_returns_200(self):
        resp = await self.client.get("/v1/workers")
        self.assertEqual(resp.status, 200)

    async def test_empty_registry_returns_empty_list(self):
        resp = await self.client.get("/v1/workers")
        body = await resp.json()
        self.assertEqual(body["object"], "list")
        self.assertEqual(body["data"], [])


# ------------------------------------------------------------------ #
# POST /v1/chat/completions
# ------------------------------------------------------------------ #

class TestPostCompletions(ApiServerTestCase):

    def _payload(self, model: str, user_msg: str, **extra) -> dict:
        return {
            "model": model,
            "messages": [{"role": "user", "content": user_msg}],
            **extra,
        }

    async def test_returns_200_for_valid_request(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json=self._payload("tasker/chat", "Hello, world"),
        )
        self.assertEqual(resp.status, 200)

    async def test_response_is_openai_shape(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json=self._payload("tasker/chat", "write a poem"),
        )
        body = await resp.json()
        self.assertEqual(body["object"], "chat.completion")
        self.assertIn("id", body)
        self.assertTrue(body["id"].startswith("chatcmpl-"))
        choices = body["choices"]
        self.assertEqual(len(choices), 1)
        self.assertEqual(choices[0]["message"]["role"], "assistant")
        self.assertIsInstance(choices[0]["message"]["content"], str)
        self.assertEqual(choices[0]["finish_reason"], "stop")

    async def test_model_field_echoed_in_response(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json=self._payload("tasker/code", "fix the bug"),
        )
        body = await resp.json()
        self.assertEqual(body["model"], "tasker/code")

    async def test_all_five_modes_accepted(self):
        for mode in ("chat", "code", "cowork", "research", "secure"):
            resp = await self.client.post(
                "/v1/chat/completions",
                json=self._payload(f"tasker/{mode}", "test task"),
            )
            self.assertEqual(resp.status, 200, f"mode={mode} got {resp.status}")

    async def test_returns_400_for_non_tasker_model(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json=self._payload("gpt-4o", "hello"),
        )
        self.assertEqual(resp.status, 400)

    async def test_returns_400_for_unknown_mode(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json=self._payload("tasker/unknown", "hello"),
        )
        self.assertEqual(resp.status, 400)

    async def test_returns_400_for_missing_user_message(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json={"model": "tasker/chat", "messages": [{"role": "assistant", "content": "hi"}]},
        )
        self.assertEqual(resp.status, 400)

    async def test_returns_400_for_invalid_json(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            data=b"not-json",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status, 400)

    async def test_step_fn_output_appears_in_content(self):
        # _echo_step returns "completed: <description>" — should appear in response
        resp = await self.client.post(
            "/v1/chat/completions",
            json=self._payload("tasker/chat", "build me a widget"),
        )
        body = await resp.json()
        content = body["choices"][0]["message"]["content"]
        self.assertIn("completed", content)

    async def test_usage_field_present(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json=self._payload("tasker/chat", "task"),
        )
        body = await resp.json()
        self.assertIn("usage", body)
        self.assertIn("prompt_tokens", body["usage"])


# ------------------------------------------------------------------ #
# Live dispatch: real provider_map/concurrency_mgr wiring (main()'s path),
# no _step_fn override -- exercises _make_live_step_fn end-to-end with a
# fake provider standing in for the network call.
# ------------------------------------------------------------------ #

def _worker(worker_id: str = "local-w1") -> WorkerManifest:
    return WorkerManifest(
        id=worker_id,
        provider=ProviderType.OLLAMA,
        model_id="lfm2.5-thinking:latest",
        compute_location=ComputeLocation.LOCAL_HARDWARE,
        capabilities={Capability.TOOL_USE},
        tool_protocol=ToolProtocol.LFM25,
        context_window=32768,
        cost_input=0.0,
        cost_output=0.0,
        ollama_usage_level=None,
        latency_class=LatencyClass.FAST,
        available=True,
        requires_gpu=False,
        vram_mb=None,
    )


class _FakeProvider:
    """Stand-in provider for the integration tests. When used as the single
    wired OllamaProvider it must answer BOTH orchestrator plan/synthesize calls
    (which expect a JSON plan array) AND worker dispatch calls (which expect a
    plain answer). It distinguishes the two by role: THINKER -> plan JSON,
    WORKER -> plain answer."""

    def __init__(self, output: str = "real worker answer", status: WorkerStatus = WorkerStatus.SUCCESS):
        self._output = output
        self._status = status
        self.calls: list = []

    def supports(self, worker) -> bool:
        return True

    async def execute(self, task, worker) -> WorkerResult:
        self.calls.append((task, worker))
        if task.role.value == "thinker":
            # Orchestrator plan/synthesize call: return a valid single-step plan
            # so the API path actually exercises multi-step orchestration code
            # while still dispatching exactly one worker call.
            output = '[{"description": "do it", "role": "worker", "capabilities": ["tool_use"]}]'
        else:
            output = self._output if self._status == WorkerStatus.SUCCESS else None
        return WorkerResult(
            task_id=task.task_id,
            worker_id=worker.id,
            status=self._status,
            output=output,
            tool_results=[],
            usage=ModelUsage(0, 0, 0.0),
            duration_ms=5,
            reason=None if self._status == WorkerStatus.SUCCESS else "simulated failure",
        )


class LiveDispatchTestCase(unittest.IsolatedAsyncioTestCase):
    """Builds create_app() with provider_map/concurrency_mgr set (main()'s
    production path) instead of a test _step_fn override."""

    async def asyncSetUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        store = CheckpointStore(store_dir=Path(self._tmp.name))
        self.registry = WorkerRegistry()
        self.registry.register(_worker())
        self.concurrency_mgr = OllamaCloudConcurrencyManager(OllamaPlan.PRO)

    async def asyncTearDown(self):
        self._tmp.cleanup()

    def _app(self, provider, **kwargs):
        store = CheckpointStore(store_dir=Path(self._tmp.name))
        return create_app(
            registry=self.registry,
            store=store,
            provider_map={ProviderType.OLLAMA: provider},
            concurrency_mgr=self.concurrency_mgr,
            **kwargs,
        )

    async def test_live_dispatch_returns_provider_output(self):
        from aiohttp.test_utils import TestClient, TestServer

        provider = _FakeProvider(output="the real answer")
        app = self._app(provider)
        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "tasker/chat", "messages": [{"role": "user", "content": "hello"}]},
            )
            self.assertEqual(resp.status, 200)
            body = await resp.json()
        self.assertEqual(body["choices"][0]["message"]["content"], "the real answer")
        # With real orchestration wired, the provider now also answers the
        # orchestrator plan() call in addition to the worker dispatch call.
        worker_calls = [(t, w) for t, w in provider.calls if t.role.value == "worker"]
        self.assertEqual(len(worker_calls), 1)
        task, worker = worker_calls[0]
        # The worker instruction comes from the orchestrator-generated step
        # description, not the raw user prompt, in the multi-step path.
        self.assertEqual(task.instruction, "do it")
        self.assertEqual(worker.id, "local-w1")

    async def test_live_dispatch_long_prompt_not_truncated(self):
        from aiohttp.test_utils import TestClient, TestServer

        provider = _FakeProvider()
        app = self._app(provider)
        long_prompt = "x" * 200
        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "tasker/chat", "messages": [{"role": "user", "content": long_prompt}]},
            )
            self.assertEqual(resp.status, 200)
        # The orchestrator plan prompt carries the full task text;
        # the fake provider returns a fixed step description regardless.
        thinker_calls = [(t, w) for t, w in provider.calls if t.role.value == "thinker"]
        self.assertEqual(len(thinker_calls), 1)
        task, _ = thinker_calls[0]
        self.assertIn(long_prompt, task.instruction)

    async def test_live_dispatch_worker_failure_returns_500(self):
        from aiohttp.test_utils import TestClient, TestServer

        provider = _FakeProvider(status=WorkerStatus.FAILED)
        app = self._app(provider)
        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "tasker/chat", "messages": [{"role": "user", "content": "hi"}]},
            )
        self.assertEqual(resp.status, 500)

    async def test_no_provider_map_falls_back_to_stub(self):
        """Neither _step_fn nor provider_map/concurrency_mgr set -> documented
        stub response, unchanged from before this session's wiring."""
        from aiohttp.test_utils import TestClient, TestServer

        store = CheckpointStore(store_dir=Path(self._tmp.name))
        app = create_app(registry=self.registry, store=store)
        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "tasker/chat", "messages": [{"role": "user", "content": "hi"}]},
            )
            self.assertEqual(resp.status, 200)
            body = await resp.json()
        self.assertIn("[step 0:", body["choices"][0]["message"]["content"])

    async def test_step_fn_override_wins_over_provider_map(self):
        from aiohttp.test_utils import TestClient, TestServer

        async def override(step):
            return "override output"

        provider = _FakeProvider()
        app = self._app(provider, _step_fn=override)
        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "tasker/chat", "messages": [{"role": "user", "content": "hi"}]},
            )
            body = await resp.json()
        self.assertEqual(body["choices"][0]["message"]["content"], "override output")
        # The orchestrator still calls the provider for plan()/synthesize(),
        # but _step_fn overrides the actual step execution so no worker
        # dispatch call (role=worker) is made.
        worker_calls = [(t, w) for t, w in provider.calls if t.role.value == "worker"]
        self.assertEqual(worker_calls, [])


# ------------------------------------------------------------------ #
# allowed_modes (main()'s --mode flag)
# ------------------------------------------------------------------ #

class AllowedModesTestCase(unittest.IsolatedAsyncioTestCase):

    async def test_models_list_restricted_to_allowed_mode(self):
        from aiohttp.test_utils import TestClient, TestServer

        app = create_app(allowed_modes={"chat"})
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/v1/models")
            body = await resp.json()
        ids = {m["id"] for m in body["data"]}
        self.assertEqual(ids, {"tasker/chat"})

    async def test_completions_rejects_disallowed_mode(self):
        from aiohttp.test_utils import TestClient, TestServer

        app = create_app(allowed_modes={"chat"}, _step_fn=_echo_step)
        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "tasker/cowork", "messages": [{"role": "user", "content": "hi"}]},
            )
        self.assertEqual(resp.status, 400)

    async def test_completions_accepts_allowed_mode(self):
        from aiohttp.test_utils import TestClient, TestServer

        app = create_app(allowed_modes={"chat"}, _step_fn=_echo_step)
        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "tasker/chat", "messages": [{"role": "user", "content": "hi"}]},
            )
        self.assertEqual(resp.status, 200)


if __name__ == "__main__":
    unittest.main()

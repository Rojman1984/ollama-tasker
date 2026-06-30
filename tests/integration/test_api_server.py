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

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from tasker.api.server import create_app
from tasker.session.checkpoint import CheckpointStore
from tasker.workers.base import PlanStep
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


if __name__ == "__main__":
    unittest.main()

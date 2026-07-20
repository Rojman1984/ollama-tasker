"""
Unit tests -- tasker/setup/onboarding.py (dynamic /model onboarding).

Live-testing request: an unknown /model <worker_id> that looks like a
genuine Ollama model tag should offer to pull it via HTTP /api/pull
(never the `ollama` CLI -- CLAUDE.md's binding server rules), probe it
for tool-calling readiness, and auto-register it. No real HTTP or
registry file writes anywhere in this file -- pull, probe, and the
registry write are all injected/mocked.
"""
import unittest
from unittest import mock

from tasker.setup.onboarding import looks_like_model_tag, onboard_model, pull_model
from tasker.workers.base import (
    Capability,
    ComputeLocation,
    LatencyClass,
    ProviderType,
    ToolProtocol,
    WorkerManifest,
)
from tasker.workers.registry import WorkerRegistry


class TestLooksLikeModelTag(unittest.TestCase):

    def test_accepts_genuine_ollama_tags(self):
        self.assertTrue(looks_like_model_tag("llama3.2:3b"))
        self.assertTrue(looks_like_model_tag("qwen3:1.7b"))
        self.assertTrue(looks_like_model_tag("nemotron-3-ultra:cloud"))

    def test_rejects_registry_style_ids_without_a_colon(self):
        self.assertFalse(looks_like_model_tag("lfm2.5-local"))
        self.assertFalse(looks_like_model_tag("claude-sonnet-4-6"))
        self.assertFalse(looks_like_model_tag("fugu-ultra"))

    def test_rejects_empty_and_whitespace(self):
        self.assertFalse(looks_like_model_tag(""))
        self.assertFalse(looks_like_model_tag("has a space:tag"))

    def test_rejects_bare_colon_with_empty_side(self):
        self.assertFalse(looks_like_model_tag(":tag"))
        self.assertFalse(looks_like_model_tag("name:"))


def _pull_fn_returning(status: int, last: dict, events: list[dict] | None = None):
    async def _fn(base_url, model_name, progress_cb):
        for evt in (events or []):
            if progress_cb is not None:
                progress_cb(evt)
        return status, last
    return _fn


class TestPullModel(unittest.IsolatedAsyncioTestCase):

    async def test_success_on_final_status_success(self):
        fn = _pull_fn_returning(200, {"status": "success"})
        ok, msg = await pull_model("http://localhost:11434", "llama3.2:3b", _pull_fn=fn)
        self.assertTrue(ok)

    async def test_failure_on_non_200(self):
        fn = _pull_fn_returning(500, {})
        ok, msg = await pull_model("http://localhost:11434", "llama3.2:3b", _pull_fn=fn)
        self.assertFalse(ok)
        self.assertIn("500", msg)

    async def test_failure_on_error_field(self):
        fn = _pull_fn_returning(200, {"error": "pull model manifest: file does not exist"})
        ok, msg = await pull_model("http://localhost:11434", "nonexistent:tag", _pull_fn=fn)
        self.assertFalse(ok)
        self.assertIn("does not exist", msg)

    async def test_failure_on_unexpected_final_status(self):
        fn = _pull_fn_returning(200, {"status": "downloading"})
        ok, msg = await pull_model("http://localhost:11434", "llama3.2:3b", _pull_fn=fn)
        self.assertFalse(ok)

    async def test_exception_from_transport_reported_not_raised(self):
        async def _raising_fn(base_url, model_name, progress_cb):
            raise ConnectionError("refused")

        ok, msg = await pull_model(
            "http://localhost:11434", "llama3.2:3b", _pull_fn=_raising_fn
        )
        self.assertFalse(ok)
        self.assertIn("refused", msg)

    async def test_progress_callback_invoked_for_each_event(self):
        events = [{"status": "pulling manifest"}, {"status": "downloading"}, {"status": "success"}]
        fn = _pull_fn_returning(200, {"status": "success"}, events=events)
        seen = []
        ok, _ = await pull_model(
            "http://localhost:11434", "llama3.2:3b",
            progress_cb=seen.append, _pull_fn=fn,
        )
        self.assertTrue(ok)
        self.assertEqual(seen, events)


def _manifest(worker_id: str = "llama3.2-local") -> WorkerManifest:
    return WorkerManifest(
        id=worker_id,
        provider=ProviderType.OLLAMA,
        model_id="llama3.2:3b",
        compute_location=ComputeLocation.LOCAL_HARDWARE,
        capabilities={Capability.TOOL_USE},
        tool_protocol=ToolProtocol.NATIVE,
        context_window=8192,
        cost_input=0.0,
        cost_output=0.0,
        ollama_usage_level=None,
        latency_class=LatencyClass.FAST,
        available=True,
        requires_gpu=False,
        vram_mb=None,
    )


class _FakeReadinessResult:
    def __init__(self, supported: bool, manifest: WorkerManifest | None, protocol=ToolProtocol.NATIVE):
        self.supported = supported
        self.suggested_manifest = manifest
        self.recommended_protocol = protocol


class _FakeChecker:
    def __init__(self, result):
        self._result = result
        self.checked_with: str | None = None

    async def check(self, model_name):
        self.checked_with = model_name
        return self._result


class TestOnboardModel(unittest.IsolatedAsyncioTestCase):

    async def test_pull_failure_never_probes_or_registers(self):
        registry = WorkerRegistry()
        pull_fn = _pull_fn_returning(500, {})
        checker = _FakeChecker(_FakeReadinessResult(True, _manifest()))

        with mock.patch("tasker.setup.onboarding.write_manifest_to_registry") as m_write:
            manifest, message = await onboard_model(
                "llama3.2:3b", registry, "http://localhost:11434",
                _checker=checker, _pull_fn=pull_fn,
            )

        self.assertIsNone(manifest)
        self.assertIn("Pull failed", message)
        self.assertIsNone(checker.checked_with)
        m_write.assert_not_called()
        self.assertIsNone(registry.get("llama3.2-local"))

    async def test_pull_success_but_probe_unsupported_does_not_register(self):
        registry = WorkerRegistry()
        pull_fn = _pull_fn_returning(200, {"status": "success"})
        checker = _FakeChecker(_FakeReadinessResult(False, None))

        with mock.patch("tasker.setup.onboarding.write_manifest_to_registry") as m_write:
            manifest, message = await onboard_model(
                "llama3.2:3b", registry, "http://localhost:11434",
                _checker=checker, _pull_fn=pull_fn,
            )

        self.assertIsNone(manifest)
        self.assertIn("readiness probe", message)
        self.assertEqual(checker.checked_with, "llama3.2:3b")
        m_write.assert_not_called()

    async def test_pull_and_probe_success_registers_and_returns_manifest(self):
        registry = WorkerRegistry()
        expected = _manifest("llama3.2-local")
        pull_fn = _pull_fn_returning(200, {"status": "success"})
        checker = _FakeChecker(_FakeReadinessResult(True, expected, ToolProtocol.NATIVE))

        with mock.patch("tasker.setup.onboarding.write_manifest_to_registry") as m_write:
            manifest, message = await onboard_model(
                "llama3.2:3b", registry, "http://localhost:11434",
                _checker=checker, _pull_fn=pull_fn,
            )

        self.assertIs(manifest, expected)
        self.assertIn("Registered 'llama3.2-local'", message)
        m_write.assert_called_once()
        # registered in the live registry too, not just written to disk --
        # so the caller can select it immediately without a reload.
        self.assertIs(registry.get("llama3.2-local"), expected)

    async def test_progress_callback_threaded_through_to_pull(self):
        registry = WorkerRegistry()
        seen = []

        async def pull_fn(base_url, model_name, progress_cb):
            progress_cb({"status": "pulling manifest"})
            progress_cb({"status": "success"})
            return 200, {"status": "success"}

        checker = _FakeChecker(_FakeReadinessResult(True, _manifest()))
        with mock.patch("tasker.setup.onboarding.write_manifest_to_registry"):
            await onboard_model(
                "llama3.2:3b", registry, "http://localhost:11434",
                progress_cb=seen.append, _checker=checker, _pull_fn=pull_fn,
            )
        self.assertEqual(len(seen), 2)


if __name__ == "__main__":
    unittest.main()

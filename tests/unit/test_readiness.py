"""
Unit tests -- tasker/setup/readiness.py
Phase 8.2 (addendum numbering) -- SDD_ADDENDUM_PHASE8.md B.4

Per B.10: OllamaProvider.execute() is mocked (a fake provider object);
/api/tags and /api/show go through injected _get_fn/_post_fn fakes. No
live Ollama calls anywhere.
"""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from tasker.setup.readiness import (
    PROBE_TOOL,
    ReadinessChecker,
    assign_roles,
    format_report,
    write_manifest_to_registry,
)
from tasker.workers.base import (
    Capability,
    ComputeLocation,
    LatencyClass,
    ModelUsage,
    OllamaUsageLevel,
    ProviderType,
    ToolProtocol,
    WorkerManifest,
    WorkerResult,
    WorkerRole,
    WorkerStatus,
    WorkerToolResult,
)


def _good_call() -> WorkerToolResult:
    return WorkerToolResult(
        tool_name="get_current_time",
        tool_input={"timezone": "America/Chicago"},
        tool_output=None,
        error=None,
        duration_ms=0,
    )


def _result(
    status: WorkerStatus = WorkerStatus.SUCCESS,
    tool_results: list[WorkerToolResult] | None = None,
    output: str | None = '[{"name": "get_current_time", "arguments": {"timezone": "America/Chicago"}}]',
    duration_ms: int = 3000,
    reason: str | None = None,
) -> WorkerResult:
    return WorkerResult(
        task_id="t",
        worker_id="w",
        status=status,
        output=output,
        tool_results=tool_results if tool_results is not None else [],
        usage=ModelUsage(0, 0, 0.0),
        duration_ms=duration_ms,
        reason=reason,
    )


class _FakeProvider:
    """Returns one canned WorkerResult per probe round, keyed by protocol."""

    def __init__(self, by_protocol: dict[ToolProtocol, WorkerResult | Exception]):
        self.by_protocol = by_protocol
        self.calls: list[tuple[str, ToolProtocol]] = []

    async def execute(self, task, worker):
        self.calls.append((worker.model_id, worker.tool_protocol))
        outcome = self.by_protocol[worker.tool_protocol]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _fake_get_fn(tags: list[str]):
    async def get_fn(url):
        return 200, {"models": [{"name": n} for n in tags]}
    return get_fn


def _fake_post_fn(context_length: int | None):
    async def post_fn(url, payload):
        if context_length is None:
            return 500, {}
        return 200, {"model_info": {"llama.context_length": context_length}}
    return post_fn


def _checker(
    provider: _FakeProvider,
    *,
    tags: list[str] | None = None,
    context_length: int | None = 4096,
    registry_path: Path | None = None,
) -> ReadinessChecker:
    tags = tags if tags is not None else ["some-model:latest"]
    get_fn = _fake_get_fn(tags)
    post_fn = _fake_post_fn(context_length)

    return ReadinessChecker(
        base_url="http://localhost:11434",
        registry_path=registry_path or Path("/nonexistent/worker_registry.yaml"),
        provider=provider,
        _get_fn=get_fn,
        _post_fn=post_fn,
    )


class TestProbeRounds(unittest.TestCase):

    def test_native_success_skips_later_rounds(self):
        provider = _FakeProvider({
            ToolProtocol.NATIVE: _result(tool_results=[_good_call()], output=None),
        })
        checker = _checker(provider, tags=["some-model:latest"])
        result = asyncio.run(checker.check("some-model:latest"))

        self.assertTrue(result.supported)
        self.assertEqual(result.recommended_protocol, ToolProtocol.NATIVE)
        self.assertTrue(result.native_result.succeeded)
        self.assertFalse(result.lfm25_result.attempted)
        self.assertFalse(result.json_extract_result.attempted)
        self.assertEqual([p for _, p in provider.calls], [ToolProtocol.NATIVE])
        self.assertEqual(result.parsed_tool_call["name"], "get_current_time")
        self.assertEqual(result.parsed_tool_call["arguments"]["timezone"], "America/Chicago")

    def test_native_rejected_falls_through_to_lfm25(self):
        provider = _FakeProvider({
            ToolProtocol.NATIVE: _result(tool_results=[], output="I cannot call tools."),
            ToolProtocol.LFM25: _result(tool_results=[_good_call()]),
        })
        checker = _checker(provider)
        result = asyncio.run(checker.check("some-model:latest"))

        self.assertTrue(result.supported)
        self.assertEqual(result.recommended_protocol, ToolProtocol.LFM25)
        self.assertTrue(result.native_result.attempted)
        self.assertFalse(result.native_result.succeeded)
        self.assertTrue(result.lfm25_result.succeeded)
        self.assertFalse(result.json_extract_result.attempted)

    def test_all_rounds_rejected_yields_unsupported(self):
        provider = _FakeProvider({
            p: _result(tool_results=[], output="plain text")
            for p in (ToolProtocol.NATIVE, ToolProtocol.LFM25, ToolProtocol.JSON_EXTRACT)
        })
        checker = _checker(provider)
        result = asyncio.run(checker.check("some-model:latest"))

        self.assertFalse(result.supported)
        self.assertIsNone(result.recommended_protocol)
        self.assertIsNone(result.suggested_manifest)
        self.assertEqual(result.recommended_roles, [])
        self.assertEqual(len(provider.calls), 3)

    def test_third_round_success(self):
        provider = _FakeProvider({
            ToolProtocol.NATIVE: _result(tool_results=[]),
            ToolProtocol.LFM25: _result(tool_results=[]),
            ToolProtocol.JSON_EXTRACT: _result(tool_results=[_good_call()]),
        })
        checker = _checker(provider)
        result = asyncio.run(checker.check("some-model:latest"))

        self.assertTrue(result.supported)
        self.assertEqual(result.recommended_protocol, ToolProtocol.JSON_EXTRACT)

    def test_provider_exception_counts_as_rejection_not_crash(self):
        provider = _FakeProvider({
            ToolProtocol.NATIVE: RuntimeError("connection refused"),
            ToolProtocol.LFM25: _result(tool_results=[_good_call()]),
        })
        checker = _checker(provider)
        result = asyncio.run(checker.check("some-model:latest"))

        self.assertTrue(result.supported)
        self.assertIn("connection refused", result.native_result.error)
        self.assertEqual(result.recommended_protocol, ToolProtocol.LFM25)

    def test_wrong_tool_or_missing_required_arg_is_rejection(self):
        wrong_tool = WorkerToolResult("hallucinated", {"timezone": "UTC"}, None, None, 0)
        missing_arg = WorkerToolResult("get_current_time", {"city": "Chicago"}, None, None, 0)
        provider = _FakeProvider({
            ToolProtocol.NATIVE: _result(tool_results=[wrong_tool]),
            ToolProtocol.LFM25: _result(tool_results=[missing_arg]),
            ToolProtocol.JSON_EXTRACT: _result(tool_results=[]),
        })
        checker = _checker(provider)
        result = asyncio.run(checker.check("some-model:latest"))

        self.assertFalse(result.supported)
        self.assertFalse(result.native_result.succeeded)
        self.assertFalse(result.lfm25_result.succeeded)

    def test_failed_worker_status_is_rejection_with_reason(self):
        provider = _FakeProvider({
            ToolProtocol.NATIVE: _result(
                status=WorkerStatus.FAILED, output=None, reason="HTTP 500",
            ),
            ToolProtocol.LFM25: _result(tool_results=[_good_call()]),
        })
        checker = _checker(provider)
        result = asyncio.run(checker.check("some-model:latest"))

        self.assertEqual(result.native_result.error, "HTTP 500")
        self.assertTrue(result.supported)


class TestNotPulled(unittest.TestCase):

    def test_unpulled_model_runs_no_probes(self):
        provider = _FakeProvider({})
        checker = _checker(provider, tags=["other-model:latest"])
        result = asyncio.run(checker.check("some-model:latest"))

        self.assertFalse(result.pulled_locally)
        self.assertFalse(result.supported)
        self.assertFalse(result.native_result.attempted)
        self.assertEqual(provider.calls, [])
        report = format_report(result)
        self.assertIn("ollama pull some-model:latest", report)

    def test_cloud_model_absent_from_tags_is_still_probed(self):
        # B.4.2 cloud-model exception (live-verified): a signed-in server
        # serves :cloud models via /api/chat even when they're not in
        # /api/tags -- the pull gate applies to local models only.
        provider = _FakeProvider({
            ToolProtocol.NATIVE: _result(tool_results=[_good_call()]),
        })
        checker = _checker(provider, tags=["something-else:latest"], context_length=131072)
        result = asyncio.run(checker.check("kimi-k2.7-code:cloud"))

        self.assertFalse(result.pulled_locally)
        self.assertTrue(result.supported)
        self.assertEqual(result.recommended_protocol, ToolProtocol.NATIVE)
        report = format_report(result)
        self.assertIn("pull not required", report)
        self.assertNotIn("ollama pull", report)

    def test_tagless_name_matches_latest(self):
        provider = _FakeProvider({
            ToolProtocol.NATIVE: _result(tool_results=[_good_call()]),
        })
        checker = _checker(provider, tags=["some-model:latest"])
        result = asyncio.run(checker.check("some-model"))
        self.assertTrue(result.pulled_locally)


class TestRoleAssignment(unittest.TestCase):
    """B.4.6 rules, driven directly through assign_roles()."""

    def test_local_small_context(self):
        roles = assign_roles(ComputeLocation.LOCAL_HARDWARE, 8192, ToolProtocol.NATIVE)
        self.assertEqual(roles, [WorkerRole.BACKGROUND_AGENT, WorkerRole.EXECUTION_WORKER])

    def test_local_large_context_adds_reasoning(self):
        roles = assign_roles(ComputeLocation.LOCAL_HARDWARE, 32768, ToolProtocol.NATIVE)
        self.assertIn(WorkerRole.REASONING_WORKER, roles)
        self.assertNotIn(WorkerRole.ORCHESTRATOR, roles)

    def test_any_location_128k_adds_orchestrator(self):
        roles = assign_roles(ComputeLocation.LOCAL_HARDWARE, 128000, ToolProtocol.NATIVE)
        self.assertIn(WorkerRole.ORCHESTRATOR, roles)

    def test_cloud_large_context(self):
        roles = assign_roles(ComputeLocation.OLLAMA_CLOUD, 128000, ToolProtocol.NATIVE)
        self.assertIn(WorkerRole.REASONING_WORKER, roles)
        self.assertIn(WorkerRole.ORCHESTRATOR, roles)

    def test_lfm25_removes_orchestrator_and_confirms_execution(self):
        roles = assign_roles(ComputeLocation.LOCAL_HARDWARE, 128000, ToolProtocol.LFM25)
        self.assertNotIn(WorkerRole.ORCHESTRATOR, roles)
        self.assertIn(WorkerRole.EXECUTION_WORKER, roles)

    def test_json_extract_removes_orchestrator_on_cloud(self):
        roles = assign_roles(ComputeLocation.OLLAMA_CLOUD, 128000, ToolProtocol.JSON_EXTRACT)
        self.assertNotIn(WorkerRole.ORCHESTRATOR, roles)
        self.assertIn(WorkerRole.EXECUTION_WORKER, roles)


class TestSuggestedManifest(unittest.TestCase):

    def test_local_manifest_fields(self):
        provider = _FakeProvider({
            ToolProtocol.NATIVE: _result(tool_results=[]),
            ToolProtocol.LFM25: _result(tool_results=[_good_call()], duration_ms=3000),
        })
        checker = _checker(provider, tags=["lfm2.5-thinking:latest"], context_length=128000)
        result = asyncio.run(checker.check("lfm2.5-thinking:latest"))

        m = result.suggested_manifest
        self.assertEqual(m.id, "lfm2.5-thinking-local")
        self.assertEqual(m.provider, ProviderType.OLLAMA)
        self.assertEqual(m.compute_location, ComputeLocation.LOCAL_HARDWARE)
        self.assertEqual(m.tool_protocol, ToolProtocol.LFM25)
        self.assertEqual(m.context_window, 128000)
        self.assertIsNone(m.ollama_usage_level)
        self.assertEqual(m.tool_result_role, "tool")
        self.assertEqual(m.latency_class, LatencyClass.MEDIUM)
        self.assertIn(Capability.TOOL_USE, m.capabilities)
        self.assertEqual(m.worker_role, result.recommended_roles)

    def test_cloud_model_inferred_from_tag(self):
        provider = _FakeProvider({
            ToolProtocol.NATIVE: _result(tool_results=[_good_call()], duration_ms=15000),
        })
        checker = _checker(provider, tags=["brand-new:cloud"], context_length=131072)
        result = asyncio.run(checker.check("brand-new:cloud"))

        m = result.suggested_manifest
        self.assertEqual(m.id, "brand-new-cloud")
        self.assertEqual(m.compute_location, ComputeLocation.OLLAMA_CLOUD)
        self.assertEqual(m.ollama_usage_level, OllamaUsageLevel.MEDIUM)
        self.assertIsNone(m.tool_result_role)
        self.assertEqual(m.latency_class, LatencyClass.SLOW)

    def test_fast_probe_gives_fast_latency_class(self):
        provider = _FakeProvider({
            ToolProtocol.NATIVE: _result(tool_results=[_good_call()], duration_ms=900),
        })
        checker = _checker(provider)
        result = asyncio.run(checker.check("some-model:latest"))
        self.assertEqual(result.suggested_manifest.latency_class, LatencyClass.FAST)

    def test_context_window_falls_back_when_show_fails(self):
        provider = _FakeProvider({
            ToolProtocol.NATIVE: _result(tool_results=[_good_call()]),
        })
        checker = _checker(provider, context_length=None)
        result = asyncio.run(checker.check("some-model:latest"))
        self.assertEqual(result.suggested_manifest.context_window, 8192)

    def test_existing_registry_entry_reuses_id_capabilities_and_usage_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "worker_registry.yaml"
            registry_path.write_text(yaml.safe_dump({"workers": [{
                "id": "lfm2.5-local",
                "provider": "ollama",
                "model_id": "lfm2.5-thinking:latest",
                "compute_location": "local",
                "capabilities": ["tool_use", "code", "search"],
                "tool_protocol": "native",
                "context_window": 128000,
                "cost_input": 0.0,
                "cost_output": 0.0,
                "ollama_usage_level": None,
                "latency_class": "medium",
                "requires_gpu": False,
            }]}), encoding="utf-8")

            provider = _FakeProvider({
                ToolProtocol.NATIVE: _result(tool_results=[]),
                ToolProtocol.LFM25: _result(tool_results=[_good_call()]),
            })
            checker = _checker(
                provider, tags=["lfm2.5-thinking:latest"],
                context_length=128000, registry_path=registry_path,
            )
            result = asyncio.run(checker.check("lfm2.5-thinking:latest"))

        m = result.suggested_manifest
        self.assertEqual(m.id, "lfm2.5-local")  # existing id kept, not re-derived
        self.assertIn(Capability.CODE, m.capabilities)      # union with existing
        self.assertIn(Capability.SEARCH, m.capabilities)
        self.assertEqual(m.tool_protocol, ToolProtocol.LFM25)  # probe verdict wins


class TestRegistryWrite(unittest.TestCase):

    def _manifest(self, worker_id: str = "new-model-local") -> WorkerManifest:
        return WorkerManifest(
            id=worker_id,
            provider=ProviderType.OLLAMA,
            model_id="new-model:latest",
            compute_location=ComputeLocation.LOCAL_HARDWARE,
            capabilities={Capability.TOOL_USE},
            tool_protocol=ToolProtocol.LFM25,
            context_window=32768,
            cost_input=0.0,
            cost_output=0.0,
            ollama_usage_level=None,
            latency_class=LatencyClass.MEDIUM,
            available=True,
            requires_gpu=False,
            vram_mb=None,
            tool_result_role="tool",
            worker_role=[WorkerRole.BACKGROUND_AGENT, WorkerRole.EXECUTION_WORKER],
        )

    _EXISTING = (
        "# Header comment that must survive.\n"
        "workers:\n"
        "  - id: old-worker\n"
        "    provider: ollama\n"
        "    model_id: \"old:latest\"\n"
        "    compute_location: local\n"
        "    capabilities: [tool_use]\n"
        "    tool_protocol: native\n"
        "    context_window: 4096\n"
        "    cost_input: 0.0\n"
        "    cost_output: 0.0\n"
        "    ollama_usage_level: null\n"
        "    latency_class: fast\n"
        "    requires_gpu: false\n"
    )

    def test_append_new_entry_preserves_existing_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "worker_registry.yaml"
            path.write_text(self._EXISTING, encoding="utf-8")

            outcome = write_manifest_to_registry(self._manifest(), path)
            text = path.read_text(encoding="utf-8")

        self.assertEqual(outcome, "added")
        self.assertIn("# Header comment that must survive.", text)
        self.assertIn("- id: old-worker", text)
        self.assertIn("- id: new-model-local", text)
        # The result must be loadable by the real registry loader.
        data = yaml.safe_load(text)
        ids = [w["id"] for w in data["workers"]]
        self.assertEqual(ids, ["old-worker", "new-model-local"])
        new_entry = data["workers"][1]
        self.assertEqual(new_entry["tool_protocol"], "lfm25")
        self.assertEqual(new_entry["worker_role"], ["background_agent", "execution_worker"])

    def test_update_existing_entry_replaces_only_that_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "worker_registry.yaml"
            path.write_text(self._EXISTING, encoding="utf-8")

            updated = self._manifest("old-worker")
            updated.tool_protocol = ToolProtocol.JSON_EXTRACT
            outcome = write_manifest_to_registry(updated, path)
            text = path.read_text(encoding="utf-8")

        self.assertEqual(outcome, "updated")
        self.assertIn("# Header comment that must survive.", text)
        data = yaml.safe_load(text)
        self.assertEqual(len(data["workers"]), 1)
        self.assertEqual(data["workers"][0]["id"], "old-worker")
        self.assertEqual(data["workers"][0]["tool_protocol"], "json_extract")

    def test_update_middle_entry_keeps_following_entries(self):
        text = self._EXISTING + (
            "\n"
            "  - id: second-worker\n"
            "    provider: ollama\n"
            "    model_id: \"second:latest\"\n"
            "    compute_location: local\n"
            "    capabilities: [tool_use]\n"
            "    tool_protocol: native\n"
            "    context_window: 4096\n"
            "    cost_input: 0.0\n"
            "    cost_output: 0.0\n"
            "    ollama_usage_level: null\n"
            "    latency_class: fast\n"
            "    requires_gpu: false\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "worker_registry.yaml"
            path.write_text(text, encoding="utf-8")

            write_manifest_to_registry(self._manifest("old-worker"), path)
            result_text = path.read_text(encoding="utf-8")

        data = yaml.safe_load(result_text)
        ids = [w["id"] for w in data["workers"]]
        self.assertEqual(ids, ["old-worker", "second-worker"])
        self.assertEqual(data["workers"][0]["tool_protocol"], "lfm25")


class TestFormatReport(unittest.TestCase):

    def test_supported_report_contains_rounds_and_entry(self):
        provider = _FakeProvider({
            ToolProtocol.NATIVE: _result(tool_results=[]),
            ToolProtocol.LFM25: _result(tool_results=[_good_call()]),
        })
        checker = _checker(provider, tags=["lfm2.5-thinking:latest"], context_length=128000)
        result = asyncio.run(checker.check("lfm2.5-thinking:latest"))
        report = format_report(result)

        self.assertIn("MODEL READINESS REPORT", report)
        self.assertIn("ROUND 1", report)
        self.assertIn("REJECTED", report)
        self.assertIn("ROUND 2", report)
        self.assertIn("SUPPORTED", report)
        self.assertIn("Recommended protocol:  lfm25", report)
        self.assertIn("WORKER REGISTRY ENTRY", report)
        self.assertIn('get_current_time(timezone="America/Chicago")', report)

    def test_unsupported_report_states_verdict(self):
        provider = _FakeProvider({
            p: _result(tool_results=[], output="nope")
            for p in (ToolProtocol.NATIVE, ToolProtocol.LFM25, ToolProtocol.JSON_EXTRACT)
        })
        checker = _checker(provider)
        result = asyncio.run(checker.check("some-model:latest"))
        report = format_report(result)
        self.assertIn("NOT SUPPORTED", report)


class TestCliCheckModel(unittest.TestCase):
    """
    Drives wizard.cli_main() end-to-end with only the checker's external
    touchpoints (provider + HTTP fns) replaced, by patching __init__ to
    inject them regardless of what kwargs cli_main passes.
    """

    @staticmethod
    def _patched_init(provider, registry_path):
        real_init = ReadinessChecker.__init__
        get_fn = _fake_get_fn(["some-model:latest"])
        post_fn = _fake_post_fn(4096)

        def fake_init(self, **kwargs):
            real_init(
                self,
                base_url=kwargs.get("base_url", "http://localhost:11434"),
                registry_path=registry_path,
                provider=provider,
                _get_fn=get_fn,
                _post_fn=post_fn,
            )
        return fake_init

    def test_check_model_prints_report_and_writes_on_yes(self):
        from tasker.setup import wizard

        provider = _FakeProvider({
            ToolProtocol.NATIVE: _result(tool_results=[_good_call()]),
        })

        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "worker_registry.yaml"
            registry_path.write_text("workers:\n", encoding="utf-8")

            with mock.patch.object(
                ReadinessChecker, "__init__",
                self._patched_init(provider, registry_path),
            ), mock.patch("builtins.print") as m_print:
                wizard.cli_main([
                    "--check-model", "some-model:latest",
                    "--registry", str(registry_path),
                    "--yes",
                ])

            text = registry_path.read_text(encoding="utf-8")

        printed = "\n".join(str(c.args[0]) for c in m_print.call_args_list if c.args)
        self.assertIn("MODEL READINESS REPORT", printed)
        self.assertIn("- id: some-model-local", text)

    def test_check_model_unsupported_writes_nothing(self):
        from tasker.setup import wizard

        provider = _FakeProvider({
            p: _result(tool_results=[], output="nope")
            for p in (ToolProtocol.NATIVE, ToolProtocol.LFM25, ToolProtocol.JSON_EXTRACT)
        })

        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "worker_registry.yaml"
            registry_path.write_text("workers:\n", encoding="utf-8")

            with mock.patch.object(
                ReadinessChecker, "__init__",
                self._patched_init(provider, registry_path),
            ), mock.patch("builtins.print"):
                wizard.cli_main([
                    "--check-model", "some-model:latest",
                    "--registry", str(registry_path), "--yes",
                ])

            text = registry_path.read_text(encoding="utf-8")

        self.assertEqual(text, "workers:\n")


if __name__ == "__main__":
    unittest.main()

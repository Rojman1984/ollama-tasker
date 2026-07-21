"""
Unit tests -- tasker/tui/screens/model_selector.py
SDD_ADDENDUM_PHASE8.md B.4 / Phase 8.4.
"""
import unittest
from pathlib import Path
from unittest import mock

from textual.app import App
from textual.widgets import Button, OptionList, Static

from tasker.setup.readiness import ProbeResult, ReadinessResult
from tasker.tui.screens.model_selector import ModelSelectorScreen
from tasker.tui.widgets.history_input import HistoryInput
from tasker.tui.widgets.readiness_panel import ReadinessReportPanel
from tasker.workers.base import Capability, ComputeLocation, LatencyClass, ProviderType, ToolProtocol, WorkerManifest


_UNATTEMPTED = ProbeResult(ToolProtocol.NATIVE, False, False, None, None, None)


def _no_cache():
    return mock.patch("tasker.config.detect._read_matching_cache", return_value=None)


def _fake_registry_yaml(tmp_path: Path) -> Path:
    """Write a minimal registry with one local and one cloud Ollama worker."""
    path = tmp_path / "worker_registry.yaml"
    path.write_text(
        "workers:\n"
        "  - id: lfm2.5-local\n"
        "    provider: ollama\n"
        "    model_id: lfm2.5-thinking:latest\n"
        "    compute_location: local\n"
        "    capabilities: [tool_use]\n"
        "    tool_protocol: lfm25\n"
        "    context_window: 128000\n"
        "  - id: kimi-cloud\n"
        "    provider: ollama\n"
        "    model_id: kimi-k2.7-code:cloud\n"
        "    compute_location: ollama_cloud\n"
        "    capabilities: [tool_use, reasoning]\n"
        "    tool_protocol: native\n"
        "    context_window: 262144\n",
        encoding="utf-8",
    )
    return path


def _model_app(screen: ModelSelectorScreen) -> App:
    class _ModelApp(App):
        def on_mount(self) -> None:
            self.push_screen(screen)
    return _ModelApp()


class _FakeChecker:
    def __init__(self, supported: bool) -> None:
        self.supported = supported

    async def check(self, model_name: str) -> ReadinessResult:
        if self.supported:
            return ReadinessResult(
                model_id="lfm2.5-local",
                ollama_model=model_name,
                pulled_locally=True,
                native_result=_UNATTEMPTED,
                lfm25_result=_UNATTEMPTED,
                json_extract_result=_UNATTEMPTED,
                supported=True,
                recommended_protocol=ToolProtocol.NATIVE,
                recommended_capabilities={Capability.TOOL_USE},
                recommended_roles=[],
                raw_response="raw",
                parsed_tool_call=None,
                suggested_manifest=WorkerManifest(
                    id="test-local",
                    provider=ProviderType.OLLAMA,
                    model_id=model_name,
                    compute_location=ComputeLocation.LOCAL_HARDWARE,
                    capabilities={Capability.TOOL_USE},
                    tool_protocol=ToolProtocol.NATIVE,
                    context_window=4096,
                    cost_input=0.0,
                    cost_output=0.0,
                    ollama_usage_level=None,
                    latency_class=LatencyClass.FAST,
                    available=True,
                    requires_gpu=False,
                    vram_mb=None,
                ),
            )
        return ReadinessResult(
            model_id="rejected",
            ollama_model=model_name,
            pulled_locally=True,
            native_result=_UNATTEMPTED,
            lfm25_result=_UNATTEMPTED,
            json_extract_result=_UNATTEMPTED,
            supported=False,
            recommended_protocol=None,
            recommended_capabilities=set(),
            recommended_roles=[],
            raw_response="",
            parsed_tool_call=None,
            suggested_manifest=None,
        )


class TestModelSelectorScreenComposition(unittest.IsolatedAsyncioTestCase):

    async def test_two_panels_and_input_present(self):
        with _no_cache():
            async def empty_tags(url: str):
                return 200, {"models": []}

            app = _model_app(ModelSelectorScreen(_get_fn=empty_tags))
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause(0.3)
                self.assertIsInstance(app.screen.query_one("#model-input", HistoryInput), HistoryInput)
                self.assertIsInstance(app.screen.query_one("#model-list", OptionList), OptionList)
                self.assertIsInstance(app.screen.query_one(ReadinessReportPanel), ReadinessReportPanel)
                self.assertIsInstance(app.screen.query_one("#test-model"), Button)
                self.assertIsInstance(app.screen.query_one("#add-registry"), Button)


class TestModelSelectorReadiness(unittest.IsolatedAsyncioTestCase):

    async def test_supported_result_enables_add_button(self):
        with _no_cache():
            async def empty_tags(url: str):
                return 200, {"models": []}

            screen = ModelSelectorScreen(checker=_FakeChecker(True), _get_fn=empty_tags)
            app = _model_app(screen)
            async with app.run_test() as pilot:
                await pilot.pause()
                app.screen.query_one("#model-input", HistoryInput).value = "test-model:latest"
                await pilot.click("#test-model")
                await pilot.pause()
                await pilot.pause(0.3)
                self.assertTrue(app.screen.query_one("#add-registry", Button).disabled is False)
                self.assertIn("test-model:latest", str(app.screen.query_one(ReadinessReportPanel).query_one("#report-content", Static).render()))

    async def test_unsupported_result_keeps_button_disabled(self):
        with _no_cache():
            async def empty_tags(url: str):
                return 200, {"models": []}

            screen = ModelSelectorScreen(checker=_FakeChecker(False), _get_fn=empty_tags)
            app = _model_app(screen)
            async with app.run_test() as pilot:
                await pilot.pause()
                app.screen.query_one("#model-input", HistoryInput).value = "bad-model:latest"
                await pilot.click("#test-model")
                await pilot.pause()
                await pilot.pause(0.3)
                self.assertTrue(app.screen.query_one("#add-registry", Button).disabled)


class TestModelSelectorRegistryWrite(unittest.IsolatedAsyncioTestCase):

    async def test_add_to_registry_writes_entry(self):
        import tempfile
        with _no_cache(), tempfile.TemporaryDirectory() as d:
            registry_path = _fake_registry_yaml(Path(d))

            async def empty_tags(url: str):
                return 200, {"models": []}

            screen = ModelSelectorScreen(
                registry_path=registry_path,
                checker=_FakeChecker(True),
                _get_fn=empty_tags,
            )
            app = _model_app(screen)
            async with app.run_test() as pilot:
                await pilot.pause()
                app.screen.query_one("#model-input", HistoryInput).value = "new-model:latest"
                await pilot.click("#test-model")
                await pilot.pause()
                await pilot.pause(0.3)
                await pilot.click("#add-registry")
                await pilot.pause()
                await pilot.pause(0.3)
                text = registry_path.read_text(encoding="utf-8")
                self.assertIn("new-model:latest", text)


if __name__ == "__main__":
    import unittest
    unittest.main()

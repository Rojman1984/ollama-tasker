"""
tasker.tui.screens.model_selector
---------------------------------
ModelSelectorScreen -- two-panel screen for probing Ollama models and adding
confirmed-compatible workers to the registry.

Left panel: list of candidate model tags (local `ollama list` + cloud entries
from `worker_registry.yaml`) plus a manual-entry input with history and tab
completion.
Right panel: `ReadinessReportPanel` showing the formatted probe report.

Operations are async workers so the UI stays responsive during model
inference. See SDD_ADDENDUM_PHASE8.md B.4 / B.5.2 / B.5.5.
"""
from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import aiohttp

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, OptionList, Static

from tasker.setup.readiness import (
    ReadinessChecker,
    ReadinessResult,
    _DEFAULT_REGISTRY_PATH,
    write_manifest_to_registry,
)
from tasker.tui.messages import ReadinessCheckCompleted, WorkerRegistryUpdated
from tasker.tui.widgets.history_input import HistoryInput
from tasker.tui.widgets.readiness_panel import ReadinessReportPanel
from tasker.tui.widgets.status_bar import HardwareStatusBar
from tasker.workers.base import ComputeLocation, ProviderType
from tasker.workers.registry import WorkerRegistry


_TagFn = Callable[[str], Awaitable[tuple[int, dict]]]


def _default_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


def _ollama_cloud_tags(registry: WorkerRegistry) -> list[str]:
    """Collect Ollama Cloud model tags already declared in the registry."""
    return [
        w.model_id
        for w in registry.list_all()
        if w.provider == ProviderType.OLLAMA and w.compute_location == ComputeLocation.OLLAMA_CLOUD
    ]


async def _default_get_fn(url: str) -> tuple[int, dict]:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            return resp.status, await resp.json()


class ModelSelectorScreen(Screen):
    """Interactive model selector + readiness checker screen."""

    BINDINGS = [
        ("b", "back", "Back to menu"),
    ]

    DEFAULT_CSS = """
    ModelSelectorScreen {
        layout: vertical;
    }
    #selector-header {
        height: auto;
        padding: 1 2;
    }
    #selector-title {
        width: 1fr;
        text-style: bold;
    }
    #selector-body {
        height: 1fr;
        padding: 0 1;
    }
    #left-panel {
        width: 40%;
        height: 1fr;
        border: round $primary;
        padding: 1;
    }
    #model-input {
        margin-bottom: 1;
    }
    #model-list {
        height: 1fr;
        border: none;
    }
    #selector-actions {
        height: auto;
        margin-top: 1;
    }
    #right-panel {
        width: 60%;
        height: 1fr;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        base_url: str | None = None,
        registry_path: str | Path | None = None,
        checker: ReadinessChecker | None = None,
        *,
        _get_fn: _TagFn | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.base_url = (base_url or _default_base_url()).rstrip("/")
        self.registry_path = (
            Path(registry_path) if registry_path is not None else _DEFAULT_REGISTRY_PATH
        )
        self._checker = checker
        self._get_fn = _get_fn or _default_get_fn
        self._candidates: list[tuple[str, str]] = []  # (tag, label)
        self._last_result: ReadinessResult | None = None

    def compose(self) -> ComposeResult:
        yield HardwareStatusBar()
        with Horizontal(id="selector-header"):
            yield Static("Model Selector", id="selector-title")
            yield Button("Back to Menu", id="back", variant="default")
        with Horizontal(id="selector-body"):
            with Vertical(id="left-panel"):
                yield HistoryInput(
                    placeholder="model tag (e.g. lfm2.5-thinking:latest)",
                    id="model-input",
                    completer=self._completion_candidates,
                )
                yield OptionList(id="model-list")
                with Horizontal(id="selector-actions"):
                    yield Button("Test Model", id="test-model", variant="primary")
                    yield Button("Add to Registry", id="add-registry", variant="success", disabled=True)
            with VerticalScroll(id="right-panel"):
                yield ReadinessReportPanel()
        yield Footer()

    def on_mount(self) -> None:
        # Pass the async method (callable) rather than a pre-created coroutine.
        self.run_worker(self._load_candidates)

    # ------------------------------------------------------------------ #
    # Candidate list
    # ------------------------------------------------------------------ #

    async def _load_candidates(self) -> None:
        """Populate the model list from the registry and /api/tags."""
        registry = WorkerRegistry.load_from_yaml(self.registry_path)
        candidates: dict[str, str] = {}

        # Registry Ollama workers (local and cloud).
        for worker in registry.list_all():
            if worker.provider == ProviderType.OLLAMA:
                tag = worker.model_id
                label = f"{tag}  ({worker.id}, {worker.tool_protocol.value})"
                candidates[tag] = label

        # Local models from Ollama.
        try:
            status, data = await self._get_fn(f"{self.base_url}/api/tags")
            if status == 200:
                for model in data.get("models", []):
                    tag = model.get("name", "")
                    if tag and tag not in candidates:
                        candidates[tag] = f"{tag}  (local, not registered)"
        except Exception as exc:
            self.app.notify(f"Could not query local models: {exc}", severity="warning", timeout=5)

        self._candidates = sorted(candidates.items(), key=lambda item: item[0].lower())
        option_list = self.query_one("#model-list", OptionList)
        option_list.clear_options()
        option_list.add_options(
            [self._option_for(tag, label) for tag, label in self._candidates]
        )

    def _option_for(self, tag: str, label: str) -> Any:
        from textual.widgets.option_list import Option
        return Option(label, id=tag)

    def _completion_candidates(self, value: str) -> list[str]:
        """Completer callback used by HistoryInput for tab completion."""
        return [tag for tag, _ in self._candidates]

    def _selected_tag(self) -> str:
        """Return the currently selected model tag, or the input value."""
        option_list = self.query_one("#model-list", OptionList)
        try:
            idx = option_list.highlighted_option
        except Exception:
            idx = None
        if idx is not None and 0 <= idx < len(self._candidates):
            return self._candidates[idx][0]
        return self.query_one("#model-input", HistoryInput).value.strip()

    # ------------------------------------------------------------------ #
    # Readiness check
    # ------------------------------------------------------------------ #

    def _get_checker(self) -> ReadinessChecker:
        if self._checker is None:
            self._checker = ReadinessChecker(
                base_url=self.base_url, registry_path=self.registry_path
            )
        return self._checker

    def action_test_model(self) -> None:
        tag = self._selected_tag()
        if not tag:
            self.app.notify("Select or type a model tag first", severity="warning", timeout=2)
            return
        self.query_one(ReadinessReportPanel).show_progress(
            f"Probing {tag}... (this can take a while for large models)"
        )
        self.query_one("#add-registry", Button).disabled = True

        async def _task() -> None:
            await self._probe_model(tag)

        self.run_worker(_task)

    async def _probe_model(self, tag: str) -> None:
        try:
            result = await self._get_checker().check(tag)
            self._last_result = result
            self.post_message(ReadinessCheckCompleted(result))
        except Exception as exc:
            self.app.notify(f"Readiness check failed: {exc}", severity="error", timeout=5)

    def on_readiness_check_completed(self, event: ReadinessCheckCompleted) -> None:
        self.query_one(ReadinessReportPanel).show_result(event.result)
        self.query_one("#add-registry", Button).disabled = not event.result.supported

    # ------------------------------------------------------------------ #
    # Registry write
    # ------------------------------------------------------------------ #

    def action_add_to_registry(self) -> None:
        if self._last_result is None or self._last_result.suggested_manifest is None:
            self.app.notify("No supported model to add", severity="warning", timeout=2)
            return
        manifest = self._last_result.suggested_manifest
        try:
            outcome = write_manifest_to_registry(manifest, self.registry_path)
            self.app.notify(
                f"Registry entry '{manifest.id}' {outcome}.",
                severity="information",
                timeout=3,
            )
            self.post_message(WorkerRegistryUpdated(manifest))
            # Refresh candidate list so the new entry appears.
            self.run_worker(self._load_candidates)
        except Exception as exc:
            self.app.notify(f"Could not write registry: {exc}", severity="error", timeout=5)

    # ------------------------------------------------------------------ #
    # Event handlers
    # ------------------------------------------------------------------ #

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is not None:
            self.query_one("#model-input", HistoryInput).value = event.option.id

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Only react to the model-tag input being submitted.
        if isinstance(event.input, HistoryInput) and event.input.id == "model-input":
            self.action_test_model()
            event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "test-model":
            self.action_test_model()
            event.stop()
        elif button_id == "add-registry":
            self.action_add_to_registry()
            event.stop()
        elif button_id == "back":
            self.app.pop_screen()
            event.stop()

    def action_back(self) -> None:
        self.app.pop_screen()

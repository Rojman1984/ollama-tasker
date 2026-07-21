"""Generate a headless TUI transcript for Phase 8.4 manual verification.

This script drives the Textual app through the Setup Wizard and Model Selector
screens without a real terminal, using mocked environment/readiness data, and
writes a human-readable transcript plus the resulting scratch registry.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest import mock

from textual.app import App

from tasker.setup.readiness import ProbeResult, ReadinessResult
from tasker.setup.wizard import StepStatus, WizardStepResult
from tasker.tui.app import TuiApp
from tasker.tui.screens.model_selector import ModelSelectorScreen
from tasker.tui.widgets.readiness_panel import ReadinessReportPanel
from tasker.tui.widgets.step_row import WizardStepRow
from tasker.workers.base import (
    Capability,
    ComputeLocation,
    LatencyClass,
    ProviderType,
    ToolProtocol,
    WorkerManifest,
)


def _fake_wizard_results() -> list[WizardStepResult]:
    return [
        WizardStepResult(
            step_id="1.1", step_name="Python version check",
            status=StepStatus.OK, message="Python 3.12 OK",
            detail=None, action_required=None, can_continue=True,
        ),
        WizardStepResult(
            step_id="2.3", step_name="Ollama service reachability",
            status=StepStatus.OK, message="Ollama service reachable at http://localhost:11434",
            detail=None, action_required=None, can_continue=True,
        ),
        WizardStepResult(
            step_id="3.1", step_name="Hardware detection",
            status=StepStatus.OK, message="Profile: tier2_designlab",
            detail=None, action_required=None, can_continue=True,
        ),
        WizardStepResult(
            step_id="3.3", step_name="GPU acceleration guidance",
            status=StepStatus.OK,
            message="NVIDIA GPU detected (GeForce GTX 1050 Ti); WSL2 passthrough confirmed.",
            detail=None, action_required=None, can_continue=True,
        ),
        WizardStepResult(
            step_id="4", step_name="GPU acceleration verification",
            status=StepStatus.OK, message="GPU OFFLOAD CONFIRMED: full offload.",
            detail=None, action_required=None, can_continue=True,
        ),
        WizardStepResult(
            step_id="6.1", step_name="Worker registry status",
            status=StepStatus.OK, message="2 worker(s) registered.",
            detail="lfm2.5-local (ollama/lfm2.5-thinking:latest, protocol=lfm25)\n"
                   "kimi-cloud (ollama/kimi-k2.7-code:cloud, protocol=native)",
            action_required=None, can_continue=True,
        ),
        WizardStepResult(
            step_id="7", step_name="Summary",
            status=StepStatus.OK, message="All checks passed.",
            detail=None, action_required=None, can_continue=True,
        ),
    ]


_ATTEMPTED = ProbeResult(ToolProtocol.NATIVE, True, True, "tool call ok", {"name": "get_current_time", "arguments": {"timezone": "America/Chicago"}}, None)


def _fake_readiness_result(model_name: str) -> ReadinessResult:
    return ReadinessResult(
        model_id="probe-model-local",
        ollama_model=model_name,
        pulled_locally=True,
        native_result=_ATTEMPTED,
        lfm25_result=ProbeResult(ToolProtocol.LFM25, False, False, None, None, None),
        json_extract_result=ProbeResult(ToolProtocol.JSON_EXTRACT, False, False, None, None, None),
        supported=True,
        recommended_protocol=ToolProtocol.NATIVE,
        recommended_capabilities={Capability.TOOL_USE},
        recommended_roles=[],
        raw_response="[{name: get_current_time, arguments: {timezone: America/Chicago}}]",
        parsed_tool_call={"name": "get_current_time", "arguments": {"timezone": "America/Chicago"}},
        suggested_manifest=WorkerManifest(
            id="probe-model-local",
            provider=ProviderType.OLLAMA,
            model_id=model_name,
            compute_location=ComputeLocation.LOCAL_HARDWARE,
            capabilities={Capability.TOOL_USE},
            tool_protocol=ToolProtocol.NATIVE,
            context_window=32768,
            cost_input=0.0,
            cost_output=0.0,
            ollama_usage_level=None,
            latency_class=LatencyClass.FAST,
            available=True,
            requires_gpu=False,
            vram_mb=None,
        ),
    )


async def _drive(app: App, registry_path: Path) -> list[str]:
    lines: list[str] = []
    async with app.run_test() as pilot:
        await pilot.pause()
        lines.append("=== WelcomeScreen ===")
        lines.append(f"Screen type: {type(app.screen).__name__}")

        # Open Setup Wizard from the menu.
        with mock.patch(
            "tasker.tui.screens.setup_wizard.run_wizard",
            return_value=_fake_wizard_results(),
        ):
            await pilot.click("#menu-setup_wizard")
            await pilot.pause()
            await pilot.pause(0.4)
            lines.append("")
            lines.append("=== SetupWizardScreen ===")
            lines.append(f"Screen type: {type(app.screen).__name__}")
            rows = list(app.screen.query(WizardStepRow))
            lines.append(f"WizardStepRow count: {len(rows)}")
            for row in rows:
                r = row.result
                lines.append(
                    f"  {r.step_id} [{r.status.value}] {r.step_name}: {r.message}"
                )
            gpu_guidance = str(
                app.screen.query_one("#gpu-guidance").render()
            ).strip()
            if gpu_guidance:
                lines.append("GPU guidance panel:")
                for line in gpu_guidance.splitlines():
                    lines.append(f"  {line}")

            # Back to menu.
            await pilot.click("#back")
            await pilot.pause()

        # Open Model Selector directly with mocked dependencies.
        async def empty_tags(url: str):
            return 200, {"models": []}

        class FakeChecker:
            async def check(self, model_name: str) -> ReadinessResult:
                return _fake_readiness_result(model_name)

        app.push_screen(
            ModelSelectorScreen(
                registry_path=registry_path,
                checker=FakeChecker(),
                _get_fn=empty_tags,
            )
        )
        await pilot.pause()
        await pilot.pause(0.4)
        lines.append("")
        lines.append("=== ModelSelectorScreen ===")
        lines.append(f"Screen type: {type(app.screen).__name__}")
        option_list = app.screen.query_one("#model-list")
        lines.append(f"Candidate model count: {option_list.option_count}")

        # Type a manual tag and run the probe.
        app.screen.query_one("#model-input").value = "probe-model:latest"
        await pilot.click("#test-model")
        await pilot.pause()
        await pilot.pause(0.4)
        panel = app.screen.query_one(ReadinessReportPanel)
        report = str(panel.query_one("#report-content").render()).strip()
        lines.append("Readiness report (first 10 lines):")
        for line in report.splitlines()[:10]:
            lines.append(f"  {line}")
        add_button = app.screen.query_one("#add-registry")
        lines.append(f"Add to Registry button disabled: {add_button.disabled}")

        # Add to registry.
        await pilot.click("#add-registry")
        await pilot.pause()
        await pilot.pause(0.4)
        lines.append("")
        lines.append("=== Registry file after Add to Registry ===")
        lines.append(registry_path.read_text(encoding="utf-8"))

    return lines


def main() -> None:
    repo_root = Path(__file__).parent.parent
    out_dir = repo_root / "docs" / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "phase_8_4_tui_transcript.txt"

    with tempfile.TemporaryDirectory() as d:
        registry_path = Path(d) / "worker_registry.yaml"
        registry_path.write_text(
            "workers:\n"
            "  - id: lfm2.5-local\n"
            "    provider: ollama\n"
            "    model_id: lfm2.5-thinking:latest\n"
            "    compute_location: local\n"
            "    capabilities: [tool_use]\n"
            "    tool_protocol: lfm25\n"
            "    context_window: 128000\n"
            "    cost_input: 0.0\n"
            "    cost_output: 0.0\n"
            "    latency_class: medium\n"
            "    requires_gpu: false\n"
            "  - id: kimi-cloud\n"
            "    provider: ollama\n"
            "    model_id: kimi-k2.7-code:cloud\n"
            "    compute_location: ollama_cloud\n"
            "    capabilities: [tool_use, reasoning]\n"
            "    tool_protocol: native\n"
            "    context_window: 262144\n"
            "    cost_input: 0.0\n"
            "    cost_output: 0.0\n"
            "    latency_class: fast\n"
            "    requires_gpu: false\n",
            encoding="utf-8",
        )

        # Suppress hardware-cache lookup and real logging.
        with mock.patch(
            "tasker.config.detect._read_matching_cache", return_value=None
        ):
            lines = asyncio.run(_drive(TuiApp(), registry_path))

    header = [
        "Phase 8.4 Headless TUI Transcript",
        "Generated by scripts/phase_8_4_transcript.py",
        "",
        "This transcript was produced via Textual's headless App.run_test()",
        "driver. It demonstrates that SetupWizardScreen and ModelSelectorScreen",
        "mount, run their async workers, and (for the model selector) write to",
        "the worker registry. The two B.8 'manual verification' checklist items",
        "still require Roland's eyes-on check in a real terminal.",
        "",
    ]
    out_path.write_text("\n".join(header + lines), encoding="utf-8")
    print(f"Transcript written to {out_path}")


if __name__ == "__main__":
    main()

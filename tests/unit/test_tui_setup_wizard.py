"""
Unit tests -- tasker/tui/screens/setup_wizard.py
SDD_ADDENDUM_PHASE8.md B.3 / Phase 8.4.
"""
import unittest
from unittest import mock

from textual.app import App
from textual.widgets import Button, Static

from tasker.setup.wizard import StepStatus, WizardStepResult
from tasker.tui.screens.setup_wizard import SetupWizardScreen
from tasker.tui.widgets.status_bar import HardwareStatusBar
from tasker.tui.widgets.step_row import WizardStepRow


def _no_cache():
    return mock.patch("tasker.config.detect._read_matching_cache", return_value=None)


def _fake_results() -> list[WizardStepResult]:
    return [
        WizardStepResult(
            step_id="1.1", step_name="Python version check",
            status=StepStatus.OK, message="Python 3.12 OK",
            detail=None, action_required=None, can_continue=True,
        ),
        WizardStepResult(
            step_id="3.1", step_name="Hardware detection",
            status=StepStatus.OK, message="Profile: tier1_tasker",
            detail=None, action_required=None, can_continue=True,
        ),
        WizardStepResult(
            step_id="3.3", step_name="GPU acceleration guidance",
            status=StepStatus.WARNING,
            message="AMD APU detected but env vars missing.",
            detail=None,
            action_required=(
                "export OLLAMA_VULKAN=1\n"
                "export ROCR_VISIBLE_DEVICES=-1\n"
                "export HIP_VISIBLE_DEVICES=-1"
            ),
            can_continue=True,
        ),
        WizardStepResult(
            step_id="7", step_name="Summary",
            status=StepStatus.WARNING,
            message="1 warning(s) found -- harness will work, review recommended.",
            detail=None, action_required=None, can_continue=True,
        ),
    ]


def _wizard_app(screen: SetupWizardScreen) -> App:
    """Build a minimal app that mounts *screen* for headless testing."""
    class _WizardApp(App):
        def on_mount(self) -> None:
            self.push_screen(screen)
    return _WizardApp()


class TestSetupWizardScreenComposition(unittest.IsolatedAsyncioTestCase):

    async def test_status_bar_and_controls_present(self):
        with _no_cache():
            app = _wizard_app(SetupWizardScreen())
            async with app.run_test() as pilot:
                await pilot.pause()
                self.assertEqual(len(app.screen.query(HardwareStatusBar)), 1)
                self.assertIsInstance(app.screen.query_one("#rerun-all"), Button)
                self.assertIsInstance(app.screen.query_one("#back"), Button)
                self.assertIn("Setup Wizard", str(app.screen.query_one("#wizard-title", Static).render()))


class TestSetupWizardRun(unittest.IsolatedAsyncioTestCase):

    async def test_wizard_results_create_rows(self):
        with _no_cache(), mock.patch(
            "tasker.tui.screens.setup_wizard.run_wizard",
            return_value=_fake_results(),
        ):
            app = _wizard_app(SetupWizardScreen())
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause(0.3)
                rows = list(app.screen.query(WizardStepRow))
                self.assertEqual(len(rows), 4)
                ids = [r.result.step_id for r in rows]
                self.assertEqual(ids, ["1.1", "3.1", "3.3", "7"])

    async def test_gpu_guidance_panel_shows_action(self):
        with _no_cache(), mock.patch(
            "tasker.tui.screens.setup_wizard.run_wizard",
            return_value=_fake_results(),
        ):
            app = _wizard_app(SetupWizardScreen())
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause(0.3)
                guidance = app.screen.query_one("#gpu-guidance", Static)
                self.assertIn("OLLAMA_VULKAN", str(guidance.render()))
                self.assertTrue(guidance.has_class("visible"))

    async def test_rerun_all_button_clears_and_re_runs(self):
        with _no_cache(), mock.patch(
            "tasker.tui.screens.setup_wizard.run_wizard",
            return_value=_fake_results(),
        ) as m_run:
            app = _wizard_app(SetupWizardScreen())
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause(0.3)
                self.assertEqual(len(list(app.screen.query(WizardStepRow))), 4)
                await pilot.click("#rerun-all")
                await pilot.pause()
                await pilot.pause(0.3)
                self.assertEqual(m_run.call_count, 2)
                self.assertEqual(len(list(app.screen.query(WizardStepRow))), 4)


if __name__ == "__main__":
    import unittest
    unittest.main()

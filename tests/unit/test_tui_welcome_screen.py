"""
Unit tests -- tasker/tui/screens/welcome.py (WelcomeScreen)
SDD_ADDENDUM_PHASE8.md B.5.2 / Phase 8.3.

Driven headlessly through Textual's App.run_test()/Pilot -- no real
terminal needed. Hardware cache access is mocked (no live detection).
"""
import unittest
from unittest import mock

from textual.widgets import ListView

from tasker.tui.app import TuiApp
from tasker.tui.screens.welcome import MENU_ITEMS
from tasker.tui.widgets.status_bar import HardwareStatusBar


def _no_cache():
    return mock.patch("tasker.config.detect._read_matching_cache", return_value=None)


class TestWelcomeScreenLayout(unittest.IsolatedAsyncioTestCase):

    async def test_status_bar_present(self):
        with _no_cache():
            app = TuiApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                self.assertEqual(len(app.screen.query(HardwareStatusBar)), 1)

    async def test_menu_has_all_five_items_plus_quit(self):
        with _no_cache():
            app = TuiApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                list_view = app.screen.query_one("#menu-list", ListView)
                self.assertEqual(len(list_view.children), len(MENU_ITEMS) + 1)

    async def test_all_expected_menu_ids_present(self):
        with _no_cache():
            app = TuiApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                for key, _, _ in MENU_ITEMS:
                    self.assertEqual(len(app.screen.query(f"#menu-{key}")), 1)
                self.assertEqual(len(app.screen.query("#menu-quit")), 1)

    async def test_title_shown(self):
        with _no_cache():
            app = TuiApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                title = app.screen.query_one("#title")
                self.assertEqual(title.content, "Ollama Tasker")


class TestWelcomeScreenMenuSelection(unittest.IsolatedAsyncioTestCase):

    async def _select(self, pilot, app, item_id: str) -> str:
        await pilot.click(f"#{item_id}")
        await pilot.pause()
        return app.screen.query_one("#menu-notice").content

    async def test_setup_wizard_shows_phase_8_4_notice(self):
        with _no_cache():
            app = TuiApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                notice = await self._select(pilot, app, "menu-setup_wizard")
        self.assertIn("Setup Wizard", notice)
        self.assertIn("Phase 8.4", notice)

    async def test_model_selector_shows_phase_8_4_notice(self):
        with _no_cache():
            app = TuiApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                notice = await self._select(pilot, app, "menu-model_selector")
        self.assertIn("Model Selector", notice)
        self.assertIn("Phase 8.4", notice)

    async def test_run_task_shows_phase_8_5_notice(self):
        with _no_cache():
            app = TuiApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                notice = await self._select(pilot, app, "menu-run_task")
        self.assertIn("Run Task", notice)
        self.assertIn("Phase 8.5", notice)

    async def test_view_sessions_shows_phase_8_5_notice(self):
        with _no_cache():
            app = TuiApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                notice = await self._select(pilot, app, "menu-view_sessions")
        self.assertIn("View Sessions", notice)
        self.assertIn("Phase 8.5", notice)

    async def test_daemon_shows_not_implemented_notice(self):
        with _no_cache():
            app = TuiApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                notice = await self._select(pilot, app, "menu-daemon")
        self.assertIn("Daemon", notice)
        self.assertIn("Not yet implemented", notice)

    async def test_quit_item_exits_app(self):
        with _no_cache():
            app = TuiApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.click("#menu-quit")
                await pilot.pause()
        self.assertFalse(app.is_running)

    async def test_q_binding_exits_app(self):
        with _no_cache():
            app = TuiApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("q")
                await pilot.pause()
        self.assertFalse(app.is_running)


if __name__ == "__main__":
    unittest.main()

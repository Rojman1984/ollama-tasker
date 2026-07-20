"""
Unit tests -- tasker/tui/app.py (TuiApp, main())
SDD_ADDENDUM_PHASE8.md B.5 / Phase 8.3.

Screen-content assertions live in test_tui_welcome_screen.py; this file
covers TuiApp's own boot behavior and the `tasker` console script's
main() wiring.
"""
import unittest
from unittest import mock

from tasker.tui.app import TuiApp, main
from tasker.tui.screens.welcome import WelcomeScreen


def _no_cache():
    return mock.patch("tasker.config.detect._read_matching_cache", return_value=None)


class TestTuiAppBoot(unittest.IsolatedAsyncioTestCase):

    async def test_pushes_welcome_screen_on_mount(self):
        with _no_cache():
            app = TuiApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                self.assertIsInstance(app.screen, WelcomeScreen)

    async def test_title_set(self):
        with _no_cache():
            app = TuiApp()
            async with app.run_test() as pilot:
                await pilot.pause()
        self.assertEqual(app.title, "Ollama Tasker")


class TestMain(unittest.TestCase):

    def test_main_runs_the_app(self):
        with mock.patch.object(TuiApp, "run") as m_run:
            main()
        m_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()

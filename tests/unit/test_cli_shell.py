"""
Unit tests -- cli/shell.py REPL UX fixes (2026-07-20).

Live user testing found:
  1. `_first_positional()` mis-parsed boolean flags (e.g. --verbose) as if
     they took a value, swallowing the next real token.
  2. The REPL's "Unknown command" handler gave no guidance -- a user
     typing "/chat" (meaning "/mode chat") got no hint.
  3. The interactive shell showed WARNING+ plumbing logs by default,
     cluttering the chat flow; --verbose should restore them.
"""
import logging
import unittest
from unittest import mock

from cli.shell import _first_positional, _suggest_command


class TestSuggestCommand(unittest.TestCase):

    def test_mode_name_typed_as_bare_command_suggests_mode_switch(self):
        self.assertEqual(_suggest_command("/chat"), "/mode chat")
        self.assertEqual(_suggest_command("/cowork"), "/mode cowork")

    def test_typo_of_known_command_suggests_nearest_match(self):
        self.assertEqual(_suggest_command("/wrkers"), "/workers")
        self.assertEqual(_suggest_command("/hlep"), "/help")

    def test_unrelated_input_returns_none(self):
        self.assertIsNone(_suggest_command("/xyzzy"))


class TestFirstPositional(unittest.TestCase):

    def _first(self, argv):
        with mock.patch("sys.argv", ["tasker"] + argv):
            return _first_positional()

    def test_bool_flag_does_not_swallow_following_task(self):
        self.assertEqual(self._first(["--verbose", "do the thing"]), "do the thing")

    def test_bool_flag_does_not_swallow_following_subcommand(self):
        self.assertEqual(self._first(["--verbose", "workers"]), "workers")

    def test_value_flag_still_skips_its_value(self):
        self.assertEqual(self._first(["--mode", "cowork", "do the thing"]), "do the thing")

    def test_last_bool_flag_before_subcommand(self):
        self.assertEqual(self._first(["resume", "--last"]), "resume")


class TestVerboseLoggingDefault(unittest.TestCase):
    """
    main() defaults the interactive shell to ERROR-level logging (quiet
    chat flow); --verbose restores WARNING; TASKER_LOG_LEVEL always wins
    over both when explicitly set.
    """

    def _run_main(self, argv, env=None):
        import cli.shell as shell_mod

        # logging.basicConfig() is a no-op once handlers exist, so each
        # call in this test class needs a clean slate to actually observe
        # the level main() picks.
        logging.getLogger().handlers.clear()
        with mock.patch("sys.argv", ["tasker"] + argv), \
             mock.patch.dict("os.environ", env or {}, clear=False), \
             mock.patch.object(shell_mod, "_load_registry", return_value=mock.Mock(list_all=lambda: [])), \
             mock.patch("cli.shell.CheckpointStore"), \
             mock.patch.object(shell_mod, "_repl") as m_repl:
            shell_mod.main()
            return m_repl

    def tearDown(self):
        logging.getLogger().setLevel(logging.WARNING)

    def test_default_is_quiet_error_level(self):
        self._run_main([])
        self.assertEqual(logging.getLogger().getEffectiveLevel(), logging.ERROR)

    def test_verbose_flag_restores_warning_level(self):
        self._run_main(["--verbose"])
        self.assertEqual(logging.getLogger().getEffectiveLevel(), logging.WARNING)

    def test_env_var_overrides_both_defaults(self):
        self._run_main([], env={"TASKER_LOG_LEVEL": "INFO"})
        self.assertEqual(logging.getLogger().getEffectiveLevel(), logging.INFO)

    def test_env_var_overrides_verbose_flag_too(self):
        self._run_main(["--verbose"], env={"TASKER_LOG_LEVEL": "CRITICAL"})
        self.assertEqual(logging.getLogger().getEffectiveLevel(), logging.CRITICAL)


if __name__ == "__main__":
    unittest.main()

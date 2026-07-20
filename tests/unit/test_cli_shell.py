"""
Unit tests -- cli/shell.py REPL UX fixes (2026-07-20).

Live user testing found:
  1. `_first_positional()` mis-parsed boolean flags (e.g. --verbose) as if
     they took a value, swallowing the next real token.
  2. The REPL's "Unknown command" handler gave no guidance -- a user
     typing "/chat" (meaning "/mode chat") got no hint.
  3. The interactive shell showed WARNING+ plumbing logs by default,
     cluttering the chat flow; --verbose should restore them.

A second live session (same day) found CHAT mode itself was broken --
routed through the full orchestrator pipeline instead of a direct call
-- fixed via _run_chat_task() (tasker/runtime/dispatch.py, see
test_chat_dispatch.py). This file's TestReplChatCommands class covers
the REPL-level wiring for that fix: /model, /effort, /status, and that
chat-mode input dispatches through _run_chat_task while every other
mode still dispatches through _run_task.
"""
import io
import logging
import unittest
from contextlib import redirect_stdout
from unittest import mock

from cli.shell import _first_positional, _repl, _suggest_command


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


class TestReplChatCommands(unittest.TestCase):
    """
    Drives _repl()'s input loop directly with a scripted input() sequence
    and a fake registry (no real dispatch, no HTTP, no asyncio.run of a
    real pipeline -- _run_chat_task/_run_task are mocked at the call
    boundary since that's a hard requirement for the module-level
    `asyncio.run(...)` call inside _repl to not explode on a MagicMock).
    """

    def _registry_with(self, worker_ids):
        registry = mock.Mock()
        registry.get = lambda wid: mock.Mock(id=wid) if wid in worker_ids else None
        return registry

    def _run_repl(self, inputs, registry=None, initial_mode="chat"):
        registry = registry or self._registry_with(["lfm2.5-local", "pinned-worker"])
        store = mock.Mock()
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=inputs + ["/quit"]), \
             mock.patch("cli.shell._run_chat_task") as m_chat, \
             mock.patch("cli.shell._run_task") as m_task, \
             redirect_stdout(out):
            _repl(registry, store, initial_mode=initial_mode)
        return out.getvalue(), m_chat, m_task

    def test_model_command_pins_worker(self):
        output, _, _ = self._run_repl(["/model pinned-worker", "/model"])
        self.assertIn("CHAT model pinned to: pinned-worker", output)
        self.assertIn("Current CHAT model: pinned-worker (explicit)", output)

    def test_model_command_rejects_unknown_worker(self):
        output, _, _ = self._run_repl(["/model does-not-exist"])
        self.assertIn("Unknown worker id: 'does-not-exist'", output)

    def test_model_command_with_no_arg_shows_default(self):
        output, _, _ = self._run_repl(["/model"])
        self.assertIn("Current CHAT model: lfm2.5-local (default, effort=med)", output)

    def test_effort_command_sets_and_shows_level(self):
        output, _, _ = self._run_repl(["/effort high", "/effort"])
        self.assertIn("CHAT effort set to: high", output)
        self.assertIn("Current CHAT effort: high", output)

    def test_effort_command_rejects_invalid_level(self):
        output, _, _ = self._run_repl(["/effort extreme"])
        self.assertIn("Usage: /effort <low|med|high>", output)

    def test_status_includes_chat_model_and_effort(self):
        output, _, _ = self._run_repl(["/model pinned-worker", "/effort low", "/status"])
        self.assertIn("chat_model=pinned-worker", output)
        self.assertIn("chat_effort=low", output)

    def test_status_shows_default_model_when_unset(self):
        output, _, _ = self._run_repl(["/status"])
        self.assertIn("chat_model=lfm2.5-local (default)", output)
        self.assertIn("chat_effort=med", output)

    def test_chat_mode_input_dispatches_via_run_chat_task(self):
        _, m_chat, m_task = self._run_repl(["Hello"], initial_mode="chat")
        m_chat.assert_called_once()
        m_task.assert_not_called()
        call_args = m_chat.call_args
        self.assertEqual(call_args[0][0], "Hello")   # the raw message

    def test_non_chat_mode_input_dispatches_via_run_task(self):
        _, m_chat, m_task = self._run_repl(["do a code thing"], initial_mode="code")
        m_task.assert_called_once()
        m_chat.assert_not_called()

    def test_chat_history_persists_across_turns_in_same_session(self):
        _, m_chat, _ = self._run_repl(["first", "second"], initial_mode="chat")
        self.assertEqual(m_chat.call_count, 2)
        first_history_arg = m_chat.call_args_list[0][0][3]
        second_history_arg = m_chat.call_args_list[1][0][3]
        # same list object across turns -- the REPL's history accumulates
        # in place (mutated by _run_chat_task in production; here the
        # mock never mutates it, but identity is what matters).
        self.assertIs(first_history_arg, second_history_arg)

    def test_model_and_effort_forwarded_to_run_chat_task(self):
        _, m_chat, _ = self._run_repl(
            ["/model pinned-worker", "/effort high", "Hello"], initial_mode="chat"
        )
        kwargs = m_chat.call_args.kwargs
        self.assertEqual(kwargs["model_override"], "pinned-worker")
        self.assertEqual(kwargs["effort"], "high")


if __name__ == "__main__":
    unittest.main()

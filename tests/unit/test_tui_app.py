"""
Unit tests -- tasker/tui/app.py

Rudimentary interactive REPL behind the `tasker` console script (see that
module's docstring for the scoped-deviation rationale vs. the eventual
full Textual TUI). Everything here is mocked at the tasker.tui.app import
boundary -- no live Ollama calls, no real orchestrator/provider wiring,
matching this project's established test convention (see
test_setup_wizard.py, test_cli_session_wiring.py).
"""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from tasker.session.budget import BudgetSnapshot
from tasker.session.checkpoint import Checkpoint, CheckpointStore
from tasker.session.manager import SessionState
from tasker.tui import app as tui_app
from tasker.workers.base import (
    AgentRole,
    Capability,
    ExecutionPlan,
    OllamaPlan,
    PlanStep,
    StepStatus,
)
from tasker.workers.registry import WorkerRegistry


def _plan() -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="p1",
        original_task="test task",
        steps=[PlanStep(
            index=0, description="step 0", role=AgentRole.WORKER,
            required_capabilities={Capability.TOOL_USE}, depends_on=[],
            status=StepStatus.PENDING,
        )],
        dependency_graph={0: []},
    )


class _FakeBudget:
    def __init__(self, plan=OllamaPlan.PRO):
        self.plan = plan
        self.usage_consumed = 12.5
        self.weekly_usage_consumed = 40.0
        self.session_limit = 3000.0
        self.weekly_limit = 15000.0
        self.usage_pct = 12.5 / 3000.0
        self.weekly_usage_pct = 40.0 / 15000.0
        self.window_remaining = timedelta(hours=4, minutes=58, seconds=3, microseconds=123)


class _FakeSessionMgr:
    def __init__(self, state=SessionState.RUNNING):
        self.state = state


class _FakeConcurrencyMgr:
    slots_available = 3


def _fake_pipeline(state=SessionState.RUNNING):
    return (
        "tier1_tasker", "config-stub", _FakeBudget(), _FakeSessionMgr(state),
        _FakeConcurrencyMgr(), {"provider": "stub"}, "orchestrator-stub",
    )


# --------------------------------------------------------------------------- #
# _dispatch: per-mode pipeline caching + pause eviction
# --------------------------------------------------------------------------- #

class TestDispatch(unittest.IsolatedAsyncioTestCase):

    async def test_builds_pipeline_once_and_reuses_on_second_call(self):
        pipeline = _fake_pipeline()
        pipelines: dict = {}
        with mock.patch.object(tui_app, "_build_pipeline", return_value=pipeline) as m_build, \
             mock.patch.object(tui_app, "_run_task", new=mock.AsyncMock()) as m_run:
            await tui_app._dispatch("chat", "hi", WorkerRegistry(), mock.Mock(), pipelines)
            await tui_app._dispatch("chat", "hi again", WorkerRegistry(), mock.Mock(), pipelines)

        m_build.assert_called_once()
        self.assertEqual(m_run.call_count, 2)
        self.assertIs(pipelines["chat"], pipeline)
        # Both calls used the same cached pipeline object.
        self.assertIs(m_run.call_args_list[0].kwargs["pipeline"], pipeline)
        self.assertIs(m_run.call_args_list[1].kwargs["pipeline"], pipeline)

    async def test_different_modes_get_separate_pipelines(self):
        pipelines: dict = {}
        built = []

        def fake_build(mode, store, policy):
            p = _fake_pipeline()
            built.append((mode, p))
            return p

        with mock.patch.object(tui_app, "_build_pipeline", side_effect=fake_build), \
             mock.patch.object(tui_app, "_run_task", new=mock.AsyncMock()):
            await tui_app._dispatch("chat", "hi", WorkerRegistry(), mock.Mock(), pipelines)
            await tui_app._dispatch("cowork", "build it", WorkerRegistry(), mock.Mock(), pipelines)

        self.assertEqual(len(pipelines), 2)
        self.assertIsNot(pipelines["chat"], pipelines["cowork"])

    async def test_config_error_does_not_cache(self):
        pipelines: dict = {}
        with mock.patch.object(tui_app, "_build_pipeline", return_value=None) as m_build, \
             mock.patch.object(tui_app, "_run_task", new=mock.AsyncMock()) as m_run:
            await tui_app._dispatch("chat", "hi", WorkerRegistry(), mock.Mock(), pipelines)

        m_build.assert_called_once()
        m_run.assert_not_called()
        self.assertNotIn("chat", pipelines)

    async def test_paused_session_evicts_cached_pipeline(self):
        pipeline = _fake_pipeline(state=SessionState.RUNNING)
        pipelines = {"chat": pipeline}

        async def fake_run(*args, **kwargs):
            # Simulate _execute_steps pausing mid-run.
            kwargs["pipeline"][3].state = SessionState.PAUSED

        with mock.patch.object(tui_app, "_build_pipeline") as m_build, \
             mock.patch.object(tui_app, "_run_task", side_effect=fake_run):
            await tui_app._dispatch("chat", "hi", WorkerRegistry(), mock.Mock(), pipelines)

        m_build.assert_not_called()   # reused the pre-seeded cache entry
        self.assertNotIn("chat", pipelines)

    async def test_running_session_keeps_cached_pipeline(self):
        pipeline = _fake_pipeline(state=SessionState.RUNNING)
        pipelines = {"chat": pipeline}
        with mock.patch.object(tui_app, "_run_task", new=mock.AsyncMock()):
            await tui_app._dispatch("chat", "hi", WorkerRegistry(), mock.Mock(), pipelines)
        self.assertIn("chat", pipelines)


# --------------------------------------------------------------------------- #
# _print_budget
# --------------------------------------------------------------------------- #

class TestPrintBudget(unittest.TestCase):

    def test_no_pipeline_shows_config_only(self):
        profile = mock.Mock()
        profile.ollama_plan.value = "pro"
        with mock.patch("tasker.modes.base.ModeConfigurator.load_profile", return_value=profile), \
             mock.patch("builtins.print") as m_print:
            tui_app._print_budget("chat", None)
        printed = "\n".join(str(c.args[0]) for c in m_print.call_args_list if c.args)
        self.assertIn("mode=chat", printed)
        self.assertIn("plan=pro", printed)
        self.assertIn("No tasks run yet in this mode", printed)

    def test_config_error_reports_cleanly(self):
        with mock.patch(
            "tasker.modes.base.ModeConfigurator.load_profile",
            side_effect=RuntimeError("bad profile"),
        ), mock.patch("builtins.print") as m_print:
            tui_app._print_budget("chat", None)
        printed = "\n".join(str(c.args[0]) for c in m_print.call_args_list if c.args)
        self.assertIn("Config error", printed)

    def test_with_pipeline_shows_live_usage(self):
        pipeline = _fake_pipeline()
        with mock.patch("builtins.print") as m_print:
            tui_app._print_budget("cowork", pipeline)
        printed = "\n".join(str(c.args[0]) for c in m_print.call_args_list if c.args)
        self.assertIn("mode=cowork", printed)
        self.assertIn("plan=pro", printed)
        self.assertIn("state=running", printed)
        self.assertIn("12.5 / 3000", printed)
        self.assertIn("3 slot(s) free", printed)
        # window_remaining's microseconds must not leak into the display.
        self.assertNotIn("123", printed)


# --------------------------------------------------------------------------- #
# _repl: slash commands, driven via mocked input()
# --------------------------------------------------------------------------- #

class ReplTestCase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = CheckpointStore(store_dir=Path(self._tmp.name))
        self.registry = WorkerRegistry()

    def tearDown(self):
        self._tmp.cleanup()

    def _run_repl(self, lines: list[str], **kwargs):
        """Feed `lines` to input() in order and run _repl() to completion.
        Caller must ensure the sequence ends in /quit or /exit."""
        with mock.patch("builtins.input", side_effect=lines) as m_input, \
             mock.patch("builtins.print") as m_print:
            tui_app._repl(self.registry, self.store, **kwargs)
        printed = "\n".join(str(c.args[0]) for c in m_print.call_args_list if c.args)
        return m_input, printed

    def test_quit_exits_immediately(self):
        m_input, _ = self._run_repl(["/quit"])
        self.assertEqual(m_input.call_count, 1)

    def test_exit_alias_also_exits(self):
        m_input, _ = self._run_repl(["/exit"])
        self.assertEqual(m_input.call_count, 1)

    def test_keyboard_interrupt_exits_cleanly(self):
        with mock.patch("builtins.input", side_effect=KeyboardInterrupt), \
             mock.patch("builtins.print"):
            tui_app._repl(self.registry, self.store)   # must not raise

    def test_empty_line_is_ignored(self):
        m_input, _ = self._run_repl(["", "  ", "/quit"])
        self.assertEqual(m_input.call_count, 3)

    def test_prompt_shows_initial_mode(self):
        m_input, _ = self._run_repl(["/quit"], initial_mode="code")
        self.assertEqual(m_input.call_args_list[0].args[0], "tasker (code)> ")

    def test_mode_switch_updates_prompt(self):
        m_input, printed = self._run_repl(["/mode cowork", "/quit"])
        self.assertIn("Mode set to: cowork", printed)
        self.assertEqual(m_input.call_args_list[1].args[0], "tasker (cowork)> ")

    def test_mode_no_arg_shows_current(self):
        _, printed = self._run_repl(["/mode", "/quit"])
        self.assertIn("Current mode: chat", printed)

    def test_mode_invalid_is_rejected(self):
        m_input, printed = self._run_repl(["/mode bogus", "/quit"])
        self.assertIn("Unknown mode: 'bogus'", printed)
        # Prompt still reflects the unchanged mode on the next iteration.
        self.assertEqual(m_input.call_args_list[1].args[0], "tasker (chat)> ")

    def test_all_five_modes_accepted(self):
        for m in ("chat", "code", "cowork", "research", "secure"):
            _, printed = self._run_repl([f"/mode {m}", "/quit"])
            self.assertIn(f"Mode set to: {m}", printed)

    def test_workers_command_delegates_to_print_workers(self):
        with mock.patch.object(tui_app, "_print_workers") as m_pw:
            self._run_repl(["/workers", "/quit"])
        m_pw.assert_called_once_with(self.registry)

    def test_checkpoints_command_delegates_to_print_checkpoints(self):
        with mock.patch.object(tui_app, "_print_checkpoints") as m_pc:
            self._run_repl(["/checkpoints", "/quit"])
        m_pc.assert_called_once_with(self.store)

    def test_budget_command_delegates_with_mode_and_cached_pipeline(self):
        with mock.patch.object(tui_app, "_print_budget") as m_pb:
            self._run_repl(["/budget", "/quit"])
        m_pb.assert_called_once_with("chat", None)

    def test_help_lists_all_commands(self):
        _, printed = self._run_repl(["/help", "/quit"])
        for token in ("/mode", "/workers", "/budget", "/resume", "/checkpoints", "/help", "/quit"):
            self.assertIn(token, printed)

    def test_unknown_command_shows_message(self):
        _, printed = self._run_repl(["/bogus", "/quit"])
        self.assertIn("Unknown command: /bogus", printed)

    def test_resume_no_arg_shows_usage(self):
        _, printed = self._run_repl(["/resume", "/quit"])
        self.assertIn("Usage: /resume", printed)

    def test_resume_last_no_checkpoints(self):
        _, printed = self._run_repl(["/resume --last", "/quit"])
        self.assertIn("No checkpoints found.", printed)

    def test_resume_last_calls_resume_task_with_latest_id(self):
        cp = Checkpoint.new(
            mode="chat", hardware_profile="tier1_tasker", original_task="t",
            budget_snapshot=BudgetSnapshot(
                captured_at=datetime.now().astimezone(), usage_pct=1.0,
                weekly_usage_pct=0.2, window_remaining_s=0.0, plan="pro",
            ),
            plan=_plan(),
        )
        self.store.save(cp)
        with mock.patch.object(tui_app, "_resume_task", new=mock.AsyncMock()) as m_resume:
            self._run_repl(["/resume --last", "/quit"])
        m_resume.assert_called_once_with(cp.id, self.registry, self.store, None)

    def test_resume_explicit_id_calls_resume_task(self):
        with mock.patch.object(tui_app, "_resume_task", new=mock.AsyncMock()) as m_resume:
            self._run_repl(["/resume abc-123", "/quit"])
        m_resume.assert_called_once_with("abc-123", self.registry, self.store, None)

    def test_non_slash_input_dispatches_task(self):
        with mock.patch.object(tui_app, "_dispatch", new=mock.AsyncMock()) as m_dispatch:
            self._run_repl(["build me a widget", "/quit"])
        self.assertEqual(m_dispatch.call_count, 1)
        args = m_dispatch.call_args.args
        self.assertEqual(args[0], "chat")
        self.assertEqual(args[1], "build me a widget")
        self.assertEqual(args[2], self.registry)
        self.assertEqual(args[3], self.store)
        self.assertIsInstance(args[4], dict)

    def test_pipelines_dict_persists_across_turns_in_same_repl_call(self):
        """The same `pipelines` dict object must be threaded through every
        _dispatch call within one _repl() invocation, not rebuilt per turn."""
        seen_dicts = []

        async def fake_dispatch(mode, task, registry, store, pipelines):
            seen_dicts.append(pipelines)

        with mock.patch.object(tui_app, "_dispatch", side_effect=fake_dispatch):
            self._run_repl(["one", "two", "/quit"])
        self.assertIs(seen_dicts[0], seen_dicts[1])

    def test_startup_banner_shows_worker_count_and_mode(self):
        from tasker.workers.base import ComputeLocation, LatencyClass, ProviderType, ToolProtocol, WorkerManifest

        def _w(i):
            return WorkerManifest(
                id=f"w{i}", provider=ProviderType.OLLAMA, model_id=f"m{i}",
                compute_location=ComputeLocation.LOCAL_HARDWARE,
                capabilities={Capability.TOOL_USE}, tool_protocol=ToolProtocol.NATIVE,
                context_window=4096, cost_input=0.0, cost_output=0.0,
                ollama_usage_level=None, latency_class=LatencyClass.FAST,
                available=True, requires_gpu=False, vram_mb=None,
            )
        self.registry.register(_w(1))
        self.registry.register(_w(2))
        _, printed = self._run_repl(["/quit"])
        self.assertIn("workers: 2 registered", printed)
        self.assertIn("mode: chat", printed)


# --------------------------------------------------------------------------- #
# main()
# --------------------------------------------------------------------------- #

class TestMain(unittest.TestCase):

    def test_main_wires_registry_store_and_repl(self):
        registry = WorkerRegistry()
        store = mock.Mock()
        with mock.patch.object(tui_app, "_load_registry", return_value=registry) as m_load, \
             mock.patch.object(tui_app, "CheckpointStore", return_value=store), \
             mock.patch.object(tui_app, "_repl") as m_repl:
            tui_app.main()
        m_load.assert_called_once()
        m_repl.assert_called_once_with(registry, store)


if __name__ == "__main__":
    unittest.main()

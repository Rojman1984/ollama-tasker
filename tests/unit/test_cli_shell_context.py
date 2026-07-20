"""
Unit tests -- cli/shell.py context controls (2026-07-20 REPL/TUI UX
sprint, part 2): /context, /models, /budget-initializes-at-0.0, and the
per-mode pipeline caching that backs all three.
"""
import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from unittest import mock

from cli.shell import _format_hms, _print_budget, _print_models, _repl
from tasker.session.budget import OllamaSessionBudget
from tasker.session.manager import SessionState
from tasker.workers.base import (
    Capability,
    ComputeLocation,
    LatencyClass,
    OllamaPlan,
    ProviderType,
    ToolProtocol,
    WorkerManifest,
)
from tasker.workers.registry import WorkerRegistry


def _worker(
    worker_id: str,
    compute_location=ComputeLocation.LOCAL_HARDWARE,
    tool_protocol=ToolProtocol.NATIVE,
    context_window=32768,
) -> WorkerManifest:
    return WorkerManifest(
        id=worker_id,
        provider=ProviderType.OLLAMA,
        model_id="test:latest",
        compute_location=compute_location,
        capabilities={Capability.TOOL_USE},
        tool_protocol=tool_protocol,
        context_window=context_window,
        cost_input=0.0,
        cost_output=0.0,
        ollama_usage_level=None,
        latency_class=LatencyClass.MEDIUM,
        available=True,
        requires_gpu=False,
        vram_mb=None,
    )


class TestFormatHms(unittest.TestCase):

    def test_formats_hours_minutes_seconds(self):
        self.assertEqual(_format_hms(timedelta(hours=4, minutes=58, seconds=32)), "4:58:32")

    def test_zero(self):
        self.assertEqual(_format_hms(timedelta(seconds=0)), "0:00:00")

    def test_negative_clamped_to_zero(self):
        self.assertEqual(_format_hms(timedelta(seconds=-5)), "0:00:00")


class TestPrintBudget(unittest.TestCase):

    def _pipeline_with_budget(self, usage=0.0, plan=OllamaPlan.PRO):
        budget = OllamaSessionBudget(plan=plan, window_start=datetime.now().astimezone())
        budget.usage_consumed = usage
        return ("tier1_tasker", mock.Mock(), budget, mock.Mock(), mock.Mock(), mock.Mock(), mock.Mock())

    def test_initializes_at_zero(self):
        out = io.StringIO()
        with redirect_stdout(out):
            _print_budget("chat", self._pipeline_with_budget(usage=0.0))
        self.assertIn("budget=0.0/", out.getvalue())
        self.assertIn("(0.0%)", out.getvalue())

    def test_shows_accumulated_usage(self):
        out = io.StringIO()
        with redirect_stdout(out):
            _print_budget("chat", self._pipeline_with_budget(usage=42.5))
        self.assertIn("budget=42.5/", out.getvalue())

    def test_none_pipeline_reports_unavailable_not_a_crash(self):
        out = io.StringIO()
        with redirect_stdout(out):
            _print_budget("chat", None)
        self.assertIn("budget unavailable", out.getvalue())


class TestPrintModels(unittest.TestCase):

    def test_groups_default_local_cloud(self):
        registry = WorkerRegistry()
        registry.register(_worker("lfm2.5-local"))  # DEFAULT_CHAT_WORKER_ID
        registry.register(_worker("other-local", context_window=16384))
        registry.register(_worker("cloud-worker", compute_location=ComputeLocation.OLLAMA_CLOUD))
        out = io.StringIO()
        with mock.patch("tasker.config.detect.load_cached_gpu_info", return_value=None), \
             redirect_stdout(out):
            _print_models(registry)
        text = out.getvalue()
        self.assertIn("DEFAULT:", text)
        self.assertIn("lfm2.5-local", text)
        self.assertIn("LOCAL:", text)
        self.assertIn("other-local", text)
        self.assertIn("CLOUD:", text)
        self.assertIn("cloud-worker", text)

    def test_shows_tool_protocol_and_max_context(self):
        registry = WorkerRegistry()
        registry.register(_worker("lfm2.5-local", tool_protocol=ToolProtocol.LFM25, context_window=131072))
        out = io.StringIO()
        with mock.patch("tasker.config.detect.load_cached_gpu_info", return_value=None), \
             redirect_stdout(out):
            _print_models(registry)
        text = out.getvalue()
        self.assertIn("lfm25", text)
        self.assertIn("131072", text)

    def test_empty_registry(self):
        out = io.StringIO()
        with redirect_stdout(out):
            _print_models(WorkerRegistry())
        self.assertIn("no workers registered", out.getvalue())

    def test_vram_hint_shown_when_capped(self):
        from tasker.config.gpu_backends import GPUInfo

        registry = WorkerRegistry()
        w = _worker("lfm2.5-local", context_window=200_000)
        w.vram_mb = 2000
        registry.register(w)
        gpu = GPUInfo(vendor="nvidia", name="small", memory_mb=4096, is_unified_memory=False)
        out = io.StringIO()
        with mock.patch("tasker.config.detect.load_cached_gpu_info", return_value=gpu), \
             redirect_stdout(out):
            _print_models(registry)
        self.assertIn("fits ~", out.getvalue())


class TestReplContextAndBudgetCommands(unittest.TestCase):

    def _registry_with(self, worker_ids):
        registry = mock.Mock()
        registry.get = lambda wid: mock.Mock(id=wid) if wid in worker_ids else None
        registry.list_all = lambda: []
        return registry

    def _fake_pipeline(self):
        budget = OllamaSessionBudget(plan=OllamaPlan.PRO, window_start=datetime.now().astimezone())
        session_mgr = mock.Mock()
        session_mgr.state = SessionState.RUNNING
        return ("tier1_tasker", mock.Mock(), budget, session_mgr, mock.Mock(), mock.Mock(), mock.Mock())

    def _run_repl(self, inputs, initial_mode="chat"):
        registry = self._registry_with(["lfm2.5-local"])
        store = mock.Mock()
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=inputs + ["/quit"]), \
             mock.patch("cli.shell._run_chat_task"), \
             mock.patch("cli.shell._run_task"), \
             mock.patch("cli.shell._build_pipeline", return_value=self._fake_pipeline()), \
             mock.patch("cli.shell._init_readline"), \
             mock.patch("cli.shell.default_transcript_path", return_value=None), \
             mock.patch("cli.shell._save_history"), \
             redirect_stdout(out):
            _repl(registry, store, initial_mode=initial_mode)
        return out.getvalue()

    def test_budget_shows_real_zero_at_session_start_not_placeholder(self):
        output = self._run_repl(["/budget"])
        self.assertNotIn("not active", output)
        self.assertIn("budget=0.0/", output)

    def test_context_command_sets_and_shows(self):
        output = self._run_repl(["/context 4096", "/context"])
        self.assertIn("CHAT context override set to: 4096 tokens", output)
        self.assertIn("Current CHAT context override: 4096 tokens", output)

    def test_context_command_rejects_non_positive(self):
        output = self._run_repl(["/context 0", "/context -5", "/context abc"])
        self.assertEqual(output.count("Usage: /context <positive integer tokens>"), 3)

    def test_context_command_default_message(self):
        output = self._run_repl(["/context"])
        self.assertIn("No CHAT context override set", output)

    def test_status_includes_chat_context(self):
        output = self._run_repl(["/context 8192", "/status"])
        self.assertIn("chat_context=8192 tokens", output)

    def test_status_shows_auto_when_no_override(self):
        output = self._run_repl(["/status"])
        self.assertIn("chat_context=auto", output)

    def test_context_override_forwarded_to_run_chat_task(self):
        registry = self._registry_with(["lfm2.5-local"])
        store = mock.Mock()
        with mock.patch("builtins.input", side_effect=["/context 4096", "Hello", "/quit"]), \
             mock.patch("cli.shell._run_chat_task") as m_chat, \
             mock.patch("cli.shell._build_pipeline", return_value=self._fake_pipeline()), \
             mock.patch("cli.shell._init_readline"), \
             mock.patch("cli.shell.default_transcript_path", return_value=None), \
             mock.patch("cli.shell._save_history"), \
             redirect_stdout(io.StringIO()):
            _repl(registry, store, initial_mode="chat")
        kwargs = m_chat.call_args.kwargs
        self.assertEqual(kwargs["context_override"], 4096)

    def test_models_command_and_alias_both_work(self):
        registry = WorkerRegistry()
        registry.register(_worker("lfm2.5-local"))
        store = mock.Mock()
        with mock.patch("builtins.input", side_effect=["/models", "/model list", "/quit"]), \
             mock.patch("cli.shell._run_chat_task"), \
             mock.patch("cli.shell._build_pipeline", return_value=self._fake_pipeline()), \
             mock.patch("tasker.config.detect.load_cached_gpu_info", return_value=None), \
             mock.patch("cli.shell._init_readline"), \
             mock.patch("cli.shell.default_transcript_path", return_value=None), \
             mock.patch("cli.shell._save_history"), \
             redirect_stdout(io.StringIO()) as out:
            _repl(registry, store, initial_mode="chat")
        self.assertEqual(out.getvalue().count("DEFAULT:"), 2)


class TestPipelineCachingAndEviction(unittest.TestCase):
    """The REPL builds one pipeline per mode up front and reuses it across
    turns (so budget accumulates); a pipeline whose session went PAUSED is
    evicted so the next task in that mode starts fresh."""

    def _registry_with(self, worker_ids):
        registry = mock.Mock()
        registry.get = lambda wid: mock.Mock(id=wid) if wid in worker_ids else None
        registry.list_all = lambda: []
        return registry

    def test_same_pipeline_object_reused_across_chat_turns(self):
        budget = OllamaSessionBudget(plan=OllamaPlan.PRO, window_start=datetime.now().astimezone())
        session_mgr = mock.Mock()
        session_mgr.state = SessionState.RUNNING
        pipeline = ("tier1_tasker", mock.Mock(), budget, session_mgr, mock.Mock(), mock.Mock(), mock.Mock())

        registry = self._registry_with(["lfm2.5-local"])
        store = mock.Mock()
        with mock.patch("builtins.input", side_effect=["first", "second", "/quit"]), \
             mock.patch("cli.shell._run_chat_task") as m_chat, \
             mock.patch("cli.shell._build_pipeline", return_value=pipeline) as m_build, \
             mock.patch("cli.shell._init_readline"), \
             mock.patch("cli.shell.default_transcript_path", return_value=None), \
             mock.patch("cli.shell._save_history"), \
             redirect_stdout(io.StringIO()):
            _repl(registry, store, initial_mode="chat")

        # _build_pipeline is called once (REPL startup), not once per turn.
        self.assertEqual(m_build.call_count, 1)
        first_pipeline_arg = m_chat.call_args_list[0].kwargs["pipeline"]
        second_pipeline_arg = m_chat.call_args_list[1].kwargs["pipeline"]
        self.assertIs(first_pipeline_arg, second_pipeline_arg)

    def test_non_chat_mode_paused_pipeline_evicted_and_rebuilt(self):
        running_mgr = mock.Mock()
        running_mgr.state = SessionState.RUNNING
        paused_mgr = mock.Mock()
        paused_mgr.state = SessionState.PAUSED

        pipeline1 = ("tier1_tasker", mock.Mock(), mock.Mock(), paused_mgr, mock.Mock(), mock.Mock(), mock.Mock())
        pipeline2 = ("tier1_tasker", mock.Mock(), mock.Mock(), running_mgr, mock.Mock(), mock.Mock(), mock.Mock())

        registry = self._registry_with([])
        store = mock.Mock()
        with mock.patch("builtins.input", side_effect=["do a thing", "do another", "/quit"]), \
             mock.patch("cli.shell._run_task") as m_task, \
             mock.patch("cli.shell._build_pipeline", side_effect=[pipeline1, pipeline2]) as m_build, \
             mock.patch("cli.shell._init_readline"), \
             mock.patch("cli.shell.default_transcript_path", return_value=None), \
             mock.patch("cli.shell._save_history"), \
             redirect_stdout(io.StringIO()):
            _repl(registry, store, initial_mode="code")

        # First call used pipeline1 (paused after dispatch -> evicted);
        # second call had to rebuild -> pipeline2.
        self.assertEqual(m_build.call_count, 2)
        self.assertIs(m_task.call_args_list[0].kwargs["pipeline"], pipeline1)
        self.assertIs(m_task.call_args_list[1].kwargs["pipeline"], pipeline2)


if __name__ == "__main__":
    unittest.main()

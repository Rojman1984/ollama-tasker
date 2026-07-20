"""
Unit tests -- tool executor (tasker/tools/executor.py)

Covers the real dispatch layer for BASH/GIT/FILE_READ/FILE_WRITE/
CODE_SEARCH, the LOCAL_HARDWARE gate for mutating/executing tools, the
BASH denylist, path containment, timeouts, and output truncation.
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tasker.tools.executor import (
    _MAX_OUTPUT_CHARS,
    _exec_calculator,
    _exec_linter,
    _exec_test_runner,
    _run_pytest,
    _run_unittest,
    execute_tool,
)
from tasker.workers.base import (
    Capability,
    ComputeLocation,
    LatencyClass,
    ProviderType,
    ToolProtocol,
    WorkerManifest,
    WorkerToolResult,
)


def _worker(compute_location: ComputeLocation = ComputeLocation.LOCAL_HARDWARE) -> WorkerManifest:
    return WorkerManifest(
        id="w1",
        provider=ProviderType.OLLAMA,
        model_id="lfm2.5-thinking:latest",
        compute_location=compute_location,
        capabilities={Capability.TOOL_USE},
        tool_protocol=ToolProtocol.LFM25,
        context_window=32768,
        cost_input=0.0,
        cost_output=0.0,
        ollama_usage_level=None,
        latency_class=LatencyClass.MEDIUM,
        available=True,
        requires_gpu=False,
        vram_mb=None,
    )


def _tr(tool_name: str, tool_input: dict) -> WorkerToolResult:
    return WorkerToolResult(
        tool_name=tool_name, tool_input=tool_input, tool_output=None, error=None, duration_ms=0,
    )


class ToolExecutorTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class TestBash(ToolExecutorTestCase):

    async def test_success(self):
        r = await execute_tool(_tr("bash", {"command": "echo hi"}), worker=_worker(), cwd=self.cwd)
        self.assertIsNone(r.error)
        self.assertEqual(r.tool_output, "hi\n")

    async def test_nonzero_exit_is_error(self):
        r = await execute_tool(_tr("bash", {"command": "exit 3"}), worker=_worker(), cwd=self.cwd)
        self.assertEqual(r.error, "exited with code 3")

    async def test_missing_command_is_error(self):
        r = await execute_tool(_tr("bash", {}), worker=_worker(), cwd=self.cwd)
        self.assertIn("missing required", r.error)

    async def test_denylist_blocks_dangerous_command(self):
        r = await execute_tool(_tr("bash", {"command": "sudo rm -rf /"}), worker=_worker(), cwd=self.cwd)
        self.assertIn("denylist", r.error)
        self.assertIsNone(r.tool_output)

    async def test_local_hardware_gate_blocks_cloud_worker(self):
        r = await execute_tool(
            _tr("bash", {"command": "echo hi"}),
            worker=_worker(ComputeLocation.OLLAMA_CLOUD),
            cwd=self.cwd,
        )
        self.assertIn("LOCAL_HARDWARE", r.error)
        self.assertIsNone(r.tool_output)

    async def test_timeout_kills_process(self):
        r = await execute_tool(
            _tr("bash", {"command": "sleep 5"}), worker=_worker(), cwd=self.cwd, timeout_s=0.2,
        )
        self.assertIn("timed out", r.error)

    async def test_output_truncated(self):
        r = await execute_tool(
            _tr("bash", {"command": "python3 -c \"print('x' * 20000)\""}),
            worker=_worker(), cwd=self.cwd,
        )
        self.assertLessEqual(len(r.tool_output), _MAX_OUTPUT_CHARS + len("\n... [output truncated]"))
        self.assertTrue(r.tool_output.endswith("[output truncated]"))

    async def test_never_raises_on_garbage_input(self):
        r = await execute_tool(_tr("bash", {"command": 12345}), worker=_worker(), cwd=self.cwd)
        self.assertIsNotNone(r.error)


class TestGit(ToolExecutorTestCase):

    async def test_success(self):
        r = await execute_tool(_tr("git", {"args": "--version"}), worker=_worker(), cwd=self.cwd)
        self.assertIsNone(r.error)
        self.assertIn("git version", r.tool_output)

    async def test_invalid_subcommand_is_error(self):
        r = await execute_tool(_tr("git", {"args": "not-a-real-subcommand"}), worker=_worker(), cwd=self.cwd)
        self.assertIsNotNone(r.error)

    async def test_local_hardware_gate_blocks_cloud_worker(self):
        r = await execute_tool(
            _tr("git", {"args": "--version"}), worker=_worker(ComputeLocation.OLLAMA_CLOUD), cwd=self.cwd,
        )
        self.assertIn("LOCAL_HARDWARE", r.error)

    async def test_no_shell_operators_possible(self):
        """Argv-based exec -- a shell operator in args is passed as a literal
        argument to git, not interpreted, unlike BASH."""
        r = await execute_tool(_tr("git", {"args": "status; echo pwned"}), worker=_worker(), cwd=self.cwd)
        self.assertIsNotNone(r.error)
        self.assertNotIn("pwned", r.tool_output or "")


class TestFileReadWrite(ToolExecutorTestCase):

    async def test_write_then_read(self):
        w = await execute_tool(
            _tr("file_write", {"path": "notes.txt", "content": "hello"}), worker=_worker(), cwd=self.cwd,
        )
        self.assertIsNone(w.error)
        r = await execute_tool(_tr("file_read", {"path": "notes.txt"}), worker=_worker(), cwd=self.cwd)
        self.assertEqual(r.tool_output, "hello")

    async def test_write_creates_parent_dirs(self):
        w = await execute_tool(
            _tr("file_write", {"path": "sub/dir/notes.txt", "content": "x"}), worker=_worker(), cwd=self.cwd,
        )
        self.assertIsNone(w.error)
        self.assertTrue((self.cwd / "sub" / "dir" / "notes.txt").exists())

    async def test_read_missing_file_is_error(self):
        r = await execute_tool(_tr("file_read", {"path": "nope.txt"}), worker=_worker(), cwd=self.cwd)
        self.assertIn("no such file", r.error)

    async def test_read_path_traversal_rejected(self):
        r = await execute_tool(_tr("file_read", {"path": "../../etc/passwd"}), worker=_worker(), cwd=self.cwd)
        self.assertIn("escapes", r.error)

    async def test_write_path_traversal_rejected(self):
        r = await execute_tool(
            _tr("file_write", {"path": "/etc/passwd", "content": "x"}), worker=_worker(), cwd=self.cwd,
        )
        self.assertIn("escapes", r.error)

    async def test_write_local_hardware_gate_blocks_cloud_worker(self):
        r = await execute_tool(
            _tr("file_write", {"path": "notes.txt", "content": "x"}),
            worker=_worker(ComputeLocation.OLLAMA_CLOUD),
            cwd=self.cwd,
        )
        self.assertIn("LOCAL_HARDWARE", r.error)

    async def test_read_ungated_for_cloud_worker(self):
        (self.cwd / "notes.txt").write_text("hello")
        r = await execute_tool(
            _tr("file_read", {"path": "notes.txt"}), worker=_worker(ComputeLocation.OLLAMA_CLOUD), cwd=self.cwd,
        )
        self.assertIsNone(r.error)
        self.assertEqual(r.tool_output, "hello")


class TestCodeSearch(ToolExecutorTestCase):

    async def test_finds_match(self):
        (self.cwd / "a.py").write_text("def foo():\n    pass\n")
        r = await execute_tool(_tr("code_search", {"pattern": "def foo"}), worker=_worker(), cwd=self.cwd)
        self.assertIsNone(r.error)
        self.assertIn("a.py", r.tool_output)

    async def test_no_matches_is_not_an_error(self):
        (self.cwd / "a.py").write_text("def foo():\n    pass\n")
        r = await execute_tool(_tr("code_search", {"pattern": "nonexistent_symbol"}), worker=_worker(), cwd=self.cwd)
        self.assertIsNone(r.error)
        self.assertEqual(r.tool_output, "(no matches)")

    async def test_missing_pattern_is_error(self):
        r = await execute_tool(_tr("code_search", {}), worker=_worker(), cwd=self.cwd)
        self.assertIn("missing required", r.error)


class TestWebSearch(ToolExecutorTestCase):
    """WEB_SEARCH via the Brave Search API (SDD 5.1a). All HTTP is mocked
    via tasker.tools.executor._search_get_fn -- never a real network call."""

    def _mock_search(self, status, data):
        async def fn(url, headers, timeout_s):
            return status, data
        return mock.patch("tasker.tools.executor._search_get_fn", fn)

    async def test_missing_query(self):
        with mock.patch.dict("os.environ", {"BRAVE_API_KEY": "key"}):
            r = await execute_tool(_tr("web_search", {}), worker=_worker(), cwd=self.cwd)
        self.assertIn("missing required", r.error)

    async def test_no_api_key_configured(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            r = await execute_tool(
                _tr("web_search", {"query": "test"}), worker=_worker(), cwd=self.cwd,
            )
        self.assertIsNone(r.tool_output)
        self.assertIn("BRAVE_API_KEY", r.error)

    async def test_successful_search_returns_structured_results(self):
        brave_response = {
            "web": {
                "results": [
                    {"title": "Result One", "url": "https://example.com/one", "description": "First result"},
                    {"title": "Result Two", "url": "https://example.com/two", "description": "Second result"},
                ]
            }
        }
        with mock.patch.dict("os.environ", {"BRAVE_API_KEY": "key"}), \
             self._mock_search(200, brave_response):
            r = await execute_tool(
                _tr("web_search", {"query": "test query"}), worker=_worker(), cwd=self.cwd,
            )
        self.assertIsNone(r.error)
        self.assertEqual(r.tool_output["query"], "test query")
        self.assertEqual(len(r.tool_output["results"]), 2)
        self.assertEqual(r.tool_output["results"][0]["url"], "https://example.com/one")
        self.assertEqual(r.tool_output["results"][0]["title"], "Result One")

    async def test_results_without_a_url_are_dropped(self):
        brave_response = {"web": {"results": [{"title": "No URL", "description": "x"}]}}
        with mock.patch.dict("os.environ", {"BRAVE_API_KEY": "key"}), \
             self._mock_search(200, brave_response):
            r = await execute_tool(
                _tr("web_search", {"query": "q"}), worker=_worker(), cwd=self.cwd,
            )
        self.assertEqual(r.tool_output["results"], [])

    async def test_capped_at_max_results(self):
        brave_response = {
            "web": {"results": [
                {"title": f"R{i}", "url": f"https://example.com/{i}", "description": ""}
                for i in range(10)
            ]}
        }
        with mock.patch.dict("os.environ", {"BRAVE_API_KEY": "key"}), \
             self._mock_search(200, brave_response):
            r = await execute_tool(
                _tr("web_search", {"query": "q"}), worker=_worker(), cwd=self.cwd,
            )
        self.assertEqual(len(r.tool_output["results"]), 5)

    async def test_non_200_status(self):
        with mock.patch.dict("os.environ", {"BRAVE_API_KEY": "key"}), \
             self._mock_search(401, {"error": "unauthorized"}):
            r = await execute_tool(
                _tr("web_search", {"query": "q"}), worker=_worker(), cwd=self.cwd,
            )
        self.assertIsNone(r.tool_output)
        self.assertIn("401", r.error)

    async def test_transport_exception_reported_not_raised(self):
        async def raising_fn(url, headers, timeout_s):
            raise ConnectionError("refused")

        with mock.patch.dict("os.environ", {"BRAVE_API_KEY": "key"}), \
             mock.patch("tasker.tools.executor._search_get_fn", raising_fn):
            r = await execute_tool(
                _tr("web_search", {"query": "q"}), worker=_worker(), cwd=self.cwd,
            )
        self.assertIn("refused", r.error)

    async def test_works_from_cloud_worker_not_local_gated(self):
        # WEB_SEARCH/RETRIEVE are network reads, not local execution --
        # never in _LOCAL_ONLY_TOOLS, must work from an OLLAMA_CLOUD worker.
        with mock.patch.dict("os.environ", {"BRAVE_API_KEY": "key"}), \
             self._mock_search(200, {"web": {"results": []}}):
            r = await execute_tool(
                _tr("web_search", {"query": "q"}),
                worker=_worker(ComputeLocation.OLLAMA_CLOUD), cwd=self.cwd,
            )
        self.assertIsNone(r.error)


class TestRetrieve(ToolExecutorTestCase):
    """RETRIEVE -- fetch a URL and strip it to readable text (SDD 5.1a).
    All HTTP is mocked via tasker.tools.executor._page_get_fn."""

    def _mock_page(self, status, body):
        async def fn(url, timeout_s):
            return status, body
        return mock.patch("tasker.tools.executor._page_get_fn", fn)

    async def test_missing_url(self):
        r = await execute_tool(_tr("retrieve", {}), worker=_worker(), cwd=self.cwd)
        self.assertIn("missing required", r.error)

    async def test_rejects_non_http_url(self):
        r = await execute_tool(
            _tr("retrieve", {"url": "not-a-url"}), worker=_worker(), cwd=self.cwd,
        )
        self.assertIn("absolute http", r.error)

    async def test_strips_html_to_readable_text(self):
        html = "<html><head><style>.x{}</style></head><body><h1>Title</h1><p>Hello &amp; welcome.</p></body></html>"
        with self._mock_page(200, html):
            r = await execute_tool(
                _tr("retrieve", {"url": "https://example.com/page"}), worker=_worker(), cwd=self.cwd,
            )
        self.assertIsNone(r.error)
        self.assertIn("Title", r.tool_output["content"])
        self.assertIn("Hello & welcome.", r.tool_output["content"])
        self.assertNotIn("<h1>", r.tool_output["content"])
        self.assertEqual(r.tool_output["url"], "https://example.com/page")

    async def test_script_and_style_blocks_dropped(self):
        html = "<p>Real content</p><script>evil_stuff();</script><style>body{color:red}</style>"
        with self._mock_page(200, html):
            r = await execute_tool(
                _tr("retrieve", {"url": "https://example.com"}), worker=_worker(), cwd=self.cwd,
            )
        self.assertIn("Real content", r.tool_output["content"])
        self.assertNotIn("evil_stuff", r.tool_output["content"])
        self.assertNotIn("color:red", r.tool_output["content"])

    async def test_non_200_status(self):
        with self._mock_page(404, "not found"):
            r = await execute_tool(
                _tr("retrieve", {"url": "https://example.com/missing"}), worker=_worker(), cwd=self.cwd,
            )
        self.assertIsNone(r.tool_output)
        self.assertIn("404", r.error)

    async def test_long_content_truncated(self):
        html = "<p>" + ("word " * 5000) + "</p>"
        with self._mock_page(200, html):
            r = await execute_tool(
                _tr("retrieve", {"url": "https://example.com"}), worker=_worker(), cwd=self.cwd,
            )
        self.assertLessEqual(len(r.tool_output["content"]), _MAX_OUTPUT_CHARS + 50)

    async def test_works_from_cloud_worker_not_local_gated(self):
        with self._mock_page(200, "<p>ok</p>"):
            r = await execute_tool(
                _tr("retrieve", {"url": "https://example.com"}),
                worker=_worker(ComputeLocation.OLLAMA_CLOUD), cwd=self.cwd,
            )
        self.assertIsNone(r.error)


class TestCalculator(ToolExecutorTestCase):

    async def test_addition(self):
        r = await execute_tool(_tr("calculator", {"expression": "2 + 3"}), worker=_worker(), cwd=self.cwd)
        self.assertIsNone(r.error)
        self.assertEqual(r.tool_output["result"], 5)

    async def test_subtraction_and_unary_minus(self):
        r = await execute_tool(_tr("calculator", {"expression": "10 - 3 - 2"}), worker=_worker(), cwd=self.cwd)
        self.assertEqual(r.tool_output["result"], 5)
        r2 = await execute_tool(_tr("calculator", {"expression": "-5 + 2"}), worker=_worker(), cwd=self.cwd)
        self.assertEqual(r2.tool_output["result"], -3)

    async def test_multiplication_division_floor_power(self):
        r = await execute_tool(_tr("calculator", {"expression": "(2 + 3) * 4"}), worker=_worker(), cwd=self.cwd)
        self.assertEqual(r.tool_output["result"], 20)
        r2 = await execute_tool(_tr("calculator", {"expression": "7 // 2"}), worker=_worker(), cwd=self.cwd)
        self.assertEqual(r2.tool_output["result"], 3)
        r3 = await execute_tool(_tr("calculator", {"expression": "2 ** 10"}), worker=_worker(), cwd=self.cwd)
        self.assertEqual(r3.tool_output["result"], 1024)
        r4 = await execute_tool(_tr("calculator", {"expression": "7 % 3"}), worker=_worker(), cwd=self.cwd)
        self.assertEqual(r4.tool_output["result"], 1)

    async def test_missing_expression(self):
        r = await execute_tool(_tr("calculator", {}), worker=_worker(), cwd=self.cwd)
        self.assertIn("missing required", r.error)

    async def test_eval_blocked(self):
        r = await execute_tool(_tr("calculator", {"expression": "__import__('os').system('echo pwned')"}), worker=_worker(), cwd=self.cwd)
        self.assertIsNotNone(r.error)
        self.assertNotIn("pwned", str(r.tool_output) + r.error)

    async def test_function_call_blocked(self):
        r = await execute_tool(_tr("calculator", {"expression": "abs(-5)"}), worker=_worker(), cwd=self.cwd)
        self.assertIsNotNone(r.error)

    async def test_not_local_gated(self):
        r = await execute_tool(_tr("calculator", {"expression": "1 + 1"}), worker=_worker(ComputeLocation.OLLAMA_CLOUD), cwd=self.cwd)
        self.assertIsNone(r.error)
        self.assertEqual(r.tool_output["result"], 2)


class TestTestRunner(ToolExecutorTestCase):

    async def test_pytest_success_parsed(self):
        pytest_output = (
            "test_ok.py::test_passes PASSED\n"
            "1 passed in 0.01s\n"
        )
        with mock.patch("tasker.tools.executor.shutil.which", return_value="/fake/pytest"), \
             mock.patch("tasker.tools.executor._run_argv", return_value=(pytest_output, None)):
            r = await _run_pytest(self.cwd, self.cwd, 30.0)
        self.assertIsNone(r[1], msg=r[1])
        self.assertEqual(r[0]["framework"], "pytest")
        self.assertEqual(r[0]["passed"], 1)
        self.assertEqual(r[0]["failed"], 0)
        self.assertEqual(r[0]["skipped"], 0)
        self.assertEqual(r[0]["failing_tests"], [])

    async def test_pytest_failure_parsed(self):
        pytest_output = (
            "test_fail.py::test_fails FAILED\n"
            "1 failed in 0.01s\n"
        )
        with mock.patch("tasker.tools.executor.shutil.which", return_value="/fake/pytest"), \
             mock.patch("tasker.tools.executor._run_argv", return_value=(pytest_output, "exited with code 1")):
            r = await _run_pytest(self.cwd, self.cwd, 30.0)
        # pytest exit code is surfaced as a note, not a tool error.
        self.assertIsNone(r[1], msg=r[1])
        self.assertEqual(r[0]["framework"], "pytest")
        self.assertEqual(r[0]["passed"], 0)
        self.assertEqual(r[0]["failed"], 1)
        self.assertEqual(r[0]["failing_tests"], ["test_fail.py::test_fails"])

    async def test_pytest_skipped_parsed(self):
        pytest_output = (
            "test_skip.py::test_skipped SKIPPED\n"
            "1 skipped in 0.01s\n"
        )
        with mock.patch("tasker.tools.executor.shutil.which", return_value="/fake/pytest"), \
             mock.patch("tasker.tools.executor._run_argv", return_value=(pytest_output, None)):
            r = await _run_pytest(self.cwd, self.cwd, 30.0)
        self.assertEqual(r[0]["passed"], 0)
        self.assertEqual(r[0]["failed"], 0)
        self.assertEqual(r[0]["skipped"], 1)

    async def test_unittest_success_parsed(self):
        unittest_output = (
            "test_pass (__main__.T) ... ok\n"
            "Ran 1 test in 0.003s\n\nOK\n"
        )
        with mock.patch("tasker.tools.executor._run_argv", return_value=(unittest_output, None)):
            r = await _run_unittest(self.cwd, self.cwd, 30.0)
        self.assertIsNone(r[1], msg=r[1])
        self.assertEqual(r[0]["framework"], "unittest")
        self.assertEqual(r[0]["passed"], 1)
        self.assertEqual(r[0]["failed"], 0)
        self.assertEqual(r[0]["failing_tests"], [])

    async def test_unittest_failure_parsed(self):
        unittest_output = (
            "test_fail (__main__.T) ... FAIL\n"
            "Ran 1 test in 0.003s\n\nFAILED (failures=1)\n"
        )
        with mock.patch("tasker.tools.executor._run_argv", return_value=(unittest_output, "exited with code 1")):
            r = await _run_unittest(self.cwd, self.cwd, 30.0)
        self.assertIsNone(r[1], msg=r[1])
        self.assertEqual(r[0]["passed"], 0)
        self.assertEqual(r[0]["failed"], 1)
        self.assertEqual(r[0]["failing_tests"], ["test_fail"])

    async def test_unittest_fallback_runs_real_tests(self):
        # Hide pytest from PATH so the executor falls back to unittest discover.
        (self.cwd / "test_unit.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n    def test_pass(self): self.assertTrue(True)\n",
            encoding="utf-8",
        )
        with mock.patch("tasker.tools.executor.shutil.which", return_value=None):
            r = await execute_tool(_tr("test_runner", {}), worker=_worker(), cwd=self.cwd)
        self.assertIsNone(r.error, msg=r.error)
        self.assertEqual(r.tool_output["framework"], "unittest")
        self.assertGreaterEqual(r.tool_output["passed"], 1)

    async def test_missing_path_defaults_to_cwd(self):
        (self.cwd / "test_default.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n    def test_default(self): pass\n",
            encoding="utf-8",
        )
        r = await execute_tool(_tr("test_runner", {}), worker=_worker(), cwd=self.cwd)
        self.assertIsNone(r.error, msg=r.error)
        self.assertGreaterEqual(r.tool_output["passed"], 1)


class TestLinter(ToolExecutorTestCase):

    async def test_linter_not_installed(self):
        with mock.patch("tasker.tools.executor.shutil.which", return_value=None):
            r = await execute_tool(_tr("linter", {"path": "."}), worker=_worker(), cwd=self.cwd)
        self.assertIsNone(r.tool_output)
        self.assertIn("linter not installed", r.error)

    async def test_linter_finds_issue(self):
        (self.cwd / "bad.py").write_text("import os\n", encoding="utf-8")
        r = await execute_tool(_tr("linter", {"path": "bad.py"}), worker=_worker(), cwd=self.cwd)
        self.assertIsNone(r.error, msg=f"unexpected error: {r.error}")
        self.assertEqual(r.tool_output["tool"], "ruff")
        self.assertGreaterEqual(r.tool_output["error_count"], 1)
        self.assertTrue(any(f.get("file", "").endswith("bad.py") for f in r.tool_output["findings"]))

    async def test_linter_clean_file(self):
        (self.cwd / "good.py").write_text("x = 1\n", encoding="utf-8")
        r = await execute_tool(_tr("linter", {"path": "good.py"}), worker=_worker(), cwd=self.cwd)
        self.assertIsNone(r.error, msg=r.error)
        self.assertEqual(r.tool_output["error_count"], 0)


class TestUnknownTool(ToolExecutorTestCase):

    async def test_unknown_tool_name_not_implemented(self):
        r = await execute_tool(_tr("totally_unknown", {}), worker=_worker(), cwd=self.cwd)
        self.assertIn("no execution implementation", r.error)


if __name__ == "__main__":
    unittest.main()

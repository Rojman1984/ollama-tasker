"""
Unit tests -- tool executor (tasker/tools/executor.py)

Covers the real dispatch layer for BASH/GIT/FILE_READ/FILE_WRITE/
CODE_SEARCH, the LOCAL_HARDWARE gate for mutating/executing tools, the
BASH denylist, path containment, timeouts, and output truncation.
"""
import tempfile
import unittest
from pathlib import Path

from tasker.tools.executor import _MAX_OUTPUT_CHARS, execute_tool
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


class TestUnimplementedTools(ToolExecutorTestCase):

    async def test_linter_not_implemented(self):
        r = await execute_tool(_tr("linter", {"path": "."}), worker=_worker(), cwd=self.cwd)
        self.assertIn("no execution implementation", r.error)

    async def test_test_runner_not_implemented(self):
        r = await execute_tool(_tr("test_runner", {}), worker=_worker(), cwd=self.cwd)
        self.assertIn("no execution implementation", r.error)

    async def test_unknown_tool_name_not_implemented(self):
        r = await execute_tool(_tr("totally_unknown", {}), worker=_worker(), cwd=self.cwd)
        self.assertIn("no execution implementation", r.error)


if __name__ == "__main__":
    unittest.main()

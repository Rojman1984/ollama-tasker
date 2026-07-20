"""
Unit tests -- side-effect honesty guard (tasker/tools/honesty.py).

Live bug: cowork task "create a text file with hello from tasker! and
provide the path" produced NO file, but the worker's final answer
claimed "verified at example.txt" and the run synthesized it as a plain
success. Fix (3) of that session's three-part fix: if a worker's output
claims a side effect but the step executed zero tool calls, rewrite the
output to lead with an explicit [unverified] marker.
"""
import unittest

from tasker.tools.honesty import UNVERIFIED_PREFIX, check_side_effect_honesty
from tasker.workers.base import ModelUsage, WorkerResult, WorkerStatus, WorkerToolResult


def _result(output: str | None, tool_results: list | None = None) -> WorkerResult:
    return WorkerResult(
        task_id="t1",
        worker_id="w1",
        status=WorkerStatus.SUCCESS,
        output=output,
        tool_results=tool_results or [],
        usage=ModelUsage(0, 0, 0.0),
        duration_ms=0,
    )


def _tool_result() -> WorkerToolResult:
    return WorkerToolResult(
        tool_name="file_write",
        tool_input={"path": "example.txt"},
        tool_output="ok",
        error=None,
        duration_ms=5,
    )


class TestCheckSideEffectHonesty(unittest.TestCase):

    def test_flags_file_claim_with_zero_tool_calls(self):
        result = _result("I created the file and verified it at example.txt.")
        flagged = check_side_effect_honesty(result)
        self.assertTrue(flagged.output.startswith(UNVERIFIED_PREFIX))
        self.assertIn("verified it at example.txt", flagged.output)

    def test_does_not_flag_when_a_tool_actually_ran(self):
        result = _result("Created the file at example.txt.", tool_results=[_tool_result()])
        flagged = check_side_effect_honesty(result)
        self.assertEqual(flagged.output, "Created the file at example.txt.")

    def test_does_not_flag_plain_chat_answer_with_no_tools(self):
        result = _result("The capital of France is Paris.")
        flagged = check_side_effect_honesty(result)
        self.assertEqual(flagged.output, "The capital of France is Paris.")

    def test_does_not_flag_generic_success_language_alone(self):
        # "successfully" alone (no object) must not trip the guard --
        # too generic, would false-positive on ordinary chat answers.
        result = _result("I successfully answered your question.")
        flagged = check_side_effect_honesty(result)
        self.assertEqual(flagged.output, "I successfully answered your question.")

    def test_flags_command_ran_claim(self):
        result = _result("I ran the command and it completed.")
        flagged = check_side_effect_honesty(result)
        self.assertTrue(flagged.output.startswith(UNVERIFIED_PREFIX))

    def test_flags_via_filename_shaped_token_without_object_word(self):
        result = _result("Done -- wrote hello.txt as requested.")
        flagged = check_side_effect_honesty(result)
        self.assertTrue(flagged.output.startswith(UNVERIFIED_PREFIX))

    def test_none_output_not_flagged(self):
        result = _result(None)
        flagged = check_side_effect_honesty(result)
        self.assertIsNone(flagged.output)

    def test_empty_output_not_flagged(self):
        result = _result("")
        flagged = check_side_effect_honesty(result)
        self.assertEqual(flagged.output, "")

    def test_original_claim_preserved_in_full(self):
        original = "Task complete. File created at /tmp/hello.txt with the requested content."
        result = _result(original)
        flagged = check_side_effect_honesty(result)
        self.assertIn(original, flagged.output)


if __name__ == "__main__":
    unittest.main()

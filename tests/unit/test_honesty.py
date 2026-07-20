"""
Unit tests -- side-effect honesty guard (tasker/tools/honesty.py).

Live bug 1: cowork task "create a text file with hello from tasker! and
provide the path" produced NO file, but the worker's final answer
claimed "verified at example.txt" and the run synthesized it as a plain
success. Fix: if a worker's output claims a side effect but the step
executed zero tool calls, rewrite the output to lead with an explicit
[unverified] marker.

Live bug 2 (found immediately after shipping the above): a plain "Hello"
greeting in chat mode tripped the same guard -- the model's friendly
reply merely mentioned file/command language (an offer to help) without
claiming to have done anything, and nothing about the request itself
asked for a side effect. Fix: gate the guard on *context_texts* (the
task and/or step description) -- it now only ever fires when the
request itself implied a side effect.
"""
import unittest

from tasker.tools.honesty import (
    RESEARCH_UNVERIFIED_PREFIX,
    UNVERIFIED_PREFIX,
    check_research_grounding,
    check_side_effect_honesty,
)
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


_FILE_TASK = "create a text file with hello from tasker! and provide the path"


class TestCheckSideEffectHonesty(unittest.TestCase):

    def test_flags_file_claim_with_zero_tool_calls_when_task_implied_one(self):
        result = _result("I created the file and verified it at example.txt.")
        flagged = check_side_effect_honesty(result, _FILE_TASK)
        self.assertTrue(flagged.output.startswith(UNVERIFIED_PREFIX))
        self.assertIn("verified it at example.txt", flagged.output)

    def test_does_not_flag_when_a_tool_actually_ran(self):
        result = _result("Created the file at example.txt.", tool_results=[_tool_result()])
        flagged = check_side_effect_honesty(result, _FILE_TASK)
        self.assertEqual(flagged.output, "Created the file at example.txt.")

    def test_does_not_flag_plain_chat_answer_with_no_tools(self):
        result = _result("The capital of France is Paris.")
        flagged = check_side_effect_honesty(result, "what is the capital of France?")
        self.assertEqual(flagged.output, "The capital of France is Paris.")

    def test_does_not_flag_generic_success_language_alone(self):
        # "successfully" alone (no object) must not trip the guard --
        # too generic, would false-positive on ordinary chat answers.
        result = _result("I successfully answered your question.")
        flagged = check_side_effect_honesty(result, _FILE_TASK)
        self.assertEqual(flagged.output, "I successfully answered your question.")

    def test_flags_command_ran_claim_when_task_implied_one(self):
        result = _result("I ran the command and it completed.")
        flagged = check_side_effect_honesty(result, "run the build command")
        self.assertTrue(flagged.output.startswith(UNVERIFIED_PREFIX))

    def test_flags_via_filename_shaped_token_without_object_word(self):
        result = _result("Done -- wrote hello.txt as requested.")
        flagged = check_side_effect_honesty(result, _FILE_TASK)
        self.assertTrue(flagged.output.startswith(UNVERIFIED_PREFIX))

    def test_none_output_not_flagged(self):
        result = _result(None)
        flagged = check_side_effect_honesty(result, _FILE_TASK)
        self.assertIsNone(flagged.output)

    def test_empty_output_not_flagged(self):
        result = _result("")
        flagged = check_side_effect_honesty(result, _FILE_TASK)
        self.assertEqual(flagged.output, "")

    def test_original_claim_preserved_in_full(self):
        original = "Task complete. File created at /tmp/hello.txt with the requested content."
        result = _result(original)
        flagged = check_side_effect_honesty(result, _FILE_TASK)
        self.assertIn(original, flagged.output)

    def test_second_context_text_also_gates_open(self):
        # step.description carries the request in some callers instead of
        # (or in addition to) the original task -- either should gate it.
        result = _result("I created the file and verified it at example.txt.")
        flagged = check_side_effect_honesty(result, "unrelated task text", _FILE_TASK)
        self.assertTrue(flagged.output.startswith(UNVERIFIED_PREFIX))

    # ------------------------------------------------------------------ #
    # Live bug 2: gating on request intent, not just the answer's wording
    # ------------------------------------------------------------------ #

    def test_greeting_with_offer_language_not_flagged(self):
        # A plain "Hello" never asked for any side effect -- the model's
        # friendly reply offering to help must not trip the guard even
        # though it happens to use file/command words.
        result = _result(
            "Hello! I'm ready to help -- let me know if you'd like me to "
            "run any commands or create files."
        )
        flagged = check_side_effect_honesty(result, "Hello")
        self.assertEqual(flagged.output, result.output)

    def test_no_context_texts_disables_the_guard(self):
        result = _result("I created the file and verified it at example.txt.")
        flagged = check_side_effect_honesty(result)
        self.assertEqual(flagged.output, result.output)

    def test_falsy_context_texts_ignored_not_erroring(self):
        result = _result("I created the file and verified it at example.txt.")
        flagged = check_side_effect_honesty(result, "", None, _FILE_TASK)
        self.assertTrue(flagged.output.startswith(UNVERIFIED_PREFIX))


def _tr(tool_name: str) -> WorkerToolResult:
    return WorkerToolResult(
        tool_name=tool_name, tool_input={}, tool_output="ok", error=None, duration_ms=5,
    )


class TestCheckResearchGrounding(unittest.TestCase):
    """
    SDD 5.1a: research-mode factual output with zero retrieval tool calls
    is marked [unverified -- no sources retrieved]. Live bug: a research
    task fabricated an entire model comparison and a benchmark statistic
    with zero tool calls.
    """

    def test_flags_output_with_no_retrieval_calls(self):
        flagged = check_research_grounding("Model A beats Model B by 12%.", [])
        self.assertTrue(flagged.startswith(RESEARCH_UNVERIFIED_PREFIX))
        self.assertIn("Model A beats Model B by 12%.", flagged)

    def test_does_not_flag_when_web_search_occurred(self):
        output = "Model A beats Model B by 12%."
        flagged = check_research_grounding(output, [_tr("web_search")])
        self.assertEqual(flagged, output)

    def test_does_not_flag_when_retrieve_occurred(self):
        output = "Model A beats Model B by 12%."
        flagged = check_research_grounding(output, [_tr("retrieve")])
        self.assertEqual(flagged, output)

    def test_unrelated_tool_calls_do_not_count_as_grounding(self):
        # A bash/file_read call happened, but that's not a retrieval --
        # the claim is still unverifiable.
        flagged = check_research_grounding("A fact.", [_tr("bash")])
        self.assertTrue(flagged.startswith(RESEARCH_UNVERIFIED_PREFIX))

    def test_none_output_untouched(self):
        self.assertIsNone(check_research_grounding(None, []))

    def test_empty_output_untouched(self):
        self.assertEqual(check_research_grounding("", []), "")

    def test_already_flagged_output_not_double_flagged(self):
        already = f"{RESEARCH_UNVERIFIED_PREFIX} A fact."
        flagged = check_research_grounding(already, [])
        self.assertEqual(flagged.count(RESEARCH_UNVERIFIED_PREFIX), 1)

    def test_no_output_side_keyword_gate_unlike_side_effect_guard(self):
        # Unlike check_side_effect_honesty, ANY research output with zero
        # retrieval calls is flagged -- no dual-signal keyword heuristic,
        # since a research claim doesn't need side-effect-shaped wording
        # to be unverifiable.
        flagged = check_research_grounding("Just a plain sentence.", [])
        self.assertTrue(flagged.startswith(RESEARCH_UNVERIFIED_PREFIX))


if __name__ == "__main__":
    unittest.main()

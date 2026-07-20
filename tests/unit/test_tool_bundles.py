"""
Unit tests -- step-aware tool narrowing (tasker/tools/bundles.py)

Regression coverage for the fix where a small local model (lfm2.5-
thinking) reliably lost its answer inside <think> when offered the full
7-tool CODE_BUNDLE on every step -- confirmed identically across Q4, Q8,
and bf16 precision, but 100% reliable when offered just the 1 tool a
step actually needed. narrow_bundle_to_step() deterministically narrows
via keyword matching on the step description (PlanStep only carries free
text + the too-coarse Capability enum, so this is rule-based, not
LLM-classified).
"""
import unittest

from tasker.tools.bundles import CODE_BUNDLE, RESEARCH_BUNDLE, narrow_bundle_to_step
from tasker.workers.base import ToolID


class TestNarrowBundleToStepKeywordMatches(unittest.TestCase):

    def test_bash_keyword_matches(self):
        result = narrow_bundle_to_step(CODE_BUNDLE, "Run this bash command")
        self.assertEqual(result, {ToolID.BASH})

    def test_file_read_keyword_matches(self):
        result = narrow_bundle_to_step(CODE_BUNDLE, "Read the file at config.yaml")
        self.assertEqual(result, {ToolID.FILE_READ})

    def test_file_write_keyword_matches(self):
        result = narrow_bundle_to_step(CODE_BUNDLE, "Write to a new file called output.txt")
        self.assertEqual(result, {ToolID.FILE_WRITE})

    def test_git_keyword_matches(self):
        result = narrow_bundle_to_step(CODE_BUNDLE, "Show the git diff for this branch")
        self.assertEqual(result, {ToolID.GIT})

    def test_linter_keyword_matches(self):
        result = narrow_bundle_to_step(CODE_BUNDLE, "Lint the source files")
        self.assertEqual(result, {ToolID.LINTER})

    def test_test_runner_keyword_matches(self):
        result = narrow_bundle_to_step(CODE_BUNDLE, "Run the unit tests")
        self.assertEqual(result, {ToolID.TEST_RUNNER})

    def test_code_search_keyword_matches(self):
        result = narrow_bundle_to_step(CODE_BUNDLE, "Search for the function definition")
        self.assertEqual(result, {ToolID.CODE_SEARCH})


class TestNarrowBundleToStepResearchKeywordMatches(unittest.TestCase):
    """
    Regression coverage for a live bug: RESEARCH mode fabricated an
    entire model comparison and a fake benchmark statistic with ZERO tool
    calls, because no _TOOL_KEYWORDS entry existed for WEB_SEARCH/
    RETRIEVE/etc at all -- every research step narrowed to an EMPTY tool
    set regardless of the step's actual content, so the model could never
    call web_search/retrieve even though both were in RESEARCH_BUNDLE and
    schema-defined. This is the root-cause fix.
    """

    def test_web_search_keyword_matches(self):
        result = narrow_bundle_to_step(RESEARCH_BUNDLE, "Search the web for recent benchmark results")
        self.assertIn(ToolID.WEB_SEARCH, result)

    def test_research_keyword_matches_web_search(self):
        result = narrow_bundle_to_step(RESEARCH_BUNDLE, "Research the latest model releases")
        self.assertIn(ToolID.WEB_SEARCH, result)

    def test_retrieve_keyword_matches(self):
        result = narrow_bundle_to_step(RESEARCH_BUNDLE, "Retrieve the full text of this source")
        self.assertIn(ToolID.RETRIEVE, result)

    def test_fetch_keyword_matches_retrieve(self):
        result = narrow_bundle_to_step(RESEARCH_BUNDLE, "Fetch the article content")
        self.assertIn(ToolID.RETRIEVE, result)

    def test_pdf_keyword_matches(self):
        result = narrow_bundle_to_step(RESEARCH_BUNDLE, "Extract text from the PDF report")
        self.assertIn(ToolID.PDF_EXTRACT, result)

    def test_citation_keyword_matches(self):
        result = narrow_bundle_to_step(RESEARCH_BUNDLE, "Cite the source for this claim")
        self.assertIn(ToolID.CITATION_TRACKER, result)

    def test_contradiction_keyword_matches(self):
        result = narrow_bundle_to_step(RESEARCH_BUNDLE, "Check for contradicting claims across sources")
        self.assertIn(ToolID.CONTRADICTION_DETECTOR, result)

    def test_a_realistic_research_step_never_narrows_to_empty(self):
        # This exact shape of step description (the grounding-enforcement
        # step injected/instructed by dispatch.py's research-mode handling,
        # see _enforce_research_grounding()) previously returned an empty
        # set 100% of the time, because no WEB_SEARCH keyword existed at
        # all -- the root cause of the fabrication bug.
        result = narrow_bundle_to_step(
            RESEARCH_BUNDLE,
            "Search for and retrieve real, current sources relevant to: "
            "compare the benchmark performance of two language models",
        )
        self.assertIn(ToolID.WEB_SEARCH, result)
        self.assertNotEqual(result, frozenset())


class TestNarrowBundleToStepRealStepDescriptions(unittest.TestCase):
    """
    The exact step descriptions observed live last session against
    lfm2.5-thinking:latest -- all of these previously triggered the
    empty-content failure when offered the full 7-tool bundle.
    """

    def test_list_files_in_current_directory(self):
        result = narrow_bundle_to_step(CODE_BUNDLE, "List files in current directory")
        self.assertEqual(result, {ToolID.BASH})

    def test_run_bash_ls_command(self):
        result = narrow_bundle_to_step(
            CODE_BUNDLE, "Run bash's ls command to display file listing",
        )
        self.assertEqual(result, {ToolID.BASH})

    def test_hostname_output(self):
        result = narrow_bundle_to_step(CODE_BUNDLE, "The exact output of running hostname")
        self.assertEqual(result, {ToolID.BASH})

    def test_use_bash_to_run_ls(self):
        result = narrow_bundle_to_step(
            CODE_BUNDLE, "Use bash to run the ls command and report the exact file listing",
        )
        self.assertEqual(result, {ToolID.BASH})

    def test_listing_files_paraphrase(self):
        """Planner paraphrase observed live: gerund form, no exact 'list files' phrase."""
        result = narrow_bundle_to_step(CODE_BUNDLE, "Listing files")
        self.assertEqual(result, {ToolID.BASH})

    def test_list_current_directory_files_paraphrase(self):
        """Planner paraphrase observed live: reordered, 'list' and 'file' not adjacent."""
        result = narrow_bundle_to_step(CODE_BUNDLE, "List current directory files")
        self.assertEqual(result, {ToolID.BASH})


class TestNarrowBundleToStepEdgeCases(unittest.TestCase):

    def test_multi_keyword_overlap_returns_both(self):
        result = narrow_bundle_to_step(
            CODE_BUNDLE, "Run git commit then run the unit tests",
        )
        self.assertEqual(result, {ToolID.GIT, ToolID.TEST_RUNNER})

    def test_no_match_falls_back_to_empty_bundle(self):
        # Live evidence (Designlab1, lfm2.5-thinking:latest): falling back
        # to the FULL bundle on no-match caused the model to hallucinate an
        # irrelevant tool call (calculator("hello") for a "say hello"
        # prompt) and then never conclude -- offering nothing is safer than
        # offering something with no keyword signal behind it.
        with self.assertLogs("tasker.tools.bundles", level="WARNING") as cm:
            result = narrow_bundle_to_step(CODE_BUNDLE, "Think about the problem carefully")
        self.assertEqual(result, frozenset())
        self.assertIn("no keyword match", "\n".join(cm.output))

    def test_matched_keyword_outside_bundle_excluded(self):
        """A keyword match for a tool not present in the given bundle must
        not leak in -- narrowing intersects with the caller's bundle, and
        an empty intersection is treated the same as no match at all."""
        narrow_bundle = frozenset({ToolID.BASH})
        result = narrow_bundle_to_step(narrow_bundle, "Run git commit")
        self.assertEqual(result, frozenset())

    def test_case_insensitive_matching(self):
        result = narrow_bundle_to_step(CODE_BUNDLE, "RUN THE BASH COMMAND")
        self.assertEqual(result, {ToolID.BASH})

    def test_empty_description_falls_back_to_empty_bundle(self):
        with self.assertLogs("tasker.tools.bundles", level="WARNING"):
            result = narrow_bundle_to_step(CODE_BUNDLE, "")
        self.assertEqual(result, frozenset())


class TestNarrowBundleToStepOriginalTaskFallback(unittest.TestCase):
    """
    Live-observed: the planner-generated step_description can be garbled
    or vague (e.g. "Listing available workers") even when the user's
    original request has a clear keyword signal (e.g. "list the files in
    the current directory") -- original_task is a second chance before
    giving up to an empty bundle.
    """

    def test_garbled_step_description_falls_back_to_original_task_match(self):
        result = narrow_bundle_to_step(
            CODE_BUNDLE, "Listing available workers",
            original_task="list the files in the current directory",
        )
        self.assertEqual(result, {ToolID.BASH})

    def test_step_description_match_takes_priority_over_original_task(self):
        result = narrow_bundle_to_step(
            CODE_BUNDLE, "Run git commit",
            original_task="list the files in the current directory",
        )
        self.assertEqual(result, {ToolID.GIT})

    def test_neither_matches_falls_back_to_empty_bundle(self):
        with self.assertLogs("tasker.tools.bundles", level="WARNING") as cm:
            result = narrow_bundle_to_step(
                CODE_BUNDLE, "Think about it", original_task="Ponder deeply",
            )
        self.assertEqual(result, frozenset())
        self.assertIn("original task", "\n".join(cm.output))

    def test_no_original_task_given_behaves_as_before(self):
        with self.assertLogs("tasker.tools.bundles", level="WARNING"):
            result = narrow_bundle_to_step(CODE_BUNDLE, "Think about it")
        self.assertEqual(result, frozenset())


if __name__ == "__main__":
    unittest.main()

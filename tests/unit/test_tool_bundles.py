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

from tasker.tools.bundles import CODE_BUNDLE, narrow_bundle_to_step
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

    def test_no_match_falls_back_to_full_bundle(self):
        with self.assertLogs("tasker.tools.bundles", level="WARNING") as cm:
            result = narrow_bundle_to_step(CODE_BUNDLE, "Think about the problem carefully")
        self.assertEqual(result, CODE_BUNDLE)
        self.assertIn("no keyword match", "\n".join(cm.output))

    def test_matched_keyword_outside_bundle_excluded(self):
        """A keyword match for a tool not present in the given bundle must
        not leak in -- narrowing intersects with the caller's bundle."""
        narrow_bundle = frozenset({ToolID.BASH})
        result = narrow_bundle_to_step(narrow_bundle, "Run git commit")
        self.assertEqual(result, narrow_bundle)  # falls back: no match within this bundle

    def test_case_insensitive_matching(self):
        result = narrow_bundle_to_step(CODE_BUNDLE, "RUN THE BASH COMMAND")
        self.assertEqual(result, {ToolID.BASH})

    def test_empty_description_falls_back_to_full_bundle(self):
        with self.assertLogs("tasker.tools.bundles", level="WARNING"):
            result = narrow_bundle_to_step(CODE_BUNDLE, "")
        self.assertEqual(result, CODE_BUNDLE)


if __name__ == "__main__":
    unittest.main()

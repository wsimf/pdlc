import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from pdlc.cli import main


class GuideTests(unittest.TestCase):
    def test_prints_requested_markdown_without_configuration(self):
        output = io.StringIO()
        with patch("pdlc.cli.load_config", side_effect=AssertionError("guide loaded config")), redirect_stdout(output):
            self.assertEqual(main(["guide", "guide"]), 0)
        self.assertTrue(output.getvalue().startswith("# PDLC agent guide\n"))
        self.assertIn("pdlc inspect <WORK_ITEM>", output.getvalue())

    def test_prints_decision_guide(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["guide", "decisions"]), 0)
        self.assertTrue(output.getvalue().startswith("# Resolve a PDLC decision\n"))
        self.assertIn("pdlc post decision <WORK_ITEM>", output.getvalue())

    def test_prints_the_uncommitted_changes_guide_the_checkout_refusal_names(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["guide", "uncommitted-changes"]), 0)
        self.assertTrue(output.getvalue().startswith("# Uncommitted changes\n"))
        self.assertIn("pdlc checkout DELIVERY_TASK --carry-changes", output.getvalue())
        self.assertIn("git stash push --include-untracked -m", output.getvalue())

    def test_no_subcommand_prints_the_default_guide(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["guide"]), 0)
        self.assertTrue(output.getvalue().startswith("# PDLC agent guide\n"))

    def test_rejects_multiple_subcommands(self):
        error = io.StringIO()
        with redirect_stderr(error):
            self.assertEqual(main(["guide", "one", "two"]), 1)
        self.assertIn("usage: pdlc guide [SUBCOMMAND]", error.getvalue())

    def test_reports_missing_guide(self):
        error = io.StringIO()
        with redirect_stderr(error):
            self.assertEqual(main(["guide", "workflow"]), 1)
        self.assertEqual("No guide found for workflow\n", error.getvalue())

    def test_rejects_path_traversal_as_missing_guide(self):
        error = io.StringIO()
        with redirect_stderr(error):
            self.assertEqual(main(["guide", "../guide"]), 1)
        self.assertEqual("No guide found for ../guide\n", error.getvalue())

    def test_help_uses_leaf_command_contract(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["guide", "--help"]), 0)
        self.assertIn("pdlc guide - print a bundled Markdown guide", output.getvalue())
        self.assertIn("AVAILABLE GUIDES", output.getvalue())
        self.assertIn("  decisions", output.getvalue())
        self.assertIn("  guide", output.getvalue())

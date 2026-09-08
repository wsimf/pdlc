import io
import os
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch
from types import SimpleNamespace

from pdlc.cli import _options, _resolve, main
from pdlc.config import ConfigurationError


class CliTests(unittest.TestCase):
    def test_explicit_argv_does_not_leak_environment_or_cached_hosts(self):
        from pdlc.hosts.workitem_host import get_backend

        seen = []
        original_argv = sys.argv

        def command(*, argv):
            seen.append((type(get_backend()).__name__, argv))
            self.assertIs(sys.argv, original_argv)
            return 0

        with patch.dict(os.environ, {"PDLC_AZURE_ORG": "org", "PDLC_AZURE_PROJECT": "project"}, clear=True), patch("pdlc.cli.load_config"), patch("pdlc.cli.importlib.import_module", return_value=SimpleNamespace(main=command)):
            self.assertEqual(main(["--backend", "file", "inspect", "7"]), 0)
            self.assertNotIn("PDLC_BACKEND", os.environ)
            self.assertEqual(main(["--backend", "azure", "inspect", "8"]), 0)
            self.assertNotIn("PDLC_BACKEND", os.environ)
        self.assertEqual(seen, [("FileWorkItemBackend", ["7"]), ("AzureWorkItemBackend", ["8"])])

    def test_resolves_post_complete(self):
        module, arguments = _resolve(["post", "complete", "236", "completion.md"])
        self.assertEqual(module, "pdlc.commands.post_complete")
        self.assertEqual(arguments, ["236", "completion.md"])

    def test_resolves_single_and_two_word_commands(self):
        self.assertEqual(_resolve(["inspect", "9"])[0], "pdlc.commands.inspect")
        self.assertEqual(_resolve(["inspect", "timeline", "9"])[0], "pdlc.commands.inspect_timeline")
        self.assertEqual(_resolve(["next"])[0], "pdlc.commands.next")

    def test_supports_exec_alias(self):
        module, _ = _resolve(["exec", "post", "complete"])
        self.assertEqual(module, "pdlc.commands.post_complete")

    def test_unknown_command_raises_with_usage(self):
        with self.assertRaises(ValueError) as caught:
            _resolve(["frobnicate"])
        self.assertIn("unknown command", str(caught.exception))

    def test_options_are_promoted_to_environment_variables(self):
        saved = {key: os.environ.get(key) for key in ("PDLC_REPOSITORY", "PDLC_BACKEND")}
        try:
            remaining, _ = _options(["--repo", "o/r", "--backend", "file", "inspect", "9"])
            self.assertEqual(remaining, ["inspect", "9"])
            self.assertEqual(os.environ["PDLC_REPOSITORY"], "o/r")
            self.assertEqual(os.environ["PDLC_BACKEND"], "file")
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_option_without_a_value_is_rejected(self):
        with self.assertRaises(ValueError):
            _options(["--repo"])

    def test_bare_invocation_prints_usage(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["pdlc"]), redirect_stdout(output):
            self.assertEqual(main(), 0)
        self.assertIn("usage: pdlc", output.getvalue())

    def test_unknown_command_through_main_exits_one(self):
        err = io.StringIO()
        with patch.object(sys, "argv", ["pdlc", "frobnicate"]), redirect_stderr(err):
            self.assertEqual(main(), 1)
        self.assertIn("unknown command", err.getvalue())

    def test_configuration_errors_are_printed_to_stderr(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["pdlc", "inspect", "236"]):
            with patch(
                "pdlc.cli.load_config",
                side_effect=ConfigurationError("configure me"),
            ), redirect_stderr(output):
                from pdlc.cli import main

                self.assertEqual(main(), 1)
        self.assertIn("configure me", output.getvalue())

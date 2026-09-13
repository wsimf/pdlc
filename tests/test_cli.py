import io
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch
from types import SimpleNamespace

import pdlc.config
from pdlc.cli import _options, _resolve, main
from pdlc.config import Config, ConfigurationError, install_config


class CliTests(unittest.TestCase):
    def test_explicit_argv_does_not_leak_environment_or_cached_hosts(self):
        from pdlc.hosts.workitem_host import get_backend

        seen = []
        original_argv = sys.argv

        def command(*, argv):
            seen.append((type(get_backend()).__name__, argv))
            self.assertIs(sys.argv, original_argv)
            return 0

        def fake_load_config(start=None, *, overrides=None):
            values = {"azure_org": "org", "azure_project": "project"}
            values.update(overrides or {})
            install_config(Config(**values))
            return pdlc.config._config

        with patch("pdlc.cli.load_config", side_effect=fake_load_config), patch("pdlc.cli.importlib.import_module", return_value=SimpleNamespace(main=command)):
            self.assertEqual(main(["--backend", "file", "inspect", "7"]), 0)
            self.assertIsNone(pdlc.config._config)
            self.assertEqual(main(["--backend", "azure", "inspect", "8"]), 0)
            self.assertIsNone(pdlc.config._config)
        self.assertEqual(seen, [("FileWorkItemBackend", ["7"]), ("AzureWorkItemBackend", ["8"])])

    def test_resolves_post_complete(self):
        module, arguments = _resolve(["post", "complete", "236", "completion.md"])
        self.assertEqual(module, "pdlc.commands.post_complete")
        self.assertEqual(arguments, ["236", "completion.md"])

    def test_resolves_single_and_two_word_commands(self):
        self.assertEqual(_resolve(["inspect", "9"])[0], "pdlc.commands.inspect")
        self.assertEqual(_resolve(["inspect", "timeline", "9"])[0], "pdlc.commands.inspect_timeline")
        self.assertEqual(_resolve(["inspect", "changes", "9"])[0], "pdlc.commands.inspect_changes")
        self.assertEqual(_resolve(["next"])[0], "pdlc.commands.next")

    def test_resolves_a_three_word_command(self):
        module, arguments = _resolve(["inspect", "task", "timeline", "641"])
        self.assertEqual(module, "pdlc.commands.inspect_task_timeline")
        self.assertEqual(arguments, ["641"])
        self.assertEqual(_resolve(["inspect", "task", "641"])[0], "pdlc.commands.inspect_task")

    def test_resolves_doctor(self):
        self.assertEqual(_resolve(["doctor"])[0], "pdlc.commands.doctor")

    def test_resolves_guide(self):
        self.assertEqual(_resolve(["guide"])[0], "pdlc.commands.guide")

    def test_supports_exec_alias(self):
        module, _ = _resolve(["exec", "post", "complete"])
        self.assertEqual(module, "pdlc.commands.post_complete")

    def test_unknown_command_raises_with_usage(self):
        with self.assertRaises(ValueError) as caught:
            _resolve(["frobnicate"])
        self.assertIn("unknown command", str(caught.exception))

    def test_options_become_config_overrides(self):
        remaining, overrides = _options(["--repo", "o/r", "--backend", "file", "inspect", "9"])
        self.assertEqual(remaining, ["inspect", "9"])
        self.assertEqual(overrides, {"repository": "o/r", "backend": "file"})

    def test_option_without_a_value_is_rejected(self):
        with self.assertRaises(ValueError):
            _options(["--repo"])

    def test_bare_invocation_prints_usage(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["pdlc"]), redirect_stdout(output):
            self.assertEqual(main(), 0)
        self.assertIn("USAGE", output.getvalue())
        self.assertIn("pdlc [--repo", output.getvalue())

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
        self.assertIn("Do not continue the task", output.getvalue())

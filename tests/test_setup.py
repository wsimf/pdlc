"""The `pdlc setup` wizard: prompt helpers and the config it writes for the
file, GitHub, and Azure backends, driven by a scripted input function."""

import io
import tempfile
import tomllib
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from pdlc.commands import setup


class _QuietStdout(unittest.TestCase):
    """The wizard prints prompts and menus; keep them out of the test log."""

    def setUp(self) -> None:
        context = redirect_stdout(io.StringIO())
        context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)


def scripted(answers):
    it = iter(answers)

    def _input(_prompt: str) -> str:
        return next(it)

    return _input


class PromptHelperTests(_QuietStdout):
    def test_choose_returns_zero_based_index_and_defaults_to_first(self):
        self.assertEqual(setup._choose("Pick", ["a", "b"], scripted([""])), 0)
        self.assertEqual(setup._choose("Pick", ["a", "b"], scripted(["2"])), 1)

    def test_choose_reprompts_on_a_bad_answer(self):
        self.assertEqual(setup._choose("Pick", ["a", "b"], scripted(["9", "x", "1"])), 0)

    def test_ask_requires_a_value_or_uses_the_default(self):
        self.assertEqual(setup._ask("Name", "fallback", scripted([""])), "fallback")
        self.assertEqual(setup._ask("Name", None, scripted(["", "given"])), "given")

    def test_ask_number_rejects_non_numeric(self):
        self.assertEqual(setup._ask_number("N", None, scripted(["abc", "12"])), "12")


class WriteConfigTests(_QuietStdout):
    def test_file_backend_config_has_no_github_table(self):
        path = Path(tempfile.mkdtemp()) / ".pdlc" / "config.toml"
        setup._write_config(
            path, backend="file", code_host="file",
            repository=None, project_number=None, project_owner=None,
        )
        data = tomllib.loads(path.read_text())
        self.assertEqual(data["backend"]["name"], "file")
        self.assertNotIn("github", data.get("backend", {}))

    def test_github_backend_config_carries_project_coordinates(self):
        path = Path(tempfile.mkdtemp()) / ".pdlc" / "config.toml"
        setup._write_config(
            path, backend="github", code_host="github",
            repository="o/r", project_number="7", project_owner="o",
        )
        data = tomllib.loads(path.read_text())
        self.assertEqual(data["backend"]["github"]["repository"], "o/r")
        self.assertEqual(data["backend"]["github"]["project_number"], 7)


class MainTests(_QuietStdout):
    def _run(self, answers, *, origin=(None, None), projects=None):
        target = Path(tempfile.mkdtemp()) / ".pdlc" / "config.toml"
        with patch.object(setup, "config_path", return_value=target), \
             patch.object(setup, "_origin", return_value=origin), \
             patch.object(setup, "_projects", return_value=projects or []), \
             patch.object(setup.sys, "argv", ["pdlc setup"]):
            code = setup.main(scripted(answers))
        return code, target

    def test_help_flag_prints_usage_and_skips_the_wizard(self):
        with patch.object(setup.sys, "argv", ["pdlc setup", "--help"]):
            # No scripted input: reaching a prompt would raise StopIteration.
            self.assertEqual(setup.main(scripted([])), 0)

    def test_bare_invocation_runs_the_wizard(self):
        # Regression: an empty argv must not be mistaken for a help request.
        code, target = self._run(["3"])
        self.assertEqual(code, 0)
        self.assertTrue(target.exists())

    def test_file_backend_end_to_end(self):
        # Backend prompt -> choice 3 (file); nothing else is asked.
        code, target = self._run(["3"])
        self.assertEqual(code, 0)
        data = tomllib.loads(target.read_text())
        self.assertEqual(data["backend"]["name"], "file")

    def test_github_backend_with_detected_origin_and_listed_project(self):
        # backend=github(1), code host=github(1), owner=detected(1), project=first(1)
        code, target = self._run(
            ["1", "1", "1", "1"],
            origin=("acme", "widgets"),
            projects=[{"number": 4, "title": "Delivery"}],
        )
        self.assertEqual(code, 0)
        data = tomllib.loads(target.read_text())
        self.assertEqual(data["backend"]["github"]["repository"], "acme/widgets")
        self.assertEqual(data["backend"]["github"]["project_number"], 4)
        self.assertEqual(data["backend"]["github"]["project_owner"], "acme")


class AzureBackendTests(_QuietStdout):
    """Azure Boards is the one pairing where the work-item backend and the code
    host belong to different vendors, so the wizard asks for both halves."""

    def _run(self, answers, *, origin=(None, None)):
        target = Path(tempfile.mkdtemp()) / ".pdlc" / "config.toml"
        with patch.object(setup, "config_path", return_value=target), \
             patch.object(setup, "_origin", return_value=origin), \
             patch.object(setup.sys, "argv", ["pdlc setup"]):
            code = setup.main(scripted(answers))
        return code, tomllib.loads(target.read_text())

    def test_azure_board_with_a_detected_github_repository(self):
        # backend=azure(2), org, project, code host=github(1)
        code, data = self._run(
            ["2", "https://dev.azure.com/acme", "delivery", "1"],
            origin=("acme", "widgets"),
        )
        self.assertEqual(code, 0)
        self.assertEqual(data["backend"]["name"], "azure")
        self.assertEqual(data["backend"]["azure"]["organization"], "https://dev.azure.com/acme")
        self.assertEqual(data["backend"]["azure"]["project"], "delivery")
        self.assertEqual(data["code_host"]["name"], "github")
        # The GitHub table carries the repository for the code host, and none
        # of the Project coordinates the GitHub work-item backend would need.
        self.assertEqual(data["backend"]["github"], {"repository": "acme/widgets"})

    def test_azure_board_without_a_github_code_host_writes_no_repository(self):
        # backend=azure(2), org, project, code host=none(3)
        code, data = self._run(["2", "https://dev.azure.com/acme", "delivery", "3"])
        self.assertEqual(code, 0)
        self.assertEqual(data["code_host"]["name"], "none")
        self.assertNotIn("github", data["backend"])

"""The `pdlc setup` wizard: prompt helpers and the config it writes for the
file and GitHub backends, driven by a scripted input function."""

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
             patch.object(setup.sys, "argv", ["pdlc setup", "run"]):
            code = setup.main(scripted(answers))
        return code, target

    def test_file_backend_end_to_end(self):
        # Backend prompt -> choice 2 (file); nothing else is asked.
        code, target = self._run(["2"])
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

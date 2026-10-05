"""The `pdlc setup` wizard: prompt helpers and the config it writes for the
file, GitHub, and Azure backends, driven by a scripted input function."""

import io
import tempfile
import tomllib
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from _support import isolate_home_config
from pdlc.commands import setup
from pdlc.config import Config


class _QuietStdout(unittest.TestCase):
    """The wizard prints prompts and menus; keep them out of the test log."""

    def setUp(self) -> None:
        isolate_home_config(self)
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
    def test_file_tracker_config_has_no_github_table(self):
        path = Path(tempfile.mkdtemp()) / ".pdlc" / "config.toml"
        setup._write_config(
            path, tracker="file", code="file",
            tracker_repository=None, code_repository=None, project_number=None, project_owner=None,
        )
        data = tomllib.loads(path.read_text())
        self.assertEqual(data["tracker"], {"provider": "file"})
        self.assertEqual(data["code"], {"provider": "file"})
        self.assertEqual(data["attachments"], {"provider": "file"})

    def test_github_tracker_config_carries_project_coordinates(self):
        path = Path(tempfile.mkdtemp()) / ".pdlc" / "config.toml"
        setup._write_config(
            path, tracker="github", code="github",
            tracker_repository="o/r", code_repository=None, project_number="7", project_owner="o",
        )
        data = tomllib.loads(path.read_text())
        self.assertEqual(data["tracker"]["github"]["repository"], "o/r")
        self.assertEqual(data["tracker"]["github"]["project_number"], 7)
        # The code repository is derived from origin, so it is not written.
        self.assertEqual(data["code"], {"provider": "github"})


class MainTests(_QuietStdout):
    def _run(self, answers, *, origin=(None, None), projects=None):
        target = Path(tempfile.mkdtemp()) / ".pdlc" / "config.toml"
        # The developer checkout's own config must not supply defaults.
        with patch.object(setup, "config_path", return_value=target), \
             patch.object(setup, "load_config", return_value=Config()), \
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

    def test_file_tracker_end_to_end(self):
        # Tracker prompt -> choice 3 (file); nothing else is asked.
        code, target = self._run(["3"])
        self.assertEqual(code, 0)
        data = tomllib.loads(target.read_text())
        self.assertEqual(data["tracker"]["provider"], "file")

    def test_github_tracker_with_detected_origin_and_listed_project(self):
        # tracker=github(1), tracker repo=origin(enter), code=github(1), owner=detected(1), project=first(1)
        code, target = self._run(
            ["1", "", "1", "1", "1"],
            origin=("acme", "widgets"),
            projects=[{"number": 4, "title": "Delivery"}],
        )
        self.assertEqual(code, 0)
        data = tomllib.loads(target.read_text())
        self.assertEqual(data["tracker"]["github"]["repository"], "acme/widgets")
        self.assertEqual(data["tracker"]["github"]["project_number"], 4)
        self.assertEqual(data["tracker"]["github"]["project_owner"], "acme")
        self.assertNotIn("github", data["code"])

    def test_shared_tracker_from_a_service_repository(self):
        # The tracker differs from this checkout; the project owner follows it.
        code, target = self._run(
            ["1", "corp/product", "1", "1", "1"],
            origin=("acme", "svc-a"),
            projects=[{"number": 2, "title": "Product"}],
        )
        self.assertEqual(code, 0)
        data = tomllib.loads(target.read_text())
        self.assertEqual(data["tracker"]["github"]["repository"], "corp/product")
        self.assertEqual(data["tracker"]["github"]["project_owner"], "corp")
        self.assertEqual(data["code"], {"provider": "github"})


class AzureTrackerTests(_QuietStdout):
    """Azure Boards is the one pairing where the tracker and the code provider
    belong to different vendors, so the wizard asks for both halves."""

    def _run(self, answers, *, origin=(None, None)):
        target = Path(tempfile.mkdtemp()) / ".pdlc" / "config.toml"
        with patch.object(setup, "config_path", return_value=target), \
             patch.object(setup, "load_config", return_value=Config()), \
             patch.object(setup, "_origin", return_value=origin), \
             patch.object(setup.sys, "argv", ["pdlc setup"]):
            code = setup.main(scripted(answers))
        return code, tomllib.loads(target.read_text())

    def test_azure_board_with_a_detected_github_repository(self):
        # tracker=azure(2), org, project, code=github(1)
        code, data = self._run(
            ["2", "https://dev.azure.com/acme", "delivery", "1"],
            origin=("acme", "widgets"),
        )
        self.assertEqual(code, 0)
        self.assertEqual(data["tracker"]["provider"], "azure")
        self.assertEqual(data["tracker"]["azure"]["organization"], "https://dev.azure.com/acme")
        self.assertEqual(data["tracker"]["azure"]["project"], "delivery")
        # The code repository is derived from origin, so it is not written.
        self.assertEqual(data["code"], {"provider": "github"})
        self.assertNotIn("github", data["tracker"])

    def test_azure_board_without_origin_asks_for_the_code_repository(self):
        # tracker=azure(2), org, project, code=github(1), code repository
        code, data = self._run(["2", "https://dev.azure.com/acme", "delivery", "1", "acme/widgets"])
        self.assertEqual(code, 0)
        self.assertEqual(data["code"]["github"], {"repository": "acme/widgets"})

    def test_azure_board_without_a_github_code_provider_writes_no_repository(self):
        # tracker=azure(2), org, project, code=none(3)
        code, data = self._run(["2", "https://dev.azure.com/acme", "delivery", "3"])
        self.assertEqual(code, 0)
        self.assertEqual(data["code"], {"provider": "none"})
        self.assertNotIn("github", data["tracker"])

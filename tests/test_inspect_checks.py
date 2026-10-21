import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import Mock, patch

from pdlc.commands import config as config_command
from pdlc.commands.inspect_checks import inspect_checks, render
from pdlc.config import Config, install_config, reset_config


def _pr(number: int, checks: str) -> dict:
    return {"number": number, "repository": "acme/app", "label": f"#{number}", "url": f"https://pr/{number}", "checks": checks}


class InspectChecksTest(unittest.TestCase):
    def test_lists_checks_per_pr_and_names_ignored_ones_under_the_clause(self) -> None:
        output = render("18", [
            (_pr(149, "FAILURE"), [
                {"name": "CI / unit", "state": "FAILURE", "url": "https://run/42", "ignored": False},
                {"name": "Nightly / e2e", "state": "FAILURE", "url": "https://run/43", "ignored": True},
            ]),
            (_pr(150, "NONE"), []),
        ], ("Nightly",))

        self.assertIn("## PR #149 — FAILURE\nhttps://pr/149\n\n- FAILURE: CI / unit — https://run/42\n", output)
        self.assertIn("## PR #150 — NONE\nhttps://pr/150\n\nNo checks.\n", output)
        listed, ignored = output.split("## Ignored checks", 1)
        self.assertNotIn("Nightly / e2e", listed)
        self.assertIn("Checks matching `Nightly` are intentionally marked as ignored by the user", ignored)
        self.assertIn("- PR #149: Nightly / e2e", ignored)

    def test_omits_the_ignored_section_when_nothing_is_ignored(self) -> None:
        output = render("18", [], ())
        self.assertIn("No pull requests are registered on #18.", output)
        self.assertNotIn("Ignored checks", output)

    def test_reads_each_registered_pr_from_the_code_host(self) -> None:
        install_config(Config(ignored_checks=("lint-*",)))
        self.addCleanup(reset_config)
        host = Mock()
        host.pull_request_checks.return_value = [{"name": "lint-js", "state": "FAILURE", "url": "", "ignored": True}]
        with patch("pdlc.commands.inspect_checks.record_pull_requests", return_value=[_pr(149, "SUCCESS")]), \
                patch("pdlc.commands.inspect_checks.get_code_host", return_value=host):
            output = inspect_checks("18")
        self.assertIn("## PR #149 — SUCCESS", output)
        self.assertIn("matching `lint-*`", output)
        self.assertIn("- PR #149: lint-js", output)


class ConfigCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        install_config(Config(ignored_checks=("Nightly", "lint-*"), code_repository="acme/app", no_sleep=True))
        self.addCleanup(reset_config)

    def run_command(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = config_command.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_prints_one_setting_by_field_name_or_table_path(self) -> None:
        self.assertEqual(self.run_command("ignored_checks"), (0, "Nightly\nlint-*\n", ""))
        self.assertEqual(self.run_command("code.github.ignored_checks"), (0, "Nightly\nlint-*\n", ""))
        self.assertEqual(self.run_command("workflow.no_sleep"), (0, "true\n", ""))
        self.assertEqual(self.run_command("actor"), (0, "", ""))

    def test_lists_every_setting_without_a_name(self) -> None:
        code, output, _ = self.run_command()
        self.assertEqual(code, 0)
        self.assertIn('code.github.ignored_checks = ["Nightly", "lint-*"]\n', output)
        self.assertIn('code.github.repository = "acme/app"\n', output)
        self.assertIn("runtime.actor = (unset)\n", output)

    def test_unknown_setting_fails_and_names_the_valid_ones(self) -> None:
        code, output, error = self.run_command("ignoredPipelines")
        self.assertEqual((code, output), (1, ""))
        self.assertIn("code.github.ignored_checks", error)


if __name__ == "__main__":
    unittest.main()

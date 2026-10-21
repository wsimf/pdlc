import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pdlc.commands.doctor import run
from pdlc.config import load_config, reset_config
from pdlc.domain.lifecycle import PdlcError
from pdlc.hosts.lib.access import AccessReport
from pdlc.hosts.lib.azure import access as azure_access
from pdlc.hosts.lib.github import access as github_access

UNIGNORED_WARNING = ".pdlc/ is not ignored by Git"


class DoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.home_path = self.directory / "home" / ".pdlc" / "config.toml"
        self.repo_root = self.directory / "repo"
        (self.repo_root / ".pdlc").mkdir(parents=True)
        self.repo_config = self.repo_root / ".pdlc" / "config.toml"
        # Keep config-only tests off the real `gh`/`az`; access tests re-patch it.
        access = patch("pdlc.commands.doctor._tracker_access", return_value=None)
        self.tracker_access = access.start()
        self.addCleanup(access.stop)
        # Isolate Git from the developer's global and system ignore rules.
        self.git_config_home = self.directory / "xdg"
        self.git_config_home.mkdir()
        (self.directory / "gitconfig").write_text("")
        environment = patch.dict(os.environ, {
            "XDG_CONFIG_HOME": str(self.git_config_home),
            "GIT_CONFIG_GLOBAL": str(self.directory / "gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
        })
        environment.start()
        self.addCleanup(environment.stop)

    def test_repository_section_sources_and_loading_precedence_agree(self) -> None:
        self.home_path.parent.mkdir(parents=True)
        self.home_path.write_text(
            '[tracker]\nprovider = "file"\n'
            '[tracker.github]\nrepository = "global/repo"\n'
            '[repository."acme/A".tracker.github]\nrepository = "scoped/repo"\n'
            '[repository."acme/A".worktree]\ninit_script = "A"\n'
            '[repository."acme/B".worktree]\ninit_script = "B"\n'
        )
        self.repo_config.write_text('[tracker.github]\nrepository = "local/repo"\n')
        (self.repo_root / ".git").mkdir()
        self.addCleanup(reset_config)
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.config.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root), \
             patch("pdlc.commands.doctor.git_remote_repository", return_value="acme/A"), \
             patch("pdlc.config.git_remote_repository", return_value="acme/A"), \
             patch.dict(os.environ, {"PDLC_TRACKER_REPOSITORY": "environment/repo"}):
            for overrides, expected in ((None, "local/repo"), ({"tracker_repository": "cli/repo"}, "cli/repo")):
                with self.subTest(overrides=overrides):
                    output, code = run(overrides=overrides)
                    config = load_config(self.repo_root, overrides=overrides)
                    self.assertEqual(code, 0)
                    self.assertEqual(config.tracker_repository, expected)
                    self.assertIn(f"tracker_repository = '{expected}'", output)
                    self.assertEqual(config.code_repository, "acme/A")
                    self.assertIn("code_repository = 'acme/A' [derived from git origin]", output)
                    self.assertEqual(config.worktree_init_script, "A")
                    self.assertIn(f'worktree_init_script = \'A\' [{self.home_path} [repository."acme/A"]]', output)

    def test_invalid_unmatched_sections_report_errors_without_losing_valid_values(self) -> None:
        self.home_path.parent.mkdir(parents=True)
        self.home_path.write_text(
            '[tracker]\nprovider = "file"\n'
            '[repository."acme/A".worktree]\ninit_script = "A"\n'
            '[repository."acme/B".worktree]\nbogus = "B"\n'
            '[repository."acme/B".workflow]\nmax_attempts = 0\n'
        )
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root), \
             patch("pdlc.commands.doctor.git_remote_repository", return_value="acme/A"):
            output, code = run()
        self.assertEqual(code, 1)
        self.assertIn("worktree_init_script = 'A'", output)
        self.assertIn("bogus", output)
        self.assertIn("max_attempts", output)
        self.assertIn('[repository."acme/B"]', output)

    def test_scoped_repository_value_is_accepted(self) -> None:
        self.home_path.parent.mkdir(parents=True)
        self.home_path.write_text('[tracker]\nprovider = "file"\n[repository."acme/A".tracker.github]\nrepository = "acme/A"\n')
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root), \
             patch("pdlc.commands.doctor.git_remote_repository", return_value="acme/A"):
            output, code = run()
        self.assertEqual(code, 0)
        self.assertIn("tracker_repository = 'acme/A'", output)

    def test_reports_all_missing_github_values(self) -> None:
        self.repo_config.write_text('[tracker]\nprovider = "github"\n')
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root):
            output, code = run()
        self.assertEqual(code, 1)
        self.assertIn("missing required setting: tracker.github.repository", output)
        self.assertIn("missing required setting: tracker.github.project_number", output)
        self.assertIn("missing required setting: tracker.github.project_owner", output)
        self.assertIn("missing required setting: code.github.repository", output)
        self.assertEqual(output.count("- FAIL:"), 4)

    def test_failures_and_warnings_omit_the_empty_placeholders(self) -> None:
        self.repo_config.write_text('[tracker]\nprovider = "github"\n')
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root):
            output, _ = run()
        self.assertIn("- WARNING:", output)
        self.assertNotIn("- None", output)
        self.assertNotIn("- PASS: all validations", output)

    def test_clean_run_prints_the_empty_placeholders(self) -> None:
        self.repo_config.write_text('[tracker]\nprovider = "file"\n[code]\nprovider = "none"\n')
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root):
            output, code = run()
        self.assertEqual(code, 0)
        self.assertIn("## Warnings\n\n- None", output)
        self.assertIn("## Validations\n\n- PASS: all validations", output)

    def test_unparsable_config_warns_and_skips_validations(self) -> None:
        self.home_path.parent.mkdir(parents=True)
        self.home_path.write_text('[tracker.azure]\narea_path = "Vocus\\Flex Mission"\n')
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root):
            output, code = run()
        self.assertEqual(code, 1)
        self.assertIn(f"~/.pdlc/config.toml: unparsable ({self.home_path})", output)
        self.assertIn(f"- WARNING: {self.home_path} is not valid TOML", output)
        self.assertIn(f"- FAIL: Could not read {self.home_path}", output)
        self.assertNotIn("missing required setting", output)
        self.assertNotIn("tracker is defaulted", output)
        self.tracker_access.assert_not_called()

    def test_prints_sources_and_derivations(self) -> None:
        self.home_path.parent.mkdir(parents=True)
        self.home_path.write_text('[tracker.github]\nrepository = "acme/widgets"\n')
        self.repo_config.write_text('[tracker]\nprovider = "file"\n')
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root):
            output, code = run()
        self.assertEqual(code, 0)
        self.assertIn("tracker_repository = 'acme/widgets'", output)
        self.assertIn("code_repository = 'acme/widgets' [same as tracker_repository]", output)
        self.assertIn(str(self.home_path), output)
        # A machine-wide tracker is how several service checkouts share one.
        self.assertNotIn("WARNING: [tracker.github]", output)
        self.assertIn("tracker_provider = 'file'", output)

    def test_reports_derived_repositories_with_their_source(self) -> None:
        self.repo_config.write_text('[tracker]\nprovider = "github"\n')
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root), \
             patch("pdlc.commands.doctor.git_remote_repository", return_value="acme/widgets"):
            output, code = run()
        self.assertEqual(code, 1)
        self.assertIn("tracker_repository = 'acme/widgets' [derived from git origin]", output)
        self.assertIn("code_repository = 'acme/widgets' [derived from git origin]", output)

    def test_warns_when_the_code_repository_is_not_origin(self) -> None:
        self.repo_config.write_text(
            '[tracker]\nprovider = "file"\n[code]\nprovider = "github"\n'
            '[code.github]\nrepository = "upstream/widgets"\n'
        )
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root), \
             patch("pdlc.commands.doctor.git_remote_repository", return_value="fork/widgets"):
            output, code = run()
        self.assertEqual(code, 0)
        self.assertIn("[code.github] repository is upstream/widgets but this checkout's origin is fork/widgets", output)

    def _doctor(self) -> tuple[str, int]:
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root):
            return run()

    def test_warns_without_editing_when_pdlc_is_not_ignored(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.repo_root)], check=True)
        self.repo_config.write_text('[tracker]\nprovider = "file"\n[code]\nprovider = "none"\n')
        ignore_file = self.repo_root / ".gitignore"
        ignore_file.write_text("other-entry")
        output, code = self._doctor()
        self.assertEqual(code, 0)
        self.assertIn(f"- WARNING: {UNIGNORED_WARNING}", output)
        self.assertEqual(ignore_file.read_text(), "other-entry")

    def test_repository_ignore_rule_silences_the_warning(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.repo_root)], check=True)
        (self.repo_root / ".gitignore").write_text(".*\n")
        output, _ = self._doctor()
        self.assertNotIn(UNIGNORED_WARNING, output)

    def test_global_ignore_rule_silences_the_warning(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.repo_root)], check=True)
        (self.git_config_home / "git").mkdir()
        (self.git_config_home / "git" / "ignore").write_text(".pdlc/\n")
        output, _ = self._doctor()
        self.assertNotIn(UNIGNORED_WARNING, output)
        self.assertFalse((self.repo_root / ".gitignore").exists())

    def test_non_git_directory_does_not_warn(self) -> None:
        output, _ = self._doctor()
        self.assertNotIn(UNIGNORED_WARNING, output)
        self.assertFalse((self.repo_root / ".gitignore").exists())

    def test_tracker_access_section_joins_warnings_and_failures(self) -> None:
        self.repo_config.write_text(
            '[tracker]\nprovider = "github"\n[code]\nprovider = "github"\n'
            '[tracker.github]\nrepository = "acme/widgets"\nproject_number = 3\nproject_owner = "acme"\n'
        )
        self.tracker_access.return_value = AccessReport(
            facts=["gh login: octo via keyring (success)"],
            warnings=["gh 2.1.0 is older than the minimum 2.100.0; upgrade it"],
            errors=["gh cannot read Project acme/3: not found"],
        )
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root):
            output, code = run()
        self.assertEqual(code, 1)
        self.assertIn("## Tracker access\n\n- gh login: octo via keyring (success)", output)
        self.assertIn("- WARNING: gh 2.1.0 is older than the minimum 2.100.0", output)
        self.assertIn("- FAIL: gh cannot read Project acme/3: not found", output)

    def test_file_tracker_has_no_tracker_access_section(self) -> None:
        self.tracker_access.stop()
        self.repo_config.write_text('[tracker]\nprovider = "file"\n[code]\nprovider = "none"\n')
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root), \
             patch("pdlc.hosts.lib.github.access.run_process", side_effect=AssertionError("no gh call")), \
             patch("pdlc.hosts.lib.azure.access.run_process", side_effect=AssertionError("no az call")):
            output, code = run()
        self.assertEqual(code, 0)
        self.assertNotIn("## Tracker access", output)


def _fake_cli(responses: dict[tuple[str, ...], str | Exception]):
    """A `run_process` stand-in answering by the longest matching argument prefix."""
    calls: list[list[str]] = []

    def run_process(args, **_kwargs):
        calls.append(list(args))
        matches = [prefix for prefix in responses if tuple(args[:len(prefix)]) == prefix]
        if not matches:
            raise AssertionError(f"unexpected call: {args}")
        response = responses[max(matches, key=len)]
        if isinstance(response, Exception):
            raise response
        return response

    return run_process, calls


_GH_OK = '{"hosts":{"github.com":[{"state":"success","active":true,"login":"octo","tokenSource":"keyring","scopes":"project, repo"}]}}'


class GitHubAccessTests(unittest.TestCase):
    def check(self, responses: dict[tuple[str, ...], str | Exception]) -> tuple[AccessReport, list[list[str]]]:
        fake, calls = _fake_cli(responses)
        with patch("pdlc.hosts.lib.github.access.run_process", side_effect=fake):
            report = github_access.check_access(repository="acme/widgets", project_owner="acme", project_number="3")
        return report, calls

    def test_reports_login_scopes_repository_and_project(self) -> None:
        report, _ = self.check({
            ("gh", "--version"): "gh version 2.100.0 (2026-09-03)\n",
            ("gh", "auth", "status"): _GH_OK,
            ("gh", "repo", "view"): '{"nameWithOwner":"acme/widgets","viewerPermission":"WRITE"}',
            ("gh", "project", "view"): '{"title":"Roadmap","url":"https://github.com/orgs/acme/projects/3"}',
        })
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])
        self.assertIn("gh version: 2.100.0 (min 2.100.0)", report.facts)
        self.assertIn("gh login: octo via keyring (success)", report.facts)
        self.assertIn("gh token scopes: project, repo", report.facts)
        self.assertIn("repository: acme/widgets (permission WRITE)", report.facts)
        self.assertIn("project: acme/3 'Roadmap' (https://github.com/orgs/acme/projects/3)", report.facts)

    def test_old_version_warns_and_missing_project_scope_fails(self) -> None:
        report, _ = self.check({
            ("gh", "--version"): "gh version 2.40.1 (2023-12-13)\n",
            ("gh", "auth", "status"): _GH_OK.replace("project, repo", "repo"),
            ("gh", "repo", "view"): '{"nameWithOwner":"acme/widgets","viewerPermission":"READ"}',
            ("gh", "project", "view"): PdlcError("Could not resolve to a ProjectV2"),
        })
        self.assertIn("gh 2.40.1 is older than the minimum 2.100.0; upgrade it", report.warnings)
        self.assertTrue(any("READ permission" in warning for warning in report.warnings))
        self.assertTrue(any("`gh auth refresh -s project`" in error for error in report.errors))
        self.assertIn("gh cannot read Project acme/3: Could not resolve to a ProjectV2", report.errors)

    def test_logged_out_stops_before_access_probes(self) -> None:
        report, calls = self.check({
            ("gh", "--version"): "gh version 2.100.0\n",
            ("gh", "auth", "status"): '{"hosts":{}}',
        })
        self.assertEqual(report.errors, ["gh is not logged in to github.com; run `gh auth login`"])
        self.assertEqual(len(calls), 2)

    def test_missing_cli_fails(self) -> None:
        report, _ = self.check({("gh",): PdlcError("required command not found: gh")})
        self.assertEqual(report.facts, ["gh: not available"])
        self.assertIn("required command not found: gh", report.errors[0])


_AZ_VERSION = '{"azure-cli":"2.90.0","extensions":{"azure-devops":"1.0.8"}}'


class AzureAccessTests(unittest.TestCase):
    def check(self, responses: dict[tuple[str, ...], str | Exception], environment: dict[str, str] | None = None) -> tuple[AccessReport, list[list[str]]]:
        fake, calls = _fake_cli(responses)
        with patch("pdlc.hosts.lib.azure.access.run_process", side_effect=fake), \
             patch.dict("os.environ", environment or {}, clear=False):
            report = azure_access.check_access(organization="https://dev.azure.com/acme/", project="Widgets")
        return report, calls

    def test_pat_without_az_login_passes_on_project_and_boards_access(self) -> None:
        report, calls = self.check({
            ("az", "version"): _AZ_VERSION,
            ("az", "account", "show"): PdlcError("Please run 'az login'"),
            ("az", "devops", "project", "show"): '{"name":"Widgets","id":"abc-123"}',
            ("az", "boards", "query"): "",
        }, {"AZURE_DEVOPS_EXT_PAT": "secret"})
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])
        self.assertIn("azure-devops extension version: 1.0.8 (min 1.0.8)", report.facts)
        self.assertIn("AZURE_DEVOPS_EXT_PAT: set", report.facts)
        self.assertTrue(any(fact.startswith("az login: not logged in") for fact in report.facts))
        self.assertIn("project: https://dev.azure.com/acme/Widgets (abc-123)", report.facts)
        self.assertIn("boards: work-item query OK", report.facts)
        self.assertNotIn("secret", "\n".join(report.facts))
        project_call = next(call for call in calls if call[1:3] == ["devops", "project"])
        self.assertIn("https://dev.azure.com/acme", project_call)

    def test_missing_extension_fails_before_access_probes(self) -> None:
        report, calls = self.check({("az", "version"): '{"azure-cli":"2.90.0","extensions":{}}'})
        self.assertEqual(report.errors, ["the azure-devops az extension is not installed; run `az extension add --name azure-devops`"])
        self.assertEqual(len(calls), 1)

    def test_old_versions_warn_and_unreadable_project_skips_boards(self) -> None:
        report, calls = self.check({
            ("az", "version"): '{"azure-cli":"2.60.0","extensions":{"azure-devops":"1.0.1"}}',
            ("az", "account", "show"): "dev@acme.test\n",
            ("az", "devops", "project", "show"): PdlcError("TF401019: project does not exist or no permission"),
        })
        self.assertIn("az 2.60.0 is older than the minimum 2.90.0; upgrade it", report.warnings)
        self.assertIn("azure-devops extension 1.0.1 is older than the minimum 1.0.8; upgrade it", report.warnings)
        self.assertIn("az login: dev@acme.test", report.facts)
        self.assertTrue(report.errors[0].startswith("az devops cannot read project 'Widgets'"))
        self.assertFalse(any(call[1:2] == ["boards"] for call in calls))


if __name__ == "__main__":
    unittest.main()

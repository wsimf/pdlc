import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pdlc.commands.doctor import run
from pdlc.config import repository_root
from pdlc.domain.lifecycle import PdlcError
from pdlc.hosts.lib.access import AccessReport
from pdlc.hosts.lib.azure import access as azure_access
from pdlc.hosts.lib.github import access as github_access


class DoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.home_path = self.directory / "home" / ".pdlc" / "config.toml"
        self.repo_root = self.directory / "repo"
        (self.repo_root / ".pdlc").mkdir(parents=True)
        self.repo_config = self.repo_root / ".pdlc" / "config.toml"
        # Keep config-only tests off the real `gh`/`az`; access tests re-patch it.
        access = patch("pdlc.commands.doctor._backend_access", return_value=None)
        self.backend_access = access.start()
        self.addCleanup(access.stop)

    def test_reports_all_missing_github_values(self) -> None:
        self.repo_config.write_text('[backend]\nname = "github"\n')
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root):
            output, code = run()
        self.assertEqual(code, 1)
        self.assertIn("missing required setting: backend.github.repository", output)
        self.assertIn("missing required setting: backend.github.project_number", output)
        self.assertIn("missing required setting: backend.github.project_owner", output)
        self.assertEqual(output.count("- FAIL:"), 3)

    def test_prints_sources_derivations_and_home_repository_warning(self) -> None:
        self.home_path.parent.mkdir(parents=True)
        self.home_path.write_text('[backend.github]\nrepository = "acme/widgets"\n')
        self.repo_config.write_text('[backend]\nname = "file"\n')
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root):
            output, code = run()
        self.assertEqual(code, 0)
        self.assertIn("repository = 'acme/widgets'", output)
        self.assertIn(str(self.home_path), output)
        self.assertIn("repository is set in ~/.pdlc/config.toml", output)
        self.assertIn("backend = 'file'", output)

    def test_reports_derived_repository_as_a_warning(self) -> None:
        self.repo_config.write_text('[backend]\nname = "github"\n')
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root), \
             patch("pdlc.commands.doctor.git_remote_repository", return_value="acme/widgets"):
            output, code = run()
        self.assertEqual(code, 1)
        self.assertIn("repository = 'acme/widgets' [derived from git origin]", output)
        self.assertIn("repository is auto-derived from git origin", output)

    def test_adds_gitignore_entry_once_when_directory_is_not_ignored(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.repo_root)], check=True)
        ignore_file = self.repo_root / ".gitignore"
        ignore_file.write_text("other-entry")
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root):
            run()
            run()
        self.assertEqual(ignore_file.read_text(), "other-entry\n/.pdlc/\n")
        result = subprocess.run(
            ["git", "-C", str(self.repo_root), "check-ignore", "-q", "--", ".pdlc/"],
            check=False,
        )
        self.assertEqual(result.returncode, 0)

    def test_respects_existing_git_ignore_rule(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.repo_root)], check=True)
        ignore_file = self.repo_root / ".gitignore"
        ignore_file.write_text(".*\n")
        self.repo_config.write_text('[backend]\nname = "file"\n')
        subprocess.run(["git", "-C", str(self.repo_root), "add", "-f", ".pdlc/config.toml"], check=True)
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root):
            run()
        self.assertEqual(ignore_file.read_text(), ".*\n")

    def test_gitignore_failure_does_not_fail_doctor(self) -> None:
        self.repo_config.write_text('[backend]\nname = "file"\n')
        subprocess.run(["git", "init", "-q", str(self.repo_root)], check=True)
        (self.repo_root / ".gitignore").mkdir()
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root):
            _, code = run()
        self.assertEqual(code, 0)

    def test_non_git_directory_does_not_create_gitignore(self) -> None:
        self.repo_config.write_text('[backend]\nname = "file"\n')
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root):
            _, code = run()
        self.assertEqual(code, 0)
        self.assertFalse((self.repo_root / ".gitignore").exists())

    def test_adds_gitignore_in_linked_worktree(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.repo_root)], check=True)
        (self.repo_root / "seed").write_text("seed")
        subprocess.run(["git", "-C", str(self.repo_root), "add", "seed"], check=True)
        subprocess.run(
            ["git", "-C", str(self.repo_root), "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "seed"],
            check=True,
        )
        linked = self.directory / "linked"
        subprocess.run(["git", "-C", str(self.repo_root), "worktree", "add", "-q", "-b", "linked", str(linked)], check=True)
        (linked / ".pdlc").mkdir()
        (linked / ".pdlc" / "config.toml").write_text('[backend]\nname = "file"\n')
        self.assertTrue((linked / ".git").is_file())
        self.assertEqual(repository_root(linked), linked.resolve())

        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", side_effect=lambda: repository_root(linked)):
            _, code = run()

        self.assertEqual(code, 0)
        self.assertEqual((linked / ".gitignore").read_text(), "/.pdlc/\n")
        self.assertFalse((self.repo_root / ".gitignore").exists())

    def test_backend_access_section_joins_warnings_and_failures(self) -> None:
        self.repo_config.write_text(
            '[backend]\nname = "github"\n[code_host]\nname = "github"\n'
            '[backend.github]\nrepository = "acme/widgets"\nproject_number = 3\nproject_owner = "acme"\n'
        )
        self.backend_access.return_value = AccessReport(
            facts=["gh login: octo via keyring (success)"],
            warnings=["gh 2.1.0 is older than the minimum 2.100.0; upgrade it"],
            errors=["gh cannot read Project acme/3: not found"],
        )
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root):
            output, code = run()
        self.assertEqual(code, 1)
        self.assertIn("## Backend access\n\n- gh login: octo via keyring (success)", output)
        self.assertIn("- WARNING: gh 2.1.0 is older than the minimum 2.100.0", output)
        self.assertIn("- FAIL: gh cannot read Project acme/3: not found", output)

    def test_file_backend_has_no_backend_access_section(self) -> None:
        self.backend_access.stop()
        self.repo_config.write_text('[backend]\nname = "file"\n[code_host]\nname = "none"\n')
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root), \
             patch("pdlc.hosts.lib.github.access.run_process", side_effect=AssertionError("no gh call")), \
             patch("pdlc.hosts.lib.azure.access.run_process", side_effect=AssertionError("no az call")):
            output, code = run()
        self.assertEqual(code, 0)
        self.assertNotIn("## Backend access", output)


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

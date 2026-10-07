"""Phase 3 multi-repository behavior: tasks that name their repository, the
folder each repository is worked in, per-repository stacks, capabilities, and
verification HEADs."""

import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from pdlc.commands import inspect_capability
from pdlc.commands.prepare import _parse
from pdlc.config import Config, ConfigurationError, get_capabilities, install_config, load_config, project_root, reset_config
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.records import PullRef
from pdlc.domain.task_artifact import declared_repository, repository_errors
from pdlc.domain.verification import format_heads, parse_heads, short_heads
from pdlc.internal import verification
from pdlc.internal.repositories import in_repository, repository_folder, repository_lines, task_repository
from pdlc.commands.post_implement_task import _work_ref
from pdlc.internal.stack import resolve_predecessor, stack_entry_pr
from pdlc.internal.vcs import head_commit
from pdlc.internal.workdir import working_directory, working_repository


def _config(**values: object) -> Config:
    return Config(tracker_provider="file", code_provider="github", code_repository="acme/api", **values)  # type: ignore[arg-type]


def _task(number: int, repository: str | None = None, **fields: object) -> dict:
    body = f"**Repository:** {repository}\n" if repository else ""
    return {"number": number, "taskId": f"TASK-{number:03d}", "body": body, **fields}


class _Isolated(unittest.TestCase):
    """Redirects the home config and strips PDLC_* variables."""

    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())
        patcher = patch("pdlc.config.home_config_path", lambda: self.home / ".pdlc" / "config.toml")
        patcher.start()
        self.addCleanup(patcher.stop)
        env = patch.dict(os.environ, {k: v for k, v in os.environ.items() if not k.startswith("PDLC_")}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(reset_config)

    def write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def git_repo(self, parent: Path | None = None) -> Path:
        root = Path(tempfile.mkdtemp(dir=parent))
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "remote", "add", "origin", "git@github.com:acme/api.git"], check=True)
        return root


class ConfigTests(_Isolated):
    def test_repositories_and_checkouts_are_read_and_casefolded(self):
        self.write(self.home / ".pdlc" / "config.toml", '[code.github.checkouts]\n"Acme/Web" = "~/src/web"\n')
        root = self.git_repo()
        self.write(root / ".pdlc" / "config.toml", '[code.github]\nrepositories = ["acme/api", "Acme/Web"]\n')
        config = load_config(root)
        self.assertEqual(config.code_repositories, ("acme/api", "acme/web"))
        self.assertEqual(config.code_checkouts, {"acme/web": "~/src/web"})
        self.assertEqual(config.project_repositories(), ("acme/api", "acme/web"))

    def test_without_repositories_the_project_is_the_code_repository(self):
        self.assertEqual(_config().project_repositories(), ("acme/api",))

    def test_the_code_repository_is_always_a_project_repository(self):
        self.assertEqual(_config(code_repositories=("acme/web",)).project_repositories(), ("acme/api", "acme/web"))

    def test_relative_checkout_paths_are_refused(self):
        self.write(self.home / ".pdlc" / "config.toml", '[code.github.checkouts]\n"acme/web" = "src/web"\n')
        with self.assertRaisesRegex(ConfigurationError, "absolute path"):
            load_config(self.git_repo())

    def test_checkouts_are_home_only(self):
        root = self.git_repo()
        self.write(root / ".pdlc" / "config.toml", '[code.github.checkouts]\n"acme/web" = "/src/web"\n')
        with self.assertRaisesRegex(ConfigurationError, "home-only"):
            load_config(root)

    def test_bad_repository_names_are_refused(self):
        root = self.git_repo()
        self.write(root / ".pdlc" / "config.toml", '[code.github]\nrepositories = ["web"]\n')
        with self.assertRaises(ConfigurationError):
            load_config(root)

    def test_project_file_repository_capabilities_override_project_wide_slots(self):
        root = self.git_repo()
        self.write(
            root / ".pdlc" / "config.toml",
            '[agents]\ncore-implementer = "core"\n[skills]\nbuild-run = "xcode"\n'
            '[repository."acme/web".skills]\nbuild-run = "vite"\n',
        )
        load_config(root)
        self.assertEqual(get_capabilities().skill("build-run"), "xcode")
        self.assertEqual(get_capabilities("Acme/Web").skill("build-run"), "vite")
        self.assertEqual(get_capabilities("acme/web").agent("core-implementer"), "core")
        self.assertEqual(get_capabilities("acme/other").skill("build-run"), "xcode")

    def test_project_file_repository_section_may_not_hold_settings(self):
        root = self.git_repo()
        self.write(root / ".pdlc" / "config.toml", '[repository."acme/web".worktree]\ninit_script = "x"\n')
        with self.assertRaisesRegex(ConfigurationError, "home-only"):
            load_config(root)

    def test_inspect_capability_resolves_for_a_repository(self):
        root = self.git_repo()
        self.write(root / ".pdlc" / "config.toml", '[repository."acme/web".agents]\nui-implementer = "web-ui"\n')
        load_config(root)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(inspect_capability.main(["ui-implementer", "--repository", "acme/web"]), 0)
        self.assertEqual(out.getvalue(), "web-ui\n")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(inspect_capability.main(["ui-implementer"]), 0)
        self.assertEqual(out.getvalue(), "general-purpose\n")


_SHARED = '[code.github]\nrepositories = ["acme/api", "acme/web"]\n'


class ProjectRootTests(_Isolated):
    def test_an_umbrella_folder_config_configures_its_repositories(self):
        umbrella = Path(tempfile.mkdtemp())
        self.write(umbrella / ".pdlc" / "config.toml", _SHARED)
        repo = self.git_repo(umbrella)
        self.assertEqual(project_root(repo / "src"), umbrella.resolve())

    def test_a_stray_ancestor_config_without_repositories_is_ignored(self):
        parent = Path(tempfile.mkdtemp())
        self.write(parent / ".pdlc" / "config.toml", '[tracker]\nprovider = "file"\n')
        repo = self.git_repo(parent)
        self.assertEqual(project_root(repo), repo.resolve())

    def test_a_repository_nested_in_another_checkout_ignores_its_config(self):
        outer = self.git_repo()
        self.write(outer / ".pdlc" / "config.toml", _SHARED)
        inner = self.git_repo(outer)
        self.assertEqual(project_root(inner), inner.resolve())

    def test_the_repositorys_own_config_wins(self):
        umbrella = Path(tempfile.mkdtemp())
        self.write(umbrella / ".pdlc" / "config.toml", "")
        repo = self.git_repo(umbrella)
        self.write(repo / ".pdlc" / "config.toml", "")
        self.assertEqual(project_root(repo), repo.resolve())


class TaskRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.web = tempfile.mkdtemp()
        install_config(_config(code_repositories=("acme/api", "acme/web"), code_checkouts={"acme/web": self.web}))
        self.addCleanup(reset_config)

    def test_a_task_names_its_repository_or_belongs_to_the_code_repository(self):
        self.assertEqual(task_repository(_task(1)), "acme/api")
        self.assertEqual(task_repository(_task(2, "Acme/Web")), "acme/web")
        self.assertEqual(declared_repository("**Repository:** `acme/web`\n"), "acme/web")

    def test_repository_errors(self):
        allowed = ("acme/api", "acme/web")
        self.assertEqual(repository_errors("", allowed), [])
        self.assertEqual(repository_errors("**Repository:** acme/web\n", allowed), [])
        self.assertTrue(repository_errors("**Repository:** acme/other\n", allowed))
        self.assertTrue(repository_errors("**Repository:** web\n", allowed))

    def test_folder_routing(self):
        self.assertIsNone(repository_folder("acme/api"))
        self.assertEqual(repository_folder("Acme/Web"), Path(self.web).resolve())
        with self.assertRaisesRegex(PdlcError, r"\[code.github.checkouts\]"):
            repository_folder("acme/docs")
        install_config(_config(code_checkouts={"acme/web": "/no/such/folder"}))
        with self.assertRaisesRegex(PdlcError, "does not exist"):
            repository_folder("acme/web")

    def test_an_unnamed_repository_is_the_code_repository(self):
        # A pull request registered before refs carried their repository.
        self.assertIsNone(repository_folder(""))

    def test_a_pr_in_another_repository_links_the_work_item_qualified(self):
        install_config(Config(code_provider="github", code_repository="acme/api", tracker_repository="acme/api"))
        self.assertEqual(_work_ref("70", "acme/api"), "#70")
        self.assertEqual(_work_ref("70", "acme/web"), "acme/api#70")

    def test_a_predecessor_resolves_to_its_code_repository_task(self):
        stage = Mock(stage="Implementation")
        tasks = [
            _task(1, hasImplementation=True, prs=[PullRef(11, "acme/api")], title="WORK-2-TASK-001"),
            _task(2, "acme/web", hasImplementation=True, prs=[PullRef(21, "acme/web")], title="WORK-2-TASK-002"),
        ]
        with patch("pdlc.internal.stack.resolve_item", return_value={"number": 2}), \
                patch("pdlc.internal.stack.workflow_for_item", return_value=(Mock(terminal_stage="Complete"), stage)), \
                patch("pdlc.internal.stack.task_tree", return_value=tasks):
            predecessor = resolve_predecessor("WORK-2")
        self.assertEqual(predecessor.pr, 11)
        self.assertTrue(predecessor.branch.endswith("task-001"))

    def test_repository_lines_only_for_other_repositories(self):
        self.assertEqual(repository_lines(_task(1)), [])
        self.assertEqual(repository_lines(_task(2, "acme/web")), ["repository: acme/web", f"path: {Path(self.web).resolve()}"])

    def test_in_repository_routes_git_to_that_folder(self):
        subprocess.run(["git", "init", "-q", self.web], check=True)
        subprocess.run(
            ["git", "-C", self.web, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x"],
            check=True,
        )
        expected = subprocess.run(["git", "-C", self.web, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        with in_repository("acme/web"):
            self.assertEqual(working_repository(), "acme/web")
            self.assertEqual(head_commit(), expected)
        self.assertIsNone(working_directory())

    def test_each_repository_stacks_only_its_own_tasks(self):
        tasks = [
            _task(1, hasImplementation=True, prs=[PullRef(11, "acme/api")]),
            _task(2, "acme/web", hasImplementation=True, prs=[PullRef(21, "acme/web")]),
            _task(3, hasImplementation=False),
            _task(4, "acme/web", hasImplementation=False),
        ]
        self.assertEqual(stack_entry_pr(tasks, tasks[2]), 11)
        self.assertEqual(stack_entry_pr(tasks, tasks[3]), 21)
        self.assertIsNone(stack_entry_pr(tasks, tasks[1]))

    def test_prepare_after_is_refused_with_several_repositories(self):
        with self.assertRaisesRegex(PdlcError, "--after is not supported"):
            _parse(["WORK-1", "--after", "WORK-2"])
        install_config(_config())
        self.assertEqual(_parse(["WORK-1", "--after", "WORK-2"])[2], "WORK-2")


class HeadSpecTests(unittest.TestCase):
    def setUp(self) -> None:
        install_config(_config(code_repositories=("acme/api", "acme/web"), code_checkouts={"acme/web": tempfile.mkdtemp()}))
        self.addCleanup(reset_config)

    def test_one_repository_is_a_bare_sha(self):
        self.assertEqual(format_heads({"": "a" * 40}), "a" * 40)
        self.assertEqual(parse_heads("a" * 40), {"": "a" * 40})

    def test_several_repositories_round_trip(self):
        spec = format_heads({"acme/web": "b" * 40, "": "a" * 40})
        self.assertEqual(spec, f"{'a' * 40}, acme/web@{'b' * 40}")
        self.assertEqual(parse_heads(spec), {"": "a" * 40, "acme/web": "b" * 40})
        self.assertEqual(short_heads(spec), f"{'a' * 12}, acme/web@{'b' * 12}")

    def test_current_heads_reads_each_claim_repository(self):
        tasks = [_task(1, state="CLOSED"), _task(2, "acme/web", state="CLOSED")]
        seen = []

        def head() -> str:
            seen.append(working_repository())
            return "w" * 40 if working_repository() == "acme/web" else "a" * 40

        with patch("pdlc.internal.verification.head_commit", head):
            self.assertEqual(verification.current_heads(tasks), f"{'a' * 40}, acme/web@{'w' * 40}")
        self.assertEqual(seen, ["acme/api", "acme/web"])

    def test_changed_since_qualifies_paths_and_needs_every_claim_repository(self):
        tasks = [_task(1, state="CLOSED"), _task(2, "acme/web", state="CLOSED")]

        def changed(sha: str) -> list[str]:
            return ["app.ts"] if working_repository() == "acme/web" else ["main.py"]

        with patch("pdlc.internal.verification.changed_files", changed):
            self.assertEqual(
                verification.changed_since(f"{'a' * 40}, acme/web@{'w' * 40}", tasks),
                {"acme/api:main.py", "acme/web:app.ts"},
            )
            self.assertIsNone(verification.changed_since("a" * 40, tasks))


if __name__ == "__main__":
    unittest.main()

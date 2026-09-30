import io
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

from pdlc.cli import _usage
from pdlc.commands import prepare
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.stack import Predecessor
from pdlc.internal.worktree import sanitize_workitem, target_path, worktree_root


class SanitizeTests(unittest.TestCase):
    def test_accepts_plain_tokens(self):
        self.assertEqual(sanitize_workitem(" 142 "), "142")
        self.assertEqual(sanitize_workitem("record-142"), "record-142")

    def test_rejects_path_traversal_and_separators(self):
        for bad in ("..", ".", "a/b", "../x", "", "x y", "a$b"):
            with self.assertRaises(PdlcError):
                sanitize_workitem(bad)

    def test_target_path_expands_and_nests(self):
        path = target_path("~/wt", "myrepo", "142")
        self.assertEqual(path, Path.home() / "wt" / "myrepo" / "142")

    def test_worktree_root_defaults_when_unset(self):
        self.assertEqual(worktree_root(None), "~/.pdlc/worktrees")
        self.assertEqual(worktree_root("/custom"), "/custom")


class PrepareCommandTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.wt_root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        self.addCleanup(lambda: shutil.rmtree(self.wt_root, ignore_errors=True))
        self.repo = self.root / "myrepo"
        self.repo.mkdir()
        self._git("init", "-q")
        self._git("config", "user.email", "t@example.com")
        self._git("config", "user.name", "Test")
        self._git("commit", "-qm", "root", "--allow-empty")
        self.previous = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(lambda: os.chdir(self.previous))

    def _git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True).strip()

    def _run(self, argv, config, *, resume_task=None):
        cfg = SimpleConfig(**config)
        out, err = io.StringIO(), io.StringIO()
        with patch.object(prepare, "get_config", lambda: cfg), \
                patch.object(prepare, "_resume_task", return_value=resume_task), \
                redirect_stdout(out), redirect_stderr(err):
            code = prepare.main(argv)
        return code, out.getvalue().strip(), err.getvalue()

    def test_resumes_highest_task_with_an_open_registered_pr(self):
        tasks = [
            {"number": 1, "title": "WORK-142-TASK-001", "taskId": "TASK-001", "prs": [10]},
            {"number": 2, "title": "WORK-142-TASK-002", "taskId": "TASK-002", "prs": [20]},
            {"number": 3, "title": "WORK-142-TASK-003", "taskId": "TASK-003", "prs": [30]},
        ]
        with patch.object(prepare, "task_tree", return_value=tasks), \
                patch.object(prepare, "get_code_host") as code_host:
            code_host.return_value.pull_requests_by_number.return_value = [
                {"number": 10, "state": "MERGED"},
                {"number": 20, "state": "OPEN"},
                {"number": 30, "state": "CLOSED"},
            ]
            self.assertEqual(prepare._resume_task("142"), "WORK-142-TASK-002")
            code_host.return_value.pull_requests_by_number.assert_called_once_with([10, 20, 30])

    def test_resumes_in_new_worktree_and_keeps_path_only_on_stdout(self):
        current = os.getcwd()
        seen = []
        def checkout_task(task):
            seen.append((task, os.getcwd()))
            return "restored task branch\n"
        with patch.object(prepare, "checkout", side_effect=checkout_task):
            code, out, err = self._run(["142"], {"worktree_root": str(self.wt_root)}, resume_task="WORK-142-TASK-002")
        self.assertEqual(code, 0, err)
        self.assertEqual(seen, [("WORK-142-TASK-002", str((self.wt_root / "myrepo" / "142").resolve()))])
        self.assertEqual(os.getcwd(), current)
        self.assertEqual(out, str(self.wt_root / "myrepo" / "142"))
        self.assertIn("restored task branch", err)

    def test_resumes_existing_worktree_without_recreating_it(self):
        config = {"worktree_root": str(self.wt_root)}
        self._run(["142", "--from", "HEAD"], config)
        with patch.object(prepare, "checkout", return_value="restored task branch\n") as checkout_task:
            code, out, err = self._run(["142"], config, resume_task="WORK-142-TASK-002")
        self.assertEqual(code, 0, err)
        self.assertEqual(out, str(self.wt_root / "myrepo" / "142"))
        self.assertIn("restored task branch", err)
        checkout_task.assert_called_once_with("WORK-142-TASK-002")

    def test_checkout_failure_keeps_the_worktree_and_names_it(self):
        config = {"worktree_root": str(self.wt_root)}
        with patch.object(prepare, "checkout", side_effect=PdlcError("working tree has changes")):
            code, out, err = self._run(["142"], config, resume_task="WORK-142-TASK-002")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn(str(self.wt_root / "myrepo" / "142"), err)
        self.assertIn("working tree has changes", err)
        self.assertTrue((self.wt_root / "myrepo" / "142" / ".git").exists())

    def test_creates_worktree_and_prints_path(self):
        code, out, _ = self._run(
            ["142", "--from", "HEAD"], {"worktree_root": str(self.wt_root)}
        )
        self.assertEqual(code, 0)
        expected = self.wt_root / "myrepo" / "142"
        self.assertEqual(out, str(expected))
        self.assertTrue((expected / ".git").exists())
        self.assertIn("pdlc/record-142", self._git("worktree", "list"))

    def test_rerun_is_idempotent(self):
        config = {"worktree_root": str(self.wt_root)}
        self._run(["142", "--from", "HEAD"], config)
        code, out, err = self._run(["142", "--from", "HEAD"], config)
        self.assertEqual(code, 0)
        self.assertEqual(out, str(self.wt_root / "myrepo" / "142"))
        self.assertIn("already present", err)

    def test_unset_root_falls_back_to_default(self):
        with patch.object(prepare, "worktree_root", lambda configured: str(self.wt_root)):
            code, out, _ = self._run(["142", "--from", "HEAD"], {})
        self.assertEqual(code, 0)
        self.assertEqual(out, str(self.wt_root / "myrepo" / "142"))

    def test_init_script_runs_with_yes(self):
        marker = self.wt_root / "ran"
        code, out, _ = self._run(
            ["142", "--from", "HEAD", "--yes"],
            {
                "worktree_root": str(self.wt_root),
                "worktree_init_script": f"touch {marker}",
            },
        )
        self.assertEqual(code, 0)
        self.assertTrue(marker.exists())

    def test_directory_in_the_way_is_reported(self):
        (self.wt_root / "myrepo" / "142").mkdir(parents=True)
        code, _, err = self._run(["142", "--from", "HEAD"], {"worktree_root": str(self.wt_root)})
        self.assertEqual(code, 1)
        self.assertIn("not a Git worktree", err)

    def _predecessor(self, **fields):
        values = {"ref": "50", "complete": False, "branch": None, "pr": None, **fields}
        return patch.object(prepare, "resolve_predecessor", lambda ref: Predecessor(**values))

    def _worktree_git(self, path, *args):
        return subprocess.check_output(["git", *args], cwd=path, text=True).strip()

    def test_after_starts_from_the_predecessors_task_branch_and_records_it(self):
        self._git("switch", "-qc", "pdlc/record-50/task-002")
        self._git("commit", "-qm", "task 2", "--allow-empty")
        task_tip = self._git("rev-parse", "HEAD")
        self._git("switch", "-q", "-")
        with self._predecessor(branch="pdlc/record-50/task-002", pr=30):
            code, out, err = self._run(["draft", "--after", "50"], {"worktree_root": str(self.wt_root)})
        self.assertEqual(code, 0, err)
        self.assertEqual(self._worktree_git(out, "rev-parse", "HEAD"), task_tip)
        self.assertEqual(self._worktree_git(out, "config", "--worktree", "--get", "pdlc.after"), "50")
        self.assertEqual(self._git("config", "--get", "extensions.worktreeConfig"), "true")
        # The main checkout does not inherit the worktree's predecessor.
        self.assertNotIn("pdlc.after", self._git("config", "--list"))

    def test_after_without_a_task_pr_falls_back_to_the_default_base(self):
        root_tip = self._git("rev-parse", "HEAD")
        with self._predecessor(), patch.object(prepare, "default_base_ref", lambda: "HEAD"):
            code, out, err = self._run(["draft", "--after", "50"], {"worktree_root": str(self.wt_root)})
        self.assertEqual(code, 0, err)
        self.assertIn("no implemented task", err)
        self.assertEqual(self._worktree_git(out, "rev-parse", "HEAD"), root_tip)
        self.assertEqual(self._worktree_git(out, "config", "--get", "pdlc.after"), "50")

    def test_after_with_an_unfindable_branch_falls_back_to_the_default_base(self):
        with self._predecessor(branch="pdlc/record-50/task-009", pr=30), \
                patch.object(prepare, "default_base_ref", lambda: "HEAD"):
            code, out, err = self._run(["draft", "--after", "50"], {"worktree_root": str(self.wt_root)})
        self.assertEqual(code, 0, err)
        self.assertIn("pdlc/record-50/task-009 not found", err)
        self.assertEqual(self._worktree_git(out, "config", "--get", "pdlc.after"), "50")

    def test_after_on_an_existing_worktree_records_without_moving_it(self):
        config = {"worktree_root": str(self.wt_root)}
        _, out, _ = self._run(["draft", "--from", "HEAD"], config)
        with self._predecessor(branch="missing", pr=30):
            code, _, err = self._run(["draft", "--after", "50"], config)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._worktree_git(out, "config", "--get", "pdlc.after"), "50")

    def test_after_and_from_cannot_combine(self):
        code, _, err = self._run(["draft", "--from", "HEAD", "--after", "50"], {"worktree_root": str(self.wt_root)})
        self.assertEqual(code, 1)
        self.assertIn("cannot be combined", err)

    def test_absent_from_usage(self):
        self.assertNotIn("prepare", _usage())


class SimpleConfig:
    worktree_root = None
    worktree_init_script = None
    worktree_base_ref = None

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


if __name__ == "__main__":
    unittest.main()

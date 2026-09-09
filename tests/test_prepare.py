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

    def _run(self, argv, config):
        cfg = SimpleConfig(**config)
        out, err = io.StringIO(), io.StringIO()
        with patch.object(prepare, "get_config", lambda: cfg), redirect_stdout(out), redirect_stderr(err):
            code = prepare.main(argv)
        return code, out.getvalue().strip(), err.getvalue()

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

import io
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pdlc.cli import _usage
from pdlc.commands import cleanup
from pdlc.domain.stages import Gate
from pdlc.domain.workflow import Lifecycle


def _state(stage="Complete", lifecycle=Lifecycle.COMPLETED):
    return SimpleNamespace(stage=stage, gate=Gate.APPROVED, lifecycle=lifecycle)


class CleanupCommandTests(unittest.TestCase):
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
        self._git("branch", "pdlc/record-142")
        self._git("branch", "pdlc/my-feature/task-001")
        self._git("branch", "pdlc/my-feature/task-002")
        self._git("branch", "unrelated")
        self.wt = self.wt_root / "myrepo" / "142"
        self.wt.parent.mkdir(parents=True)
        self._git("worktree", "add", "-q", str(self.wt), "pdlc/record-142")
        self.previous = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(lambda: os.chdir(self.previous))

    def _git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True).strip()

    def _branches(self):
        return set(self._git("branch", "--format=%(refname:short)").splitlines())

    def _run(self, argv, *, state=None):
        cfg = SimpleNamespace(worktree_root=str(self.wt_root))
        err = io.StringIO()
        with patch.object(cleanup, "get_config", lambda: cfg), \
             patch.object(cleanup, "resolve_item", lambda ref: {"Status": "Complete", "Gate State": "Approved"}), \
             patch.object(cleanup, "workflow_for_item", lambda rec: (SimpleNamespace(terminal_stage="Complete"), state or _state())), \
             patch.object(cleanup, "item_slug", lambda rec: "my-feature"), \
             redirect_stderr(err):
            code = cleanup.main(argv)
        return code, err.getvalue()

    def test_removes_worktree_and_all_stack_branches(self):
        default_branch = self._git("branch", "--show-current")
        code, err = self._run(["142", "--yes"])
        self.assertEqual(code, 0)
        self.assertFalse(self.wt.exists())
        self.assertNotIn("myrepo/142", self._git("worktree", "list"))
        self.assertEqual(self._branches(), {default_branch, "unrelated"})

    def test_stack_branches_are_gone(self):
        self._run(["142", "--yes"])
        remaining = self._branches()
        self.assertNotIn("pdlc/record-142", remaining)
        self.assertNotIn("pdlc/my-feature/task-001", remaining)
        self.assertNotIn("pdlc/my-feature/task-002", remaining)
        self.assertIn("unrelated", remaining)

    def test_refuses_when_not_complete(self):
        code, err = self._run(["142", "--yes"], state=_state(stage="Verification", lifecycle=Lifecycle.PLANNING))
        self.assertEqual(code, 1)
        self.assertIn("not Complete", err)
        self.assertTrue(self.wt.exists())
        self.assertIn("pdlc/record-142", self._branches())

    def test_unset_root_falls_back_to_default(self):
        cfg = SimpleNamespace(worktree_root=None)
        err = io.StringIO()
        with patch.object(cleanup, "get_config", lambda: cfg), \
             patch.object(cleanup, "worktree_root", lambda configured: str(self.wt_root)), \
             patch.object(cleanup, "resolve_item", lambda ref: {}), \
             patch.object(cleanup, "workflow_for_item", lambda rec: (SimpleNamespace(terminal_stage="Complete"), _state())), \
             patch.object(cleanup, "item_slug", lambda rec: "my-feature"), \
             redirect_stderr(err):
            code = cleanup.main(["142", "--yes"])
        self.assertEqual(code, 0)
        self.assertFalse(self.wt.exists())

    def test_absent_from_usage(self):
        self.assertNotIn("cleanup", _usage())


if __name__ == "__main__":
    unittest.main()

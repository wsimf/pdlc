import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from pdlc.internal.vcs import changed_files, contains_commit, has_tracked_changes, head_commit


class VcsTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))
        self.git("git", "init", "-q", "-b", "main")
        self.git("git", "config", "user.email", "test@example.com")
        self.git("git", "config", "user.name", "Test")
        self.previous = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.previous)

    def git(self, *args):
        return subprocess.check_output(args, cwd=self.root, text=True).strip()

    def commit(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        self.git("git", "add", name)
        self.git("git", "commit", "-qm", name)
        return self.git("git", "rev-parse", "HEAD")

    def test_changed_files_is_a_tree_diff_that_ignores_pdlc_state(self):
        checked = self.commit("a.txt", "one")
        self.assertEqual(head_commit(), checked)
        self.assertEqual(changed_files(checked), set())
        self.commit("b.txt", "two")
        self.commit(".pdlc/config.toml", "x")
        self.assertEqual(changed_files(checked), {"b.txt"})

    def test_a_rebase_that_changes_no_content_changes_nothing(self):
        self.commit("base.txt", "base")
        self.git("git", "checkout", "-qb", "task")
        checked = self.commit("task.txt", "task")
        self.git("git", "checkout", "-q", "main")
        self.commit("main.txt", "main")
        self.git("git", "checkout", "-q", "task")
        self.git("git", "rebase", "-q", "main")
        # The rewritten commit is new, but only main.txt differs in content.
        self.assertEqual(changed_files(checked), {"main.txt"})

    def test_an_unknown_commit_proves_nothing(self):
        self.commit("a.txt", "one")
        self.assertIsNone(changed_files("0" * 40))

    def test_contains_commit_follows_ancestry(self):
        known = self.commit("known.txt", "known")
        self.git("git", "checkout", "-qb", "other")
        other = self.commit("other.txt", "other")
        self.git("git", "checkout", "-q", "main")
        self.assertTrue(contains_commit(known))
        self.assertFalse(contains_commit(other))
        self.assertFalse(contains_commit("0" * 40))

    def test_has_tracked_changes_ignores_untracked_files(self):
        self.commit("a.txt", "one")
        self.assertFalse(has_tracked_changes())
        (self.root / "scratch.txt").write_text("x")
        self.assertFalse(has_tracked_changes())
        (self.root / "a.txt").write_text("two")
        self.assertTrue(has_tracked_changes())


if __name__ == "__main__":
    unittest.main()

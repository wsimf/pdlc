import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from pdlc.internal.vcs import files_touched_by, is_stale, stale_commits


class VcsFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))
        self.git("git", "init", "-q")
        self.git("git", "config", "user.email", "test@example.com")
        self.git("git", "config", "user.name", "Test")
        self.previous = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.previous)

    def git(self, *args):
        return subprocess.check_output(args, cwd=self.root, text=True).strip()

    def commit(self, name, content):
        (self.root / name).write_text(content)
        self.git("git", "add", name)
        self.git("git", "commit", "-qm", name)
        return self.git("git", "rev-parse", "HEAD")

    def test_root_and_ordinary_commits_are_read_and_later_change_is_stale(self):
        root = self.commit("root.txt", "root")
        ordinary = self.commit("ordinary.txt", "one")
        self.assertEqual(files_touched_by(root), ["root.txt"])
        self.assertEqual(files_touched_by(ordinary), ["ordinary.txt"])
        self.assertFalse(is_stale(ordinary, files_touched_by(ordinary)))
        self.commit("ordinary.txt", "two")
        self.assertTrue(is_stale(ordinary, files_touched_by(ordinary)))

    def test_merge_commit_files_are_supported(self):
        base = self.commit("base.txt", "base")
        self.git("git", "checkout", "-qb", "side")
        side = self.commit("side.txt", "side")
        self.git("git", "checkout", "-q", "-")
        self.commit("main.txt", "main")
        self.git("git", "merge", "--no-ff", "-qm", "merge", "side")
        merge = self.git("git", "rev-parse", "HEAD")
        self.assertEqual(set(files_touched_by(merge)), {"side.txt", "main.txt"})
        self.assertFalse(is_stale(merge, files_touched_by(merge)))

    def test_unknown_and_nonancestor_anchors_are_stale(self):
        known = self.commit("known.txt", "known")
        self.assertEqual(stale_commits(["deadbeef"]), {"deadbeef"})
        self.git("git", "checkout", "-qb", "other")
        other = self.commit("other.txt", "other")
        self.git("git", "checkout", "-q", "-")
        self.assertIn(other, stale_commits([other]))
        self.assertNotIn(known, stale_commits([known]))


if __name__ == "__main__":
    unittest.main()

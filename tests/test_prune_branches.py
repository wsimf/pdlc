import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pdlc.internal.worktree import prune_merged_branches


def _pr(branch, sha, state="MERGED"):
    return {"number": 1, "title": "t", "url": "u", "state": state, "isDraft": False,
            "branch": branch, "mergedAt": None, "checks": "SUCCESS", "headSha": sha}


class PruneMergedBranchesTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "t@example.com")
        self._git("config", "user.name", "Test")
        self._git("commit", "-qm", "root", "--allow-empty")
        # A remote default without a network remote: `default_base_ref` reads
        # `origin/HEAD`, which is all the detach fallback needs.
        self._git("update-ref", "refs/remotes/origin/main", "HEAD")
        self._git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        for branch in ("pdlc/f/task-001", "pdlc/f/task-002"):
            self._git("switch", "-qc", branch)
            self._git("commit", "-qm", branch, "--allow-empty")
        self._git("switch", "-q", "main")
        self.previous = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(lambda: os.chdir(self.previous))

    def _git(self, *args, cwd=None):
        return subprocess.check_output(["git", *args], cwd=cwd or self.repo, text=True).strip()

    def _sha(self, branch):
        return self._git("rev-parse", branch)

    def _branches(self):
        return set(self._git("branch", "--format=%(refname:short)").splitlines())

    def _merged(self):
        return [_pr("pdlc/f/task-001", self._sha("pdlc/f/task-001")), _pr("pdlc/f/task-002", self._sha("pdlc/f/task-002"))]

    def test_deletes_merged_branches_whose_tip_matches_and_skips_the_rest(self):
        self._git("branch", "extra")
        result = prune_merged_branches([
            _pr("pdlc/f/task-001", self._sha("pdlc/f/task-001")),
            _pr("pdlc/f/task-002", self._sha("main")),
            _pr("extra", ""),
            _pr("gone", "abc"),
            _pr("open", "abc", state="OPEN"),
        ])
        self.assertEqual(result["deleted"], ["pdlc/f/task-001"])
        self.assertEqual({(s["branch"], s["reason"]) for s in result["skipped"]}, {
            ("pdlc/f/task-002", "sha-mismatch"), ("extra", "sha-unknown"), ("gone", "missing"),
        })
        self.assertEqual(self._branches(), {"main", "pdlc/f/task-002", "extra"})

    def test_switches_to_the_local_default_branch_when_it_is_free(self):
        self._git("switch", "-q", "pdlc/f/task-002")
        result = prune_merged_branches(self._merged())
        self.assertEqual(sorted(result["deleted"]), ["pdlc/f/task-001", "pdlc/f/task-002"])
        self.assertEqual(self._git("branch", "--show-current"), "main")

    def test_detaches_at_the_remote_default_when_the_local_default_is_checked_out_elsewhere(self):
        worktree = self.root / "wt"
        self._git("worktree", "add", "-q", str(worktree), "pdlc/f/task-002")
        os.chdir(worktree)
        result = prune_merged_branches(self._merged())
        self.assertEqual(sorted(result["deleted"]), ["pdlc/f/task-001", "pdlc/f/task-002"])
        self.assertEqual(self._git("branch", "--show-current", cwd=worktree), "")
        self.assertEqual(self._git("rev-parse", "HEAD", cwd=worktree), self._sha("origin/main"))
        self.assertEqual(self._git("branch", "--show-current"), "main")

    def test_a_dirty_tree_keeps_head_and_its_branch(self):
        self._git("switch", "-q", "pdlc/f/task-002")
        (self.repo / "wip.txt").write_text("unsaved\n")
        result = prune_merged_branches(self._merged())
        self.assertEqual(result["deleted"], ["pdlc/f/task-001"])
        self.assertEqual(result["skipped"], [{"branch": "pdlc/f/task-002", "reason": "dirty-tree"}])
        self.assertEqual(self._git("branch", "--show-current"), "pdlc/f/task-002")

    def test_a_branch_checked_out_in_another_worktree_is_left_alone(self):
        self._git("worktree", "add", "-q", str(self.root / "wt"), "pdlc/f/task-001")
        result = prune_merged_branches(self._merged())
        self.assertEqual(result["deleted"], ["pdlc/f/task-002"])
        self.assertEqual(result["skipped"], [{"branch": "pdlc/f/task-001", "reason": "checked-out-elsewhere"}])

    def test_outside_a_git_checkout_nothing_is_touched(self):
        outside = self.root / "plain"
        outside.mkdir()
        os.chdir(outside)
        merged = self._merged()
        with patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(self.root)}):
            result = prune_merged_branches(merged)
        self.assertEqual(result["deleted"], [])
        self.assertEqual({s["reason"] for s in result["skipped"]}, {"git-unavailable"})
        self.assertEqual(self._branches(), {"main", "pdlc/f/task-001", "pdlc/f/task-002"})


if __name__ == "__main__":
    unittest.main()

"""A work item's first task continues the `gh stack` the checkout is already
on, so it can build on another work item's unmerged stack in the same tree."""

from unittest.mock import patch

from _gh_replay import GitHubHostTest

from pdlc.domain.lifecycle import PdlcError
from pdlc.hosts.lib.github.code_host import GitHubCodeHost

_BRANCH = "pdlc/record-60/task-001"
_STACK = {"trunk": "main", "currentBranch": "pdlc/record-50/task-001", "branches": [{"name": "pdlc/record-50/task-001"}]}


class FirstTaskStackTests(GitHubHostTest):
    def setUp(self):
        super().setUp()
        self.host = GitHubCodeHost()
        self.gh.gh("extension", "list", response="gh\tgithub/gh-stack\tv0.1.0\n")
        self.gh.gh("stack", "top", response="")
        self.gh.gh("stack", "add", response="")
        self.gh.gh("stack", "init", response="")

    def _stack_calls(self):
        return [args for args, _ in self.gh.calls if args[0] == "stack" and args[1] != "view"]

    def _checkout(self):
        with patch("pdlc.hosts.lib.github.code_host._local_branch_exists", return_value=False):
            return self.host.checkout_task_branch(_BRANCH, None, None)

    def test_on_a_stack_the_first_task_is_added_on_its_top(self):
        self.gh.gh("stack", "view", response=_STACK)
        self.assertEqual(
            self.host.task_stack_setup(_BRANCH, None),
            [f"stackSetup: gh stack top && gh stack add {_BRANCH}  (first task — continues the stack the current branch belongs to, on trunk main)"],
        )
        self._checkout()
        self.assertEqual(self._stack_calls(), [["stack", "top"], ["stack", "add", _BRANCH]])

    def test_off_a_stack_the_first_task_starts_a_new_one(self):
        self.gh.gh("stack", "view", response=PdlcError('current branch "main" is not part of a stack'))
        self.assertIn("gh stack init", self.host.task_stack_setup(_BRANCH, None)[0])
        self._checkout()
        self.assertEqual(self._stack_calls(), [["stack", "init", _BRANCH]])

    def test_a_later_task_enters_at_its_previous_task_regardless_of_the_current_stack(self):
        self.assertIn("gh stack checkout 40", self.host.task_stack_setup("pdlc/record-60/task-002", 40)[0])
        self.assertFalse(any(args[:2] == ["stack", "view"] for args, _ in self.gh.calls))

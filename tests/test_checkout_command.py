"""`pdlc checkout`: resolving a delivery task to the branch its stack holds."""

import json
import unittest
from unittest import mock

from _support import FileBackendTest

from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.stack import resolve_task_checkout


class CheckoutTests(FileBackendTest):
    def _plan(self, record: int, task_number: int, text: str) -> None:
        log = self.records_dir() / str(record) / "tasks" / str(task_number) / "comments.jsonl"
        entry = {"body": text, "createdAt": "2026-03-01T00:00:00Z", "url": "", "author": {"login": "t"}}
        with log.open("a") as handle:
            handle.write(json.dumps(entry) + "\n")

    def _seed(self) -> None:
        self.seed_record(70, "Implementation", "Pending", slug="record-70")
        self.seed_task(70, 701, "TASK-001", "CLOSED", "WORK-70-TASK-001 [CORE] First")
        self.seed_task(70, 702, "TASK-002", "OPEN", "WORK-70-TASK-002 [CORE] Second")
        self._plan(70, 701, "## Implementation\n\nShipped.\n")
        self.register_prs(701, [40])

    def setUp(self) -> None:
        super().setUp()
        # Isolate from the developer checkout's own worktree config and tree.
        for target in ("pdlc.internal.stack.worktree_after",):
            patcher = mock.patch(target, return_value=None)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name, value in (("working_tree_dirty", False), ("current_branch", "main")):
            patcher = mock.patch(f"pdlc.commands.checkout.{name}", return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _host(self) -> mock.MagicMock:
        host = mock.MagicMock()
        host.checkout_task_branch.return_value = "did the thing"
        patcher = mock.patch("pdlc.commands.checkout.get_code_host", return_value=host)
        patcher.start()
        self.addCleanup(patcher.stop)
        return host

    # --- resolution ---

    def test_an_implemented_task_is_checked_out_from_its_own_pull_request(self):
        self._seed()
        target = resolve_task_checkout("WORK-70-TASK-001")
        self.assertEqual(target.branch, "pdlc/record-70/task-001")
        self.assertEqual(target.pr, 40)
        self.assertIsNone(target.entry_pr)

    def test_the_next_task_enters_the_stack_at_the_previous_tasks_pull_request(self):
        self._seed()
        target = resolve_task_checkout("WORK-70-TASK-002")
        self.assertEqual(target.branch, "pdlc/record-70/task-002")
        self.assertIsNone(target.pr)
        self.assertEqual(target.entry_pr, 40)

    def test_a_task_issue_number_resolves_through_its_own_title(self):
        self._seed()
        self.assertEqual(resolve_task_checkout("702").branch, "pdlc/record-70/task-002")

    def test_a_bare_task_id_is_refused(self):
        self._seed()
        with self.assertRaisesRegex(PdlcError, "WORK-N-TASK-NNN"):
            resolve_task_checkout("TASK-002")

    def test_an_unknown_task_on_a_known_record_is_an_error(self):
        self._seed()
        with self.assertRaisesRegex(PdlcError, "no delivery task TASK-009"):
            resolve_task_checkout("WORK-70-TASK-009")

    # --- the command ---

    def test_checkout_hands_the_host_the_branch_and_its_stack_entry(self):
        self._seed()
        host = self._host()
        result = self.invoke("checkout", "WORK-70-TASK-002")
        self.assertEqual(result.code, 0, result.stderr)
        host.checkout_task_branch.assert_called_once_with("pdlc/record-70/task-002", None, 40)
        self.assertIn("WORK-70-TASK-002 [CORE] Second", result.stdout)
        self.assertIn("branch: pdlc/record-70/task-002", result.stdout)
        self.assertIn("did the thing", result.stdout)

    def _on(self, branch: str, dirty: bool) -> dict[str, mock.MagicMock]:
        """Put the tree on `branch`, clean or dirty, with the stash seam mocked."""
        mocks = {}
        for name, value in (("current_branch", branch), ("working_tree_dirty", dirty)):
            patcher = mock.patch(f"pdlc.commands.checkout.{name}", return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name in ("stash_changes", "restore_stash"):
            patcher = mock.patch(f"pdlc.commands.checkout.{name}")
            mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)
        return mocks

    def test_a_dirty_tree_on_another_branch_stops_the_checkout_and_names_the_guide(self):
        self._seed()
        host = self._host()
        stash = self._on("pdlc/record-70/task-001", dirty=True)
        result = self.invoke("checkout", "WORK-70-TASK-002")
        self.assertEqual(result.code, 1)
        self.assertIn("uncommitted changes on pdlc/record-70/task-001", result.stderr)
        self.assertIn("pdlc guide uncommitted-changes", result.stderr)
        host.checkout_task_branch.assert_not_called()
        stash["stash_changes"].assert_not_called()

    def test_already_on_the_tasks_branch_is_a_no_op_even_when_dirty(self):
        self._seed()
        host = self._host()
        self._on("pdlc/record-70/task-002", dirty=True)
        result = self.invoke("checkout", "WORK-70-TASK-002")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("already on pdlc/record-70/task-002", result.stdout)
        host.checkout_task_branch.assert_not_called()

    def test_carry_changes_stashes_checks_out_and_reapplies(self):
        self._seed()
        host = self._host()
        stash = self._on("pdlc/record-70/task-001", dirty=True)
        result = self.invoke("checkout", "WORK-70-TASK-002", "--carry-changes")
        self.assertEqual(result.code, 0, result.stderr)
        stash["stash_changes"].assert_called_once()
        self.assertIn("pdlc/record-70/task-002", stash["stash_changes"].call_args.args[0])
        host.checkout_task_branch.assert_called_once_with("pdlc/record-70/task-002", None, 40)
        stash["restore_stash"].assert_called_once()
        self.assertIn("carrying the uncommitted changes from pdlc/record-70/task-001", result.stdout)

    def test_carry_changes_on_a_clean_tree_is_a_plain_checkout(self):
        self._seed()
        host = self._host()
        stash = self._on("pdlc/record-70/task-001", dirty=False)
        result = self.invoke("checkout", "WORK-70-TASK-002", "--carry-changes")
        self.assertEqual(result.code, 0, result.stderr)
        host.checkout_task_branch.assert_called_once()
        stash["stash_changes"].assert_not_called()

    def test_a_failed_carry_reapplies_the_changes_where_they_were(self):
        self._seed()
        host = self._host()
        host.checkout_task_branch.side_effect = PdlcError("stack locked")
        stash = self._on("pdlc/record-70/task-001", dirty=True)
        result = self.invoke("checkout", "WORK-70-TASK-002", "--carry-changes")
        self.assertEqual(result.code, 1)
        self.assertIn("stack locked", result.stderr)
        stash["restore_stash"].assert_called_once()

    def test_a_conflicting_carry_names_the_stash_that_keeps_the_changes(self):
        self._seed()
        self._host()
        stash = self._on("pdlc/record-70/task-001", dirty=True)
        stash["restore_stash"].side_effect = PdlcError("CONFLICT (content): src/a.py")
        result = self.invoke("checkout", "WORK-70-TASK-002", "--carry-changes")
        self.assertEqual(result.code, 1)
        self.assertIn("conflict with it", result.stderr)
        self.assertIn("pdlc: carried from pdlc/record-70/task-001 to pdlc/record-70/task-002", result.stderr)

    def test_an_after_worktrees_first_task_is_already_on_its_branch(self):
        self.seed_record(71, "Implementation", "Pending", slug="record-71")
        self.seed_task(71, 711, "TASK-001", "OPEN", "WORK-71-TASK-001 [CORE] First")
        self.seed_record(70, "Implementation", "Pending", slug="record-70")
        self.seed_task(70, 701, "TASK-001", "CLOSED", "WORK-70-TASK-001 [CORE] First")
        self._plan(70, 701, "## Implementation\n\nShipped.\n")
        self.register_prs(701, [40])
        host = self._host()

        with mock.patch("pdlc.internal.stack.worktree_after", return_value="70"):
            result = self.invoke("checkout", "WORK-71-TASK-001")

        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("already on this worktree's branch", result.stdout)
        host.checkout_task_branch.assert_not_called()

    def test_no_argument_prints_help(self):
        result = self.invoke("checkout")
        self.assertEqual(result.code, 0)
        self.assertIn("pdlc checkout DELIVERY_TASK", result.stdout)

    def test_a_second_argument_is_a_usage_error(self):
        result = self.invoke("checkout", "WORK-70-TASK-001", "WORK-70-TASK-002")
        self.assertEqual(result.code, 1)
        self.assertIn("usage: pdlc checkout", result.stderr)


if __name__ == "__main__":
    unittest.main()

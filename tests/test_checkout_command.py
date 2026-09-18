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
        clean = mock.patch("pdlc.commands.checkout.working_tree_dirty", return_value=False)
        clean.start()
        self.addCleanup(clean.stop)

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

    def test_a_dirty_tree_stops_the_checkout_before_the_host_is_called(self):
        self._seed()
        host = self._host()
        with mock.patch("pdlc.commands.checkout.working_tree_dirty", return_value=True):
            result = self.invoke("checkout", "WORK-70-TASK-002")
        self.assertEqual(result.code, 1)
        self.assertIn("uncommitted changes", result.stderr)
        host.checkout_task_branch.assert_not_called()

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

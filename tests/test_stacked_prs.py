"""Stacked task pull requests: the stack entry point PDLC resolves from its own
registry, the GitHub host's delegation to `gh stack`, and task checkpointing."""

import json
import unittest
from unittest.mock import Mock, patch

from _gh_replay import GitHubHostTest
from _support import FileBackendTest

from pdlc.domain.lifecycle import PdlcError
from pdlc.hosts.lib.github.code_host import GitHubCodeHost
from pdlc.internal.stack import stack_entry_pr, task_branch_name


class StackEntryPointTests(unittest.TestCase):
    """PDLC resolves one fact for the stack — where to enter it — from the PR
    registry. `gh stack` owns everything else."""

    def _task(self, number, task_id, *, implemented=False, prs=()):
        return {
            "number": number, "taskId": task_id,
            "hasImplementation": implemented, "prs": list(prs),
        }

    def test_branch_name_is_derived_from_the_task_identity(self):
        self.assertEqual(task_branch_name("record-9", "TASK-003"), "pdlc/record-9/task-003")

    def test_entry_is_the_previous_implemented_tasks_pull_request(self):
        delivery = [
            self._task(1, "TASK-001", implemented=True, prs=[40]),
            self._task(2, "TASK-002"),
        ]
        self.assertEqual(stack_entry_pr(delivery, delivery[1]), 40)

    def test_first_task_has_no_entry_point(self):
        delivery = [self._task(1, "TASK-001"), self._task(2, "TASK-002")]
        self.assertIsNone(stack_entry_pr(delivery, delivery[0]))

    def test_rerunning_an_earlier_task_enters_below_it_not_above(self):
        # TASK-003 is already implemented; the driver re-runs TASK-002. The entry
        # point must be TASK-001's PR — entering at TASK-003 would put the
        # re-run on top of an already-reviewed PR.
        delivery = [
            self._task(1, "TASK-001", implemented=True, prs=[40]),
            self._task(2, "TASK-002", implemented=True, prs=[41]),
            self._task(3, "TASK-003", implemented=True, prs=[42]),
        ]
        self.assertEqual(stack_entry_pr(delivery, delivery[1]), 40)

    def test_an_implemented_task_without_a_registered_pr_is_not_an_entry_point(self):
        delivery = [
            self._task(1, "TASK-001", implemented=True),
            self._task(2, "TASK-002"),
        ]
        self.assertIsNone(stack_entry_pr(delivery, delivery[1]))

    def test_ignores_entries_without_a_task_identity(self):
        delivery = [
            {"number": 1, "taskId": None, "hasImplementation": True, "prs": [40]},
            self._task(2, "TASK-002"),
        ]
        self.assertIsNone(stack_entry_pr(delivery, delivery[1]))


class GitHubStackSubmitTests(GitHubHostTest):
    """The host runs `gh stack` and reads it back; it never derives stack shape."""

    def setUp(self):
        super().setUp()
        self.host = GitHubCodeHost()

    def _stub_stack(self, *numbers):
        self.gh.gh("extension", "list", response="gh\tgithub/gh-stack\tv0.1.0\n")
        self.gh.gh("stack", "sync", response="")
        self.gh.gh("stack", "submit", response="")
        self.gh.gh("stack", "view", response={
            "trunk": "main",
            "branches": [{"branch": f"pdlc/record-9/task-{n:03d}", "number": n} for n in numbers],
        })

        def view(args, _input):
            number = int(args[2])
            return {
                "number": number, "title": f"Task {number}", "url": f"u{number}",
                "state": "OPEN", "isDraft": True,
                "headRefName": f"pdlc/record-9/task-{number:03d}", "mergedAt": None,
                "statusCheckRollup": [{"context": "CI", "state": "SUCCESS"}],
            }

        self.gh.route(lambda args, _input: args[:2] == ["pr", "view"], view)

    def _call(self, *prefix):
        return next(args for args, _ in self.gh.calls if args[: len(prefix)] == list(prefix))

    def test_submit_syncs_prunes_submits_then_returns_the_stack_bottom_to_top(self):
        self._stub_stack(1, 2)

        prs = self.host.submit_task_stack()

        self.assertEqual([pr["number"] for pr in prs], [1, 2])
        self.assertEqual(
            [pr["branch"] for pr in prs],
            ["pdlc/record-9/task-001", "pdlc/record-9/task-002"],
        )
        # `gh stack sync --prune` is what drops landed branches; PDLC never
        # lists remote branches to work that out itself.
        self.assertEqual(self._call("stack", "sync"), ["stack", "sync", "--prune"])
        self.assertEqual(self._call("stack", "submit"), ["stack", "submit", "--auto"])
        self.assertFalse(any("branches" in " ".join(args) for args, _ in self.gh.calls if args[0] == "api"))
        pr_views = [args for args, _ in self.gh.calls if args[:2] == ["pr", "view"]]
        self.assertTrue(pr_views)
        self.assertTrue(all("--json" in args for args in pr_views))
        self.assertTrue(all("statusCheckRollup" in " ".join(args) for args in pr_views))

    def test_no_repository_default_branch_lookup_is_needed(self):
        # `gh stack` resolves the trunk itself; nothing here asks GitHub for it.
        self._stub_stack(1)
        self.host.submit_task_stack()
        self.assertFalse(any(args[:2] == ["repo", "view"] for args, _ in self.gh.calls))

    def test_stack_pr_numbers_reads_only_branch_numbers(self):
        self.gh.gh("stack", "view", response={
            "trunk": "main",
            "currentBranch": "pdlc/record-9/task-002",
            "branches": [
                {"branch": "pdlc/record-9/task-001", "number": 40, "isMerged": True},
                {"branch": "pdlc/record-9/task-002", "number": 41},
                {"branch": "pdlc/record-9/task-003"},
            ],
        })
        # A branch with no PR yet is simply absent from the numbers.
        self.assertEqual(self.host.stack_pr_numbers(), [40, 41])

    def test_missing_extension_is_a_clear_error(self):
        self.gh.gh("extension", "list", response="gh\tsome/other\tv1\n")
        with self.assertRaises(PdlcError) as caught:
            self.host.submit_task_stack()
        self.assertIn("gh extension install github/gh-stack", str(caught.exception))
        self.assertFalse(any(args[0] == "stack" for args, _ in self.gh.calls))


class ImplementTaskStackTests(FileBackendTest):
    """`pdlc post implement-task` always submits and registers the task PR."""

    def _seed(self):
        self.seed_record(70, "Implementation", "Pending", slug="record-70")
        self.seed_task(70, 701, "TASK-001", "OPEN", "WORK-70-TASK-001 [CORE] Core")
        task_dir = self.records_dir() / "70" / "tasks" / "701"
        (task_dir / "comments.jsonl").write_text(json.dumps({"body": "## Technical Plan\n\nImplement the core behavior.\n"}) + "\n")

    def _assert_rejected_before_stack(self, *, status="Implementation", gate="Pending", work_type=None, skipped="", body=None):
        if not (self.records_dir() / "70").exists():
            self.seed_record(70, status, gate, slug="record-70", work_type=work_type, skipped=skipped, body=body)
            self.seed_task(70, 701, "TASK-001", "OPEN", "WORK-70-TASK-001 [CORE] Core")
        else:
            metadata = self.meta(70)
            metadata["fields"].update({"Status": status, "Gate State": gate, "Skipped States": skipped})
            if work_type is None:
                metadata.pop("workType", None)
            else:
                metadata["workType"] = work_type
            (self.records_dir() / "70" / "meta.json").write_text(json.dumps(metadata) + "\n")
        task_dir = self.records_dir() / "70" / "tasks" / "701"
        plan = json.dumps({"body": "## Technical Plan\n\nImplement the core behavior.\n"})
        (task_dir / "comments.jsonl").write_text(plan + "\n")
        before = self.task_comments_text(70, 701)
        host = Mock()
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=host):
            result = self.invoke("post_implement_task", 701, self.evidence_file("Shipped it.\n"), "--close")
        self.assertEqual(result.code, 1)
        host.submit_task_stack.assert_not_called()
        self.assertEqual(self.task_comments_text(70, 701), before)
        self.assertEqual(self.task_meta(70, 701)["state"], "OPEN")
        return result

    def test_parent_complete_is_locked_before_stack_submission(self):
        result = self._assert_rejected_before_stack(status="Complete", gate="Approved")
        self.assertIn("Complete and locked", result.stderr)

    def test_unknown_work_type_is_rejected_before_stack_submission(self):
        result = self._assert_rejected_before_stack(work_type="unknown")
        self.assertIn("unknown work type", result.stderr)

    def test_unavailable_work_type_is_rejected_before_stack_submission(self):
        result = self._assert_rejected_before_stack(work_type="bug")
        self.assertIn("workflow unavailable", result.stderr)

    def test_malformed_parent_state_is_rejected_before_stack_submission(self):
        self.seed_record(70, "Implementation", "Pending", slug="record-70")
        self.seed_task(70, 701, "TASK-001", "OPEN", "WORK-70-TASK-001 [CORE] Core")
        task_dir = self.records_dir() / "70" / "tasks" / "701"
        before = json.dumps({"body": "## Technical Plan\n\nImplement the core behavior.\n"}) + "\n"
        task_dir.joinpath("comments.jsonl").write_text(before)
        metadata = self.records_dir() / "70" / "meta.json"
        value = json.loads(metadata.read_text())
        value["fields"]["Gate State"] = "Not A Gate"
        metadata.write_text(json.dumps(value) + "\n")
        host = Mock()
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=host):
            result = self.invoke("post_implement_task", 701, self.evidence_file("Shipped it.\n"), "--close")
        self.assertEqual(self.task_comments_text(70, 701), before)
        self.assertEqual(self.task_meta(70, 701)["state"], "OPEN")
        host.submit_task_stack.assert_not_called()
        self.assertIn("invalid workflow state", result.stderr)

    def test_wrong_stage_is_rejected_before_stack_submission(self):
        result = self._assert_rejected_before_stack(status="Testing")
        self.assertIn("implementation is not active", result.stderr)

    def test_blocking_gates_are_rejected_before_stack_submission(self):
        for gate in ("Review Required", "Approval Required", "Decision Required", "CI Pending"):
            with self.subTest(gate=gate):
                result = self._assert_rejected_before_stack(gate=gate)
                self.assertIn("implementation is not active", result.stderr)

    def test_skipped_implementation_is_rejected_before_stack_submission(self):
        result = self._assert_rejected_before_stack(skipped="Implementation")
        self.assertIn("implementation is not active", result.stderr)

    def test_missing_technical_plan_is_rejected_before_stack_submission(self):
        self.seed_record(70, "Implementation", "Pending", slug="record-70")
        self.seed_task(70, 701, "TASK-001", "OPEN", "WORK-70-TASK-001 [CORE] Core")
        task_dir = self.records_dir() / "70" / "tasks" / "701"
        before = task_dir.joinpath("comments.jsonl").read_text()
        host = Mock()
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=host):
            result = self.invoke("post_implement_task", 701, self.evidence_file("Shipped it.\n"), "--close")
        self.assertEqual(result.code, 1)
        self.assertIn("has no Technical Plan", result.stderr)
        host.submit_task_stack.assert_not_called()
        self.assertEqual(task_dir.joinpath("comments.jsonl").read_text(), before)
        self.assertEqual(self.task_meta(70, 701)["state"], "OPEN")

    def test_changes_required_remains_eligible(self):
        self._seed()
        metadata = self.meta(70)
        metadata["fields"]["Gate State"] = "Changes Required"
        (self.records_dir() / "70" / "meta.json").write_text(json.dumps(metadata) + "\n")
        host = Mock()
        host.submit_task_stack.return_value = [{"number": 148, "branch": "pdlc/record-70/task-001"}]
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=host):
            result = self.invoke("post_implement_task", 701, self.evidence_file("Shipped it.\n"))
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["taskPr"]["number"], 148)

    def test_existing_implementation_evidence_can_be_retried_and_closed(self):
        self._seed()
        task_dir = self.records_dir() / "70" / "tasks" / "701"
        prior = (
            json.dumps({"body": "## Implementation\n\nPrior attempt.\n"}) + "\n"
            + json.dumps({"body": "## Technical Plan\n\nImplement the core behavior.\n"}) + "\n"
        )
        task_dir.joinpath("comments.jsonl").write_text(prior)
        host = Mock()
        host.submit_task_stack.side_effect = [
            PdlcError("stack submission failed"),
            [{"number": 148, "branch": "pdlc/record-70/task-001"}],
        ]
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=host):
            failed = self.invoke("post_implement_task", 701, self.evidence_file("Retry failed.\n"), "--close")
            self.assertEqual(failed.code, 1)
            self.assertEqual(self.task_comments_text(70, 701), prior)
            self.assertEqual(self.task_meta(70, 701)["state"], "OPEN")
            result = self.invoke("post_implement_task", 701, self.evidence_file("Retry succeeded.\n"), "--close")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(self.task_meta(70, 701)["state"], "CLOSED")

    def test_submits_and_registers_the_task_pr(self):
        self._seed()
        host = Mock()
        host.submit_task_stack.return_value = [{
            "number": 148,
            "branch": "pdlc/record-70/task-001",
            "title": "Core",
            "url": "u148",
        }]
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=host):
            result = self.invoke("post_implement_task", 701, self.write_file("impl.md", "Shipped it.\n"))
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["taskPr"]["number"], 148)
        self.assertEqual(result.json["prs"], [148])
        host.submit_task_stack.assert_called_once_with()

    def test_file_backend_reports_no_stack_support_without_mutating_the_task(self):
        self._seed()
        before = self.task_comments_text(70, 701)
        result = self.invoke("post_implement_task", 701, self.write_file("impl.md", "Shipped it.\n"))
        self.assertEqual(result.code, 1)
        self.assertIn("cannot submit stacked pull requests", result.stderr)
        self.assertEqual(self.task_meta(70, 701)["state"], "OPEN")
        self.assertEqual(self.task_comments_text(70, 701), before)


if __name__ == "__main__":
    unittest.main()

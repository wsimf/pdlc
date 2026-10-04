import unittest
from unittest.mock import patch

from pdlc.config import Config, install_config, reset_config
from pdlc.domain.records import PullRef
from pdlc.commands.inspect_test import _testable_scope_section
from pdlc.commands.inspect_implement import _next_task_section
from pdlc.commands.inspect_task import _render_task
from pdlc.internal.reporting import older_comments_notice
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal import pull_requests


class ReviewRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        install_config(Config())
        self.addCleanup(reset_config)
    def test_comment_notice_reports_exact_older_count(self):
        self.assertEqual(older_comments_notice("TASK-001", {"totalCount": 205}, 100), "105 more comments; use pdlc inspect comments TASK-001 --page 2")
        self.assertEqual(older_comments_notice("TASK-001", {"totalCount": 100}, 100), "")

    def test_next_task_omits_the_technical_plan(self):
        # The plan is no longer rendered by `inspect implement`; `inspect task` owns it.
        task = {"number": 1, "taskId": "TASK-001", "title": "Task", "isUI": False, "state": "OPEN", "hasPlan": True, "hasImplementation": False, "implementationInvalidated": False, "prs": [], "planComment": "## Technical Plan\n\nsecret"}
        with patch("pdlc.commands.inspect_implement.after_predecessor", return_value=None):
            output = _next_task_section({"Slug": "record-1"}, [task], task, [])
        self.assertNotIn("secret", output)
        self.assertNotIn("Technical Plan", output)

    def test_inspect_task_output_includes_comment_notice(self):
        # The truncated-comment notice must reach the reader where the plan is now
        # rendered — `inspect task`, which pulls the plan from the task's comments.
        task = {"number": 1, "taskId": "TASK-001", "title": "Task", "url": "", "state": "OPEN", "isUI": False,
                "hasPlan": True, "hasImplementation": False, "implementationInvalidated": False, "needsPlan": False,
                "prs": [], "body": "b",
                "planComment": "plan", "commentObjects": [], "comments": [{}] * 100, "commentsMeta": {"totalCount": 101}}
        with patch("pdlc.commands.inspect_task.get_capabilities") as caps:
            caps.return_value.agent.return_value = "general-purpose"
            output = _render_task(task)
        self.assertIn("1 more comments; use pdlc inspect comments 1 --page 2", output)

    def test_testable_scope_fetches_each_task_pr_once_and_keeps_ownership(self):
        tasks = [
            {"state": "CLOSED", "hasImplementation": True, "title": "A", "prs": [PullRef(1)], "isUI": False},
            {"state": "CLOSED", "hasImplementation": True, "title": "B", "prs": [PullRef(2)], "isUI": False},
        ]
        prs = [{"number": 1, "repository": "", "state": "MERGED", "checks": "SUCCESS", "isDraft": False}, {"number": 2, "repository": "", "state": "MERGED", "checks": "SUCCESS", "isDraft": False}]
        with patch("pdlc.commands.inspect_test._files_for_pull_request", side_effect=lambda pr: [f"f{pr['number']}"]) as fetch:
            output = "\n".join(_testable_scope_section(tasks, prs))
        self.assertEqual(fetch.call_count, 2)
        self.assertIn("### A\n\nPR #1", output)
        self.assertIn("### B\n\nPR #2", output)
        self.assertNotIn("### A\n\nPR #1 (MERGED, checks: SUCCESS)\nFiles touched:\n- f1\n\nPR #2", output)

    def test_registry_snapshot_avoids_record_and_task_fetches(self):
        record = {"prs": [PullRef(1)]}
        pr = {"number": 1, "repository": "", "label": "#1", "title": "PR", "url": "", "state": "OPEN", "isDraft": False, "branch": "task", "mergedAt": None, "checks": "NONE"}
        with patch.object(pull_requests, "resolve_item") as resolve, patch.object(pull_requests, "get_backend") as backend:
            with patch.object(pull_requests, "get_code_host") as host:
                host.return_value.pull_requests.return_value = [pr]
                self.assertEqual(pull_requests.record_pull_requests("7", record=record, tasks=[]), [pr])
        resolve.assert_not_called()
        backend.assert_not_called()

    def test_equal_length_wrong_pr_identity_is_rejected(self):
        record = {"prs": [1]}
        with patch.object(pull_requests, "get_code_host") as host:
            host.return_value.pull_requests_by_number.return_value = [{"number": 99}]
            with self.assertRaises(PdlcError):
                pull_requests.record_pull_requests("7", record=record, tasks=[])


if __name__ == "__main__":
    unittest.main()

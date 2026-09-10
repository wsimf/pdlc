import unittest
from unittest.mock import patch

from pdlc.commands.inspect_test import _testable_scope_section
from pdlc.commands.inspect_verify import _reuse_items
from pdlc.commands.post_complete import _stale_rows
from pdlc.commands.inspect_implement import _next_task_section
from pdlc.commands.inspect_task import _render_task
from pdlc.internal.reporting import older_comments_notice
from pdlc.domain.evidence import parse_verification_report
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal import pull_requests


class ReviewRegressionTests(unittest.TestCase):
    def test_comment_notice_reports_exact_older_count(self):
        self.assertEqual(older_comments_notice("TASK-001", {"totalCount": 205}, 100), "105 more comments; use pdlc inspect comments TASK-001 --page 2")
        self.assertEqual(older_comments_notice("TASK-001", {"totalCount": 100}, 100), "")

    def test_next_task_omits_the_technical_plan(self):
        # The plan is no longer rendered by `inspect implement`; `inspect task` owns it.
        task = {"number": 1, "taskId": "TASK-001", "title": "Task", "isUI": False, "state": "OPEN", "hasPlan": True, "hasImplementation": False, "planComment": "## Technical Plan\n\nsecret"}
        output, chosen = _next_task_section({"Slug": "record-1"}, [task], None, None)
        self.assertIs(chosen, task)
        self.assertNotIn("secret", output)
        self.assertNotIn("Technical Plan", output)

    def test_inspect_task_output_includes_comment_notice(self):
        # The truncated-comment notice must reach the reader where the plan is now
        # rendered — `inspect task`, which pulls the plan from the task's comments.
        task = {"number": 1, "taskId": "TASK-001", "title": "Task", "url": "", "state": "OPEN", "isUI": False,
                "hasPlan": True, "hasImplementation": False, "needsPlan": False, "prs": [], "body": "b",
                "planComment": "plan", "commentObjects": [], "comments": [{}] * 100, "commentsMeta": {"totalCount": 101}}
        with patch("pdlc.commands.inspect_task.get_capabilities") as caps:
            caps.return_value.agent.return_value = "general-purpose"
            output = _render_task(task)
        self.assertIn("1 more comments; use pdlc inspect comments 1 --page 2", output)
    REPORT = """## Claims Audit
- Claim (Verified @ deadbeef)
## User Journeys
- Journey (Verified @ deadbeef)
## UX
- Clean
## Cumulative Review
- Clean
## Findings
- None
Recommendation: Changes Required
"""

    def test_unknown_anchor_is_stale_in_both_readers(self):
        with patch("pdlc.commands.inspect_verify.stale_commits", return_value={"deadbeef"}) as stale:
            self.assertTrue(all(item["stale"] for item in _reuse_items(self.REPORT)))
        stale.assert_called_once_with(["deadbeef", "deadbeef"])
        with patch("pdlc.internal.vcs.stale_commits", return_value={"deadbeef"}):
            self.assertEqual(_stale_rows(self.REPORT), [
                "Claim (Verified @ deadbeef)", "Journey (Verified @ deadbeef)"
            ])

    def test_parser_accepts_heading_case_and_ignores_unknown_heading(self):
        body = """## claims audit
- Claim (Verified @ HEAD)
## Unknown
- Must not become evidence
## USER JOURNEYS
- Journey (Verified @ HEAD)
## ux
- Clean
## cumulative review
- Clean
## Findings
- None
Recommendation: Approval Required
"""
        report = parse_verification_report(body)
        self.assertEqual([row.text for row in report.rows], ["Claim (Verified @ HEAD)", "Journey (Verified @ HEAD)", "Clean", "Clean"])

    def test_testable_scope_fetches_each_task_pr_once_and_keeps_ownership(self):
        tasks = [
            {"state": "CLOSED", "hasImplementation": True, "title": "A", "prs": [1], "isUI": False},
            {"state": "CLOSED", "hasImplementation": True, "title": "B", "prs": [2], "isUI": False},
        ]
        prs = [{"number": 1, "state": "MERGED", "checks": "SUCCESS", "isDraft": False}, {"number": 2, "state": "MERGED", "checks": "SUCCESS", "isDraft": False}]
        with patch("pdlc.commands.inspect_test._files_for_pull_request", side_effect=lambda pr: [f"f{pr['number']}"]) as fetch:
            output = "\n".join(_testable_scope_section(tasks, prs))
        self.assertEqual(fetch.call_count, 2)
        self.assertIn("### A\n\nPR #1", output)
        self.assertIn("### B\n\nPR #2", output)
        self.assertNotIn("### A\n\nPR #1 (MERGED, checks: SUCCESS)\nFiles touched:\n- f1\n\nPR #2", output)

    def test_registry_snapshot_avoids_record_and_task_fetches(self):
        record = {"prs": [1]}
        pr = {"number": 1, "title": "PR", "url": "", "state": "OPEN", "isDraft": False, "branch": "task", "mergedAt": None, "checks": "NONE"}
        with patch.object(pull_requests, "resolve_item") as resolve, patch.object(pull_requests, "get_backend") as backend:
            with patch.object(pull_requests, "get_code_host") as host:
                host.return_value.pull_requests_by_number.return_value = [pr]
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

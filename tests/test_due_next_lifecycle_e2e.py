"""File-host lifecycle scenarios that verify the public ``pdlc inspect`` route.

The literal prose oracle is intentionally limited to Product, UI, and Tasks;
the remaining stages are checked against their action/owner contract while
``docs/due-next-decision.md`` is still being completed.
"""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

from _support import FileBackendTest


class DueNextLifecycleE2ETests(FileBackendTest):
    def inspect_due(self, issue: int, notation: str, action: str, *, text: str | None = None) -> str:
        result = self.invoke("inspect", issue, "--full")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn(f"Due next: {notation} →", result.stdout)
        self.assertIn(action, result.stdout)
        if text is not None:
            self.assertIn(text, result.stdout)
        return result.stdout

    def next_action(self, issue: int, action: str) -> None:
        result = self.next("--work-item", issue)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.front_matter("action"), action)

    def make_product(self) -> tuple[int, str]:
        evidence = self.evidence_file()
        product = self.write_file(
            "product.md",
            "## Product\nThe shell ships.\n\n"
            "### 4. Functional requirements\n- FR-1: lands.\n\n"
            "### 5. Constraints\n- C-1: commands own mutations.\n\n"
            "## Decisions\n- Decided to ship.\n\n## Open Questions\n- none\n",
        )
        result = self.invoke(
            "post_write", "--title", "Shell", "--slug", "shell",
            "--evidence", evidence, "--body", product,
        )
        self.assertEqual(result.code, 0, result.stderr)
        return result.json["work_item_number"], evidence

    def test_valid_lifecycle_checks_inspect_at_each_resting_state(self):
        issue, evidence = self.make_product()
        self.inspect_due(issue, "Product.ApprovalRequired", "pdlc post approve")
        self.next_action(issue, "human-approval")

        self.assertEqual(self.invoke("post_approve", issue, evidence).code, 0)
        self.inspect_due(issue, "UI.Pending", "pdlc-tasks")
        self.next_action(issue, "pdlc-tasks")

        ui = self.write_file("ui.md", "## UI\n\nUJ-1 covers the first run.\n")
        self.mark_ui_reviewed(issue, ui)
        self.assertEqual(
            self.invoke("post_tasks", "--work-item", issue, "--stage", "UI",
                        "--body", ui, "--evidence", evidence).code,
            0,
        )
        self.inspect_due(issue, "UI.ApprovalRequired", "pdlc post approve")
        self.next_action(issue, "human-approval")
        self.assertEqual(self.invoke("post_approve", issue, evidence).code, 0)

        task_body = self.write_file("task.md", "**Blocked by:** None\n**Type:** AFK\n**Requirements Covered:** FR-1, C-1\n**UI Journeys:** UJ-1\n\n**Scope:**\nBuild the core.\n\n**Acceptance Criteria:**\n- [ ] FR-1 works.\n")
        manifest = self.write_file(
            "manifest.json",
            json.dumps([{
                "id": "TASK-001", "action": "create", "title": "Build core", "body": task_body,
                "type": "ui", "covers": ["FR-1", "C-1", "UJ-1"],
            }]),
        )
        self.mark_tasks_reviewed(issue, manifest)
        tasks = self.invoke(
            "post_tasks", "--work-item", issue, "--stage", "Tasks",
            "--manifest", manifest, "--evidence", evidence,
        )
        self.assertEqual(tasks.code, 0, tasks.stderr)
        task_number = tasks.json["tasks"][0]["number"]
        self.inspect_due(issue, "Tasks.ApprovalRequired", "pdlc post approve")
        self.next_action(issue, "human-approval")
        self.assertEqual(self.invoke("post_approve", issue, evidence).code, 0)

        plan_manifest = self.reviewed_plan_manifest(issue, {"TASK-001": "Touch core_service.py."})
        planned = self.invoke(
            "post_plan", "--work-item", issue, "--manifest", plan_manifest,
            "--evidence", evidence,
        )
        self.assertEqual(planned.code, 0, planned.stderr)
        self.inspect_due(issue, "TechnicalPlan.ApprovalRequired", "pdlc post approve")
        self.next_action(issue, "human-approval")
        self.assertEqual(self.invoke("post_approve", issue, evidence).code, 0)
        self.inspect_due(issue, "Implementation.Pending", "pdlc-implement")
        self.next_action(issue, "pdlc-implement")

        implementation = self.write_file("implementation.md", self.implementation_summary("Shipped. FR-1 covered."))
        code_host = Mock()
        code_host.submit_task_stack.return_value = [{
            "number": 147, "repository": "", "title": "Task implementation", "url": "https://x/147",
            "state": "OPEN", "isDraft": True, "branch": "pdlc/shell/task-001",
            "mergedAt": None, "checks": "SUCCESS",
        }]
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=code_host):
            implemented = self.invoke("post_implement_task", task_number, implementation)
        self.assertEqual(implemented.code, 0, implemented.stderr)
        self.seed_prs(issue, [{
            "number": 147, "repository": "", "title": "Task implementation", "url": "https://x/147",
            "state": "OPEN", "isDraft": False, "branch": "feature/task",
            "mergedAt": None, "checks": "SUCCESS", "relation": "closes",
        }])
        stage_host = Mock()
        with patch("pdlc.commands.post_implement.get_code_host", return_value=stage_host), \
             patch("pdlc.commands.post_implement.check_out"):
            self.assertEqual(self.invoke("post_implement", issue, evidence).code, 0)
        stage_host.submit_task_stack.assert_called_once_with()
        self.inspect_due(issue, "Implementation.ReviewRequired", "pdlc-review")
        self.next_action(issue, "pdlc-review")
        self.assertEqual(self.invoke("post_review", issue, "approval-required", evidence).code, 0)
        self.inspect_due(issue, "Implementation.ApprovalRequired", "pdlc post approve")
        self.assertEqual(self.invoke("post_approve", issue, evidence).code, 0)

        self.inspect_due(issue, "Testing.Pending", "pdlc-test")
        self.next_action(issue, "pdlc-test")
        trace = self.write_file("trace.md", "FR-1 -> core_service.py\n")
        test_host = Mock()
        test_host.ensure_pull_request_linked.return_value = {
            "number": 147, "repository": "", "title": "Task implementation", "url": "https://x/147",
            "state": "OPEN", "isDraft": False, "branch": "feature/task",
            "mergedAt": None, "checks": "SUCCESS",
        }
        with patch("pdlc.commands.post_test.get_code_host", return_value=test_host):
            tested = self.invoke("post_test", issue, evidence, "--traceability", trace)
        test_host.submit_task_stack.assert_called_once_with()
        self.assertEqual(tested.code, 0, tested.stderr)
        self.assertEqual(self.invoke("post_review", issue, "approval-required", evidence).code, 0)
        self.inspect_due(issue, "Testing.ApprovalRequired", "pdlc post approve")
        self.assertEqual(self.invoke("post_approve", issue, evidence).code, 0)

        verified = self.invoke("post_verify", issue, self.verify_report(issue))
        self.assertEqual(verified.code, 0, verified.stderr)
        self.inspect_due(issue, "Verification.ApprovalRequired", "pdlc post complete")
        self.next_action(issue, "human-approval")

    def test_user_invalidation_returns_to_stale_and_routes_to_owner(self):
        issue, evidence = self.make_product()
        self.invoke("post_approve", issue, evidence)
        invalidation = self.write_file("invalidate-ui.md", "The journey needs a clearer empty state.\n")
        result = self.invoke("post_invalidate", issue, "UI", invalidation)
        self.assertEqual(result.code, 0, result.stderr)
        output = self.inspect_due(issue, "UI.Stale", "pdlc-tasks", text="invalidated")
        self.assertIn("1 open change request for UI: Invalidation.", output)
        changes = self.invoke("inspect_changes", issue)
        self.assertIn("The journey needs a clearer empty state.", changes.stdout)
        self.next_action(issue, "pdlc-tasks")

    def test_automated_review_findings_route_back_to_implementation(self):
        self.seed_record(81, "Implementation", "Review Required")
        findings = self.write_file("findings.md", "## Findings\n\n- Add retry coverage.\n")
        result = self.invoke("post_review", 81, "changes-required", findings)
        self.assertEqual(result.code, 0, result.stderr)
        self.inspect_due(81, "Implementation.ChangesRequired", "pdlc-implement")
        timeline = self.invoke("inspect_timeline", 81, "--full")
        self.assertEqual(timeline.code, 0, timeline.stderr)
        self.assertIn("Add retry coverage.", timeline.stdout)
        self.next_action(81, "pdlc-implement")


if __name__ == "__main__":
    import unittest

    unittest.main()

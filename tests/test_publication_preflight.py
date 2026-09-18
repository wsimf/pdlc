"""Rejected publications must not touch PRs or record their linkage."""

from unittest.mock import Mock, patch

from pdlc.domain.lifecycle import PdlcError

from _support import FileBackendTest


class PublicationPreflightTests(FileBackendTest):
    def test_invalid_reauthoring_preserves_approval_gate(self):
        body = self.write_file("task-body.md", "task body\n")
        evidence = self.evidence_file()
        self.seed_record(80, "Tasks", "Approval Required")
        manifest = self.write_file("bad-manifest.json", '[{"id": 1, "title": "Bad", "body": "' + str(body) + '", "ui": false, "covers": ["FR-1"]}]')
        result = self.invoke("post_tasks", "--work-item", 80, "--stage", "Tasks", "--manifest", manifest, "--evidence", evidence)
        self.assertEqual(result.code, 1)
        self.assertEqual(self.state(80), ("Tasks", "Approval Required"))
        self.assertEqual(self.comments_text(80), "")

        self.seed_record(81, "Technical Plan", "Approval Required")
        self.seed_task(81, 811, "TASK-001", "OPEN", "WORK-81-TASK-001 Task")
        bad_plan = self.write_file("bad-plan.json", '[{"id": 1, "plan": "' + str(body) + '"}]')
        result = self.invoke("post_plan", "--work-item", 81, "--manifest", bad_plan, "--evidence", evidence)
        self.assertEqual(result.code, 1)
        self.assertEqual(self.state(81), ("Technical Plan", "Approval Required"))
        self.assertEqual(self.comments_text(81), "")

    def test_invalid_ui_reauthoring_preserves_gate_and_body(self):
        self.seed_record(82, "UI", "Approval Required")
        before = self.body(82)
        body = self.write_file("bad-ui.md", "UI prose without an explicit journey or no UI decision.\n")
        result = self.invoke("post_tasks", "--work-item", 82, "--stage", "UI", "--body", body, "--evidence", self.evidence_file())
        self.assertEqual(result.code, 1)
        self.assertEqual(self.state(82), ("UI", "Approval Required"))
        self.assertEqual(self.body(82), before)
        self.assertEqual(self.comments_text(82), "")

    def test_post_test_pushes_the_stack_before_posting_and_a_failed_push_posts_nothing(self):
        evidence = self.evidence_file()
        traceability = self.write_file("trace.md", "FR-1: covered.\n")
        self.seed_record(40, "Testing", "Pending")
        host = Mock()
        host.submit_task_stack.side_effect = PdlcError("push refused")
        with patch("pdlc.commands.post_test.get_code_host", return_value=host), \
                patch("pdlc.commands.post_test.attach_pr") as register:
            result = self.invoke("post_test", 40, evidence, "--traceability", traceability)
        self.assertEqual(result.code, 1, result.stdout)
        self.assertIn("push refused", result.stderr)
        host.ensure_pull_request_linked.assert_not_called()
        register.assert_not_called()
        self.assertEqual(self.state(40), ("Testing", "Pending"))
        self.assertEqual(self.comments_text(40), "")

    def test_invalid_workflows_stop_before_pr_writes(self):
        evidence = self.evidence_file()
        traceability = self.write_file("trace.md", "FR-1: covered.\n")
        issue = 25
        for command, stage in (("post_implement", "Implementation"), ("post_test", "Testing")):
            for work_type, gate, error in (
                ("bug", "Pending", "workflow unavailable"),
                ("unknown", "Pending", "unknown work type"),
                ("feature", "Review Required", "must be invalidated"),
            ):
                with self.subTest(command=command, work_type=work_type, gate=gate):
                    issue += 1
                    self.seed_record(issue, stage, gate, work_type=work_type)
                    args = [issue, evidence]
                    if command == "post_test":
                        args += ["--traceability", traceability]
                    module = f"pdlc.commands.{command}"
                    with patch(f"{module}.get_code_host") as host, patch(f"{module}.attach_pr") as register:
                        result = self.invoke(command, *args)
                    self.assertEqual(result.code, 1, result.stdout)
                    self.assertIn(error, result.stderr)
                    host.assert_not_called()
                    register.assert_not_called()
                    self.assertEqual(self.state(issue), (stage, gate))
                    self.assertEqual(self.comments_text(issue), "")

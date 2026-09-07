"""Rejected publications must not touch PRs or record their linkage."""

from unittest.mock import patch

from _support import FileBackendTest


class PublicationPreflightTests(FileBackendTest):
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

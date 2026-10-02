"""Discussion posting, inspect visibility, and uncertain-write recovery."""

import json
from unittest.mock import patch

from _support import FileBackendTest
from pdlc import cli
from pdlc.domain.lifecycle import PdlcError, TransientError
from pdlc.hosts.lib import process
from pdlc.internal import failure
from pdlc.internal.workitem import comments_for_issue


class AttachUserCommentTests(FileBackendTest):
    def setUp(self):
        super().setUp()
        self.seed_record(70, "Implementation", "Pending")
        self.seed_task(70, 701, "TASK-001", "OPEN", "WORK-70-TASK-001 Core")
        process.reset_run_state()
        failure.reset()
        self.addCleanup(process.reset_run_state)
        self.addCleanup(failure.reset)

    def test_preserves_body_and_state_on_records_and_tasks(self):
        body = "  Keep this behind a flag.\n\nMore context.\n"
        for number, inspect in ((70, "inspect"), (701, "inspect_task")):
            with self.subTest(number=number):
                path = self.records_dir() / "70"
                if number == 701:
                    path = path / "tasks" / "701"
                before_meta = json.loads((path / "meta.json").read_text())
                before_body = (path / "body.md").read_bytes()
                result = self.invoke("post_attach_user_comment", number, "--body", "text:" + body)
                self.assertEqual(result.code, 0, result.stderr)
                comments = comments_for_issue(str(number))
                self.assertEqual(result.json, {"workItem": number, "comment": comments[0]["url"]})
                self.assertEqual(comments[0]["body"], body)
                self.assertEqual(comments[0]["author"]["login"], "tester")
                after_meta = json.loads((path / "meta.json").read_text())
                after_meta.pop("commentSeq", None)
                self.assertEqual(before_meta, after_meta)
                self.assertEqual(before_body, (path / "body.md").read_bytes())
                inspected = self.invoke(inspect, number, *(("--full",) if number == 70 else ()))
                self.assertEqual(inspected.code, 0, inspected.stderr)
                output = inspected.stdout
                self.assertIn("## User Comments", output)
                self.assertIn("Keep this behind a flag.", output)

    def test_file_and_stdin_and_repeated_calls(self):
        source = self.work / "comment.md"
        source.write_text("Please keep café support.\n")
        for argument, stdin in ((str(source), None), ("-", source.read_text())):
            result = self.invoke("post_attach_user_comment", 70, "--body", argument, stdin=stdin)
            self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual([c["body"] for c in comments_for_issue("70")], [source.read_text()] * 2)

    def test_invalid_inputs_never_write(self):
        for source in ("text:", "text: \n", "text:PDLC-REVIEW\nbody", "text: \nPDLC-APPROVED", "text:## Technical Plan\nbody", "text:\n## Implementation\nbody", str(self.work / "missing.md")):
            with self.subTest(source=source):
                result = self.invoke("post_attach_user_comment", 70, "--body", source)
                self.assertEqual(result.code, 1)
                self.assertTrue(result.stderr.startswith("pdlc: comment body"), result.stderr)
        result = self.invoke("post_attach_user_comment", "oops", "--body", "text:Hello")
        self.assertEqual(result.stderr, "pdlc: work item number must be numeric: oops\n")
        self.assertEqual(comments_for_issue("70"), [])

    def test_unknown_target_is_refused(self):
        result = self.invoke("post_attach_user_comment", 999, "--body", "text:Hello")
        self.assertEqual(result.code, 1)
        self.assertEqual(comments_for_issue("70"), [])

    def test_failure_outputs_preserve_error_and_recovery(self):
        invocation = ["post", "attach-user-comment", "70", "--body", "text:Hello"]
        failure.set_invocation(invocation)
        cases = ((False, PdlcError("permission denied"), 1), (False, TransientError("DNS failure", attempts=3), 75), (True, TransientError("connection reset", attempts=1), 76))
        for writes, error, expected in cases:
            with self.subTest(code=expected):
                process.reset_run_state()

                def fail(*args):
                    if writes:
                        process._mark_write(True)
                    raise error

                with patch("pdlc.commands.post_attach_user_comment.post_comment", side_effect=fail) as post:
                    result = self.invoke("post_attach_user_comment", 70, "--body", "text:Hello")
                self.assertEqual(result.code, expected, result.stderr)
                post.assert_called_once_with("70", "Hello")
                if expected == 1:
                    self.assertEqual(result.stderr, "pdlc: permission denied\n")
                elif expected == 75:
                    self.assertIn("pdlc: transient: DNS failure (3 attempts)", result.stderr)
                    self.assertIn("nothing was changed", result.stderr)
                else:
                    self.assertIn("pdlc: transient: connection reset", result.stderr)
                    self.assertIn("pdlc inspect comments 70 --page 1", result.stderr)
                    self.assertIn("next-page", result.stderr)
                    self.assertIn("creates a duplicate", result.stderr)
        self.assertEqual(comments_for_issue("70"), [])

    def test_dispatch_and_help(self):
        module, args = cli._resolve(["post", "attach-user-comment", "70", "--body", "text:Hello"])
        self.assertEqual(module, "pdlc.commands.post_attach_user_comment")
        self.assertEqual(args, ["70", "--body", "text:Hello"])
        result = self.invoke("post_attach_user_comment", "--help")
        self.assertEqual(result.code, 0)
        self.assertIn("--body FILE|-|text:BODY", result.stdout)
        self.assertIn("attach-user-comment", cli._usage())

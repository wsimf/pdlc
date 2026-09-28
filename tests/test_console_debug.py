"""Console diagnostics do not change external-call execution or results."""

from __future__ import annotations

import io
import subprocess
import unittest
from contextlib import redirect_stderr
from unittest import mock

from pdlc.domain.lifecycle import TransientError
from pdlc.hosts.lib import process
from pdlc.internal import trace
from _support import FileBackendTest


class ConsoleDebugTest(unittest.TestCase):
    def setUp(self) -> None:
        process.reset_run_state()
        trace.set_console_debug(True)
        self.addCleanup(process.reset_run_state)
        self.addCleanup(trace.set_console_debug, False)

    def test_debug_uses_the_same_subprocess_call_and_captured_output(self) -> None:
        output = io.StringIO()
        completed = subprocess.CompletedProcess([], 0, b"json result", b"child detail")
        with redirect_stderr(output), mock.patch.object(process.shutil, "which", return_value="/usr/bin/gh"), mock.patch.object(process.subprocess, "run", return_value=completed) as run:
            self.assertEqual(process.run_process(["gh", "stack", "submit", "--auto"]), "json result")
        self.assertTrue(run.call_args.kwargs["capture_output"])
        self.assertEqual(run.call_count, 1)
        self.assertIn("starting gh stack submit", output.getvalue())
        self.assertIn("gh stack submit exited 0 after", output.getvalue())
        self.assertNotIn("json result", output.getvalue())
        self.assertNotIn("child detail", output.getvalue())

    def test_timeout_preserves_transient_error_and_logs_elapsed_time(self) -> None:
        output = io.StringIO()
        with redirect_stderr(output), mock.patch.object(process.shutil, "which", return_value="/usr/bin/gh"), mock.patch.object(process.subprocess, "run", side_effect=subprocess.TimeoutExpired("gh", 120)) as run:
            with self.assertRaises(TransientError) as caught:
                process.run_process(["gh", "stack", "submit", "--auto"], single_request=False)
        self.assertEqual(run.call_count, 1)
        self.assertIn("gh stack submit timed out after", output.getvalue())
        self.assertIn("gh timed out after 120s", str(caught.exception))


class CommandProgressTest(FileBackendTest):
    def setUp(self) -> None:
        super().setUp()
        trace.set_console_debug(True)
        self.addCleanup(trace.set_console_debug, False)

    def test_inspect_reports_snapshot_and_pr_reads_without_changing_output(self) -> None:
        self.seed_record(70, "Product", "Pending")

        result = self.invoke("inspect", 70)

        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("loading work item '70', tasks, and comments", result.stderr)
        self.assertIn("loading 0 registered PR(s) for work item '70'", result.stderr)
        self.assertIn("# Due Next", result.stdout)
        self.assertNotIn("DEBUG pdlc", result.stdout)

    def test_post_reports_task_read_and_pr_registration_without_changing_json(self) -> None:
        self.seed_record(70, "Implementation", "Pending")
        self.seed_task(70, 701, "TASK-001", "OPEN", "WORK-70-TASK-001 [CORE] Core")

        result = self.invoke("post_attach_pr", 701, 12)

        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("loading 1 delivery task(s)", result.stderr)
        self.assertIn("registering PR #12 on work item '701'", result.stderr)
        self.assertEqual(result.json, {"task": 701, "prs": [12]})


if __name__ == "__main__":
    unittest.main()

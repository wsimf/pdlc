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


if __name__ == "__main__":
    unittest.main()

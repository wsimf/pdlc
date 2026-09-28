"""Per-command console diagnostics preserve host output and timeout behavior."""

from __future__ import annotations

import io
import sys
import threading
import unittest
from contextlib import redirect_stderr

from pdlc.domain.lifecycle import TransientError
from pdlc.hosts.lib import process
from pdlc.internal import trace


class _SignallingStderr(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.progress = threading.Event()

    def write(self, value: str) -> int:
        written = super().write(value)
        if "child progress" in self.getvalue():
            self.progress.set()
        return written


class ConsoleDebugTest(unittest.TestCase):
    def setUp(self) -> None:
        process.reset_run_state()
        trace.set_console_debug(True)
        self.addCleanup(process.reset_run_state)
        self.addCleanup(trace.set_console_debug, False)

    def test_child_stderr_is_visible_before_exit_without_polluting_stdout(self) -> None:
        output = _SignallingStderr()
        result: list[str] = []
        program = "import sys,time; print('child progress', file=sys.stderr, flush=True); time.sleep(0.6); print('json result')"
        with redirect_stderr(output):
            worker = threading.Thread(target=lambda: result.append(process.run_process([sys.executable, "-c", program])))
            worker.start()
            self.assertTrue(output.progress.wait(2), output.getvalue())
            self.assertTrue(worker.is_alive())
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result, ["json result\n"])
        self.assertIn("exited 0 after", output.getvalue())

    def test_timeout_shows_partial_stderr_and_preserves_transient_error(self) -> None:
        output = io.StringIO()
        program = "import sys,time; print('child progress', file=sys.stderr, flush=True); time.sleep(1)"
        with redirect_stderr(output), self.assertRaises(TransientError) as caught:
            process.run_process([sys.executable, "-c", program], timeout=0.2)
        self.assertIn("child progress", output.getvalue())
        self.assertIn("timed out after", output.getvalue())
        self.assertIn("timed out after 0.2s", str(caught.exception))


if __name__ == "__main__":
    unittest.main()

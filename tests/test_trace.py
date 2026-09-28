"""`record_external_call` appends one line per external CLI invocation to
`~/.pdlc/debug.log` only when `PDLC_DEBUG` is truthy, and never raises."""

from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock

from pdlc.internal import trace
from pdlc.config import Config, install_config, reset_config


class RecordExternalCallTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.log = Path(directory.name) / ".pdlc" / "debug.log"
        self.enterContext(mock.patch.object(trace, "_LOG_PATH", self.log))
        trace.set_console_debug(False)
        reset_config()
        self.addCleanup(trace.set_console_debug, False)
        self.addCleanup(reset_config)

    def _enable(self, value: str = "true") -> None:
        self.enterContext(mock.patch.dict(os.environ, {"PDLC_DEBUG": value}))

    def test_disabled_writes_nothing(self) -> None:
        self._enable("false")
        trace.record_external_call("gh", ["gh", "pr", "view", "1"])
        self.assertFalse(self.log.exists())

    def test_enabled_appends_one_formatted_line_per_call(self) -> None:
        self._enable()
        trace.record_external_call("az", ["az", "boards", "work-item", "show", "--id", "5"])
        trace.record_external_call("git", ["git", "log", "--oneline"])
        lines = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[0], r"^\[.+\] - \(az\) : az boards work-item show --id 5$")
        self.assertTrue(lines[1].endswith(" - (git) : git log --oneline"))

    def test_write_failure_is_swallowed(self) -> None:
        self._enable("1")
        with mock.patch.object(type(self.log), "mkdir", side_effect=OSError("boom")):
            trace.record_external_call("git", ["git", "status"])  # must not raise

    def test_file_debug_and_console_debug_are_independent(self) -> None:
        install_config(Config(debug=True))
        output = StringIO()
        with redirect_stderr(output):
            trace.record_external_call("gh", ["gh", "stack", "submit", "--auto"])
        self.assertEqual(output.getvalue(), "")
        self.assertIn("gh stack submit --auto", self.log.read_text(encoding="utf-8"))

        self.log.unlink()
        install_config(Config(debug=False))
        trace.set_console_debug(True)
        with redirect_stderr(output):
            trace.record_external_call("gh", ["gh", "api", "graphql", "-f", "query=private"])
        self.assertIn("starting gh api", output.getvalue())
        self.assertNotIn("query=private", output.getvalue())
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()

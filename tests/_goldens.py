"""Whole-output golden comparison shared by the golden suites.

Not named `test_*.py` on purpose: it is a mixin, not a suite. A golden suite
mixes it into its harness, points `GOLDENS` at its fixture directory, and calls
`assertGolden` with the command result it wants pinned. Regenerate every golden
after an intended edit with `PDLC_UPDATE_GOLDENS=1`, then read the diff before
committing it.
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path


class GoldenMixin(unittest.TestCase):
    GOLDENS: Path
    home: Path

    def setUp(self) -> None:
        super().setUp()
        # Evidence timestamps render in the local zone, so a golden recorded in
        # one timezone would fail everywhere else; pin the process to UTC.
        original = os.environ.get("TZ")
        os.environ["TZ"] = "UTC"
        time.tzset()
        self.addCleanup(time.tzset)
        self.addCleanup(lambda: os.environ.__setitem__("TZ", original) if original else os.environ.pop("TZ", None))

    def scrub(self, text: str) -> str:
        """Replace per-run temp paths with stable placeholders, so an output that
        names its scratch file or the record store still compares across runs."""
        for path, placeholder in ((self.home, "$PDLC_HOME"), (Path(tempfile.gettempdir()), "$TMPDIR")):
            for form in {str(path), str(path.resolve())}:
                text = text.replace(form, placeholder)
        return text

    def assertGolden(self, name: str, result, *, suffix: str = ".md") -> None:
        """Compare `result` — a command `Result`, which must have succeeded, or
        already-rendered text — against the golden `name` in full."""
        if isinstance(result, str):
            text = result
        else:
            self.assertEqual(result.code, 0, result.stderr)
            text = result.stdout
        text = self.scrub(text)
        path = self.GOLDENS / f"{name}{suffix}"
        if os.environ.get("PDLC_UPDATE_GOLDENS"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            return
        self.assertTrue(path.exists(), f"missing golden {path}; regenerate with PDLC_UPDATE_GOLDENS=1")
        self.assertEqual(text, path.read_text(encoding="utf-8"), f"output drifted from {path}")

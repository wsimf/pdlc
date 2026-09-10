"""`run_process` pins every child CLI to a UTF-8 locale, so a non-UTF-8 host
locale cannot make `az` encode an em dash as the lone CP-1252 byte 0x97 that a
UTF-8 decode then rejects — after the mutating call has already reached Azure.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

from pdlc.hosts.lib.process import run_process


class RunProcessLocaleTest(unittest.TestCase):
    def test_non_ascii_round_trips_despite_a_non_utf8_host_locale(self) -> None:
        text = "UI not required — “no” user-facing change, café"
        program = (
            "import sys; "
            f"sys.stdout.write({text!r})"
        )
        # A Latin-1 host locale would otherwise give the child a CP-1252/Latin-1
        # stdout codec; `run_process` must override it.
        host_env = {**os.environ, "LANG": "en_US.ISO8859-1", "LC_ALL": ""}
        with mock.patch.dict(os.environ, host_env, clear=True):
            out = run_process([sys.executable, "-I", "-c", program])
        self.assertEqual(out, text)

    def test_child_sees_a_utf8_locale(self) -> None:
        program = "import sys, locale; sys.stdout.write(locale.getpreferredencoding(False))"
        out = run_process([sys.executable, "-c", program])
        self.assertIn("UTF-8", out.upper())


if __name__ == "__main__":
    unittest.main()

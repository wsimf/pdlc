"""`run_process` must return usable text no matter how the child CLI encoded its
output: it pins POSIX children to a UTF-8 locale, and it still recovers a Windows
`az` response that arrives in the ANSI code page (an em dash as the lone byte
0x97, CRLF line endings) instead of aborting on the UTF-8 decode.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

from pdlc.hosts.lib.process import run_process


class RunProcessEncodingTest(unittest.TestCase):
    def test_non_ascii_round_trips_despite_a_non_utf8_host_locale(self) -> None:
        text = "UI not required — “no” user-facing change, café"
        host_env = {**os.environ, "LANG": "en_US.ISO8859-1", "LC_ALL": ""}
        with mock.patch.dict(os.environ, host_env, clear=True):
            out = run_process([sys.executable, "-I", "-c", f"import sys; sys.stdout.write({text!r})"])
        self.assertEqual(out, text)

    def test_recovers_cp1252_bytes_the_child_wrote_raw(self) -> None:
        program = r"import sys; sys.stdout.buffer.write('a — b\r\nc\r\n'.encode('cp1252'))"
        out = run_process([sys.executable, "-c", program])
        self.assertEqual(out, "a — b\nc\n")

    def test_undefined_bytes_do_not_abort(self) -> None:
        program = r"import sys; sys.stdout.buffer.write(b'ok \x81 end')"
        self.assertIn("ok", run_process([sys.executable, "-c", program]))


if __name__ == "__main__":
    unittest.main()

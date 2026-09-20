"""Scratch files carry briefs a sub-agent executes, so the write must not be
divertible by anything that got to the path first."""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pdlc.internal.scratch import scratch_path, write_scratch


class ScratchPathTest(unittest.TestCase):
    def test_names_the_file_for_the_backing_store(self) -> None:
        with mock.patch("pdlc.internal.scratch.ref_label", return_value="pdlc"):
            self.assertEqual(scratch_path("prompt-42").name, "pdlc-prompt-42.md")

    def test_suffix_is_selectable(self) -> None:
        with mock.patch("pdlc.internal.scratch.ref_label", return_value="pdlc"):
            self.assertEqual(scratch_path("verify-42", ".json").name, "pdlc-verify-42.json")

    def test_lands_in_the_temp_directory(self) -> None:
        with mock.patch("pdlc.internal.scratch.ref_label", return_value="pdlc"):
            self.assertEqual(scratch_path("42").parent, Path(tempfile.gettempdir()))


class WriteScratchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.path = self.directory / "brief.md"

    def test_writes_the_text_and_returns_the_path(self) -> None:
        self.assertEqual(write_scratch(self.path, "brief\n"), self.path)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "brief\n")

    def test_readable_only_by_its_owner(self) -> None:
        write_scratch(self.path, "secret\n")
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_replaces_a_previous_run_rather_than_appending(self) -> None:
        write_scratch(self.path, "first run\n")
        write_scratch(self.path, "second\n")
        self.assertEqual(self.path.read_text(encoding="utf-8"), "second\n")

    def test_a_loose_permissive_file_does_not_survive_the_rewrite(self) -> None:
        self.path.write_text("stale\n", encoding="utf-8")
        os.chmod(self.path, 0o666)
        write_scratch(self.path, "fresh\n")
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_a_symlink_planted_at_the_path_is_not_followed(self) -> None:
        target = self.directory / "authorized_keys"
        target.write_text("original\n", encoding="utf-8")
        self.path.symlink_to(target)

        write_scratch(self.path, "injected\n")

        self.assertEqual(target.read_text(encoding="utf-8"), "original\n")
        self.assertFalse(self.path.is_symlink())
        self.assertEqual(self.path.read_text(encoding="utf-8"), "injected\n")


if __name__ == "__main__":
    unittest.main()

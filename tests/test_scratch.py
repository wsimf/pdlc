"""Generated CLI files stay in the configured cache and have private names."""

from __future__ import annotations

import os
import re
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pdlc.config import Config, install_config, reset_config
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.scratch import scratch_path, write_scratch
from pdlc.hosts.lib.azure.transport import _request_file
from pdlc.hosts.lib.github.transport import body_file

POSIX_ONLY = unittest.skipUnless(os.name == "posix", "POSIX file modes")


class ScratchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        install_config(Config(cache_root=str(self.root)))
        self.addCleanup(reset_config)
        self.label = mock.patch("pdlc.internal.scratch.ref_label", return_value="pdlc")
        self.label.start()
        self.addCleanup(self.label.stop)

    def test_custom_root_keeps_each_work_item_in_its_own_directory(self) -> None:
        path = scratch_path("42", "prompt-42")
        self.assertEqual(path.parent, self.root / ".pdlc" / "cache" / "42")
        self.assertRegex(path.name, r"^pdlc-prompt-42-[0-9a-f]{6}\.md$")

    def test_repository_default_uses_repository_root(self) -> None:
        install_config(Config())
        with mock.patch("pdlc.internal.scratch.project_root", return_value=self.root):
            self.assertEqual(scratch_path("42", "42").parent, self.root / ".pdlc" / "cache" / "42")

    def test_global_default_uses_home(self) -> None:
        install_config(Config(cache_root="global_default"))
        with mock.patch("pdlc.internal.scratch.Path.home", return_value=self.root):
            self.assertEqual(scratch_path("42", "42").parent, self.root / ".pdlc" / "cache" / "42")

    def test_relative_custom_root_is_relative_to_repository(self) -> None:
        install_config(Config(cache_root="artifacts"))
        with mock.patch("pdlc.internal.scratch.project_root", return_value=self.root):
            self.assertEqual(scratch_path("42", "42").parent, self.root / "artifacts" / ".pdlc" / "cache" / "42")

    def test_each_file_has_a_fresh_random_suffix_and_requested_type(self) -> None:
        first = scratch_path("42", "verify-42", ".json")
        second = scratch_path("42", "verify-42", ".json")
        self.assertNotEqual(first, second)
        self.assertTrue(re.fullmatch(r"pdlc-verify-42-[0-9a-f]{6}\.json", first.name))

    def test_rejects_path_traversal_in_item_and_name(self) -> None:
        escapes = ("../evil", "..\\evil", "nested/evil", "nested\\evil", "C:evil", "brief:stream", "..", ".", "")
        for value in escapes:
            with self.subTest(value=value), self.assertRaises(PdlcError):
                scratch_path(value, "brief")
            with self.subTest(name=value), self.assertRaises(PdlcError):
                scratch_path("42", value)

    def test_writes_into_created_directory(self) -> None:
        path = scratch_path("42", "brief")
        self.assertEqual(write_scratch(path, "brief\n"), path)
        self.assertEqual(path.read_text(encoding="utf-8"), "brief\n")

    @POSIX_ONLY
    def test_directory_and_file_are_owner_only(self) -> None:
        path = scratch_path("42", "brief")
        write_scratch(path, "secret\n")
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_existing_file_is_not_overwritten(self) -> None:
        path = scratch_path("42", "brief")
        write_scratch(path, "original\n")
        with self.assertRaises(FileExistsError):
            write_scratch(path, "replacement\n")
        self.assertEqual(path.read_text(encoding="utf-8"), "original\n")

    @POSIX_ONLY
    def test_symlink_file_is_not_followed(self) -> None:
        path = scratch_path("42", "brief")
        path.parent.mkdir(parents=True)
        target = self.root / "target"
        target.write_text("original\n")
        path.symlink_to(target)
        with self.assertRaises(FileExistsError):
            write_scratch(path, "replacement\n")
        self.assertEqual(target.read_text(), "original\n")

    @POSIX_ONLY
    def test_symlink_work_item_directory_is_refused(self) -> None:
        path = scratch_path("42", "brief")
        path.parent.parent.mkdir(parents=True)
        path.parent.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(PdlcError):
            write_scratch(path, "brief\n")

    def test_github_request_body_uses_cache_and_is_removed(self) -> None:
        with body_file("body\n") as name:
            path = Path(name)
            self.assertEqual(path.parent, self.root / ".pdlc" / "cache" / "unscoped")
            self.assertEqual(path.read_text(), "body\n")
        self.assertFalse(path.exists())

    def test_azure_request_body_uses_cache_and_is_removed(self) -> None:
        with _request_file({"value": 42}) as name:
            path = Path(name)
            self.assertEqual(path.parent, self.root / ".pdlc" / "cache" / "unscoped")
            self.assertEqual(path.read_text(), '{"value": 42}')
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()

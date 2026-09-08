"""Local attachment handling: `pdlc post *` stores files under
`$PDLC_HOME/<n>/attachments/`, never writes their metadata to the record, the
inspectors render them, and a malformed manifest fails cleanly."""

import json

from _support import FileBackendTest


class PostWriteAttachmentTests(FileBackendTest):
    def test_attachments_are_stored_locally_and_kept_off_the_record(self):
        draft = self.write_file(
            "product.md",
            "## Product\nShips.\n\n### 4. Functional requirements\n- FR-1: lands.\n\n"
            "### 5. Constraints\n- C-1: x.\n\n## Decisions\n- d\n\n## Open Questions\n- none\n",
        )
        mockup = self.write_file("navigation.png", "navigation mockup bytes\n")
        unlabelled = self.write_file("empty-state.png", "empty state mockup bytes\n")

        created = self.invoke(
            "post_write", "--title", "Shell", "--slug", "shell",
            "--evidence", self.evidence_file(), "--body", draft,
            "--attachment", mockup, "--attachment-description", "Primary navigation mockup",
            "--attachment", unlabelled,
        )
        self.assertEqual(created.code, 0, created.stderr)
        issue = created.json["work_item_number"]
        self.assertEqual(len(created.json["attachments"]), 2)
        self.assertEqual(created.json["attachments"][0]["description"], "Primary navigation mockup")

        manifest = self.home / str(issue) / "attachments" / "files.json"
        self.assertTrue(manifest.is_file())
        self.assertIn("Primary navigation mockup", manifest.read_text())
        # Never leaked into the durable record.
        self.assertNotIn("Primary navigation mockup", self.body(issue))
        self.assertNotIn("Primary navigation mockup", self.comments_text(issue))

        inspected = self.invoke("inspect", issue).stdout
        self.assertIn("## Attachments", inspected)
        self.assertIn("Primary navigation mockup", inspected)

    def test_dry_run_task_authoring_never_creates_attachment_storage(self):
        self.seed_record(32, "UI", "Pending")
        ok = self.write_file("ui.md", "## UI\n\nUJ-1 covers the first run.\n")
        mockup = self.write_file("m.png", "bytes\n")
        result = self.invoke("post_tasks", "--work-item", 32, "--stage", "UI",
                             "--body", ok, "--dry-run", "--attachment", mockup)
        self.assertEqual(result.json["journeys"], ["UJ-1"])
        self.assertFalse((self.home / "32" / "attachments").exists())

    def test_malformed_attachment_metadata_fails_cleanly(self):
        from pdlc.hosts.lib.file.attachment_host import FileAttachmentHost

        directory = self.home / "1" / "attachments"
        directory.mkdir(parents=True)
        (directory / "files.json").write_text(json.dumps({"version": 1, "files": [None]}))
        with self.assertRaises(Exception) as caught:
            FileAttachmentHost().list_for("1")
        self.assertIn("entry 1 is not an object", str(caught.exception))

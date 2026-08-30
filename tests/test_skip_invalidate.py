"""`pdlc post skip`, `pdlc post invalidate`, and the skip cascade `pdlc next`
applies when a declared stage arrives."""

from _support import FileBackendTest


class SkipInvalidateTests(FileBackendTest):
    def test_skip_records_the_state_and_invalidate_returns_to_stale(self):
        self.seed_record(60, "Product", "Approval Required")
        self.assertEqual(
            self.invoke("post_skip", "--work-item", 60, "--state", "Testing",
                        "--justification", "service only").code,
            0,
        )
        self.assertEqual(self.fields(60)["Skipped States"], "Testing")

        self.assertEqual(self.invoke("post_invalidate", 60, "Product", self.evidence_file()).code, 0)
        self.assertEqual(self.fields(60)["Gate State"], "Stale")
        self.assertIn(
            "Invalidated stage: Product",
            self.invoke("inspect_timeline", 60, "--full").stdout,
        )

    def test_invalidate_refuses_a_locked_complete_record(self):
        self.seed_record(61, "Complete", "Approved")
        result = self.invoke("post_invalidate", 61, "Verification", self.evidence_file())
        self.assertEqual(result.code, 1)
        self.assertIn("Complete and locked", result.stderr)

    def test_invalidate_cannot_target_a_downstream_stage(self):
        self.seed_record(62, "Tasks", "Pending")
        result = self.invoke("post_invalidate", 62, "Implementation", self.evidence_file())
        self.assertEqual(result.code, 1)
        self.assertIn("downstream of the active stage", result.stderr)

    def test_next_cascades_past_a_declared_skip(self):
        self.seed_record(63, "Technical Plan", "Pending", skipped="Technical Plan")
        result = self.next("--work-item", 63)
        self.assertEqual(result.front_matter("action"), "pdlc-implement")
        self.assertEqual(self.fields(63)["Status"], "Implementation")
        self.assertIn("PDLC-SKIPPED", self.comments_text(63))

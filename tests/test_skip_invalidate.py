"""`pdlc post skip`, `pdlc post invalidate`, and the skip cascade `pdlc next`
applies when a declared stage arrives."""

import json

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

    def test_invalidate_to_technical_plan_reopens_every_closed_task_by_default(self):
        self.seed_record(64, "Implementation", "Pending")
        self.seed_task(64, 641, "TASK-001", "CLOSED", "WORK-64-TASK-001 [CORE] one")
        self.seed_task(64, 642, "TASK-002", "OPEN", "WORK-64-TASK-002 [CORE] two")
        result = self.invoke("post_invalidate", 64, "Technical Plan", self.evidence_file())
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(self.task_meta(64, 641)["state"], "OPEN")
        self.assertEqual(self.task_meta(64, 642)["state"], "OPEN")
        self.assertIn("Invalidated stage: Technical Plan", self.task_comments_text(64, 641))

    def test_invalidate_task_flag_narrows_reopening_to_named_tasks(self):
        self.seed_record(65, "Implementation", "Pending")
        self.seed_task(65, 651, "TASK-001", "CLOSED", "WORK-65-TASK-001 [CORE] one")
        self.seed_task(65, 652, "TASK-002", "CLOSED", "WORK-65-TASK-002 [CORE] two")
        result = self.invoke(
            "post_invalidate", 65, "Technical Plan", self.evidence_file(), "--task", 651,
        )
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(self.task_meta(65, 651)["state"], "OPEN")
        self.assertEqual(self.task_meta(65, 652)["state"], "CLOSED")

    def test_invalidate_task_flag_rejects_an_unknown_task(self):
        self.seed_record(66, "Implementation", "Pending")
        self.seed_task(66, 661, "TASK-001", "CLOSED", "WORK-66-TASK-001 [CORE] one")
        result = self.invoke(
            "post_invalidate", 66, "Technical Plan", self.evidence_file(), "--task", 999,
        )
        self.assertEqual(result.code, 1)
        self.assertIn("unknown delivery task", result.stderr)
        self.assertEqual(self.task_meta(66, 661)["state"], "CLOSED")

    def test_invalidate_task_flag_rejected_for_a_non_task_scoped_stage(self):
        self.seed_record(67, "Implementation", "Pending")
        self.seed_task(67, 671, "TASK-001", "CLOSED", "WORK-67-TASK-001 [CORE] one")
        result = self.invoke(
            "post_invalidate", 67, "Tasks", self.evidence_file(), "--task", 671,
        )
        self.assertEqual(result.code, 1)
        self.assertIn("--task only applies", result.stderr)
        self.assertEqual(self.task_meta(67, 671)["state"], "CLOSED")

    def test_invalidate_clears_reopened_task_implementation_evidence(self):
        self.seed_record(68, "Implementation", "Pending")
        self.seed_task(68, 681, "TASK-001", "CLOSED", "WORK-68-TASK-001 [CORE] one")
        self.seed_implementation_comment(68, 681, "Shipped the endpoint.")

        before = self.invoke("inspect_task", 681).stdout
        self.assertIn("hasImplementation: true", before)

        result = self.invoke("post_invalidate", 68, "Technical Plan", self.evidence_file())
        self.assertEqual(result.code, 0, result.stderr)

        after = self.invoke("inspect_task", 681).stdout
        self.assertIn("hasImplementation: false", after)
        self.assertIn("needsPlan: true", after)

        comment = json.loads(self.task_comments_text(68, 681).splitlines()[0])
        self.assertTrue(comment["body"].startswith("Invalidated stage: Technical Plan"))
        self.assertIn("Shipped the endpoint.", comment["body"])

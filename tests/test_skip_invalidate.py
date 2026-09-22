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
        self.assertEqual(
            json.loads(self.comments_text(63))["body"],
            "PDLC-SKIPPED\n\nTechnical Plan skipped (declared in Skipped States).\n",
        )

    def test_next_heals_a_stray_approved_gate_on_an_active_stage(self):
        self.seed_record(76, "Technical Plan", "Approved")
        self.seed_publication(76, "Technical Plan")
        result = self.next("--work-item", 76)
        self.assertEqual(result.front_matter("action"), "pdlc-implement")
        self.assertEqual(self.fields(76)["Status"], "Implementation")
        self.assertEqual(self.fields(76)["Gate State"], "Pending")
        self.assertIn("PDLC-APPROVED", self.comments_text(76))

    def test_next_heals_a_stray_approved_gate_at_the_completion_boundary_without_completing(self):
        # A bare record `pdlc post complete` would refuse must not reach
        # Complete through the heal either.
        self.seed_record(77, "Verification", "Approved")
        result = self.next("--work-item", 77)
        self.assertEqual(result.front_matter("action"), "human-approval")
        self.assertEqual(self.fields(77)["Status"], "Verification")
        self.assertEqual(self.fields(77)["Gate State"], "Approval Required")
        text = self.comments_text(77)
        self.assertIn("Verification.Approved was found directly", text)
        self.assertNotIn("PDLC-APPROVED", text)

    def test_continue_heals_a_stray_approved_gate_at_the_completion_boundary_without_completing(self):
        self.seed_record(81, "Verification", "Approved")
        result = self.invoke("continue_", 81)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["to"], "Verification.ApprovalRequired")
        self.assertEqual(self.fields(81)["Status"], "Verification")
        self.assertNotIn("PDLC-APPROVED", self.comments_text(81))

    def test_next_heals_ci_pending_on_a_stage_that_is_not_ci_gated(self):
        self.seed_record(78, "UI", "CI Pending")
        result = self.next("--work-item", 78)
        self.assertEqual(result.front_matter("action"), "human-approval")
        self.assertEqual(self.fields(78)["Status"], "UI")
        self.assertEqual(self.fields(78)["Gate State"], "Approval Required")
        text = self.comments_text(78)
        self.assertIn("CIPending", text)
        self.assertNotIn("PDLC-APPROVED", text)

    def test_continue_heals_a_stray_approved_gate(self):
        self.seed_record(79, "Technical Plan", "Approved")
        self.seed_publication(79, "Technical Plan")
        result = self.invoke("continue_", 79)
        self.assertEqual(result.code, 0, result.stderr)
        body = json.loads(result.stdout)
        self.assertEqual(body, {
            "healed": True, "work_item": 79,
            "from": "TechnicalPlan.Approved", "to": "Implementation.Pending",
        })
        self.assertEqual(self.fields(79)["Status"], "Implementation")
        self.assertEqual(self.fields(79)["Gate State"], "Pending")

    def test_continue_refuses_a_state_with_nothing_to_heal(self):
        self.seed_record(80, "Technical Plan", "Pending")
        result = self.invoke("continue_", 80)
        self.assertEqual(result.code, 1)
        self.assertIn("not a self-healable state", result.stderr)
        self.assertEqual(self.fields(80)["Gate State"], "Pending")

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
        self.register_prs(681, [900])

        before = self.invoke("inspect_task", 681).stdout
        self.assertIn("hasImplementation: true", before)
        self.assertIn("implementationInvalidated: false", before)

        result = self.invoke("post_invalidate", 68, "Technical Plan", self.evidence_file())
        self.assertEqual(result.code, 0, result.stderr)

        after = self.invoke("inspect_task", 681).stdout
        # `hasImplementation` tracks the attached PR, which invalidation never
        # touches; the comment deletion instead flips `implementationInvalidated`.
        self.assertIn("hasImplementation: true", after)
        self.assertIn("implementationInvalidated: true", after)
        self.assertIn("needsPlan: true", after)

        remaining = [json.loads(line) for line in self.task_comments_text(68, 681).splitlines()]
        self.assertEqual(len(remaining), 1)
        self.assertIn("Invalidated stage: Technical Plan", remaining[0]["body"])
        self.assertNotIn("Shipped the endpoint.", remaining[0]["body"])

    def test_invalidate_to_technical_plan_also_deletes_the_plan_comment(self):
        self.seed_record(72, "Implementation", "Pending")
        self.seed_task(72, 721, "TASK-001", "CLOSED", "WORK-72-TASK-001 [CORE] one")
        self.seed_plan_comment(72, 721, "Add the validation helper.")
        self.seed_implementation_comment(72, 721, "Shipped the endpoint.")
        self.register_prs(721, [900])

        result = self.invoke("post_invalidate", 72, "Technical Plan", self.evidence_file())
        self.assertEqual(result.code, 0, result.stderr)

        after = self.invoke("inspect_task", 721).stdout
        self.assertIn("hasPlan: false", after)
        self.assertIn("hasImplementation: true", after)
        self.assertIn("implementationInvalidated: true", after)

        remaining = [json.loads(line) for line in self.task_comments_text(72, 721).splitlines()]
        self.assertEqual(len(remaining), 1)
        self.assertNotIn("Add the validation helper.", self.task_comments_text(72, 721))
        self.assertNotIn("Shipped the endpoint.", self.task_comments_text(72, 721))

    def test_invalidate_to_implementation_keeps_the_plan_comment(self):
        self.seed_record(73, "Testing", "Pending")
        self.seed_task(73, 731, "TASK-001", "CLOSED", "WORK-73-TASK-001 [CORE] one")
        self.seed_plan_comment(73, 731, "Add the validation helper.")
        self.seed_implementation_comment(73, 731, "Shipped the endpoint.")
        self.register_prs(731, [900])

        result = self.invoke("post_invalidate", 73, "Implementation", self.evidence_file())
        self.assertEqual(result.code, 0, result.stderr)

        after = self.invoke("inspect_task", 731).stdout
        self.assertIn("hasPlan: true", after)
        self.assertIn("hasImplementation: true", after)
        self.assertIn("implementationInvalidated: true", after)
        self.assertIn("Add the validation helper.", self.task_comments_text(73, 731))
        self.assertNotIn("Shipped the endpoint.", self.task_comments_text(73, 731))

    def test_invalidate_clears_every_implementation_comment_not_just_the_latest(self):
        self.seed_record(74, "Implementation", "Pending")
        self.seed_task(74, 741, "TASK-001", "CLOSED", "WORK-74-TASK-001 [CORE] one")
        self.seed_implementation_comment(74, 741, "First attempt.")
        self.seed_implementation_comment(74, 741, "Reworked attempt.")
        self.register_prs(741, [900])

        result = self.invoke("post_invalidate", 74, "Technical Plan", self.evidence_file())
        self.assertEqual(result.code, 0, result.stderr)

        after = self.invoke("inspect_task", 741).stdout
        self.assertIn("implementationInvalidated: true", after)
        self.assertIn("needsPlan: true", after)
        text = self.task_comments_text(74, 741)
        self.assertNotIn("First attempt.", text)
        self.assertNotIn("Reworked attempt.", text)

    def test_needs_plan_tracks_plan_comment_regardless_of_implementation(self):
        self.seed_record(75, "Implementation", "Pending")
        self.seed_task(75, 751, "TASK-001", "OPEN", "WORK-75-TASK-001 [CORE] one")
        self.seed_implementation_comment(75, 751, "Shipped the endpoint.")
        self.register_prs(751, [900])

        before = self.invoke("inspect_task", 751).stdout
        self.assertIn("hasPlan: false", before)
        self.assertIn("needsPlan: true", before)
        self.assertIn("hasImplementation: true", before)
        self.assertIn("implementationInvalidated: false", before)

        self.seed_plan_comment(75, 751, "Add the validation helper.")
        after = self.invoke("inspect_task", 751).stdout
        self.assertIn("hasPlan: true", after)
        self.assertIn("needsPlan: false", after)

    def test_task_timeline_shows_plan_and_implementation_before_invalidation(self):
        self.seed_record(69, "Implementation", "Pending")
        self.seed_task(69, 691, "TASK-001", "OPEN", "WORK-69-TASK-001 [CORE] one")
        self.seed_implementation_comment(69, 691, "Shipped the endpoint.")

        full = self.invoke("inspect_task_timeline", 691, "--full")
        self.assertEqual(full.code, 0, full.stderr)
        self.assertIn("## IMPLEMENTATION", full.stdout)
        self.assertIn("Shipped the endpoint.", full.stdout)

        compact = self.invoke("inspect_task_timeline", 691)
        self.assertEqual(compact.code, 0, compact.stderr)
        self.assertIn("## IMPLEMENTATION", compact.stdout)

    def test_task_timeline_shows_invalidation_after_reopen_with_no_evidence_left_dangling(self):
        self.seed_record(70, "Implementation", "Pending")
        self.seed_task(70, 701, "TASK-001", "CLOSED", "WORK-70-TASK-001 [CORE] one")
        self.seed_implementation_comment(70, 701, "Shipped the endpoint.")

        result = self.invoke("post_invalidate", 70, "Technical Plan", self.evidence_file())
        self.assertEqual(result.code, 0, result.stderr)

        full = self.invoke("inspect_task_timeline", 701, "--full")
        self.assertEqual(full.code, 0, full.stderr)
        self.assertNotIn("## IMPLEMENTATION", full.stdout)
        self.assertNotIn("Shipped the endpoint.", full.stdout)
        self.assertEqual(full.stdout.count("## INVALIDATED"), 1)
        self.assertIn("Reopened for rework.", full.stdout)

    def test_task_timeline_reports_no_evidence(self):
        self.seed_record(71, "Implementation", "Pending")
        self.seed_task(71, 711, "TASK-001", "OPEN", "WORK-71-TASK-001 [CORE] one")
        result = self.invoke("inspect_task_timeline", 711, "--full")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("No task evidence comments found", result.stdout)

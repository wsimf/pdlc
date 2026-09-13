"""Review outcomes and the CI-pending gate: decision-required routing, the
CI reconciliation a clean Implementation review triggers, and churn-gated
autonomous approval past the Implementation and Testing gates."""

import json

from _support import FileBackendTest

DECISION_EVIDENCE = (
    "## Decision Required\n\nQuestion: snap geometry on-device or server-side?\n"
    "Options: A/B.\nRecommendation: A.\nBlocks: TASK-001.\n"
)


class ReviewOutcomeTests(FileBackendTest):
    def test_decision_required_needs_a_decision_section(self):
        self.seed_record(25, "Implementation", "Review Required")
        bad = self.write_file("no-heading.md", "Findings: approach is ambiguous.\n")
        result = self.invoke("post_review", 25, "decision-required", bad)
        self.assertEqual(result.code, 1)
        self.assertIn("must include a '## Decision Required' section", result.stderr)

    def test_decision_required_parks_the_record_and_halts_the_loop(self):
        self.seed_record(25, "Implementation", "Review Required")
        decision = self.write_file("decision.md", DECISION_EVIDENCE)
        result = self.invoke("post_review", 25, "decision-required", decision)
        self.assertEqual(result.json["gateState"], "Decision Required")
        self.assertEqual(self.fields(25)["Gate State"], "Decision Required")
        self.assertIn("PDLC-DECISION", self.comments_text(25))
        self.assertEqual(self.next("--work-item", 25).front_matter("action"), "human-decision")
        self.assertIn("## DECISION", self.invoke("inspect_timeline", 25, "--full").stdout)
        self.assertIn("Decision Required", self.invoke("inspect_review", 25).stdout)

    def test_decision_manifest_answers_and_defers(self):
        self.seed_record(25, "Implementation", "Review Required")
        self.invoke("post_review", 25, "decision-required",
                    self.write_file("d.md", DECISION_EVIDENCE))
        deferred_body = self.write_file(
            "deferred.md",
            "## Product\n\n### 1. Problem\nTile quota is unsettled.\n\n"
            "## Decisions\n- none yet\n\n## Open Questions\n- What is the ceiling?\n",
        )
        manifest = self.write_file(
            "decisions.json",
            json.dumps([
                {"decision": "On-device vs server-side", "answer": "On-device",
                 "rationale": "offline-first", "affects": "TASK-001"},
                {"decision": "Tile-pin quota ceiling",
                 "defer": {"title": "Tile pin quota", "slug": "tile-pin-quota", "body": deferred_body}},
            ]),
        )
        resolved = self.invoke("post_decision", 25, "--manifest", manifest)
        self.assertEqual(resolved.code, 0, resolved.stderr)
        child = resolved.json["deferred"][0]["number"]
        self.assertEqual(resolved.json["gateState"], "Changes Required")
        self.assertEqual(self.fields(25)["Gate State"], "Changes Required")
        self.assertEqual(self.state(child), ("Product", "Pending"))
        self.assertIn(f"tracked as #{child}", self.body(25))
        self.assertIn("PDLC-RESOLUTION", self.comments_text(25))
        self.assertEqual(self.next("--work-item", 25).front_matter("action"), "pdlc-implement")

    def test_decision_manifest_refuses_a_second_run(self):
        self.seed_record(25, "Implementation", "Review Required")
        self.invoke("post_review", 25, "decision-required",
                    self.write_file("d.md", DECISION_EVIDENCE))
        manifest = self.write_file("m.json", json.dumps([
            {"decision": "snap geometry on-device or server-side?", "answer": "A",
             "rationale": "z", "affects": "TASK-001"}
        ]))
        self.assertEqual(self.invoke("post_decision", 25, "--manifest", manifest).code, 0)
        result = self.invoke("post_decision", 25, "--manifest", manifest)
        self.assertEqual(result.code, 1)
        self.assertIn("requires Gate State = Decision Required", result.stderr)


class CiPendingGateTests(FileBackendTest):
    def test_clean_review_parks_at_ci_pending_while_checks_run(self):
        self.seed_record(26, "Implementation", "Review Required")
        self.green_pr(26, number=148, checks="PENDING")
        result = self.invoke("post_review", 26, "approval-required", self.evidence_file())
        self.assertEqual(result.json["gateState"], "CI Pending")
        self.assertIn("PDLC-REVIEW", self.comments_text(26))
        self.assertIn("stage: Implementation", self.comments_text(26))
        self.assertIn("verdict: Pass", self.comments_text(26))
        self.assertEqual(self.next("--work-item", 26).front_matter("action"), "none")
        self.assertIn("CI is still running", self.next("--work-item", 26).stdout)
        self.assertIn("CI Pending", self.invoke("inspect_review", 26).stdout)

    def test_green_ci_advances_to_approval_required_via_post_ci(self):
        self.seed_record(26, "Implementation", "Review Required")
        self.green_pr(26, number=148, checks="PENDING")
        self.invoke("post_review", 26, "approval-required", self.evidence_file())
        self.green_pr(26, number=148, checks="SUCCESS")
        self.assertEqual(self.next("--work-item", 26).front_matter("action"), "pdlc-post-ci")
        green = self.invoke("post_ci", 26)
        self.assertIn("## CI Passed", green.stdout)
        self.assertIn("CI passed", green.stdout)
        self.assertIn("pdlc inspect 26", green.stdout)
        self.assertEqual(self.next("--work-item", 26).front_matter("action"), "human-approval")

    def test_pending_ci_prints_retry_instruction(self):
        self.seed_record(26, "Implementation", "CI Pending")
        self.green_pr(26, number=148, checks="PENDING")
        result = self.invoke("post_ci", 26)
        self.assertIn("## CI Pending", result.stdout)
        self.assertIn("CI is still pending", result.stdout)
        self.assertIn("pdlc post ci 26", result.stdout)
        self.assertEqual(self.fields(26)["Gate State"], "CI Pending")

    def test_red_ci_at_review_time_drops_to_changes_required(self):
        self.seed_record(27, "Implementation", "Review Required")
        self.green_pr(27, number=149, checks="FAILURE")
        result = self.invoke("post_review", 27, "approval-required", self.evidence_file())
        self.assertEqual(result.json["gateState"], "Changes Required")
        self.assertIn("PDLC-REVIEW", self.comments_text(27))
        self.assertIn("Failed checks: #149 (FAILURE)", self.comments_text(27))
        self.assertEqual(self.next("--work-item", 27).front_matter("action"), "pdlc-implement")

    def test_post_ci_refuses_a_record_not_at_ci_pending(self):
        self.seed_record(27, "Implementation", "Changes Required")
        result = self.invoke("post_ci", 27)
        self.assertEqual(result.code, 1)
        self.assertIn("requires Gate State = CI Pending", result.stderr)

    def test_failed_ci_prints_inspection_instruction(self):
        self.seed_record(27, "Implementation", "CI Pending")
        self.green_pr(27, number=149, checks="FAILURE")
        result = self.invoke("post_ci", 27)
        self.assertIn("## CI Failed", result.stdout)
        self.assertIn("CI failed", result.stdout)
        self.assertIn("Failed checks: #149 (FAILURE)", result.stdout)
        self.assertIn("pdlc inspect 27", result.stdout)
        self.assertIn("PDLC-REVIEW", self.comments_text(27))
        self.assertIn("CI check has failed", self.comments_text(27))
        self.assertIn("Failed checks: #149 (FAILURE)", self.comments_text(27))
        self.assertIn("Failed checks: #149 (FAILURE)", self.invoke("inspect", 27, "--full").stdout)

    def test_no_linked_pr_advances_straight_through(self):
        self.seed_record(28, "Implementation", "Review Required")
        result = self.invoke("post_review", 28, "approval-required", self.evidence_file())
        self.assertEqual(result.json["gateState"], "Approval Required")


class ChurnGateTests(FileBackendTest):
    def test_first_pass_green_ci_stops_at_approval_required(self):
        self.seed_record(63, "Implementation", "CI Pending")
        self.green_pr(63)
        self.assertIn("## CI Passed", self.invoke("post_ci", 63).stdout)

    def test_one_loopback_green_ci_skips_the_human_step(self):
        self.seed_record(64, "Implementation", "CI Pending")
        self.green_pr(64)
        self.add_rework_review(64)
        result = self.invoke("post_ci", 64)
        self.assertIn("## CI Passed", result.stdout)
        self.assertIn("pdlc inspect 64", result.stdout)
        self.assertEqual(self.fields(64)["Status"], "Testing")
        self.assertIn("PDLC-AUTOAPPROVED", self.comments_text(64))
        self.assertEqual(self.next("--work-item", 64).front_matter("action"), "pdlc-test")

    def test_clean_testing_review_autoapproves_across_stage_bounces(self):
        self.seed_record(65, "Testing", "Review Required")
        self.add_rework_review(65)
        self.add_rework_review(65, "Testing")
        result = self.invoke("post_review", 65, "approval-required", self.evidence_file())
        self.assertEqual(result.json["gateState"], "Verification / Pending")
        self.assertTrue(result.json["autoApproved"])
        self.assertEqual(self.fields(65)["Status"], "Verification")

    def test_past_the_cap_the_gate_stops_for_the_driver_again(self):
        self.seed_record(66, "Implementation", "CI Pending")
        self.green_pr(66)
        for _ in range(4):
            self.add_rework_review(66)
        self.assertIn("## CI Passed", self.invoke("post_ci", 66).stdout)

    def test_driver_invalidation_does_not_count_as_a_rework_loop(self):
        self.seed_record(73, "Implementation", "CI Pending")
        self.green_pr(73)
        self.add_invalidation(73)
        self.assertIn("## CI Passed", self.invoke("post_ci", 73).stdout)

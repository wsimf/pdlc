"""`pdlc post verify`: the three recommendations, the autonomous upstream
bounce, and the guards on `--decision` / `--bounce` / structurally invalid
clean evidence."""

import json

from _support import FileBackendTest


def _clean_report(sha: str) -> str:
    return (
        f"### Claims Audit\n\n- FR-1 confirmed (Verified @ {sha})\n\n"
        f"### User Journeys\n\n- UJ-1 confirmed (Verified @ {sha})\n\n"
        "### UX\n\n- Reviewed — no critical findings\n\n"
        "### Cumulative Review\n\n- Clean — no findings\n"
    )


class VerificationTests(FileBackendTest):
    def test_clean_run_lands_approval_required_directly(self):
        self.seed_record(67, "Verification", "Pending")
        report = self.write_file("report.md", _clean_report(self.head_sha()))
        result = self.invoke("post_verify", 67, report, "--recommendation", "Approval Required")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(self.state(67), ("Verification", "Approval Required"))

    def test_verification_approval_is_never_auto_advanced(self):
        self.seed_record(67, "Verification", "Pending")
        self.add_invalidation(67)
        report = self.write_file("report.md", _clean_report(self.head_sha()))
        self.invoke("post_verify", 67, report, "--recommendation", "Approval Required")
        self.assertEqual(self.fields(67)["Gate State"], "Approval Required")
        self.assertEqual(self.next("--work-item", 67).front_matter("action"), "human-approval")

    def test_structurally_invalid_clean_evidence_is_refused_at_publish(self):
        self.seed_record(71, "Verification", "Pending")
        result = self.invoke("post_verify", 71, "-", "--recommendation", "Approval Required",
                             stdin="just some prose\n")
        self.assertEqual(result.code, 1)
        self.assertIn("clean verification evidence is not valid", result.stderr)
        self.assertEqual(self.fields(71)["Gate State"], "Pending")

    def test_decision_recommendation_parks_the_record(self):
        self.seed_record(90, "Verification", "Pending")
        report = self.write_file("report.md", _clean_report(self.head_sha()))
        decision = self.write_file(
            "v-decision.md",
            "## Decision Required\n\nQuestion: keep the 2m elevation drift or fix it?\n"
            "Options: keep / fix.\nRecommendation: keep.\nBlocks: completion.\n"
            "Why not mechanical: tolerance is a product call.\n",
        )
        result = self.invoke("post_verify", 90, report,
                             "--recommendation", "Decision Required", "--decision", decision)
        self.assertEqual(result.json["gateState"], "Decision Required")
        self.assertIn("PDLC-DECISION", self.comments_text(90))
        self.assertEqual(self.next("--work-item", 90).front_matter("action"), "human-decision")
        self.assertIn("parked at Decision Required", self.invoke("inspect_verify", 90).stdout)

    def test_decision_file_rejected_without_matching_recommendation(self):
        self.seed_record(90, "Verification", "Pending")
        report = self.write_file("report.md", _clean_report(self.head_sha()))
        decision = self.write_file("d.md", "## Decision Required\n\nQuestion: x?\n")
        result = self.invoke("post_verify", 90, report,
                             "--recommendation", "Approval Required", "--decision", decision)
        self.assertEqual(result.code, 1)
        self.assertIn("only valid with --recommendation 'Decision Required'", result.stderr)

    def test_bounce_returns_an_upstream_stage_to_stale(self):
        self.seed_record(69, "Verification", "Pending")
        result = self.invoke("post_verify", 69, "-", "--recommendation", "Changes Required",
                             "--bounce", "Implementation", stdin="report\n")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(self.state(69), ("Implementation", "Stale"))
        self.assertIn("Invalidated stage: Implementation", self.comments_text(69))
        self.assertIn("PDLC-VERIFICATION", self.comments_text(69))
        self.assertEqual(self.next("--work-item", 69).front_matter("action"), "pdlc-implement")

    def test_bounce_rejected_unless_changes_required(self):
        self.seed_record(70, "Verification", "Pending")
        result = self.invoke("post_verify", 70, "-", "--recommendation", "Approval Required",
                             "--bounce", "Implementation", stdin="report\n")
        self.assertEqual(result.code, 1)
        self.assertIn("bounce is only valid", result.stderr)

    def test_stdin_can_supply_only_one_input(self):
        self.seed_record(22, "Verification", "Pending")
        result = self.invoke("post_verify", 22, "-", "--recommendation", "Approval Required",
                             "--fixed", "-", stdin="report\n")
        self.assertEqual(result.code, 1)
        self.assertIn("stdin can supply only one input", result.stderr)

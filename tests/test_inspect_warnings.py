"""`pdlc inspect` flags a gate that claims more than the record's evidence shows.

The domain rule is `evidence_warnings`; `pdlc inspect` renders its sentences
under `# Warnings`, just above `# Due Next`, and only when there is one — a
record whose gate and evidence agree renders exactly as before.
"""

from __future__ import annotations

import json
import unittest

from _support import FileBackendTest
from pdlc.domain.changes import evidence_warnings
from pdlc.domain.evidence import ReviewVerdict, compose_review
from pdlc.domain.stages import Gate
from pdlc.domain.workflow import Lifecycle, State
from pdlc.domain.workflows.workflow_feature import FEATURE_PIPELINE


def _review(stage: str, verdict: ReviewVerdict) -> str:
    return "PDLC-REVIEW\n\n" + compose_review(stage, verdict, "## Findings\n\n- detail")


def _warnings(stage: str, gate: Gate, *bodies: str) -> list[str]:
    comments = [
        {"body": body, "createdAt": f"2026-04-{day:02d}T00:00:00Z", "url": f"u{day}", "author": {"login": "t"}}
        for day, body in enumerate(bodies, start=1)
    ]
    return evidence_warnings(comments, FEATURE_PIPELINE, State(stage, gate, Lifecycle.PLANNING))


class EvidenceWarningTests(unittest.TestCase):
    def test_gates_that_claim_nothing_are_never_flagged(self):
        for gate in (Gate.PENDING, Gate.CHANGES_REQUIRED, Gate.STALE, Gate.DECISION_REQUIRED):
            with self.subTest(gate=gate.value):
                self.assertEqual(_warnings("Implementation", gate), [])

    def test_approval_required_without_a_publication(self):
        self.assertEqual(_warnings("Tasks", Gate.APPROVAL_REQUIRED), [
            "Tasks is at Approval Required, but its evidence does not support approval: "
            "no PDLC-TASKS publication of Tasks is on record."
        ])
        self.assertEqual(_warnings("Tasks", Gate.APPROVAL_REQUIRED, "PDLC-TASKS\n\ntasks"), [])

    def test_review_required_needs_a_current_publication_to_review(self):
        self.assertEqual(_warnings("Testing", Gate.REVIEW_REQUIRED), [
            "Testing is at Review Required, but no PDLC-TESTING publication of Testing is on record, "
            "so there is nothing current to review."
        ])
        self.assertEqual(_warnings("Testing", Gate.REVIEW_REQUIRED, "PDLC-TESTING\n\ncoverage"), [])
        red = "PDLC-REVIEW\n\nCI failed stage: Testing\n\nFailed checks: #1 (FAILURE).\n"
        self.assertIn("CI failure", _warnings("Testing", Gate.REVIEW_REQUIRED, "PDLC-TESTING\n\ncoverage", red)[0])

    def test_ci_pending_needs_a_clean_result_of_the_latest_publication(self):
        published = "PDLC-IMPLEMENTATION\n\nshipped"
        self.assertEqual(_warnings("Implementation", Gate.CI_PENDING, published), [
            "Implementation is at CI Pending, but its evidence shows no clean result for CI to settle: "
            "no passing review of Implementation follows its latest PDLC-IMPLEMENTATION publication."
        ])
        self.assertEqual(_warnings("Implementation", Gate.CI_PENDING, published, _review("Implementation", ReviewVerdict.PASS)), [])
        self.assertEqual(_warnings("Verification", Gate.CI_PENDING, _review("Verification", ReviewVerdict.PASS)), [])
        self.assertIn("Review findings", _warnings("Verification", Gate.CI_PENDING, _review("Verification", ReviewVerdict.CHANGES_REQUIRED))[0])

    def test_ci_pending_on_a_pull_request_stage_needs_one_registered(self):
        published = ("PDLC-TESTING\n\ncoverage", _review("Testing", ReviewVerdict.PASS))
        comments = [
            {"body": body, "createdAt": f"2026-04-{day:02d}T00:00:00Z", "url": "", "author": {"login": "t"}}
            for day, body in enumerate(published, start=1)
        ]
        testing = State("Testing", Gate.CI_PENDING, Lifecycle.PLANNING)
        self.assertEqual(evidence_warnings(comments, FEATURE_PIPELINE, testing, has_pull_requests=False), [
            "Testing is at CI Pending with no registered pull request, so there is no CI to check."
        ])
        self.assertEqual(evidence_warnings(comments, FEATURE_PIPELINE, testing, has_pull_requests=True), [])
        verification = [{"body": _review("Verification", ReviewVerdict.PASS), "createdAt": "", "url": "", "author": {"login": "t"}}]
        self.assertEqual(
            evidence_warnings(verification, FEATURE_PIPELINE, State("Verification", Gate.CI_PENDING, Lifecycle.PLANNING), has_pull_requests=False),
            [],
        )

    def test_only_implementation_and_testing_publish_through_pull_requests(self):
        publishing = {stage.name for stage in FEATURE_PIPELINE.stages if stage.publishes_pull_requests}
        self.assertEqual(publishing, {"Implementation", "Testing"})

    def test_a_stray_approved_is_flagged_only_when_its_heal_would_replay_an_unsupported_approval(self):
        self.assertEqual(_warnings("Technical Plan", Gate.APPROVED), [
            "Technical Plan is at a stray Approved its evidence does not support "
            "(no PDLC-PLAN publication of Technical Plan is on record); "
            "it heals to Technical Plan / Approval Required, not the next stage."
        ])
        self.assertEqual(_warnings("Technical Plan", Gate.APPROVED, "PDLC-PLAN\n\nplanned"), [])
        # The completion boundary's heal replays no approval.
        self.assertEqual(_warnings("Verification", Gate.APPROVED), [])


class InspectWarningsSectionTests(FileBackendTest):
    def test_the_section_sits_above_due_next_in_both_renders(self):
        self.seed_record(401, "Implementation", "CI Pending")
        self.seed_publication(401, "Implementation", passed_review=False)
        for flag in ((), ("--full",)):
            with self.subTest(flag=flag):
                result = self.invoke("inspect", 401, *flag)
                self.assertEqual(result.code, 0, result.stderr)
                self.assertIn(
                    "# Warnings\n\nThe Gate State claims more than this work item's evidence shows.",
                    result.stdout,
                )
                self.assertIn("- Implementation is at CI Pending, but", result.stdout)
                self.assertLess(result.stdout.index("# Warnings"), result.stdout.index("# Due Next"))
                self.assertGreater(result.stdout.index("# Warnings"), result.stdout.index("# Tasks"))

    def test_no_section_when_the_gate_and_evidence_agree(self):
        self.seed_record(402, "Implementation", "CI Pending")
        self.seed_publication(402, "Implementation")
        self.green_pr(402)
        self.assertNotIn("# Warnings", self.invoke("inspect", 402, "--full").stdout)

    def test_ci_pending_with_no_registered_pull_request_is_flagged(self):
        self.seed_record(405, "Testing", "CI Pending")
        self.seed_publication(405, "Testing")
        result = self.invoke("inspect", 405, "--full")
        self.assertIn("- Testing is at CI Pending with no registered pull request, so there is no CI to check.", result.stdout)
        self.assertEqual(result.stdout.count("\n- Testing is at"), 1)

    def test_no_section_for_a_stage_declared_skipped(self):
        self.seed_record(403, "Verification", "Approval Required", skipped="Verification")
        result = self.invoke("inspect", 403, "--full")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertNotIn("# Warnings", result.stdout)

    def test_a_review_required_record_with_an_open_request_since_publishing_is_flagged(self):
        self.seed_record(404, "Testing", "Review Required")
        self.seed_publication(404, "Testing", passed_review=False)
        with (self.records_dir() / "404" / "comments.jsonl").open("a") as handle:
            handle.write(json.dumps({
                "body": "PDLC-INVALIDATED\n\nInvalidated stage: Testing\n\nRe-scope.",
                "createdAt": "2026-06-01T00:00:00Z", "url": "", "author": {"login": "t"},
            }) + "\n")
        result = self.invoke("inspect", 404, "--full")
        self.assertIn(
            "- Testing is at Review Required, but its latest PDLC-TESTING publication leaves "
            "1 open change request for Testing: Invalidation, so there is nothing current to review.",
            result.stdout,
        )


if __name__ == "__main__":
    unittest.main()

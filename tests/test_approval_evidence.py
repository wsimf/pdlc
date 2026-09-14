"""`pdlc post approve` approves only what the stage's evidence supports.

Approval needs the stage's latest publication on record, no change request
open since it, and — for Implementation and Testing, which are reviewed only
after they publish — a passing review of that publication. The domain rule is
`approval_gap`; the command refuses on it before posting anything.
"""

from __future__ import annotations

import json
import unittest

from _support import FileBackendTest
from pdlc.domain.changes import approval_gap
from pdlc.domain.evidence import ReviewVerdict, compose_review
from pdlc.domain.workflows.workflow_feature import FEATURE_PIPELINE


def _review(stage: str, verdict: ReviewVerdict, text: str = "- detail", **bounce: str) -> str:
    return "PDLC-REVIEW\n\n" + compose_review(stage, verdict, f"## Findings\n\n{text}", **bounce)


def _thread(*bodies: str) -> list[dict]:
    return [
        {"body": body, "createdAt": f"2026-04-{day:02d}T00:00:00Z", "url": f"u{day}", "author": {"login": "t"}}
        for day, body in enumerate(bodies, start=1)
    ]


def _gap(stage: str, *bodies: str) -> str | None:
    return approval_gap(_thread(*bodies), FEATURE_PIPELINE, stage)


class ApprovalGapTests(unittest.TestCase):
    def test_a_stage_that_never_published_has_nothing_to_approve(self):
        self.assertEqual(_gap("Tasks"), "no PDLC-TASKS publication of Tasks is on record")
        self.assertEqual(_gap("Technical Plan", "PDLC-TASKS\n\ntasks"), "no PDLC-PLAN publication of Technical Plan is on record")

    def test_a_pre_publication_review_is_settled_by_the_publication(self):
        self.assertIsNone(_gap("Tasks", _review("Tasks", ReviewVerdict.CHANGES_REQUIRED), "PDLC-TASKS\n\ntasks"))

    def test_a_request_after_the_publication_blocks_approval(self):
        gap = _gap("UI", "PDLC-UI\n\nui", "PDLC-INVALIDATED\n\nInvalidated stage: UI\n\nScope moved.")
        self.assertEqual(gap, "its latest PDLC-UI publication leaves 1 open change request for UI: Invalidation")
        self.assertIsNone(_gap("UI", "PDLC-UI\n\nui", "PDLC-INVALIDATED\n\nInvalidated stage: UI\n\nx", "PDLC-UI\n\nagain"))

    def test_another_stages_request_does_not_block_approval(self):
        self.assertIsNone(_gap("Tasks", "PDLC-TASKS\n\ntasks", "PDLC-INVALIDATED\n\nInvalidated stage: Product\n\nx"))

    def test_a_post_publication_reviewed_stage_needs_a_passing_review_of_its_latest_publication(self):
        published = "PDLC-IMPLEMENTATION\n\nshipped"
        passed = _review("Implementation", ReviewVerdict.PASS)
        missing = "no passing review of Implementation follows its latest PDLC-IMPLEMENTATION publication"
        self.assertEqual(_gap("Implementation", published), missing)
        self.assertIsNone(_gap("Implementation", published, passed))
        self.assertEqual(_gap("Implementation", published, passed, "PDLC-IMPLEMENTATION\n\nre-shipped"), missing)
        self.assertEqual(_gap("Testing", "PDLC-TESTING\n\ncoverage", _review("Implementation", ReviewVerdict.PASS)), missing.replace("Implementation", "Testing").replace("IMPLEMENTATION", "TESTING"))

    def test_a_ci_failure_or_bounce_after_a_clean_review_blocks_approval(self):
        published = ("PDLC-IMPLEMENTATION\n\nshipped", _review("Implementation", ReviewVerdict.PASS))
        red = "PDLC-REVIEW\n\nCI failed stage: Implementation\n\nFailed checks: #1 (FAILURE).\n"
        self.assertIn("CI failure", _gap("Implementation", *published, red) or "")
        bounce = _review("Verification", ReviewVerdict.CHANGES_REQUIRED, bounce="Implementation", loop="delivery-rework")
        self.assertIn("Verification bounce", _gap("Implementation", *published, bounce) or "")


class PostApproveEvidenceTests(FileBackendTest):
    def _comment(self, record: int, body: str, created: str = "2026-06-01T00:00:00Z") -> None:
        with (self.records_dir() / str(record) / "comments.jsonl").open("a") as handle:
            handle.write(json.dumps({"body": body, "createdAt": created, "url": "", "author": {"login": "t"}}) + "\n")

    def _assert_refused(self, record: int, stage: str, reason: str) -> None:
        result = self.invoke("post_approve", record, self.evidence_file())
        self.assertEqual(result.code, 1)
        self.assertIn(f"pdlc: cannot approve {stage}: {reason}", result.stderr)
        self.assertEqual(self.state(record), (stage, "Approval Required"))
        self.assertNotIn("PDLC-APPROVED", self.comments_text(record))

    def test_refuses_a_stage_with_no_publication_on_record(self):
        self.seed_record(301, "Tasks", "Approval Required")
        self._assert_refused(301, "Tasks", "no PDLC-TASKS publication of Tasks is on record")

    def test_refuses_while_a_change_request_is_open_since_the_publication(self):
        self.seed_record(302, "Technical Plan", "Approval Required")
        self.seed_publication(302, "Technical Plan")
        self._comment(302, _review("Technical Plan", ReviewVerdict.CHANGES_REQUIRED))
        self._assert_refused(302, "Technical Plan", "its latest PDLC-PLAN publication leaves 1 open change request for Technical Plan: Review findings")

    def test_refuses_an_implementation_publication_with_no_passing_review(self):
        self.seed_record(303, "Implementation", "Approval Required")
        self.seed_publication(303, "Implementation", passed_review=False)
        self._assert_refused(303, "Implementation", "no passing review of Implementation follows its latest PDLC-IMPLEMENTATION publication")

    def test_approves_a_published_stage_with_nothing_open(self):
        for number, stage, following in ((304, "UI", "Tasks"), (305, "Testing", "Verification")):
            with self.subTest(stage=stage):
                self.seed_record(number, stage, "Approval Required")
                self.seed_publication(number, stage)
                result = self.invoke("post_approve", number, self.evidence_file())
                self.assertEqual(result.code, 0, result.stderr)
                self.assertEqual(self.state(number), (following, "Pending"))
                self.assertIn("PDLC-APPROVED", self.comments_text(number))

    def test_force_approves_over_missing_evidence_and_records_the_override(self):
        self.seed_record(308, "Implementation", "Approval Required")
        self.seed_publication(308, "Implementation", passed_review=False)
        result = self.invoke("post_approve", 308, self.evidence_file(), "--force")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertTrue(result.json["forced"])
        self.assertEqual(self.state(308), ("Testing", "Pending"))
        text = self.comments_text(308)
        self.assertIn("PDLC-APPROVED", text)
        self.assertIn("Approved with --force over missing evidence: no passing review of Implementation follows its latest PDLC-IMPLEMENTATION publication.", text)

    def test_force_with_supporting_evidence_is_not_an_override(self):
        self.seed_record(309, "UI", "Approval Required")
        self.seed_publication(309, "UI")
        result = self.invoke("post_approve", 309, self.evidence_file(), "--force")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertFalse(result.json["forced"])
        self.assertNotIn("--force", self.comments_text(309))

    def test_force_does_not_bypass_the_gate_or_boundary_refusals(self):
        self.seed_record(310, "Tasks", "Pending")
        self.assertIn("approval requires Gate State = Approval Required", self.invoke("post_approve", 310, self.evidence_file(), "--force").stderr)
        self.seed_record(311, "Verification", "Approval Required")
        self.assertIn("use pdlc post complete", self.invoke("post_approve", 311, self.evidence_file(), "--force").stderr)

    def test_the_gate_and_boundary_refusals_still_come_first(self):
        self.seed_record(306, "Tasks", "Pending")
        self.assertIn("approval requires Gate State = Approval Required", self.invoke("post_approve", 306, self.evidence_file()).stderr)
        self.seed_record(307, "Verification", "Approval Required")
        self.assertIn("use pdlc post complete", self.invoke("post_approve", 307, self.evidence_file()).stderr)


if __name__ == "__main__":
    unittest.main()

"""Backend-independent domain logic: the routing table, GitHub ref
neutralization, the verification-report parser, the completion-evidence
parser, and the completion-readiness policy."""

import unittest

from pdlc.commands.post_write import product_fragments
from pdlc.domain.completion import completion_blockers
from pdlc.domain.completion_evidence import parse_completion_report, undispositioned_questions
from pdlc.domain.evidence import parse_verification_report
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.model import due_next
from pdlc.hosts.github_common import neutralize_refs

GOOD_VERIFICATION = """## Verification Run Results

### Claims Audit

- FR-1 holds (Verified @ abc123)

### User Journeys

- UJ-1 confirmed (Verified @ abc123)

### UX

- Reviewed — clean

### Ultra Review

- Clean

### Findings

None

Recommendation: Approval Required
"""

GOOD_COMPLETION = """## Shipped

Tile pinning shipped across 7 tasks, PRs #144-#153, all merged.

## Verification

clean @ abc123 — claims, journeys, UX reviewed, ultra review clean.

## Decisions

- Evict pinned tiles LRU once the regional cap is hit (TASK-004).

## Open Questions

- Should tile eviction be LRU or manual-only? — Resolved: LRU, capped per region.
- Do we cap pinned regions at five? — Deferred: revisit for the paid tier, tracked as #210.

## Limitations

- Profile migration deferred to a follow-up record.

## Skipped Stages

- None
"""

MARKERS = ["PRODUCT", "APPROVED", "UI", "APPROVED", "TASKS", "APPROVED",
           "PLAN", "APPROVED", "IMPLEMENTATION", "APPROVED", "TESTING", "APPROVED"]
CLOSED_TASK = {"state": "CLOSED", "hasImplementation": True, "number": 1, "title": "t"}
MERGED_PR = {"relation": "closes", "state": "MERGED", "checks": "SUCCESS", "number": 9}


class RoutingTableTests(unittest.TestCase):
    def test_skipped_verification_still_stops_for_a_human(self):
        due = due_next({"Status": "Verification", "Gate State": "Pending", "Skipped States": "Verification"})
        self.assertEqual(due["state"], "Verification.ApprovalRequired")
        self.assertEqual(due["action"], "human-approval")

    def test_decision_required_is_a_human_stop(self):
        due = due_next({"Status": "Implementation", "Gate State": "Decision Required", "Skipped States": ""})
        self.assertEqual(due["action"], "human-decision")
        self.assertFalse(due["autonomous"])

    def test_ci_pending_is_autonomous(self):
        due = due_next({"Status": "Implementation", "Gate State": "CI Pending", "Skipped States": ""})
        self.assertEqual(due["action"], "pdlc-post-ci")
        self.assertTrue(due["autonomous"])
        self.assertEqual(due["next_state"], "Implementation.ApprovalRequired")


class NeutralizeRefsTests(unittest.TestCase):
    def test_cases(self):
        self.assertEqual(neutralize_refs("see #148 now"), r"see \#148 now")
        self.assertEqual(neutralize_refs("#1 and #23."), r"\#1 and \#23.")
        self.assertEqual(neutralize_refs("## Heading"), "## Heading")
        self.assertEqual(neutralize_refs("hex #123abc"), "hex #123abc")
        self.assertEqual(neutralize_refs(r"already \#5"), r"already \#5")
        self.assertEqual(neutralize_refs("entity &#8212;"), "entity &#8212;")
        self.assertEqual(neutralize_refs("owner/repo#9"), "owner/repo#9")
        self.assertEqual(
            neutralize_refs("https://github.com/x/y/pull/12"),
            "https://github.com/x/y/pull/12",
        )
        self.assertEqual(
            neutralize_refs("```\ncode #5\n```\nprose #6\n"),
            "```\ncode #5\n```\nprose \\#6\n",
        )


class VerificationReportTests(unittest.TestCase):
    def test_parses_a_clean_report(self):
        report = parse_verification_report(GOOD_VERIFICATION)
        self.assertEqual(report.recommendation, "Approval Required")
        self.assertEqual(report.verified_commits, ("abc123", "abc123"))
        self.assertEqual(report.findings, ())

    def test_rejections(self):
        cases = [
            (GOOD_VERIFICATION.replace("### UX\n\n- Reviewed — clean\n\n", ""), "missing required section"),
            (GOOD_VERIFICATION.replace("- FR-1 holds (Verified @ abc123)", "- FR-1 holds"), "Verified @"),
            (GOOD_VERIFICATION.replace("Recommendation: Approval Required", "Recommendation: Ship it"),
             "recommendation must be one of"),
        ]
        for body, needle in cases:
            with self.subTest(needle=needle):
                with self.assertRaises(PdlcError) as caught:
                    parse_verification_report(body)
                self.assertIn(needle, str(caught.exception))


class CompletionEvidenceTests(unittest.TestCase):
    def test_parses_all_sections(self):
        report = parse_completion_report(GOOD_COMPLETION)
        self.assertEqual(report.verified_commit, "abc123")
        self.assertEqual(len(report.decisions), 1)
        self.assertEqual(len(report.dispositioned_questions), 2)
        self.assertEqual(report.skipped_stages, ())

    def test_rejections(self):
        cases = [
            ("just a sentence", "missing required section"),
            (GOOD_COMPLETION.replace("clean @ abc123 — ", ""), "clean @ <commit>"),
            (
                GOOD_COMPLETION.replace(
                    "- Should tile eviction be LRU or manual-only? — Resolved: LRU, capped per region.",
                    "- Should tile eviction be LRU or manual-only?",
                ),
                "not a disposition",
            ),
        ]
        for body, needle in cases:
            with self.subTest(needle=needle):
                with self.assertRaises(PdlcError) as caught:
                    parse_completion_report(body)
                self.assertIn(needle, str(caught.exception))

    def test_undispositioned_questions_matches_live_entries(self):
        report = parse_completion_report(GOOD_COMPLETION)
        live = "- Should tile eviction be LRU or manual-only?\n- What is the tile-pin quota ceiling?"
        self.assertEqual(undispositioned_questions(report, live), ["What is the tile-pin quota ceiling?"])
        self.assertEqual(undispositioned_questions(report, "- none"), [])


class CompletionBlockersTests(unittest.TestCase):
    def test_a_clean_verification_record_has_no_blockers(self):
        blockers = completion_blockers(
            status="Verification", gate="Approval Required", tasks=[CLOSED_TASK],
            pull_requests=[MERGED_PR], timeline_markers=MARKERS, skipped_states="",
            verification_body=GOOD_VERIFICATION, stale_rows=[], open_questions="- none",
        )
        self.assertEqual(blockers, [])

    def test_a_broken_record_surfaces_every_code(self):
        codes = {b.code for b in completion_blockers(
            status="Testing", gate="Pending",
            tasks=[{"state": "OPEN", "hasImplementation": False, "number": 2, "title": "x"}],
            pull_requests=[{"relation": "closes", "state": "OPEN", "checks": "FAILURE", "number": 9}],
            timeline_markers=["PRODUCT"], skipped_states="",
            verification_body=None, stale_rows=None,
            open_questions="- Should we cache tiles?",
        )}
        self.assertEqual(
            codes,
            {"status", "gate", "open-tasks", "pull-requests",
             "stage-evidence", "stage-settlement", "no-verification"},
        )

    def test_a_complete_record_short_circuits(self):
        done = completion_blockers(
            status="Complete", gate="Approved", tasks=[], pull_requests=[],
            timeline_markers=[], skipped_states="", verification_body=None,
        )
        self.assertEqual([b.code for b in done], ["already-complete"])

    def test_undispositioned_open_questions_block_completion(self):
        codes = {b.code for b in completion_blockers(
            status="Verification", gate="Approval Required", tasks=[CLOSED_TASK],
            pull_requests=[MERGED_PR], timeline_markers=MARKERS, skipped_states="",
            verification_body=GOOD_VERIFICATION, stale_rows=[],
            open_questions="- a lingering question", evidence_body=GOOD_COMPLETION,
        )}
        self.assertEqual(codes, {"open-questions"})

    def test_autoapproved_and_skipped_count_as_settlement(self):
        markers = ["PRODUCT", "APPROVED", "UI", "APPROVED", "TASKS", "APPROVED",
                   "PLAN", "APPROVED", "IMPLEMENTATION", "AUTOAPPROVED", "TESTING", "AUTOAPPROVED"]
        blockers = completion_blockers(
            status="Verification", gate="Approval Required", tasks=[CLOSED_TASK],
            pull_requests=[MERGED_PR], timeline_markers=markers, skipped_states="",
            verification_body=GOOD_VERIFICATION, stale_rows=[], open_questions="- none",
        )
        self.assertFalse(any(b.code == "stage-settlement" for b in blockers))


class ProductFragmentsTests(unittest.TestCase):
    def test_extracts_the_three_owned_sections(self, tmp=None):
        import tempfile
        from pathlib import Path

        directory = Path(tempfile.mkdtemp())
        draft = directory / "owned.md"
        draft.write_text("## Product\np\n\n## Decisions\nd\n\n## Open Questions\nq\n")
        self.assertEqual(
            product_fragments(draft),
            {"Product": "p", "Decisions": "d", "Open Questions": "q"},
        )

        draft.write_text("Intro\n\n## Product\np\n\n## Decisions\nd\n\n## Open Questions\nq\n")
        with self.assertRaises(PdlcError) as caught:
            product_fragments(draft)
        self.assertIn("only ## Product", str(caught.exception))

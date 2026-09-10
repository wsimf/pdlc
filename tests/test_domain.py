"""Backend-independent domain logic: the routing table, GitHub ref
neutralization, the verification-report parser, the completion-evidence
parser, and the completion-readiness policy."""

import unittest

from pdlc.commands.post_write import product_fragments
from pdlc.domain.completion import completion_blockers
from pdlc.domain.workflow import FEATURE_PIPELINE
from pdlc.domain.completion_evidence import parse_completion_report, undispositioned_questions
from pdlc.domain.evidence import ReviewVerdict, compose_review, parse_review, parse_verification_report
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.model import TASK_EVIDENCE_HEADINGS, due_next, review_rework_count, user_comments, user_comments_markdown, verification_evidence_comments
from pdlc.hosts.lib.github.transport import neutralize_refs

GOOD_VERIFICATION = """## Verification Run Results

### Claims Audit

- FR-1 holds (Verified @ abc123)

### User Journeys

- UJ-1 confirmed (Verified @ abc123)

### UX

- Reviewed — clean

### Cumulative Review

- Clean

### Findings

None

Recommendation: Approval Required
"""

GOOD_COMPLETION = """## Shipped

Tile pinning shipped across 7 tasks, PRs #144-#153, all merged.

## Verification

clean @ abc123 — claims, journeys, UX reviewed, cumulative review clean.

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
    def test_product_requires_interactive_human_input(self):
        due = due_next({"Status": "Product", "Gate State": "Pending", "Skipped States": ""})
        self.assertEqual(due["action"], "human-input")
        self.assertFalse(due["autonomous"])
        self.assertEqual(due["owner"], "human — invoke pdlc-write interactively")

    def test_missing_work_type_uses_feature_pipeline(self):
        due = due_next({"Status": "Implementation", "Gate State": "Pending", "Skipped States": ""})
        self.assertEqual(due["action"], "pdlc-implement")

    def test_unavailable_work_type_is_blocked(self):
        due = due_next({"workType": "bug", "Status": "Implementation", "Gate State": "Pending"})
        self.assertEqual(due["action"], "blocked")
        self.assertIn("stop here and let the user know this workflow is not supported", due["reason"])

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
        self.assertNotIn("next_state", due)


class UserCommentsTests(unittest.TestCase):
    _COMMENTS = [
        {"body": "PDLC-PRODUCT\n\nauthored", "createdAt": "2026-01-03T00:00:00Z",
         "url": "u3", "author": {"login": "bot"}},
        {"body": "can we also handle the empty state?", "createdAt": "2026-01-01T00:00:00Z",
         "url": "u1", "author": {"login": "sudara"}},
        {"body": "PDLC-UNKNOWNMARKER\n\nfuture", "createdAt": "2026-01-02T00:00:00Z",
         "url": "u2", "author": {"login": "bot"}},
        {"body": "agreed, filing a follow-up", "createdAt": "2026-01-04T00:00:00Z",
         "url": "u4", "author": {"login": "otherbot"}},
    ]

    def test_keeps_only_unmarked_comments_oldest_first(self):
        kept = user_comments(self._COMMENTS)
        self.assertEqual([c["url"] for c in kept], ["u1", "u4"])

    def test_markdown_section(self):
        out = user_comments_markdown(self._COMMENTS)
        self.assertTrue(out.startswith("## User Comments"))
        self.assertIn("### @sudara — ", out)
        self.assertIn("can we also handle the empty state?", out)
        self.assertNotIn("PDLC-", out)

    def test_markdown_none_when_all_marked(self):
        self.assertEqual(user_comments_markdown(self._COMMENTS[:1]), "## User Comments\n\nNone")

    _WITH_EVIDENCE = _COMMENTS + [
        {"body": "## Technical Plan\n\nown the seam", "createdAt": "2026-01-05T00:00:00Z",
         "url": "plan", "author": {"login": "planner"}},
        {"body": "\n## Implementation\n\nshipped it", "createdAt": "2026-01-06T00:00:00Z",
         "url": "impl", "author": {"login": "impl"}},
    ]

    def test_exclude_headings_drops_unmarked_task_evidence_comments(self):
        kept = user_comments(self._WITH_EVIDENCE, exclude_headings=TASK_EVIDENCE_HEADINGS)
        self.assertEqual([c["url"] for c in kept], ["u1", "u4"])
        out = user_comments_markdown(self._WITH_EVIDENCE, exclude_headings=TASK_EVIDENCE_HEADINGS)
        self.assertNotIn("own the seam", out)
        self.assertNotIn("shipped it", out)

    def test_exclude_headings_keeps_comments_that_only_mention_the_heading_later(self):
        comment = {"body": "looks good\n\n## Technical Plan is solid", "createdAt": "2026-01-07T00:00:00Z",
                   "url": "reply", "author": {"login": "sudara"}}
        kept = user_comments([comment], exclude_headings=TASK_EVIDENCE_HEADINGS)
        self.assertEqual([c["url"] for c in kept], ["reply"])


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
    @staticmethod
    def review_comment(
        stage: str,
        verdict: ReviewVerdict,
        body: str = "",
        *,
        bounce: str | None = None,
        loop: str | None = None,
    ) -> str:
        return f"PDLC-REVIEW\n\n{compose_review(stage, verdict, body, bounce=bounce, loop=loop)}"

    def test_review_metadata_round_trips(self):
        body = compose_review(
            "Verification",
            ReviewVerdict.CHANGES_REQUIRED,
            "## Findings\n\n- retry",
            bounce="Implementation",
            loop="delivery-rework",
        )
        self.assertTrue(body.startswith("---\nstage: Verification\n"))
        self.assertIn("\n---\n\n## Findings", body)
        review = parse_review(f"PDLC-REVIEW\n\n{body}")
        self.assertEqual(review.stage, "Verification")
        self.assertEqual(review.verdict, ReviewVerdict.CHANGES_REQUIRED)
        self.assertEqual(review.bounce, "Implementation")
        self.assertEqual(review.loop, "delivery-rework")

    def test_rework_count_requires_verification_bounce_and_matching_loop(self):
        def comment(body: str, created_at: str) -> dict:
            return {"body": body, "createdAt": created_at}

        comments = [
            comment("PDLC-INVALIDATED\n\nInvalidated stage: Implementation", "2026-01-01T00:00:00Z"),
            comment(self.review_comment("Testing", ReviewVerdict.CHANGES_REQUIRED, bounce="Implementation", loop="delivery-rework"), "2026-01-02T00:00:00Z"),
            comment(self.review_comment("Verification", ReviewVerdict.CHANGES_REQUIRED, bounce="Implementation", loop="another-loop"), "2026-01-03T00:00:00Z"),
            comment(self.review_comment("Verification", ReviewVerdict.CHANGES_REQUIRED, bounce="Implementation", loop="delivery-rework"), "2026-01-04T00:00:00Z"),
        ]
        self.assertEqual(review_rework_count(comments, "delivery-rework"), 1)

    def test_verification_evidence_uses_structured_review_stage(self):
        comments = [
            {"body": "PDLC-VERIFICATION\n\nlegacy", "createdAt": "2026-01-01T00:00:00Z"},
            {"body": self.review_comment("Implementation", ReviewVerdict.PASS), "createdAt": "2026-01-02T00:00:00Z"},
            {"body": self.review_comment("Verification", ReviewVerdict.PASS), "createdAt": "2026-01-03T00:00:00Z"},
            {
                "body": self.review_comment("Testing", ReviewVerdict.PASS, "## Findings\n\nQuoted evidence:\nstage: Verification"),
                "createdAt": "2026-01-04T00:00:00Z",
            },
        ]
        self.assertEqual(
            [comment["createdAt"] for comment in verification_evidence_comments(comments)],
            ["2026-01-03T00:00:00Z"],
        )

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
            pipeline=FEATURE_PIPELINE,
            status="Verification", gate="Approval Required", tasks=[CLOSED_TASK],
            pull_requests=[MERGED_PR], timeline_markers=MARKERS, skipped_states="",
            verification_body=GOOD_VERIFICATION, stale_rows=[], open_questions="- none",
        )
        self.assertEqual(blockers, [])

    def test_a_broken_record_surfaces_every_code(self):
        codes = {b.code for b in completion_blockers(
            pipeline=FEATURE_PIPELINE,
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
            pipeline=FEATURE_PIPELINE,
            status="Complete", gate="Approved", tasks=[], pull_requests=[],
            timeline_markers=[], skipped_states="", verification_body=None,
        )
        self.assertEqual([b.code for b in done], ["already-complete"])

    def test_undispositioned_open_questions_block_completion(self):
        codes = {b.code for b in completion_blockers(
            pipeline=FEATURE_PIPELINE,
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
            pipeline=FEATURE_PIPELINE,
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

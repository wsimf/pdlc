"""Backend-independent domain logic: the routing table, GitHub ref
neutralization, the review front matter, the completion-evidence
parser, and the completion-readiness policy."""

import unittest

from pdlc.commands.post_write import product_fragments
from pdlc.domain.completion import completion_blockers
from pdlc.domain.workflows.workflow_feature import FEATURE_PIPELINE
from pdlc.domain.stages import Gate
from pdlc.domain.workflow import Event, Lifecycle, State
from pdlc.domain.completion_evidence import parse_completion_report, undispositioned_questions
from pdlc.domain.evidence import ReviewVerdict, compose_review, parse_review
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.verification import Report, Row, render
from pdlc.domain.model import TASK_EVIDENCE_HEADINGS, due_next, review_rework_count, user_comments, user_comments_markdown, verification_evidence_comments
from pdlc.hosts.lib.github.transport import neutralize_refs

GOOD_VERIFICATION = render(Report(
    head="abc123" + "0" * 34, run_at="2026-01-01 00:00 UTC", recommendation="Approval Required",
    claims=(Row("TASK-001", "confirmed", "holds"),), journeys=(Row("UJ-1", "accepted"),),
    ux=Row("ux", "clean"), cumulative=Row("cumulative", "clean"),
))

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

    def test_only_resolution_or_invalidation_leaves_decision_required(self):
        state = State("Technical Plan", Gate.DECISION_REQUIRED, Lifecycle.PLANNING)
        for event in (Event.PUBLISHED, Event.REAUTHORED, Event.APPROVED, Event.SKIPPED):
            with self.subTest(event=event):
                with self.assertRaisesRegex(ValueError, "pdlc guide decisions"):
                    FEATURE_PIPELINE.next_state(state, event)
        resolved = FEATURE_PIPELINE.next_state(state, Event.DECISION_RESOLVED)
        self.assertEqual(resolved.gate, Gate.CHANGES_REQUIRED)
        invalidated = FEATURE_PIPELINE.next_state(state, Event.INVALIDATED, requested_target="Tasks")
        self.assertEqual((invalidated.stage, invalidated.gate), ("Tasks", Gate.STALE))

    def test_reauthor_stages_re_land_from_review_required(self):
        for stage in ("Product", "UI", "Tasks", "Technical Plan"):
            with self.subTest(stage=stage):
                state = State(stage, Gate.REVIEW_REQUIRED, Lifecycle.PLANNING)
                reset = FEATURE_PIPELINE.next_state(state, Event.REAUTHORED)
                self.assertEqual(reset.gate, Gate.STALE)
        with self.assertRaises(ValueError):
            FEATURE_PIPELINE.next_state(
                State("Implementation", Gate.REVIEW_REQUIRED, Lifecycle.PLANNING), Event.REAUTHORED,
            )

    def test_ci_pending_is_autonomous(self):
        due = due_next({"Status": "Implementation", "Gate State": "CI Pending", "Skipped States": ""})
        self.assertEqual(due["action"], "pdlc-post-ci")
        self.assertTrue(due["autonomous"])
        self.assertNotIn("next_state", due)

    def test_stray_approved_gate_reports_as_self_healable_not_blocked(self):
        due = due_next({"Status": "Technical Plan", "Gate State": "Approved", "Skipped States": ""})
        self.assertEqual(due["action"], "pdlc-continue")
        self.assertTrue(due["autonomous"])
        self.assertEqual(due["state"], "TechnicalPlan.Approved")
        self.assertIn("Implementation.Pending", due["owner"])
        self.assertIn("Implementation.Pending", due["reason"])

    def test_ci_pending_on_a_non_ci_gated_stage_reports_as_self_healable(self):
        due = due_next({"Status": "Product", "Gate State": "CI Pending", "Skipped States": ""})
        self.assertEqual(due["action"], "pdlc-continue")
        self.assertIn("Product.ApprovalRequired", due["owner"])

    def test_verification_is_ci_gated_like_implementation_and_testing(self):
        due = due_next({"Status": "Verification", "Gate State": "CI Pending", "Skipped States": ""})
        self.assertEqual(due["action"], "pdlc-post-ci")
        self.assertTrue(due["autonomous"])

    def test_verification_review_required_is_a_stray_state_that_heals(self):
        due = due_next({"Status": "Verification", "Gate State": "Review Required", "Skipped States": ""})
        self.assertEqual(due["action"], "pdlc-continue")
        self.assertIn("Verification.CIPending", due["owner"])


# The full 8 stages x 8 gates matrix, so a change to routing or self-heal
# behavior for any one combination fails a test naming exactly that cell
# rather than surfacing indirectly somewhere else. "blocked" covers both
# structurally invalid combinations with no single correct fix, and (for
# Complete) any gate other than the one valid terminal state.
_STAGES = (
    "Product", "UI", "Tasks", "Technical Plan", "Implementation",
    "Testing", "Verification", "Complete",
)
_GATES = (
    "Pending", "Review Required", "Changes Required", "Decision Required",
    "CI Pending", "Approval Required", "Approved", "Stale",
)

def _pending(stage: str) -> str:
    return f"{stage.replace(' ', '')}.Pending"


def _heal(source_notation: str, target_notation: str) -> dict:
    return {
        "action": "pdlc-continue",
        "reason": f"{source_notation} is a stray state; pdlc continue heals it to {target_notation}",
        "owner": f"pdlc continue — self-heals to {target_notation}",
    }


_APPROVAL_REQUIRED_REASON = "explicit human approval is required"
_DECISION_REQUIRED_REASON = "a reviewer raised a blocking decision that only the user can resolve"
_DECISION_REQUIRED_OWNER = "human — resolve the blocking review decision (see the last PDLC-DECISION comment)"
_REVIEW_REQUIRED_REASON = "review is due"

# (stage, gate) -> {action, reason, owner}, each exactly what `due_next()`
# reports. Every cell not listed here is expected to be blocked (checked
# generically below, not by pinning each validate_state error string).
_EXPECTED: dict[tuple[str, str], dict[str, str]] = {
    ("Product", "Pending"): {
        "action": "human-input", "owner": "human — invoke pdlc-write interactively",
        "reason": "product artifact is due; user must invoke pdlc-write interactively, and it is not possible to continue autonomously",
    },
    ("Product", "Changes Required"): {
        "action": "human-input", "owner": "human — invoke pdlc-write interactively",
        "reason": "product artifact is due; user must invoke pdlc-write interactively, and it is not possible to continue autonomously",
    },
    ("Product", "Stale"): {
        "action": "human-input", "owner": "human — invoke pdlc-write interactively",
        "reason": "product artifact is due; user must invoke pdlc-write interactively, and it is not possible to continue autonomously",
    },
    ("Product", "Review Required"): {
        "action": "human-input", "owner": "human — invoke pdlc-write interactively", "reason": _REVIEW_REQUIRED_REASON,
    },
    ("Product", "Decision Required"): {
        "action": "human-decision", "owner": _DECISION_REQUIRED_OWNER, "reason": _DECISION_REQUIRED_REASON,
    },
    ("Product", "Approval Required"): {
        "action": "human-approval", "owner": "human — pdlc post approve", "reason": _APPROVAL_REQUIRED_REASON,
    },
    ("Product", "CI Pending"): _heal("Product.CIPending", "Product.ApprovalRequired"),
    ("Product", "Approved"): _heal("Product.Approved", _pending("UI")),

    ("UI", "Pending"): {"action": "pdlc-tasks", "owner": "pdlc-tasks", "reason": "UI or task artifact is due"},
    ("UI", "Changes Required"): {"action": "pdlc-tasks", "owner": "pdlc-tasks", "reason": "UI or task artifact is due"},
    ("UI", "Stale"): {"action": "pdlc-tasks", "owner": "pdlc-tasks", "reason": "UI or task artifact is due"},
    ("UI", "Review Required"): {
        "action": "pdlc-tasks", "owner": "pdlc-tasks", "reason": _REVIEW_REQUIRED_REASON,
    },
    ("UI", "Decision Required"): {
        "action": "human-decision", "owner": _DECISION_REQUIRED_OWNER, "reason": _DECISION_REQUIRED_REASON,
    },
    ("UI", "Approval Required"): {
        "action": "human-approval", "owner": "human — pdlc post approve", "reason": _APPROVAL_REQUIRED_REASON,
    },
    ("UI", "CI Pending"): _heal("UI.CIPending", "UI.ApprovalRequired"),
    ("UI", "Approved"): _heal("UI.Approved", _pending("Tasks")),

    ("Tasks", "Pending"): {"action": "pdlc-tasks", "owner": "pdlc-tasks", "reason": "UI or task artifact is due"},
    ("Tasks", "Changes Required"): {"action": "pdlc-tasks", "owner": "pdlc-tasks", "reason": "UI or task artifact is due"},
    ("Tasks", "Stale"): {"action": "pdlc-tasks", "owner": "pdlc-tasks", "reason": "UI or task artifact is due"},
    ("Tasks", "Review Required"): {
        "action": "pdlc-tasks", "owner": "pdlc-tasks", "reason": _REVIEW_REQUIRED_REASON,
    },
    ("Tasks", "Decision Required"): {
        "action": "human-decision", "owner": _DECISION_REQUIRED_OWNER, "reason": _DECISION_REQUIRED_REASON,
    },
    ("Tasks", "Approval Required"): {
        "action": "human-approval", "owner": "human — pdlc post approve", "reason": _APPROVAL_REQUIRED_REASON,
    },
    ("Tasks", "CI Pending"): _heal("Tasks.CIPending", "Tasks.ApprovalRequired"),
    ("Tasks", "Approved"): _heal("Tasks.Approved", _pending("Technical Plan")),

    ("Technical Plan", "Pending"): {"action": "pdlc-plan", "owner": "pdlc-plan", "reason": "technical plan is due"},
    ("Technical Plan", "Changes Required"): {"action": "pdlc-plan", "owner": "pdlc-plan", "reason": "technical plan is due"},
    ("Technical Plan", "Stale"): {"action": "pdlc-plan", "owner": "pdlc-plan", "reason": "technical plan is due"},
    ("Technical Plan", "Review Required"): {
        "action": "pdlc-plan", "owner": "pdlc-plan", "reason": _REVIEW_REQUIRED_REASON,
    },
    ("Technical Plan", "Decision Required"): {
        "action": "human-decision", "owner": _DECISION_REQUIRED_OWNER, "reason": _DECISION_REQUIRED_REASON,
    },
    ("Technical Plan", "Approval Required"): {
        "action": "human-approval", "owner": "human — pdlc post approve", "reason": _APPROVAL_REQUIRED_REASON,
    },
    ("Technical Plan", "CI Pending"): _heal("TechnicalPlan.CIPending", "TechnicalPlan.ApprovalRequired"),
    ("Technical Plan", "Approved"): _heal("TechnicalPlan.Approved", _pending("Implementation")),

    ("Implementation", "Pending"): {
        "action": "pdlc-implement", "owner": "pdlc-implement", "reason": "next eligible delivery task is due",
    },
    ("Implementation", "Changes Required"): {
        "action": "pdlc-implement", "owner": "pdlc-implement", "reason": "next eligible delivery task is due",
    },
    ("Implementation", "Stale"): {
        "action": "pdlc-implement", "owner": "pdlc-implement", "reason": "next eligible delivery task is due",
    },
    ("Implementation", "Review Required"): {
        "action": "pdlc-review", "owner": "pdlc-review", "reason": _REVIEW_REQUIRED_REASON,
    },
    ("Implementation", "Decision Required"): {
        "action": "human-decision", "owner": _DECISION_REQUIRED_OWNER, "reason": _DECISION_REQUIRED_REASON,
    },
    ("Implementation", "Approval Required"): {
        "action": "human-approval", "owner": "human — pdlc post approve", "reason": _APPROVAL_REQUIRED_REASON,
    },
    ("Implementation", "CI Pending"): {
        "action": "pdlc-post-ci", "owner": "pdlc post ci — record the registered PR stack's CI outcome",
        "reason": "the implementation review passed; the registered PR stack's CI outcome must be recorded",
    },
    ("Implementation", "Approved"): _heal("Implementation.Approved", _pending("Testing")),

    ("Testing", "Pending"): {"action": "pdlc-test", "owner": "pdlc-test", "reason": "acceptance coverage is due"},
    ("Testing", "Changes Required"): {"action": "pdlc-test", "owner": "pdlc-test", "reason": "acceptance coverage is due"},
    ("Testing", "Stale"): {"action": "pdlc-test", "owner": "pdlc-test", "reason": "acceptance coverage is due"},
    ("Testing", "Review Required"): {
        "action": "pdlc-review", "owner": "pdlc-review", "reason": _REVIEW_REQUIRED_REASON,
    },
    ("Testing", "Decision Required"): {
        "action": "human-decision", "owner": _DECISION_REQUIRED_OWNER, "reason": _DECISION_REQUIRED_REASON,
    },
    ("Testing", "Approval Required"): {
        "action": "human-approval", "owner": "human — pdlc post approve", "reason": _APPROVAL_REQUIRED_REASON,
    },
    ("Testing", "CI Pending"): {
        "action": "pdlc-post-ci", "owner": "pdlc post ci — record the registered PR stack's CI outcome",
        "reason": "the testing review passed; the registered PR stack's CI outcome must be recorded",
    },
    ("Testing", "Approved"): _heal("Testing.Approved", _pending("Verification")),

    ("Verification", "Pending"): {"action": "pdlc-verify", "owner": "pdlc-verify", "reason": "verification is due"},
    ("Verification", "Changes Required"): {"action": "pdlc-verify", "owner": "pdlc-verify", "reason": "verification is due"},
    ("Verification", "Stale"): {"action": "pdlc-verify", "owner": "pdlc-verify", "reason": "verification is due"},
    # No persisted review policy at this stage, so a stray Review Required
    # heals straight to Approval Required instead of dispatching a reviewer.
    ("Verification", "Review Required"): _heal("Verification.ReviewRequired", "Verification.CIPending"),
    ("Verification", "Decision Required"): {
        "action": "human-decision", "owner": _DECISION_REQUIRED_OWNER, "reason": _DECISION_REQUIRED_REASON,
    },
    ("Verification", "CI Pending"): {
        "action": "pdlc-post-ci", "owner": "pdlc post ci — record the registered PR stack's CI outcome",
        "reason": "the verification review passed; the registered PR stack's CI outcome must be recorded",
    },
    ("Verification", "Approval Required"): {
        # Verification/Approval Required is the completion boundary — approval
        # routes to `pdlc post complete`, not the generic `pdlc post approve`.
        "action": "human-approval", "owner": "human — pdlc post complete", "reason": _APPROVAL_REQUIRED_REASON,
    },
    # The completion boundary never heals into Complete: completion readiness
    # is checked only by `pdlc post complete`, so it returns to its own gate.
    ("Verification", "Approved"): _heal("Verification.Approved", "Verification.ApprovalRequired"),

    ("Complete", "Approved"): {"action": "none", "owner": "none — record is Complete", "reason": "complete"},
}


class DueNextMatrixTests(unittest.TestCase):
    def test_every_stage_and_gate_combination_routes_as_expected(self):
        for stage in _STAGES:
            for gate in _GATES:
                expected = _EXPECTED.get((stage, gate))
                with self.subTest(stage=stage, gate=gate):
                    due = due_next({"Status": stage, "Gate State": gate, "Skipped States": ""})
                    if expected is None:
                        self.assertEqual(due["action"], "blocked", due)
                        self.assertTrue(due["owner"].startswith("blocked — "), due)
                        continue
                    self.assertEqual(due["action"], expected["action"], due)
                    self.assertEqual(due["owner"], expected["owner"], due)
                    self.assertEqual(due["reason"], expected["reason"], due)


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


class ReviewEvidenceTests(unittest.TestCase):
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

    def test_unsettled_findings_and_unreadable_reports_block_completion(self):
        def codes(body, **extra):
            return {b.code for b in completion_blockers(
                pipeline=FEATURE_PIPELINE,
                status="Verification", gate="Approval Required", tasks=[CLOSED_TASK],
                pull_requests=[MERGED_PR], timeline_markers=MARKERS, skipped_states="",
                verification_body=body, stale_rows=[], open_questions="- none", **extra,
            )}
        self.assertEqual(codes(GOOD_VERIFICATION, open_findings=["F-1 · open — 503s"]), {"verification-findings"})
        self.assertIn("verification-malformed", codes("## Verification Run Results\n\n- FR-1 (Verified @ abc)"))

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

"""`pdlc inspect verify` on a populated Verification-stage record: readiness,
task completion, the evidence timeline, journeys-to-review, and the git-backed
reuse/staleness pass."""

import json
from unittest import mock

from _support import FileBackendTest

BODY_WITH_JOURNEY = """## Product

The shell ships.

## UI

### UJ-1: First run

- Entry: cold launch
- Flow: the app opens to the map
- Criteria: the map is interactive within 2s

## Decisions
- none

## Open Questions
- none
"""


class InspectVerifyTests(FileBackendTest):
    def _seed_verification_record(self, gate="Changes Required"):
        sha = self.head_sha()
        self.seed_record(50, "Verification", gate, body=BODY_WITH_JOURNEY)
        self.seed_task(50, 501, "TASK-001", "CLOSED", "WORK-50-TASK-001 [UI] Build the first run")
        # A recorded implementation comment on the closed task.
        (self.records_dir() / "50" / "tasks" / "501" / "comments.jsonl").write_text(
            json.dumps({
                "body": "## Implementation\n\nShipped.",
                "createdAt": "2026-01-01T00:00:00Z", "url": "u", "author": {"login": "x"},
            }) + "\n"
        )
        self.seed_prs(50, [{
            "number": 148, "title": "impl", "url": "u", "state": "MERGED", "isDraft": False,
            "branch": "b", "mergedAt": "2026-01-02T00:00:00Z", "checks": "SUCCESS", "relation": "closes",
        }])
        # A prior verification pass — its claims-audit anchor is HEAD, so the
        # reuse pass finds nothing touched it since and keeps it valid.
        prior = (
            "PDLC-REVIEW\n\n---\nstage: Verification\nverdict: Changes Required\nbounce: null\nloop: null\n---\n\n"
            "## Verification Run Results\n\n"
            "### Claims Audit\n\n"
            f"- FR-1 holds (Verified @ {sha})\n\n"
            f"### User Journeys\n\n- None yet (Verified @ {sha})\n\n"
            "### UX\n\n- Reviewed — clean\n\n### Cumulative Review\n\n- Clean\n\n"
            "### Findings\n\n- Fixed the drift calculation\n"
            "### Findings\n\n- Fixed the drift calculation\n\nRecommendation: Changes Required\n"
        )
        with (self.records_dir() / "50" / "comments.jsonl").open("a") as handle:
            handle.write(json.dumps({
                "body": prior, "createdAt": "2026-02-01T00:00:00Z",
                "url": "file://x/50#comment-1", "author": {"login": "v"},
            }) + "\n")
        return sha

    def test_ready_record_renders_every_section(self):
        self._seed_verification_record()
        result = self.invoke("inspect_verify", 50)
        self.assertEqual(result.code, 0, result.stderr)
        for heading in (
            "## Readiness",
            "## Task Completion",
            "# Timeline",
            "## Journeys to review",
            "## Still valid",
            "## Fixed by previous runs",
        ):
            self.assertIn(heading, result.stdout)
        # UJ-1 is new since the last pass, so it is queued for a fresh review.
        self.assertIn("### UJ-1: First run", result.stdout)
        # The prior claims-audit anchor still holds against HEAD.
        self.assertIn("FR-1 holds", result.stdout.split("## Still valid", 1)[1])
        self.assertIn("Fixed the drift calculation", result.stdout)

    def test_unmerged_ci_pending_prs_do_not_block_the_pass(self):
        # Merge is a completion bar, not a verification one: a stack is audited
        # before it lands, so an OPEN / PENDING PR must not stop this pass — it
        # is only listed as diff-base context.
        self._seed_verification_record()
        self.seed_prs(50, [{
            "number": 148, "title": "impl", "url": "u", "state": "OPEN", "isDraft": False,
            "branch": "b", "mergedAt": None, "checks": "PENDING", "relation": "closes",
        }])
        result = self.invoke("inspect_verify", 50)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Ready — Gate State: Changes Required", result.stdout)
        self.assertIn("# Timeline", result.stdout)
        task_completion = result.stdout.split("## Task Completion", 1)[1].split("# Timeline", 1)[0]
        self.assertIn("#148 OPEN checks: PENDING", task_completion)
        self.assertIn("not as a blocker", task_completion)
        self.assertNotIn("dispositioned", task_completion)

    def test_timeline_is_the_compact_index_not_the_full_bodies(self):
        # Same rendering as `pdlc inspect timeline` default: full bodies to a
        # temp file, only a per-comment index inline.
        self._seed_verification_record()
        result = self.invoke("inspect_verify", 50)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("# Timeline — 1 evidence comment(s); full bodies in", result.stdout)
        self.assertIn("Read lines ", result.stdout)
        # The prior review's body lives in the file, not stdout.
        self.assertNotIn("## Verification Run Results", result.stdout)

    def test_not_a_verification_stage_stops_at_readiness(self):
        self.seed_record(51, "Implementation", "Pending")
        result = self.invoke("inspect_verify", 51)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("## Readiness", result.stdout)
        self.assertNotIn("## Task Completion", result.stdout)

    def test_approved_record_with_fresh_evidence_points_at_completion(self):
        self._seed_verification_record(gate="Approval Required")
        result = self.invoke("inspect_verify", 50)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("already verified clean, awaiting the driver", result.stdout)
        self.assertIn("pdlc-complete is next", result.stdout)
        # Still not ready — an approved record is not re-audited.
        self.assertNotIn("## Task Completion", result.stdout)

    def test_approved_record_with_stale_evidence_refuses_to_call_it_clean(self):
        # The bug this covers: readiness keyed only off the gate, so a record
        # whose verified commits had been overtaken still read "verified clean,
        # pdlc-complete is next" — while `pdlc inspect complete` blocked the
        # same record as `verification-stale`, naming no command to break the tie.
        self._seed_verification_record(gate="Approval Required")
        with mock.patch("pdlc.commands.inspect_verify.stale_commits", side_effect=lambda commits: set(commits)):
            result = self.invoke("inspect_verify", 50)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("no longer holds against current source", result.stdout)
        # The offending anchor is named, not just counted.
        self.assertIn("FR-1 holds", result.stdout)
        # And the only command that can actually reopen the stage is named.
        self.assertIn("pdlc post invalidate", result.stdout)
        self.assertNotIn("pdlc-complete is next", result.stdout)

    def test_stale_evidence_is_not_checked_for_a_record_at_another_stage(self):
        # The staleness lookup costs a comment read plus a git pair per anchor;
        # a record that plainly is not at Verification must not pay for it.
        self.seed_record(53, "Implementation", "Pending")
        with mock.patch("pdlc.commands.inspect_verify._stale_anchors") as anchors:
            result = self.invoke("inspect_verify", 53)
        self.assertEqual(result.code, 0, result.stderr)
        anchors.assert_not_called()

    def test_no_ui_task_marks_journeys_not_applicable(self):
        self.seed_record(52, "Verification", "Pending")
        self.seed_task(52, 521, "TASK-001", "CLOSED", "WORK-52-TASK-001 Core only")
        result = self.invoke("inspect_verify", 52)
        self.assertIn("Not applicable — no UI tasks", result.stdout)

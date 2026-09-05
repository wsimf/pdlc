"""`pdlc inspect verify` on a populated Verification-stage record: readiness,
task completion, the evidence timeline, journeys-to-review, and the git-backed
reuse/staleness pass."""

import json

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
            "### User Journeys\n\n- None yet\n\n"
            "### UX\n\n- Reviewed — clean\n\n### Cumulative Review\n\n- Clean\n\n"
            "### Findings\n\n- Fixed the drift calculation\n"
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

    def test_not_a_verification_stage_stops_at_readiness(self):
        self.seed_record(51, "Implementation", "Pending")
        result = self.invoke("inspect_verify", 51)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("## Readiness", result.stdout)
        self.assertNotIn("## Task Completion", result.stdout)

    def test_no_ui_task_marks_journeys_not_applicable(self):
        self.seed_record(52, "Verification", "Pending")
        self.seed_task(52, 521, "TASK-001", "CLOSED", "WORK-52-TASK-001 Core only")
        result = self.invoke("inspect_verify", 52)
        self.assertIn("Not applicable — no UI tasks", result.stdout)

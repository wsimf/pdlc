"""`pdlc inspect verify` on a populated Verification-stage record: readiness,
task completion, the evidence timeline, the source guard, journeys-to-review,
the finding ledger, and the pre-filled report with its carried-forward rows."""

import json
from pathlib import Path
from unittest import mock

from _support import FileBackendTest
from pdlc.domain.records import PullRef
from pdlc.domain.evidence import ReviewVerdict, compose_review
from pdlc.domain.verification import FindingEntry, Report, Row, render

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
            "files": ["src/pdlc/cli.py"],
        }])
        self.register_prs(501, [148])
        # A prior pass checked at HEAD: the claims row, UX, and cumulative
        # review settle and nothing has changed since, so they carry forward;
        # UJ-1 failed with F-1 open, so it is queued for a fresh review.
        prior = Report(
            head=sha, run_at="2026-02-01 00:00 UTC", recommendation="Changes Required",
            claims=(Row("TASK-001", "confirmed", "first run shipped as claimed"),),
            journeys=(Row("UJ-1", "failed", "map not interactive in time"),),
            ux=Row("ux", "clean"), cumulative=Row("cumulative", "clean"),
            findings=(
                FindingEntry("F-1", "open", about="UJ-1", text="Map takes 4s to become interactive"),
                FindingEntry("F-2", "deferred", "driver accepted: cosmetic", about="cumulative", text="Duplicated constant"),
            ),
        )
        body = "PDLC-REVIEW\n\n" + compose_review("Verification", ReviewVerdict.CHANGES_REQUIRED, render(prior))
        with (self.records_dir() / "50" / "comments.jsonl").open("a") as handle:
            handle.write(json.dumps({
                "body": body, "createdAt": "2026-02-01T00:00:00Z",
                "url": "file://x/50#comment-1", "author": {"login": "v"},
            }) + "\n")
        return sha

    def test_ready_record_renders_every_section(self):
        sha = self._seed_verification_record()
        result = self.invoke("inspect_verify", 50)
        self.assertEqual(result.code, 0, result.stderr)
        for heading in (
            "## Readiness", "## Task Completion", "# Timeline", "## Source",
            "## Journeys to review", "## Findings", "## Report",
        ):
            self.assertIn(heading, result.stdout)
        self.assertIn(f"Verifying at HEAD {sha} — every open task PR's head is included.", result.stdout)
        # UJ-1 failed last pass, so it is queued for a fresh review; UX carries.
        self.assertIn("### UJ-1: First run", result.stdout)
        self.assertIn("UX: carried forward", result.stdout)
        findings = result.stdout.split("## Findings", 1)[1]
        self.assertIn("- F-1 · open · UJ-1 — Map takes 4s to become interactive", findings)
        self.assertIn("Closed — do not raise these again:\n\n- F-2 · deferred — Duplicated constant", findings)
        self.assertIn("3 row(s) carried forward, 1 to check", result.stdout)

    def test_report_is_prefilled_with_carried_rows_and_open_findings(self):
        sha = self._seed_verification_record()
        result = self.invoke("inspect_verify", 50)
        path = result.stdout.split("Filled in at ", 1)[1].split(" ", 1)[0]
        report = json.loads(Path(path).read_text())
        self.assertEqual(report["head"], sha)
        self.assertEqual(report["claims"][0]["result"], "confirmed")
        self.assertEqual(report["claims"][0]["reuse"], f"valid — checked at {sha[:12]}")
        self.assertEqual(report["journeys"], [{"journey": "UJ-1", "reuse": "check", "result": None, "note": ""}])
        self.assertEqual([f["id"] for f in report["findings"]], ["F-1"])
        self.assertEqual(report["newFindings"], [])

    def test_a_task_touched_since_its_check_is_not_carried_forward(self):
        self._seed_verification_record()
        with mock.patch("pdlc.internal.verification.changed_files", return_value={"src/pdlc/cli.py"}):
            result = self.invoke("inspect_verify", 50)
        # The UI task changed, so its claims row, UX, and the cumulative review all need a fresh check.
        self.assertIn("0 row(s) carried forward, 4 to check", result.stdout)
        self.assertIn("UX: needs re-review", result.stdout)

    def test_open_comments_reports_none_when_every_thread_is_resolved(self):
        # The file code host has no live review-thread state, so this is the
        # default for a file-backend scenario without mocking the code host.
        self._seed_verification_record()
        result = self.invoke("inspect_verify", 50)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("## Open Comments\n\nNone.", result.stdout)

    def test_open_comments_renders_unresolved_threads_grouped_by_pr(self):
        self._seed_verification_record()
        with mock.patch(
            "pdlc.commands.inspect_verify.record_open_review_comments",
            return_value=[{
                "pr": PullRef(148), "author": "reviewer", "body": "fix the null case",
                "url": "u2", "path": "src/cache.py", "line": 42,
            }],
        ):
            result = self.invoke("inspect_verify", 50)
        self.assertEqual(result.code, 0, result.stderr)
        section = result.stdout.split("## Open Comments", 1)[1].split("# Timeline", 1)[0]
        self.assertIn("PR #148:", section)
        self.assertIn("@reviewer on src/cache.py:42 — fix the null case (u2)", section)

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
        with mock.patch("pdlc.internal.verification.changed_files", return_value={"src/pdlc/cli.py"}):
            result = self.invoke("inspect_verify", 50)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("no longer holds against current source", result.stdout)
        # The offending row is named, not just counted.
        self.assertIn("- claims TASK-001 · confirmed — first run shipped as claimed", result.stdout)
        # And the only command that can actually reopen the stage is named.
        self.assertIn("pdlc post invalidate", result.stdout)
        self.assertNotIn("pdlc-complete is next", result.stdout)

    def test_stale_evidence_is_not_checked_for_a_record_at_another_stage(self):
        # The staleness lookup costs a comment read, a PR file lookup per task,
        # and a git diff; a record that plainly is not at Verification must not pay for it.
        self.seed_record(53, "Implementation", "Pending")
        with mock.patch("pdlc.commands.inspect_verify._stale_rows") as stale_rows:
            result = self.invoke("inspect_verify", 53)
        self.assertEqual(result.code, 0, result.stderr)
        stale_rows.assert_not_called()

    def test_an_approved_record_whose_report_predates_the_schema_is_not_called_clean(self):
        self.seed_record(54, "Verification", "Approval Required")
        with (self.records_dir() / "54" / "comments.jsonl").open("a") as handle:
            legacy = "PDLC-REVIEW\n\n" + compose_review(
                "Verification", ReviewVerdict.PASS, "## Verification Run Results\n\n### Claims Audit\n\n- FR-1 (Verified @ abc)\n")
            handle.write(json.dumps({"body": legacy, "createdAt": "2026-02-01T00:00:00Z", "url": "", "author": {"login": "v"}}) + "\n")
        result = self.invoke("inspect_verify", 54)
        self.assertIn("predates pdlc.verify/1", result.stdout)
        self.assertNotIn("pdlc-complete is next", result.stdout)

    def test_no_ui_task_marks_journeys_not_applicable(self):
        self.seed_record(52, "Verification", "Pending")
        self.seed_task(52, 521, "TASK-001", "CLOSED", "WORK-52-TASK-001 Core only")
        result = self.invoke("inspect_verify", 52)
        self.assertIn("Not applicable — no UI tasks", result.stdout)

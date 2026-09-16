"""`pdlc.domain.verification`: building a report from verifier JSON, the
derived recommendation, the finding ledger, row staleness, and the Markdown
round trip every reader depends on."""

import unittest

from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.verification import (
    SCHEMA,
    Finding,
    Report,
    Row,
    VerifyContext,
    build_report,
    ledger,
    parse,
    render,
    render_decisions,
    stale_rows,
)

HEAD = "c47d0ae13f2b9e8a7d6c5b4a3f2e1d0c9b8a7f6e"
OLD = "9f3e21c0a1b2c3d4e5f60718293a4b5c6d7e8f90"


def context(**fields) -> VerifyContext:
    defaults = dict(head=HEAD, run_at="2026-09-16 10:42 UTC", tasks=("TASK-001",), journeys=None, open_comments=(), findings={})
    return VerifyContext(**{**defaults, **fields})


def clean(**fields) -> dict:
    data = {
        "schema": SCHEMA,
        "claims": [{"task": "TASK-001", "result": "confirmed", "note": "shipped as claimed"}],
        "cumulativeReview": {"result": "clean", "scope": "master..top", "note": ""},
    }
    return {**data, **fields}


def finding(fid="F-1", status="open", about="TASK-001", text="503s are not retried") -> Finding:
    return Finding(fid, about, text, "", status, "", OLD)


class BuildReportTests(unittest.TestCase):
    def test_clean_report_derives_approval_and_fills_in_what_the_record_owns(self):
        built = build_report(clean(), context())
        self.assertEqual(built.report.recommendation, "Approval Required")
        self.assertEqual(built.report.head, HEAD)
        self.assertIsNone(built.report.journeys)
        self.assertEqual(built.report.ux, Row("ux", "not_applicable"))
        self.assertEqual(built.report.cumulative, Row("cumulative", "clean", "master..top"))

    def test_early_stop_with_not_run_rows_is_a_valid_changes_required_report(self):
        # The bug this replaces: a stopped-early report could be posted but not
        # read back. `not_run` is a first-class result now.
        data = clean(
            claims=[{"task": "TASK-001", "result": "not_run"}],
            cumulativeReview={"result": "not_run"},
            newFindings=[{"about": "TASK-001", "text": "503s are not retried", "source": "https://x/pull/1#r1", "status": "open"}],
            openComments=[{"url": "https://x/pull/1#r1", "action": "finding"}],
            bounce="Implementation",
        )
        built = build_report(data, context(open_comments=("https://x/pull/1#r1",)))
        self.assertEqual(built.report.recommendation, "Changes Required")
        self.assertEqual(built.bounce, "Implementation")
        self.assertEqual([entry.id for entry in built.report.findings], ["F-1"])
        self.assertEqual(parse(render(built.report)), built.report)

    def test_new_findings_are_numbered_after_the_ledger(self):
        known = {"F-1": finding(status="fixed"), "F-2": finding("F-2", status="deferred")}
        data = clean(newFindings=[{"about": "cumulative", "text": "dup constant", "status": "open"}])
        built = build_report(data, context(findings=known))
        self.assertEqual(built.report.findings[0].id, "F-3")
        self.assertEqual(built.report.recommendation, "Changes Required")

    def test_an_unmentioned_open_finding_stays_open_and_blocks_approval(self):
        built = build_report(clean(), context(findings={"F-1": finding()}))
        self.assertEqual(built.report.recommendation, "Changes Required")

    def test_fixing_the_last_open_finding_allows_approval(self):
        data = clean(findings=[{"id": "F-1", "status": "fixed", "note": "retried now"}])
        built = build_report(data, context(findings={"F-1": finding()}))
        self.assertEqual(built.report.recommendation, "Approval Required")

    def test_deferred_findings_become_open_questions_lines_once(self):
        data = clean(findings=[{"id": "F-1", "status": "deferred", "note": "driver accepted"}])
        built = build_report(data, context(findings={"F-1": finding()}))
        self.assertEqual(built.deferred, ("F-1: 503s are not retried (driver accepted)",))
        again = build_report(data, context(findings={"F-1": finding(status="deferred")}))
        self.assertEqual(again.deferred, ())

    def test_decision_findings_derive_decision_required_and_render_blocks(self):
        decision = {"question": "Keep drift?", "options": ["keep", "fix"], "recommendation": "keep",
                    "blocks": "completion", "whyNotMechanical": "tolerance is a product call"}
        data = clean(newFindings=[{"about": "general", "text": "2m drift", "status": "decision", "decision": decision}])
        built = build_report(data, context())
        self.assertEqual(built.report.recommendation, "Decision Required")
        blocks = render_decisions(built.decisions)
        self.assertIn("## Decision Required", blocks)
        self.assertIn("Finding: F-1 — 2m drift", blocks)
        self.assertIn("Options: keep / fix", blocks)

    def test_a_finding_sent_to_the_driver_must_get_its_outcome(self):
        with self.assertRaises(PdlcError) as caught:
            build_report(clean(), context(findings={"F-1": finding(status="decision")}))
        self.assertIn("F-1: it went to the driver", str(caught.exception))

    def test_failed_row_needs_a_live_finding_and_deferred_ones_allow_approval(self):
        failing = clean(claims=[{"task": "TASK-001", "result": "failed"}])
        with self.assertRaises(PdlcError) as caught:
            build_report(failing, context())
        self.assertIn("claims TASK-001: result failed needs", str(caught.exception))
        accepted = {**failing, "newFindings": [{"about": "TASK-001", "text": "edge case", "status": "deferred", "note": "driver: next release"}]}
        self.assertEqual(build_report(accepted, context()).report.recommendation, "Approval Required")

    def test_every_problem_is_refused_together(self):
        data = {
            "schema": "wrong",
            "claims": [{"task": "TASK-404", "result": "maybe"}],
            "cumulativeReview": {"result": "clean"},
            "findings": [{"id": "F-9", "status": "fixed"}],
            "bounce": "Implementation",
        }
        with self.assertRaises(PdlcError) as caught:
            build_report(data, context(open_comments=("https://x/pull/1#r1",)))
        message = str(caught.exception)
        for needle in ("schema must be", "TASK-404", "missing a row for: TASK-001", "no action for", "F-9", "bounce is only valid"):
            self.assertIn(needle, message)

    def test_ui_records_need_every_journey_and_a_real_ux_result(self):
        with self.assertRaises(PdlcError) as caught:
            build_report(clean(ux={"result": "not_applicable"}), context(journeys=("UJ-1",)))
        self.assertIn("journeys is missing a row for: UJ-1", str(caught.exception))
        self.assertIn("ux.result cannot be not_applicable", str(caught.exception))

    def test_comment_actions_are_checked(self):
        data = clean(openComments=[{"url": "https://x/pull/1#r1", "action": "finding"}, {"url": "https://x/pull/1#r2", "action": "no_action"}])
        with self.assertRaises(PdlcError) as caught:
            build_report(data, context(open_comments=("https://x/pull/1#r1", "https://x/pull/1#r2")))
        self.assertIn("no newFindings entry has it as source", str(caught.exception))
        self.assertIn("no_action needs a note", str(caught.exception))


class MarkdownRoundTripTests(unittest.TestCase):
    def report(self) -> Report:
        data = clean(
            claims=[{"task": "TASK-001", "result": "confirmed", "note": "retries — with backoff · 3 tries"}],
            journeys=[{"journey": "UJ-1", "result": "accepted", "note": "multi\nline   note"}],
            ux={"result": "clean"},
            openComments=[{"url": "https://x/pull/1#r1", "action": "no_action", "note": "question, answered"}],
            findings=[{"id": "F-1", "status": "fixed", "note": "retried"}],
            newFindings=[{"about": "cumulative", "text": "dup — constant", "source": "cumulative review", "status": "deferred", "note": "cosmetic: later"}],
        )
        return build_report(data, context(journeys=("UJ-1",), open_comments=("https://x/pull/1#r1",), findings={"F-1": finding()})).report

    def test_parse_reads_back_exactly_what_render_wrote(self):
        report = self.report()
        self.assertEqual(parse(render(report)), report)
        self.assertEqual(report.journeys[0].note, "multi line note")

    def test_rendered_shape(self):
        text = render(self.report())
        self.assertIn(f"Run at 2026-09-16 10:42 UTC · HEAD {HEAD} · Approval Required", text)
        self.assertIn("- TASK-001 · confirmed — retries — with backoff · 3 tries", text)
        self.assertIn("- F-1 · fixed — retried", text)
        self.assertIn("- F-2 · deferred · cumulative — dup — constant\n  - source: cumulative review\n  - note: cosmetic: later", text)

    def test_parse_accepts_the_review_wrapper_around_the_report(self):
        report = self.report()
        body = "PDLC-REVIEW\n\n---\nstage: Verification\nverdict: Pass\nbounce: null\nloop: null\n---\n\n" + render(report)
        self.assertEqual(parse(body), report)

    def test_reports_from_before_the_schema_and_hand_edits_are_refused(self):
        legacy = "## Verification Run Results\nRun at 2026-01-01 00:00 UTC\n\n### Claims Audit\n\n- FR-1 holds (Verified @ abc123)\n"
        with self.assertRaises(PdlcError) as caught:
            parse(legacy)
        self.assertIn("pdlc.verify/1", str(caught.exception))
        broken = render(self.report()).replace("- ux · clean", "- UX looks fine")
        with self.assertRaises(PdlcError):
            parse(broken)


class LedgerAndStalenessTests(unittest.TestCase):
    def test_ledger_keeps_ids_text_and_latest_status_across_reports(self):
        first = build_report(clean(
            claims=[{"task": "TASK-001", "result": "failed"}],
            newFindings=[{"about": "TASK-001", "text": "503s are not retried", "status": "open"}],
        ), context(head=OLD)).report
        second = build_report(
            clean(findings=[{"id": "F-1", "status": "fixed", "note": "retried"}]),
            context(findings=ledger([first])),
        ).report
        state = ledger([parse(render(first)), parse(render(second))])
        self.assertEqual(state["F-1"].status, "fixed")
        self.assertEqual(state["F-1"].text, "503s are not retried")
        self.assertEqual(state["F-1"].raised_at, OLD)

    def test_stale_rows_follow_task_files_ui_tasks_and_any_change(self):
        report = build_report(
            clean(claims=[{"task": "TASK-001", "result": "confirmed"}, {"task": "TASK-002", "result": "confirmed"}],
                  journeys=[{"journey": "UJ-1", "result": "accepted"}], ux={"result": "clean"}),
            context(tasks=("TASK-001", "TASK-002"), journeys=("UJ-1",)),
        ).report
        files = {"TASK-001": {"a.py"}, "TASK-002": {"b.swift"}}
        self.assertEqual(stale_rows(report, set(), files, {"TASK-002"}), set())
        self.assertEqual(stale_rows(report, {"a.py"}, files, {"TASK-002"}), {("claims", "TASK-001"), ("cumulative", "cumulative")})
        self.assertEqual(
            stale_rows(report, {"b.swift"}, files, {"TASK-002"}),
            {("claims", "TASK-002"), ("journeys", "UJ-1"), ("ux", "ux"), ("cumulative", "cumulative")},
        )
        # An unreadable HEAD, or a task with no known files, proves nothing.
        self.assertEqual(len(stale_rows(report, None, files, set())), 5)
        self.assertIn(("claims", "TASK-001"), stale_rows(report, set(), {"TASK-001": None, "TASK-002": set()}, set()))


if __name__ == "__main__":
    unittest.main()

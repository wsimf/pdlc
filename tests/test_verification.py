"""`pdlc post verify`: the derived recommendations, the autonomous upstream
bounce, the source guards, and the report round trip back through
`pdlc inspect verify`."""

import json
from unittest import mock

from _support import FileBackendTest

DECISION = {
    "question": "keep the 2m elevation drift or fix it?",
    "options": ["keep", "fix"],
    "recommendation": "keep",
    "blocks": "completion",
    "whyNotMechanical": "tolerance is a product call",
}


def _open_finding(text: str = "503s are not retried") -> list[dict]:
    return [{"about": "general", "text": text, "status": "open"}]


class VerificationTests(FileBackendTest):
    def test_clean_run_with_no_linked_pr_advances_straight_through(self):
        # Verification is CI-gated like Implementation/Testing, but with no
        # registered PR there is nothing to wait on ("untracked"), so a clean
        # run still lands on Approval Required immediately.
        self.seed_record(67, "Verification", "Pending")
        result = self.invoke("post_verify", 67, self.verify_report(67))
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["recommendation"], "Approval Required")
        self.assertEqual(result.json["head"], self.head_sha())
        self.assertEqual(self.state(67), ("Verification", "Approval Required"))
        posted = json.loads(self.comments_text(67))["body"]
        self.assertIn(f"HEAD {self.head_sha()} · Approval Required", posted)

    def test_clean_run_parks_at_ci_pending_while_checks_run(self):
        self.seed_record(68, "Verification", "Pending")
        self.green_pr(68, number=148, checks="PENDING")
        result = self.invoke("post_verify", 68, self.verify_report(68))
        self.assertEqual(result.json["gateState"], "CI Pending")
        routed = self.next("--work-item", 68)
        self.assertEqual(routed.front_matter("action"), "pdlc-post-ci")
        self.assertIn("`pdlc post ci 68 --wait`", routed.stdout)

    def test_red_ci_after_a_clean_verification_drops_to_changes_required(self):
        self.seed_record(69, "Verification", "Pending")
        self.green_pr(69, number=149, checks="FAILURE")
        result = self.invoke("post_verify", 69, self.verify_report(69))
        self.assertEqual(result.json["gateState"], "Changes Required")
        self.assertIn("CI check has failed", self.comments_text(69))

    def test_verification_approval_is_never_auto_advanced(self):
        self.seed_record(67, "Verification", "Pending")
        self.add_invalidation(67)
        self.invoke("post_verify", 67, self.verify_report(67))
        self.assertEqual(self.fields(67)["Gate State"], "Approval Required")
        self.assertEqual(self.next("--work-item", 67).front_matter("action"), "human-approval")

    def test_invalid_report_is_refused_whole_before_posting(self):
        self.seed_record(71, "Verification", "Pending")
        result = self.invoke("post_verify", 71, "text:just some prose")
        self.assertEqual(result.code, 1)
        self.assertIn("report is not valid JSON", result.stderr)
        report = self.verify_report(71, schema="pdlc.verify/0", cumulativeReview={"result": "maybe"})
        result = self.invoke("post_verify", 71, report)
        self.assertEqual(result.code, 1)
        self.assertIn("schema must be", result.stderr)
        self.assertIn("cumulativeReview.result", result.stderr)
        self.assertEqual(self.fields(71)["Gate State"], "Pending")
        self.assertEqual(self.comments_text(71), "")

    def test_refused_when_head_is_not_what_was_checked(self):
        self.seed_record(73, "Verification", "Pending")
        report = self.verify_report(73)
        with mock.patch("pdlc.internal.verification.has_tracked_changes", return_value=True):
            dirty = self.invoke("post_verify", 73, report)
        self.assertEqual(dirty.code, 1)
        self.assertIn("tracked files differ from HEAD", dirty.stderr)
        self.seed_prs(73, [{"number": 150, "title": "t", "url": "u", "state": "OPEN", "isDraft": False,
                            "branch": "feature/73-task-2", "mergedAt": None, "checks": "SUCCESS",
                            "headSha": "0" * 40}])
        below = self.invoke("post_verify", 73, report)
        self.assertEqual(below.code, 1)
        self.assertIn("HEAD does not include every open task PR", below.stderr)
        self.assertIn("#150 (feature/73-task-2)", below.stderr)
        self.assertIn("check out the top of the task stack", self.invoke("inspect_verify", 73).stdout)
        self.assertEqual(self.comments_text(73), "")

    def test_decision_finding_parks_the_record(self):
        self.seed_record(90, "Verification", "Pending")
        report = self.verify_report(90, newFindings=[
            {"about": "general", "text": "2m elevation drift", "status": "decision", "decision": DECISION},
        ])
        result = self.invoke("post_verify", 90, report)
        self.assertEqual(result.json["gateState"], "Decision Required")
        self.assertEqual(result.json["findings"], ["F-1"])
        self.assertIn("PDLC-DECISION", self.comments_text(90))
        self.assertIn("Finding: F-1", self.comments_text(90))
        self.assertEqual(self.next("--work-item", 90).front_matter("action"), "human-decision")
        self.assertIn("parked at Decision Required", self.invoke("inspect_verify", 90).stdout)

    def test_bounce_returns_an_upstream_stage_to_stale(self):
        self.seed_record(69, "Verification", "Pending")
        report = self.verify_report(69, newFindings=_open_finding(), bounce="Implementation")
        result = self.invoke("post_verify", 69, report)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["bouncedTo"], "Implementation")
        self.assertEqual(self.state(69), ("Implementation", "Stale"))
        self.assertNotIn("PDLC-INVALIDATED", self.comments_text(69))
        self.assertIn("PDLC-REVIEW", self.comments_text(69))
        self.assertIn("stage: Verification", self.comments_text(69))
        self.assertIn("verdict: Changes Required", self.comments_text(69))
        self.assertIn("bounce: Implementation", self.comments_text(69))
        self.assertIn("loop: delivery-rework", self.comments_text(69))
        self.assertEqual(self.next("--work-item", 69).front_matter("action"), "pdlc-implement")

    def test_bounce_rejected_unless_the_report_derives_changes_required(self):
        self.seed_record(70, "Verification", "Pending")
        result = self.invoke("post_verify", 70, self.verify_report(70, bounce="Implementation"))
        self.assertEqual(result.code, 1)
        self.assertIn("bounce is only valid", result.stderr)

    def test_bounce_rejects_a_target_outside_pipeline_policy_before_posting(self):
        self.seed_record(72, "Verification", "Pending")
        report = self.verify_report(72, newFindings=_open_finding(), bounce="Product")
        result = self.invoke("post_verify", 72, report)
        self.assertEqual(result.code, 1)
        self.assertIn("expected one of: Implementation, Testing", result.stderr)
        self.assertEqual(self.comments_text(72), "")

    def test_stdin_supplies_the_report(self):
        self.seed_record(22, "Verification", "Pending")
        report = self.verify_report(22)
        with open(report, encoding="utf-8") as handle:
            result = self.invoke("post_verify", 22, "-", stdin=handle.read())
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(self.state(22), ("Verification", "Approval Required"))


class RereadTests(FileBackendTest):
    """The latest report is always read back by the next pass."""

    def seed_ready_record(self, record: int) -> None:
        self.seed_record(record, "Verification", "Pending")
        self.seed_task(record, record + 100, "TASK-001", "CLOSED", "Retry sync")
        self.seed_implementation_comment(record, record + 100, "done")
        # A merged task PR with known files, so its claims row can be carried forward.
        self.seed_prs(record, [{"number": record + 500, "title": "t", "url": "u", "state": "MERGED", "isDraft": False,
                                "branch": "b", "mergedAt": "2026-09-01T00:00:00Z", "checks": "SUCCESS",
                                "files": ["src/pdlc/cli.py"]}], register=False)
        self.register_prs(record + 100, [record + 500])

    def test_an_early_stop_report_does_not_break_the_next_pass(self):
        # Regression: a pass that stopped before its claims audit posted rows
        # the next `pdlc inspect verify` then refused to read.
        self.seed_ready_record(80)
        stopped = self.verify_report(80, newFindings=_open_finding(), bounce="Implementation")
        with open(stopped, encoding="utf-8") as handle:
            data = json.load(handle)
        data["claims"][0]["result"] = "not_run"
        data["cumulativeReview"]["result"] = "not_run"
        self.write_file("stopped.json", json.dumps(data))
        self.assertEqual(self.invoke("post_verify", 80, self.work / "stopped.json").code, 0)

        # The bounce sent it to Implementation; bring it back for a re-verify.
        meta = self.meta(80)
        meta["fields"].update({"Status": "Verification", "Gate State": "Changes Required"})
        (self.records_dir() / "80" / "meta.json").write_text(json.dumps(meta))

        inspected = self.invoke("inspect_verify", 80)
        self.assertEqual(inspected.code, 0, inspected.stderr)
        self.assertIn("- F-1 · open · general — 503s are not retried", inspected.stdout)
        self.assertIn("0 row(s) carried forward, 2 to check", inspected.stdout)

        fixed = self.verify_report(80, findings=[{"id": "F-1", "status": "fixed", "note": "retried now"}])
        result = self.invoke("post_verify", 80, fixed)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["recommendation"], "Approval Required")
        self.assertIn("already verified clean, awaiting the driver", self.invoke("inspect_verify", 80).stdout)

    def test_settled_rows_are_carried_forward_and_unmentioned_findings_stay_open(self):
        self.seed_ready_record(81)
        report = self.verify_report(81, newFindings=_open_finding())
        self.assertEqual(self.invoke("post_verify", 81, report).json["gateState"], "Changes Required")

        inspected = self.invoke("inspect_verify", 81)
        self.assertIn("2 row(s) carried forward, 0 to check", inspected.stdout)
        again = self.invoke("post_verify", 81, self.verify_report(81))
        self.assertEqual(again.json["recommendation"], "Changes Required")
        self.assertEqual(again.json["findings"], [])

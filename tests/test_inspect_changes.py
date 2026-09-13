"""`pdlc inspect changes`: a stage's change requests since it last published —
attribution per source, the publication boundary, legacy-comment fallbacks,
and the stage stamps `post ci` and `post decision` now write."""

import json
import unittest

from _support import FileBackendTest

from pdlc.domain.changes import open_change_requests
from pdlc.domain.workflows.workflow_feature import FEATURE_PIPELINE

DECISION_EVIDENCE = (
    "## Findings\n\n- TASK-002 skips input validation.\n\n"
    "## Decision Required\n\nQuestion: snap geometry on-device or server-side?\n"
    "Options: A/B.\nRecommendation: A.\nBlocks: TASK-001.\n"
)


def _review(stage: str, verdict: str, text: str, *, bounce: str = "null", loop: str = "null") -> str:
    return (
        f"PDLC-REVIEW\n\n---\nstage: {stage}\nverdict: {verdict}\n"
        f"bounce: {bounce}\nloop: {loop}\n---\n\n## Findings\n\n{text}\n"
    )


def _thread(*bodies: str) -> list[dict]:
    return [
        {"body": body, "createdAt": f"2026-04-{day:02d}T00:00:00Z", "url": f"u{day}", "author": {"login": "t"}}
        for day, body in enumerate(bodies, start=1)
    ]


def _open(comments: list[dict], stage: str) -> list[tuple[str, str]]:
    changes = open_change_requests(comments, FEATURE_PIPELINE, stage)
    return [(request.source, request.comment["url"]) for request in changes.requests]


class OpenChangeRequestTests(unittest.TestCase):
    def test_review_findings_stay_open_until_the_stage_republishes(self):
        comments = _thread(
            "PDLC-IMPLEMENTATION\n\nfirst pass",
            _review("Implementation", "Changes Required", "- fix retry"),
        )
        self.assertEqual(_open(comments, "Implementation"), [("review", "u2")])
        comments += _thread("x", "x", "PDLC-IMPLEMENTATION\n\nsecond pass")[2:]
        self.assertEqual(_open(comments, "Implementation"), [])

    def test_clean_review_is_not_a_change_request(self):
        comments = _thread("PDLC-IMPLEMENTATION\n\npass", _review("Implementation", "Pass", "- nit"))
        self.assertEqual(_open(comments, "Implementation"), [])

    def test_decision_review_and_its_resolution_are_both_open(self):
        comments = _thread(
            "PDLC-IMPLEMENTATION\n\npass",
            _review("Implementation", "Decision Required", "- findings\n\n## Decision Required\n\nQ?"),
            "PDLC-DECISION\n\n## Decision Required\n\nQ?",
            "PDLC-RESOLUTION\n\nResolved stage: Implementation\n\n### Q\nDecision: A",
        )
        self.assertEqual(_open(comments, "Implementation"), [("decision", "u2"), ("resolution", "u4")])

    def test_unstamped_resolution_belongs_to_the_decision_review_before_it(self):
        comments = _thread(
            "PDLC-TESTING\n\npass",
            _review("Testing", "Decision Required", "## Decision Required\n\nQ?"),
            "PDLC-RESOLUTION\n\n### Q\nDecision: A",
        )
        self.assertEqual(_open(comments, "Testing"), [("decision", "u2"), ("resolution", "u3")])

    def test_later_stage_findings_are_not_attributed_to_an_earlier_stage(self):
        comments = _thread(
            "PDLC-IMPLEMENTATION\n\npass",
            "PDLC-TESTING\n\ncoverage",
            _review("Testing", "Changes Required", "- add a journey test"),
        )
        self.assertEqual(_open(comments, "Implementation"), [])
        self.assertEqual(_open(comments, "Testing"), [("review", "u3")])

    def test_verification_bounce_belongs_to_its_target_stage(self):
        comments = _thread(
            "PDLC-IMPLEMENTATION\n\npass",
            _review("Verification", "Changes Required", "- claim fails", bounce="Implementation", loop="delivery-rework"),
        )
        self.assertEqual(_open(comments, "Implementation"), [("bounce", "u2")])
        self.assertEqual(_open(comments, "Verification"), [])

    def test_ci_note_is_attributed_by_its_stage_line_or_legacy_sentence(self):
        stamped = "PDLC-REVIEW\n\nCI failed stage: Implementation\n\nCI check has failed on the implementation pull request(s)."
        legacy = "PDLC-REVIEW\n\nCI check has failed on the testing pull request(s) after the testing review was approved."
        comments = _thread("PDLC-IMPLEMENTATION\n\npass", stamped, "PDLC-TESTING\n\ncoverage", legacy)
        self.assertEqual(_open(comments, "Implementation"), [("ci", "u2")])
        self.assertEqual(_open(comments, "Testing"), [("ci", "u4")])

    def test_verification_changes_review_is_its_own_open_request(self):
        comments = _thread(
            _review("Verification", "Pass", "- ok"),
            _review("Verification", "Changes Required", "- re-verify journey 2"),
        )
        self.assertEqual(_open(comments, "Verification"), [("review", "u2")])
        comments += _thread("x", "x", _review("Verification", "Pass", "- ok"))[2:]
        self.assertEqual(_open(comments, "Verification"), [])

    def test_invalidation_is_open_until_the_invalidated_stage_republishes(self):
        comments = _thread(
            "PDLC-PLAN\n\nplans",
            "PDLC-IMPLEMENTATION\n\npass",
            "PDLC-INVALIDATED\n\nInvalidated stage: Technical Plan\n\nwrong storage layer",
        )
        changes = open_change_requests(comments, FEATURE_PIPELINE, "Technical Plan")
        self.assertEqual(changes.published["url"], "u1")
        self.assertEqual([request.source for request in changes.requests], ["invalidation"])

    def test_stage_that_never_published_lists_every_request(self):
        comments = _thread(_review("Testing", "Changes Required", "- missing"))
        changes = open_change_requests(comments, FEATURE_PIPELINE, "Testing")
        self.assertIsNone(changes.published)
        self.assertEqual(len(changes.requests), 1)


class InspectChangesCommandTests(FileBackendTest):
    def _log(self, record: int, *bodies: str) -> None:
        log = self.records_dir() / str(record) / "comments.jsonl"
        with log.open("a") as handle:
            for entry in _thread(*bodies):
                handle.write(json.dumps(entry) + "\n")

    def test_red_ci_note_is_stamped_and_listed(self):
        self.seed_record(27, "Implementation", "CI Pending")
        self._log(27, "PDLC-IMPLEMENTATION\n\nall tasks closed")
        self.green_pr(27, number=149, checks="FAILURE")
        self.assertEqual(self.invoke("post_ci", 27).code, 0)
        self.assertIn("CI failed stage: Implementation", self.comments_text(27))
        result = self.invoke("inspect_changes", 27)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("# Open Changes — Implementation", result.stdout)
        self.assertIn("## 1. CI failure", result.stdout)
        self.assertIn("Failed checks: #149 (FAILURE)", result.stdout)

    def test_decision_findings_and_resolution_are_listed_together(self):
        self.seed_record(25, "Implementation", "Review Required")
        self.invoke("post_review", 25, "decision-required", self.write_file("d.md", DECISION_EVIDENCE))
        manifest = self.write_file(
            "decisions.json",
            json.dumps([{"decision": "On-device vs server-side", "answer": "On-device", "rationale": "offline-first"}]),
        )
        self.assertEqual(self.invoke("post_decision", 25, "--manifest", manifest).code, 0)
        self.assertIn("Resolved stage: Implementation", self.comments_text(25))
        result = self.invoke("inspect_changes", 25)
        self.assertIn("## 1. Review decision", result.stdout)
        self.assertIn("TASK-002 skips input validation", result.stdout)
        self.assertIn("## 2. Decision resolution", result.stdout)
        self.assertNotIn("## 3.", result.stdout)

    def test_nothing_open_after_republishing(self):
        self.seed_record(30, "Implementation", "Review Required")
        self._log(30, _review("Implementation", "Changes Required", "- fix"), "PDLC-IMPLEMENTATION\n\nfixed")
        result = self.invoke("inspect_changes", 30)
        self.assertIn("Implementation last published at", result.stdout)
        self.assertIn("No open change requests for Implementation.", result.stdout)

    def test_stage_flag_reports_another_stage(self):
        self.seed_record(31, "Implementation", "Pending")
        self._log(31, "PDLC-INVALIDATED\n\nInvalidated stage: Tasks\n\nsplit TASK-004")
        result = self.invoke("inspect_changes", 31, "--stage", "Tasks")
        self.assertIn("# Open Changes — Tasks", result.stdout)
        self.assertIn("## 1. Invalidation", result.stdout)

    def test_unknown_or_terminal_stage_is_refused(self):
        self.seed_record(32, "Complete", "Approved")
        result = self.invoke("inspect_changes", 32)
        self.assertEqual(result.code, 1)
        self.assertIn("pass --stage with one of", result.stderr)
        self.assertEqual(self.invoke("inspect_changes", 32, "--stage", "Nope").code, 1)


if __name__ == "__main__":
    unittest.main()

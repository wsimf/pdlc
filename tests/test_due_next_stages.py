"""Confirms every stage up to and including Testing's `# Due Next` text
matches `docs/due-next-decision.md`, the source of truth the user authored
for these stages, byte for byte.

`docs/due-next-decision.md` is parsed rather than duplicated into a second
hardcoded expectation, so the doc stays the single place that wording lives
and drifts are caught the moment either side changes. Changes Required and
Stale each carry two doc examples — evidence found and evidence not found —
so those two are handled separately from the single-example gates.
"""

import re
import unittest
from pathlib import Path

from pdlc.commands.inspect import _due_next_section
from pdlc.domain.evidence import ReviewVerdict, compose_review
from pdlc.domain.model import timeline_formatted_at
from pdlc.domain.stages import Action
from pdlc.domain.workflows.stages import (
    IMPLEMENTATION_STAGE,
    PRODUCT_STAGE,
    TASKS_STAGE,
    TECHNICAL_PLAN_STAGE,
    TESTING_STAGE,
    UI_STAGE,
    VERIFICATION_STAGE,
)

DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "due-next-decision.md"

SIMPLE_GATES = (
    "Pending", "Review Required", "CI Pending", "Approval Required", "Approved",
)
EVIDENCE_GATES = ("Changes Required", "Stale", "Decision Required")

STAGES = {
    "Product": PRODUCT_STAGE,
    "UI": UI_STAGE,
    "Tasks": TASKS_STAGE,
    "Technical Plan": TECHNICAL_PLAN_STAGE,
    "Implementation": IMPLEMENTATION_STAGE,
    "Testing": TESTING_STAGE,
    "Verification": VERIFICATION_STAGE,
}

# The work item id substituted for `{ITEM_ID}` in every stage's rendered text.
TEST_ITEM_ID = 4242

# Technical Plan's `{NEXT_PLAN_TASK}`/`{TASK_IDs}` placeholders resolve against
# real task data; this fixture (one task still needing a plan, one already
# planned) exercises both substitutions with a single, fixed expectation.
TECHNICAL_PLAN_TASKS = [
    {"number": 501, "needsPlan": True},
    {"number": 502, "needsPlan": False},
]
NEXT_PLAN_TASK_TEXT = (
    "The next task pending a Technical Plan is 501. Call `pdlc inspect task 501` for its "
    "current content, and `pdlc inspect task timeline 501` for its evidence history."
)
TASK_IDS_TEXT = "501, 502"

# Implementation's `{NEXT_IMPLEMENTATION_TASK}` placeholder resolves against
# real task data the same way; one task still eligible for implementation, one
# already implemented and closed.
IMPLEMENTATION_TASKS = [
    {"number": 701, "state": "OPEN", "isUI": False, "hasPlan": True, "hasImplementation": False, "implementationInvalidated": False},
    {"number": 702, "state": "CLOSED", "isUI": False, "hasPlan": True, "hasImplementation": True, "implementationInvalidated": False},
]
NEXT_IMPLEMENTATION_TASK_TEXT = (
    "The next task pending implementation is 701. Call `pdlc inspect task 701` for its "
    "current content, and `pdlc inspect task timeline 701` for its evidence history."
)

# Implementation and Testing's Review Required both dispatch to the generic
# pdlc-review skill rather than their own owning skill (see `pdlc-review/SKILL.md`).
REVIEW_SKILL_TEXT = Action.REVIEW.value


def _item(stage: str, gate: str) -> dict:
    return {"Status": stage, "Gate State": gate, "Skipped States": "", "content": {"number": TEST_ITEM_ID}}


def _tasks_for(stage: str) -> list[dict]:
    if stage == "Technical Plan":
        return TECHNICAL_PLAN_TASKS
    if stage == "Implementation":
        return IMPLEMENTATION_TASKS
    return []


def _stage_blocks(stage: str) -> dict[str, list[str]]:
    """Every fenced code block under each `### {stage} / <gate>` heading, in
    doc order — one block for the simple gates, two (evidence found, then
    evidence not found) for Changes Required and Stale."""
    text = DOC_PATH.read_text()
    section = text.split(f"\n## {stage}\n", 1)[1].split("\n## ", 1)[0]
    chunks = re.split(rf"\n### {re.escape(stage)} / ", section)[1:]
    blocks = {}
    for chunk in chunks:
        gate, _, rest = chunk.partition("\n")
        bodies = []
        for body in re.findall(r"```\n(.*?)```", rest, re.DOTALL):
            body = body.rstrip("\n")
            if stage in STAGES:
                body = body.replace(f"{{Stage.{stage}.skill}}", STAGES[stage].skill or "")
            body = body.replace("{ITEM_ID}", str(TEST_ITEM_ID))
            body = body.replace("{REVIEW_SKILL}", REVIEW_SKILL_TEXT)
            if stage == "Technical Plan":
                body = body.replace("{NEXT_PLAN_TASK}", NEXT_PLAN_TASK_TEXT).replace("{TASK_IDs}", TASK_IDS_TEXT)
            if stage == "Implementation":
                body = body.replace("{NEXT_IMPLEMENTATION_TASK}", NEXT_IMPLEMENTATION_TASK_TEXT)
            bodies.append(body)
        blocks[gate] = bodies
    return blocks


class DueNextMatchesDocTests(unittest.TestCase):
    def setUp(self):
        self.blocks = {stage: _stage_blocks(stage) for stage in STAGES}
        for stage in STAGES:
            with self.subTest(stage=stage):
                self.assertEqual(set(self.blocks[stage]), set(SIMPLE_GATES) | set(EVIDENCE_GATES))

    def test_simple_gates_match_the_doc_verbatim(self):
        for stage in STAGES:
            for gate in SIMPLE_GATES:
                with self.subTest(stage=stage, gate=gate):
                    self.assertEqual(len(self.blocks[stage][gate]), 1)
                    item = _item(stage, gate)
                    self.assertEqual(_due_next_section(item, [], _tasks_for(stage)), self.blocks[stage][gate][0])

    def test_evidence_gates_fall_back_to_the_doc_verbatim_when_no_marker_is_found(self):
        for stage in STAGES:
            for gate in EVIDENCE_GATES:
                with self.subTest(stage=stage, gate=gate):
                    self.assertEqual(len(self.blocks[stage][gate]), 2)
                    item = _item(stage, gate)
                    self.assertEqual(_due_next_section(item, [], _tasks_for(stage)), self.blocks[stage][gate][1])

    def test_next_pending_task_reports_none_pending_when_every_task_has_a_plan(self):
        planned_tasks = [{"number": 501, "needsPlan": False}, {"number": 502, "needsPlan": False}]
        item = _item("Technical Plan", "Pending")
        rendered = _due_next_section(item, [], planned_tasks)
        self.assertIn("No delivery tasks are currently pending a Technical Plan.", rendered)

    def test_next_pending_task_reports_none_pending_when_every_task_is_implemented(self):
        implemented_tasks = [
            {"number": 701, "state": "CLOSED", "isUI": False, "hasPlan": True, "hasImplementation": True, "implementationInvalidated": False},
        ]
        item = _item("Implementation", "Pending")
        rendered = _due_next_section(item, [], implemented_tasks)
        self.assertIn("No delivery tasks are currently pending implementation.", rendered)

    def test_changes_required_inlines_the_newest_review_or_resolution_comment(self):
        for stage in STAGES:
            with self.subTest(stage=stage):
                review_body = "PDLC-REVIEW\n\n" + compose_review(
                    stage, ReviewVerdict.CHANGES_REQUIRED, "Tighten the requirements in section 2."
                )
                comments = [
                    {"body": review_body, "createdAt": "2026-01-05T14:30:00Z", "url": "u1", "author": {"login": "reviewer"}},
                ]
                item = _item(stage, "Changes Required")
                rendered = _due_next_section(item, comments, _tasks_for(stage))

                found_template = self.blocks[stage]["Changes Required"][0]
                expected = found_template.replace(
                    "This evidence was posted at {when}.\n"
                    "{the newest PDLC-REVIEW or PDLC-DECISION comment's verbatim text, marker and metadata header stripped}",
                    f"This evidence was posted at {timeline_formatted_at('2026-01-05T14:30:00Z')}.\n"
                    "Tighten the requirements in section 2.",
                )
                self.assertNotIn("{when}", expected)
                self.assertNotIn("{the newest", expected)
                self.assertEqual(rendered, expected)

    def test_stale_inlines_the_newest_invalidated_comment(self):
        for stage in STAGES:
            with self.subTest(stage=stage):
                comments = [
                    {
                        "body": f"PDLC-INVALIDATED\n\nInvalidated stage: {stage}\n\nScope changed after the kickoff call.\n",
                        "createdAt": "2026-02-01T09:00:00Z", "url": "u1", "author": {"login": "driver"},
                    },
                ]
                item = _item(stage, "Stale")
                rendered = _due_next_section(item, comments, _tasks_for(stage))

                found_template = self.blocks[stage]["Stale"][0]
                expected = found_template.replace(
                    "This evidence was posted at {when}.\n"
                    "{the newest PDLC-INVALIDATED comment's verbatim text}",
                    f"This evidence was posted at {timeline_formatted_at('2026-02-01T09:00:00Z')}.\n"
                    f"Invalidated stage: {stage}\n\nScope changed after the kickoff call.",
                )
                self.assertNotIn("{when}", expected)
                self.assertNotIn("{the newest", expected)
                self.assertEqual(rendered, expected)

    def test_decision_required_inlines_the_newest_decision_comment(self):
        for stage in STAGES:
            with self.subTest(stage=stage):
                comments = [
                    {
                        "body": "PDLC-DECISION\n\n## Decision Required\n\nOn-device vs server-side snapping?\n",
                        "createdAt": "2026-03-01T09:00:00Z", "url": "u1", "author": {"login": "reviewer"},
                    },
                ]
                item = _item(stage, "Decision Required")
                rendered = _due_next_section(item, comments, _tasks_for(stage))

                found_template = self.blocks[stage]["Decision Required"][0]
                expected = found_template.replace(
                    "This evidence was posted at {when}.\n"
                    "{the newest PDLC-DECISION comment's verbatim text, marker stripped}",
                    f"This evidence was posted at {timeline_formatted_at('2026-03-01T09:00:00Z')}.\n"
                    "## Decision Required\n\nOn-device vs server-side snapping?",
                )
                self.assertNotIn("{when}", expected)
                self.assertNotIn("{the newest", expected)
                self.assertEqual(rendered, expected)

    def test_changes_required_prefers_the_newer_of_review_and_resolution(self):
        older_review = "PDLC-REVIEW\n\n" + compose_review("Product", ReviewVerdict.DECISION_REQUIRED, "Needs a call.")
        newer_resolution = "PDLC-RESOLUTION\n\nUser decided: keep the current scope."
        comments = [
            {"body": older_review, "createdAt": "2026-01-01T00:00:00Z", "url": "u1", "author": {"login": "reviewer"}},
            {"body": newer_resolution, "createdAt": "2026-01-02T00:00:00Z", "url": "u2", "author": {"login": "driver"}},
        ]
        item = _item("Product", "Changes Required")
        rendered = _due_next_section(item, comments, [])
        self.assertIn("User decided: keep the current scope.", rendered)
        self.assertNotIn("Needs a call.", rendered)


if __name__ == "__main__":
    unittest.main()

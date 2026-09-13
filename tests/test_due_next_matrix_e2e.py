"""Full (stage, gate) matrix for the `# Due Next` section, driven end to end.

`test_due_next_stages.py` calls `_due_next_section()` directly against a
synthetic dict and proves its output matches `docs/due-next-decision.md`.
This file instead seeds a real file-backend record for every curated stage
and gate, runs the real `pdlc inspect --full` CLI, and checks the rendered
`# Due Next` section against the same doc — exercising the CLI argument
parsing, the file backend read, and comment/task loading that the direct
function call skips. Technical Plan and Implementation additionally get real
seeded tasks (with real `## Technical Plan`/`## Implementation` comments and
registered PRs) so their `### Next Pending Task` line is produced by the
real task-classification logic, not asserted separately.
"""

from __future__ import annotations

import itertools
import json
import re
from pathlib import Path

from _support import FileBackendTest
from pdlc.domain.evidence import ReviewVerdict, compose_review
from pdlc.domain.model import timeline_formatted_at
from test_due_next_stages import EVIDENCE_GATES, REVIEW_SKILL_TEXT, SIMPLE_GATES, STAGES

DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "due-next-decision.md"


def _raw_blocks(stage: str) -> dict[str, list[str]]:
    """Every fenced `# Due Next` block for one stage, with every placeholder
    except `{ITEM_ID}`/`{TASK_IDs}`/`{NEXT_PLAN_TASK}`/`{NEXT_IMPLEMENTATION_TASK}`
    resolved — those depend on the record/task numbers a given test mints, so
    callers substitute them."""
    text = DOC_PATH.read_text()
    section = text.split(f"\n## {stage}\n", 1)[1].split("\n## ", 1)[0]
    chunks = re.split(rf"\n### {re.escape(stage)} / ", section)[1:]
    blocks = {}
    for chunk in chunks:
        gate, _, rest = chunk.partition("\n")
        bodies = []
        for body in re.findall(r"```\n(.*?)```", rest, re.DOTALL):
            body = body.rstrip("\n")
            body = body.replace(f"{{Stage.{stage}.skill}}", STAGES[stage].skill or "")
            body = body.replace("{REVIEW_SKILL}", REVIEW_SKILL_TEXT)
            bodies.append(body)
        blocks[gate] = bodies
    return blocks


def _next_plan_task_text(task_id: int) -> str:
    return (
        f"The next task pending a Technical Plan is {task_id}. Call `pdlc inspect task {task_id}` "
        f"for its current content, and `pdlc inspect task timeline {task_id}` for its evidence history."
    )


def _next_implementation_task_text(task_id: int) -> str:
    return (
        f"The next task pending implementation is {task_id}. Call `pdlc inspect task {task_id}` "
        f"for its current content, and `pdlc inspect task timeline {task_id}` for its evidence history."
    )


def _rendered_due_next(stdout: str) -> str:
    return ("# Due Next\n\n" + stdout.split("# Due Next\n\n", 1)[1]).rstrip("\n")


class DueNextMatrixE2ETests(FileBackendTest):
    def setUp(self) -> None:
        super().setUp()
        self._numbers = itertools.count(9000)

    def _fresh_number(self) -> int:
        return next(self._numbers)

    def _seed_tasks(self, record: int, stage: str) -> str:
        """Seeds task fixtures for the stages whose Due Next carries a
        `### Next Pending Task` pointer, and returns the `{TASK_IDs}` text
        Technical Plan's Review Required block needs. A no-op (empty string)
        for every other stage."""
        if stage == "Technical Plan":
            planned, needs_plan = self._fresh_number(), self._fresh_number()
            self.seed_task(record, needs_plan, "TASK-001", "OPEN", "Needs a plan")
            self.seed_task(record, planned, "TASK-002", "OPEN", "Already planned")
            self.seed_plan_comment(record, planned, "Touch core_service.py.")
            self._plan_pointer = _next_plan_task_text(needs_plan)
            return ", ".join(str(number) for number in sorted((needs_plan, planned)))
        if stage == "Implementation":
            eligible, done = self._fresh_number(), self._fresh_number()
            self.seed_task(record, eligible, "TASK-001", "OPEN", "Eligible next")
            self.seed_plan_comment(record, eligible, "Touch core_service.py.")
            self.seed_task(record, done, "TASK-002", "CLOSED", "Already shipped")
            self.seed_plan_comment(record, done, "Touch core_service.py.")
            self.seed_implementation_comment(record, done, "Shipped.")
            pr_number = self._fresh_number()
            self.seed_prs(record, [{
                "number": pr_number, "title": "impl", "url": "u", "state": "OPEN",
                "isDraft": False, "branch": "b", "mergedAt": None, "checks": "SUCCESS", "relation": "closes",
            }], register=False)
            self.register_prs(done, [pr_number])
            self._plan_pointer = _next_implementation_task_text(eligible)
        return ""

    def _expected(self, stage: str, gate: str, index: int, record: int, task_ids: str) -> str:
        body = _raw_blocks(stage)[gate][index]
        body = body.replace("{ITEM_ID}", str(record))
        body = body.replace("{TASK_IDs}", task_ids)
        body = body.replace("{NEXT_PLAN_TASK}", getattr(self, "_plan_pointer", ""))
        body = body.replace("{NEXT_IMPLEMENTATION_TASK}", getattr(self, "_plan_pointer", ""))
        return body

    def test_simple_gates_render_the_documented_text_through_the_real_cli(self):
        for stage in STAGES:
            for gate in SIMPLE_GATES:
                with self.subTest(stage=stage, gate=gate):
                    record = self._fresh_number()
                    self.seed_record(record, stage, gate)
                    task_ids = self._seed_tasks(record, stage)
                    result = self.invoke("inspect", record, "--full")
                    self.assertEqual(result.code, 0, result.stderr)
                    expected = self._expected(stage, gate, 0, record, task_ids)
                    self.assertEqual(_rendered_due_next(result.stdout), expected)

    def test_evidence_gates_fall_back_to_the_documented_text_with_no_evidence(self):
        for stage in STAGES:
            for gate in EVIDENCE_GATES:
                with self.subTest(stage=stage, gate=gate):
                    record = self._fresh_number()
                    self.seed_record(record, stage, gate)
                    task_ids = self._seed_tasks(record, stage)
                    result = self.invoke("inspect", record, "--full")
                    self.assertEqual(result.code, 0, result.stderr)
                    expected = self._expected(stage, gate, 1, record, task_ids)
                    self.assertEqual(_rendered_due_next(result.stdout), expected)

    def test_changes_required_inlines_a_real_review_comment(self):
        for stage in STAGES:
            with self.subTest(stage=stage):
                record = self._fresh_number()
                self.seed_record(record, stage, "Changes Required")
                task_ids = self._seed_tasks(record, stage)
                self._append_comment(
                    record,
                    "PDLC-REVIEW\n\n" + compose_review(stage, ReviewVerdict.CHANGES_REQUIRED, "Tighten section 2."),
                    "2026-01-05T14:30:00Z",
                )
                result = self.invoke("inspect", record, "--full")
                self.assertEqual(result.code, 0, result.stderr)
                template = self._expected(stage, "Changes Required", 0, record, task_ids)
                expected = template.replace(
                    "This evidence was posted at {when}.\n"
                    "{the newest PDLC-REVIEW or PDLC-DECISION comment's verbatim text, marker and metadata header stripped}",
                    f"This evidence was posted at {timeline_formatted_at('2026-01-05T14:30:00Z')}.\nTighten section 2.",
                )
                self.assertNotIn("{when}", expected)
                self.assertEqual(_rendered_due_next(result.stdout), expected)

    def test_stale_inlines_a_real_invalidation_comment(self):
        for stage in STAGES:
            with self.subTest(stage=stage):
                record = self._fresh_number()
                self.seed_record(record, stage, "Stale")
                task_ids = self._seed_tasks(record, stage)
                self.add_invalidation(record, stage)
                result = self.invoke("inspect", record, "--full")
                self.assertEqual(result.code, 0, result.stderr)
                template = self._expected(stage, "Stale", 0, record, task_ids)
                expected = template.replace(
                    "This evidence was posted at {when}.\n"
                    "{the newest PDLC-INVALIDATED comment's verbatim text}",
                    f"This evidence was posted at {timeline_formatted_at('2026-04-01T00:00:00Z')}.\n"
                    f"Invalidated stage: {stage}\ndetail",
                )
                self.assertNotIn("{when}", expected)
                self.assertEqual(_rendered_due_next(result.stdout), expected)

    def test_decision_required_inlines_a_real_decision_comment(self):
        for stage in STAGES:
            with self.subTest(stage=stage):
                record = self._fresh_number()
                self.seed_record(record, stage, "Decision Required")
                task_ids = self._seed_tasks(record, stage)
                self._append_comment(
                    record,
                    "PDLC-DECISION\n\n## Decision Required\n\nOn-device vs server-side snapping?",
                    "2026-03-01T09:00:00Z",
                )
                result = self.invoke("inspect", record, "--full")
                self.assertEqual(result.code, 0, result.stderr)
                template = self._expected(stage, "Decision Required", 0, record, task_ids)
                expected = template.replace(
                    "This evidence was posted at {when}.\n"
                    "{the newest PDLC-DECISION comment's verbatim text, marker stripped}",
                    f"This evidence was posted at {timeline_formatted_at('2026-03-01T09:00:00Z')}.\n"
                    "## Decision Required\n\nOn-device vs server-side snapping?",
                )
                self.assertNotIn("{when}", expected)
                self.assertEqual(_rendered_due_next(result.stdout), expected)

    def _append_comment(self, record: int, body: str, when: str) -> None:
        log = self.records_dir() / str(record) / "comments.jsonl"
        entry = {"body": body, "createdAt": when, "url": "u", "author": {"login": "reviewer"}}
        with log.open("a") as handle:
            handle.write(json.dumps(entry) + "\n")


if __name__ == "__main__":
    import unittest

    unittest.main()

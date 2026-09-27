"""Every route `pdlc next` hands out is one its target actually accepts.

`test_due_next_matrix_e2e.py` proves `pdlc next` prints the right `# Due Next`
for every curated (stage, gate). This file closes the loop on the other side:
it seeds a real file-backend record for each of those cells, lets the real
`pdlc next --work-item` route it (including any self-heal), and then drives
the entry point the route names — the owning skill's readiness command, the
command it runs, or the human command the stop asks for — and asserts that
entry point accepts the routed state instead of refusing it. A route that
names a skill whose own readiness check says "Not ready" would stall an
autonomous loop, so this is the regression that catches it.

Agent behaviour itself (whether an LLM follows the section it was handed) is
not unit-testable; `test_agent_docs.py` pins the deterministic half — that
every rendered section names exactly one real skill or real command.
"""

from __future__ import annotations

import itertools
import json

from _support import FileBackendTest
from pdlc.domain.evidence import ReviewVerdict, compose_review
from test_due_next_stages import EVIDENCE_GATES, SIMPLE_GATES, STAGES

NEXT_STAGE = {
    "Product": "UI",
    "UI": "Tasks",
    "Tasks": "Technical Plan",
    "Technical Plan": "Implementation",
    "Implementation": "Testing",
    "Testing": "Verification",
}

DECISION_EVIDENCE = (
    "## Decision Required\n\nQuestion: snap geometry on-device or server-side?\n"
    "Options: A/B.\nRecommendation: A.\nBlocks: TASK-001.\n"
)

PRODUCT_BODY = (
    "## Product\nThe shell ships.\n\n"
    "### 4. Functional requirements\n- FR-1: lands.\n\n"
    "### 5. Constraints\n- C-1: commands own mutations.\n\n"
    "## Decisions\n- Decided to ship.\n\n## Open Questions\n- none\n"
)

# Stage-owned readiness commands whose ready line is "Ready — Gate State: <gate>."
READINESS = {
    "pdlc-implement": "inspect_implement",
    "pdlc-test": "inspect_test",
    "pdlc-verify": "inspect_verify",
}


class RouteAcceptanceE2ETests(FileBackendTest):
    def setUp(self) -> None:
        super().setUp()
        self._numbers = itertools.count(7000)
        self.evidence = self.evidence_file()

    def _fresh_number(self) -> int:
        return next(self._numbers)

    def _pr(self, number: int) -> dict:
        return {
            "number": number, "title": "impl", "url": "u", "state": "OPEN", "isDraft": False,
            "branch": "b", "mergedAt": None, "checks": "SUCCESS", "relation": "closes",
        }

    def _seed(self, stage: str, gate: str) -> int:
        """A record at (stage, gate) carrying the artifacts that stage's work
        reads: an unplanned task for Technical Plan, a planned open task with a
        registered PR for Implementation, a shipped task with a registered PR
        from Testing on, the publication an approval gate needs, and the
        evidence comment an evidence gate names. A stray Approved heals onto
        the next stage, so it carries that stage's artifacts instead."""
        record = self._fresh_number()
        self.seed_record(record, stage, gate)
        works_on = NEXT_STAGE.get(stage, stage) if gate == "Approved" else stage
        if works_on == "Technical Plan":
            self.seed_task(record, self._fresh_number(), "TASK-001", "OPEN", "Needs a plan")
        elif works_on in ("Implementation", "Testing", "Verification"):
            task = self._fresh_number()
            shipped = works_on != "Implementation"
            self.seed_task(record, task, "TASK-001", "CLOSED" if shipped else "OPEN", "Core")
            self.seed_plan_comment(record, task, "Touch core_service.py.")
            if shipped:
                self.seed_implementation_comment(record, task, "Shipped.")
            pr = self._fresh_number()
            self.seed_prs(record, [self._pr(pr)], register=False)
            self.register_prs(task, [pr])
            self.register_prs(record, [pr])
        if gate in ("Approval Required", "Approved", "CI Pending") and stage != "Verification":
            # The publication (and, where the stage is reviewed after it
            # publishes, the passing review) that approval requires.
            self.seed_publication(record, stage)
        if gate == "Changes Required" and stage == "Verification":
            # Verification's own findings arrive as a structured verification
            # report; the one change request any other command raises there is
            # the CI gate's failure note.
            self._comment(record, "PDLC-REVIEW\n\nCI failed stage: Verification\n\nFailed checks: #1 (FAILURE).\n")
        elif gate == "Changes Required":
            self._comment(record, "PDLC-REVIEW\n\n" + compose_review(stage, ReviewVerdict.CHANGES_REQUIRED, "Tighten section 2."))
        elif gate == "Stale":
            self.add_invalidation(record, stage)
        elif gate == "Decision Required":
            self._comment(record, "PDLC-DECISION\n\n" + DECISION_EVIDENCE)
        return record

    def _comment(self, record: int, body: str) -> None:
        log = self.records_dir() / str(record) / "comments.jsonl"
        with log.open("a") as handle:
            handle.write(json.dumps({"body": body, "createdAt": "2026-03-01T09:00:00Z", "url": "u", "author": {"login": "reviewer"}}) + "\n")

    def _land(self, record: int, stage: str) -> object:
        """The owning skill's publishing command for a pre-publication stage."""
        if stage == "Product":
            body = self.write_file(f"product-{record}.md", PRODUCT_BODY)
            return self.invoke("post_write", "--work-item", record, "--evidence", self.evidence, "--body", body)
        if stage == "UI":
            body = self.write_file(f"ui-{record}.md", "## UI\n\nUJ-1 covers the first run.\n")
            return self.invoke("post_tasks", "--work-item", record, "--stage", "UI", "--body", body, "--evidence", self.evidence)
        if stage == "Tasks":
            task = self.write_file(f"task-{record}.md", "**Blocked by:** None\n**Type:** AFK\n**Requirements Covered:** FR-1, FR-2, C-1\n**UI Journeys:** UJ-1\n\n**Scope:**\nBuild the core.\n\n**Acceptance Criteria:**\n- [ ] FR-1 works.\n")
            manifest = self.write_file(f"tasks-{record}.json", json.dumps([
                {"id": "TASK-001", "action": "create", "title": "Build core", "body": task, "type": "ui", "covers": ["FR-1", "FR-2", "C-1", "UJ-1"]},
            ]))
            self.mark_tasks_reviewed(record, manifest)
            return self.invoke("post_tasks", "--work-item", record, "--stage", "Tasks", "--manifest", manifest, "--evidence", self.evidence)
        manifest = self.reviewed_plan_manifest(record, {"TASK-001": "Touch core_service.py."})
        return self.invoke("post_plan", "--work-item", record, "--manifest", manifest, "--evidence", self.evidence)

    def _assert_accepted(self, record: int, action: str) -> None:
        stage, gate = self.state(record)
        if action == "pdlc-post-ci":
            result = self.invoke("post_ci", record)
            self.assertEqual(result.code, 0, result.stderr)
            self.assertEqual(self.state(record), (stage, "Approval Required"))
        elif action == "pdlc-review":
            result = self.invoke("inspect_review", record)
            self.assertEqual(result.code, 0, result.stderr)
            self.assertIn("Reviewer Target", result.stdout)
            self.assertNotIn("Not ready", result.stdout)
        elif action in READINESS:
            result = self.invoke(READINESS[action], record)
            self.assertEqual(result.code, 0, result.stderr)
            self.assertIn(f"Ready — Gate State: {gate}.", result.stdout)
        elif action in ("pdlc-tasks", "pdlc-plan") or (action == "human-input" and stage == "Product"):
            result = self._land(record, stage)
            self.assertEqual(result.code, 0, result.stderr)
            self.assertEqual(self.state(record), (stage, "Approval Required"))
        elif action == "human-approval" and stage == "Verification":
            # The completion boundary: `pdlc post complete` owns it. Its gate
            # accepts the record; what remains is the completion readiness
            # findings this bare fixture deliberately lacks.
            result = self.invoke("inspect_complete", record)
            self.assertEqual(result.code, 0, result.stderr)
            self.assertNotIn("Not ready:", result.stdout)
            self.assertIn("Not ready — resolve each of these before completing:", result.stdout)
        elif action == "human-approval":
            result = self.invoke("post_approve", record, self.evidence)
            self.assertEqual(result.code, 0, result.stderr)
            self.assertEqual(self.state(record), (NEXT_STAGE[stage], "Pending"))
        elif action == "human-decision":
            manifest = self.write_file(f"decision-{record}.json", json.dumps([
                {"decision": "snap geometry on-device or server-side?", "answer": "A", "rationale": "z", "affects": "TASK-001"},
            ]))
            result = self.invoke("post_decision", record, "--manifest", manifest)
            self.assertEqual(result.code, 0, result.stderr)
            self.assertEqual(self.state(record), (stage, "Changes Required"))
        else:
            self.fail(f"{stage} / {gate}: `pdlc next` routed {action!r}, which no entry point accepts")

    def test_every_route_is_accepted_by_the_entry_point_it_names(self):
        for stage in STAGES:
            for gate in SIMPLE_GATES + EVIDENCE_GATES:
                with self.subTest(stage=stage, gate=gate):
                    record = self._seed(stage, gate)
                    routed = self.next("--work-item", record)
                    self.assertEqual(routed.code, 0, routed.stderr)
                    action = routed.front_matter("action") or ""
                    self.assertNotIn(action, ("blocked", "none", ""))
                    self._assert_accepted(record, action)


if __name__ == "__main__":
    import unittest

    unittest.main()

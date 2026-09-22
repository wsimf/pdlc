"""`pdlc prompt plan-reviewer` renders the brief for a pass's delivery-task plans."""

from __future__ import annotations

import json

from tests._support import FileBackendTest


class PromptPlanReviewerTest(FileBackendTest):
    def _seeded(self):
        self.seed_record(60, "Technical Plan", "Pending", slug="record-60")
        self.seed_task(
            60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work",
            body="## Scope\nBuild the seam.\n\nCovers FR-1.\n",
        )

    def test_a_plan_carries_the_task_body_and_proposed_plan(self):
        self._seeded()
        plan = self.write_file("plan.md", "Own src/a.py; add retry with backoff.")
        manifest = self.write_file("plan-manifest.json", json.dumps([{"id": "TASK-001", "plan": plan}]))
        result = self.invoke("prompt_plan_reviewer", 60, "--manifest", manifest)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Review the supplied delivery-task plans", result.stdout)
        self.assertIn("### WORK-60-TASK-001 — [CORE] Core work", result.stdout)
        self.assertIn("Build the seam.", result.stdout)
        self.assertIn("Own src/a.py; add retry with backoff.", result.stdout)
        self.assertIn("none, first review", result.stdout)
        self.assertNotIn("{{", result.stdout)

    def test_an_existing_plan_is_carried_alongside_the_proposal(self):
        self._seeded()
        self.seed_plan_comment(60, 601, "Original plan text.")
        plan = self.write_file("plan.md", "Revised plan.")
        manifest = self.write_file("plan-manifest.json", json.dumps([{"id": "TASK-001", "plan": plan}]))
        result = self.invoke("prompt_plan_reviewer", 60, "--manifest", manifest)
        self.assertIn("Original plan text.", result.stdout)
        self.assertIn("Revised plan.", result.stdout)

    def test_findings_render_for_a_re_review(self):
        self._seeded()
        plan = self.write_file("plan.md", "Plan.")
        manifest = self.write_file("plan-manifest.json", json.dumps([{"id": "TASK-001", "plan": plan}]))
        result = self.invoke("prompt_plan_reviewer", 60, "--manifest", manifest, "--findings", "text:resolve the spike")
        self.assertIn("resolve the spike", result.stdout)
        self.assertNotIn("none, first review", result.stdout)

    def test_refuses_an_unknown_task_id(self):
        self._seeded()
        plan = self.write_file("plan.md", "Plan.")
        manifest = self.write_file("plan-manifest.json", json.dumps([{"id": "TASK-999", "plan": plan}]))
        result = self.invoke("prompt_plan_reviewer", 60, "--manifest", manifest)
        self.assertNotEqual(result.code, 0)
        self.assertIn("TASK-999", result.stderr)

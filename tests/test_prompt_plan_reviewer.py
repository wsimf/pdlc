"""`pdlc prompt plan-reviewer` renders the brief for a pass's delivery-task plans."""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests._support import FileBackendTest


class PromptPlanReviewerTest(FileBackendTest):
    def _seeded(self):
        self.seed_record(60, "Technical Plan", "Pending", slug="record-60")
        self.seed_task(
            60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work",
            body="## Scope\nBuild the seam.\n\nCovers FR-1.\n",
        )

    def _file(self, manifest: str) -> Path:
        return Path(json.loads(Path(manifest).read_text())[0]["file"]).resolve()

    def test_a_plan_is_named_by_its_file_not_inlined(self):
        self._seeded()
        manifest = self.plan_manifest(60, {"TASK-001": "Own src/a.py; add retry with backoff."})
        result = self.invoke("prompt_plan_reviewer", "--inline", 60, "--manifest", manifest)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Review the supplied delivery-task plans", result.stdout)
        self.assertIn(f"- `TASK-001` — [CORE] Core work (new plan): `{self._file(manifest)}`", result.stdout)
        self.assertIn("Do not edit the manifest or any task file.", result.stdout)
        self.assertNotIn("Own src/a.py", result.stdout)
        self.assertNotIn("Prior findings", result.stdout)
        self.assertNotIn("{{", result.stdout)

    def test_a_replaced_plan_carries_the_recorded_one(self):
        self._seeded()
        self.seed_plan_comment(60, 601, "Original plan text.")
        manifest = self.plan_manifest(60, {"TASK-001": "Revised plan."})
        result = self.invoke("prompt_plan_reviewer", "--inline", 60, "--manifest", manifest)
        self.assertIn("(replaces its recorded plan)", result.stdout)
        self.assertIn("--- BEGIN RECORDED PLAN ---\n\nOriginal plan text.\n\n--- END RECORDED PLAN ---", result.stdout)
        self.assertNotIn("Revised plan.", result.stdout)

    def test_an_unchanged_recorded_plan_is_marked_and_not_repeated(self):
        self._seeded()
        self.seed_plan_comment(60, 601, "Original plan text.")
        manifest = self.plan_manifest(60, {})
        result = self.invoke("prompt_plan_reviewer", "--inline", 60, "--manifest", manifest)
        self.assertIn("(recorded plan, unchanged)", result.stdout)
        self.assertNotIn("Recorded plans being replaced", result.stdout)

    def test_findings_render_for_a_re_review(self):
        self._seeded()
        manifest = self.plan_manifest(60, {"TASK-001": "Plan."})
        result = self.invoke("prompt_plan_reviewer", "--inline", 60, "--manifest", manifest, "--findings", "text:resolve the spike")
        self.assertIn("### Prior findings", result.stdout)
        self.assertIn("resolve the spike", result.stdout)

    def test_a_malformed_task_file_points_at_the_dry_run(self):
        self._seeded()
        manifest = self.plan_manifest(60, {"TASK-001": "Plan."})
        self._file(manifest).write_text("just a plan\n")
        result = self.invoke("prompt_plan_reviewer", "--inline", 60, "--manifest", manifest)
        self.assertEqual(result.code, 1)
        self.assertIn("--dry-run", result.stderr)

    def test_a_hand_written_manifest_is_refused(self):
        self._seeded()
        plan = self.write_file("plan.md", "Plan.")
        manifest = self.write_file("plan-manifest.json", json.dumps([{"id": "TASK-001", "plan": plan}]))
        result = self.invoke("prompt_plan_reviewer", "--inline", 60, "--manifest", manifest)
        self.assertNotEqual(result.code, 0)
        self.assertIn("is not a plan manifest pdlc generated", result.stderr)

    def test_a_reviewer_edit_is_restored_before_the_next_review(self):
        self._seeded()
        manifest = self.reviewed_plan_manifest(60, {"TASK-001": "Plan."})
        task_file = self._file(manifest)
        reviewed = task_file.read_text()
        self.write_plan(task_file, "Edited by the reviewer.")
        result = self.invoke("prompt_plan_reviewer", "--inline", 60, "--manifest", manifest)
        self.assertEqual(result.code, 1)
        self.assertIn("pdlc restored each file to the version the reviewer was given", result.stderr)
        self.assertEqual(task_file.read_text(), reviewed)
        # Restored, the same files are handed to a fresh review.
        self.assertEqual(self.invoke("prompt_plan_reviewer", "--inline", 60, "--manifest", manifest).code, 0)

    def test_a_new_planning_pass_keeps_the_planners_edits(self):
        self._seeded()
        manifest = self.reviewed_plan_manifest(60, {"TASK-001": "Plan."})
        brief = self.invoke("prompt_tech_planner", "--inline", 60, "--current-plan-manifest-path", manifest)
        self.assertEqual(brief.code, 0, brief.stderr)
        self.write_plan(self._file(manifest), "Revised by the planner.")
        self.assertEqual(self.invoke("prompt_plan_reviewer", "--inline", 60, "--manifest", manifest).code, 0)
        self.assertIn("Revised by the planner.", self._file(manifest).read_text())

    def test_without_a_manifest_the_recorded_plans_are_reviewed_as_they_stand(self):
        self._seeded()
        self.seed_plan_comment(60, 601, "Published without review.")
        result = self.invoke("prompt_plan_reviewer", "--inline", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("(recorded plan, unchanged)", result.stdout)
        manifest = re.search(r"the manifest at `([^`]+)`", result.stdout).group(1)
        self.assertIn("Published without review.", self._file(manifest).read_text())
        # The generated files were handed to the reviewer, so they land.
        landed = self.invoke("post_plan", "--work-item", 60, "--manifest", manifest, "--evidence", self.evidence_file())
        self.assertEqual(landed.code, 0, landed.stderr)

    def _findings_path(self, stdout: str) -> Path:
        return Path(re.search(r"Write your review into `([^`]+)`", stdout).group(1))

    def test_the_brief_writes_a_findings_outline_for_the_reviewer(self):
        self._seeded()
        manifest = self.plan_manifest(60, {"TASK-001": "Plan."})
        result = self.invoke("prompt_plan_reviewer", "--inline", 60, "--manifest", manifest)
        findings = self._findings_path(result.stdout)
        self.assertEqual(findings.name, "pdlc-technical-plan-findings.md")
        outline = findings.read_text(encoding="utf-8")
        self.assertIn("Technical Plan review complete.", outline)
        self.assertIn("Verdict: <Needs Revision|Ready to Land>", outline)

    def test_a_re_review_reads_the_findings_file_before_it_is_reset(self):
        self._seeded()
        manifest = self.plan_manifest(60, {"TASK-001": "Plan."})
        findings = self._findings_path(self.invoke("prompt_plan_reviewer", "--inline", 60, "--manifest", manifest).stdout)
        findings.write_text("TASK-001 skips the cache.\nVerdict: Needs Revision\n", encoding="utf-8")
        rereview = self.invoke("prompt_plan_reviewer", "--inline", 60, "--manifest", manifest, "--findings", str(findings))
        self.assertEqual(rereview.code, 0, rereview.stderr)
        self.assertIn("TASK-001 skips the cache.", rereview.stdout)
        self.assertIn("Verdict: <Needs Revision|Ready to Land>", findings.read_text(encoding="utf-8"))

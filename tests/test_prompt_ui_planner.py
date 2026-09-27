"""`pdlc prompt ui-planner` renders the brief for a record's UI section."""

from __future__ import annotations

import re
from pathlib import Path

from pdlc.domain.model import remove_section
from tests._support import BODY_DEFAULT, FileBackendTest

NO_UI_BODY = remove_section(BODY_DEFAULT, "UI")


class PromptUiPlannerTest(FileBackendTest):
    def _fragment_path(self, stdout: str) -> Path:
        match = re.search(r"Revise the UI section at `([^`]+)`", stdout)
        self.assertIsNotNone(match, stdout)
        return Path(match.group(1))

    def test_a_first_pass_carries_no_stale_reason_or_tasks(self):
        self.seed_record(60, "UI", "Pending", slug="record-60", body=NO_UI_BODY)
        result = self.invoke("prompt_ui_planner", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Author the `UI` section for this PDLC record", result.stdout)
        self.assertIn("No UI section exists yet. Author it from the parent work item above.", result.stdout)
        self.assertIn("FR-1: The record lands.", result.stdout)
        self.assertIn("`Gate State`: `Pending`.", result.stdout)
        for absent in ("Revise the UI section", "### Invalidation reason", "### Change requests",
                       "### Driver follow-up", "Existing task tree", "{{"):
            self.assertNotIn(absent, result.stdout)

    def test_a_published_section_is_revised_from_a_generated_copy(self):
        self.seed_record(60, "UI", "Pending", slug="record-60")
        result = self.invoke("prompt_ui_planner", 60)
        self.assertEqual(result.code, 0, result.stderr)
        fragment = self._fragment_path(result.stdout)
        self.assertEqual(fragment.read_text(encoding="utf-8").strip(), "UJ-1 covers the first run.")
        # The fragment is the only copy of the section the planner sees.
        self.assertNotIn("## UI\n", result.stdout)
        self.assertNotIn("UJ-1 covers the first run.", result.stdout)
        self.assertIn("FR-1: The record lands.", result.stdout)
        self.assertNotIn("No UI section exists yet", result.stdout)

    def test_every_gate_with_a_published_section_revises_it(self):
        for number, gate in enumerate(("Stale", "Changes Required", "Approval Required"), 61):
            with self.subTest(gate=gate):
                self.seed_record(number, "UI", gate, slug=f"record-{number}")
                result = self.invoke("prompt_ui_planner", number)
                self.assertEqual(result.code, 0, result.stderr)
                self._fragment_path(result.stdout)
                self.assertNotIn("No UI section exists yet", result.stdout)

    def test_a_stale_record_carries_its_invalidation_reason(self):
        self.seed_record(60, "UI", "Stale", slug="record-60")
        self.add_invalidation(60, "UI")
        result = self.invoke("prompt_ui_planner", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("`Gate State`: `Stale`.", result.stdout)
        self.assertIn("### Invalidation reason", result.stdout)
        self.assertIn("Reconcile the section against it.\n\ndetail", result.stdout)

    def test_a_stale_record_with_no_recorded_reason_omits_the_section(self):
        self.seed_record(60, "UI", "Stale", slug="record-60")
        result = self.invoke("prompt_ui_planner", 60)
        self.assertNotIn("### Invalidation reason", result.stdout)

    def test_an_invalidation_for_another_stage_is_not_mistaken_for_this_ones(self):
        self.seed_record(60, "UI", "Stale", slug="record-60")
        self.add_invalidation(60, "Implementation")
        result = self.invoke("prompt_ui_planner", 60)
        self.assertNotIn("### Invalidation reason", result.stdout)

    def test_change_requests_against_the_ui_stage_are_carried(self):
        self.seed_record(60, "UI", "Changes Required", slug="record-60")
        self.add_rework_review(60, stage="UI")
        result = self.invoke("prompt_ui_planner", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("### Change requests", result.stdout)
        self.assertIn("--- BEGIN CHANGE REQUESTS ---\n\n### Change request", result.stdout)
        self.assertIn("## Findings\n\n- detail", result.stdout)
        self._fragment_path(result.stdout)

    def test_existing_delivery_tasks_render_as_the_task_tree(self):
        self.seed_record(60, "UI", "Stale", slug="record-60")
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work")
        result = self.invoke("prompt_ui_planner", 60)
        self.assertIn("`WORK-60-TASK-001` [CORE] Core work (OPEN)", result.stdout)

    def test_a_supplied_draft_replaces_the_published_section(self):
        self.seed_record(60, "UI", "Stale", slug="record-60")
        self.add_invalidation(60, stage="UI")
        current_ui = self.write_file("current-ui.md", "## UI\n\nUJ-1 fixed draft.\n")
        result = self.invoke(
            "prompt_ui_planner", 60,
            "--current-journeys-path", current_ui,
            "--follow-up", "text:revisit UJ-2's offline flow",
        )
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(self._fragment_path(result.stdout), Path(current_ui).resolve())
        self.assertIn("### Driver follow-up", result.stdout)
        self.assertIn("revisit UJ-2's offline flow", result.stdout)
        self.assertIn("### Invalidation reason", result.stdout)
        self.assertNotIn("UJ-1 covers the first run.", result.stdout)

    def test_rework_requires_an_existing_fragment_and_follow_up_together(self):
        self.seed_record(60, "UI", "Pending", slug="record-60")
        current_ui = self.write_file("current-ui.md", "## UI\n")
        follow_up_only = self.invoke("prompt_ui_planner", 60, "--follow-up", "text:revise")
        fragment_only = self.invoke("prompt_ui_planner", 60, "--current-journeys-path", current_ui)
        missing_fragment = self.invoke(
            "prompt_ui_planner", 60,
            "--current-journeys-path", str(self.work / "missing.md"),
            "--follow-up", "text:revise",
        )
        self.assertNotEqual(follow_up_only.code, 0)
        self.assertIn("must be supplied together", follow_up_only.stderr)
        self.assertNotEqual(fragment_only.code, 0)
        self.assertIn("must be supplied together", fragment_only.stderr)
        self.assertNotEqual(missing_fragment.code, 0)
        self.assertIn("does not exist", missing_fragment.stderr)

    def test_refuses_when_status_is_not_ui(self):
        self.seed_record(60, "Tasks", "Pending", slug="record-60")
        result = self.invoke("prompt_ui_planner", 60)
        self.assertNotEqual(result.code, 0)
        self.assertIn("not UI", result.stderr)

    def test_the_brief_names_no_pdlc_command_or_stage_marker(self):
        self.seed_record(60, "UI", "Pending", slug="record-60")
        result = self.invoke("prompt_ui_planner", 60)
        for leak in ("pdlc inspect", "pdlc post", "Gate State\n"):
            self.assertNotIn(leak, result.stdout)

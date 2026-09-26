"""`pdlc prompt ui-planner` renders the brief for a record's UI section."""

from __future__ import annotations

from pathlib import Path

from tests._support import FileBackendTest


class PromptUiPlannerTest(FileBackendTest):
    def test_a_first_pass_carries_no_stale_reason_or_tasks(self):
        self.seed_record(60, "UI", "Pending", slug="record-60")
        result = self.invoke("prompt_ui_planner", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Author the `UI` section for this PDLC record", result.stdout)
        self.assertIn("We haven't done UI planning before. This is the first time", result.stdout)
        self.assertIn("FR-1: The record lands.", result.stdout)
        self.assertIn("`Gate State`: `Pending`.", result.stdout)
        self.assertNotIn("## Driver follow-up", result.stdout)
        self.assertNotIn("n/a — first pass", result.stdout)
        self.assertNotIn("Existing task tree", result.stdout)
        self.assertNotIn("{{", result.stdout)

    def test_a_stale_record_carries_its_invalidation_reason(self):
        self.seed_record(60, "UI", "Stale", slug="record-60")
        self.add_invalidation(60, "UI")
        result = self.invoke("prompt_ui_planner", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("`Gate State`: `Stale`.", result.stdout)
        self.assertIn("detail", result.stdout)
        self.assertNotIn("n/a — first pass", result.stdout)

    def test_a_stale_record_with_no_recorded_reason_says_so(self):
        self.seed_record(60, "UI", "Stale", slug="record-60")
        result = self.invoke("prompt_ui_planner", 60)
        self.assertNotIn("stale — no invalidation comment recorded", result.stdout)

    def test_an_invalidation_for_another_stage_is_not_mistaken_for_this_ones(self):
        self.seed_record(60, "UI", "Stale", slug="record-60")
        self.add_invalidation(60, "Implementation")
        result = self.invoke("prompt_ui_planner", 60)
        self.assertNotIn("stale — no invalidation comment recorded", result.stdout)

    def test_existing_delivery_tasks_render_as_the_task_tree(self):
        self.seed_record(60, "UI", "Stale", slug="record-60")
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work")
        result = self.invoke("prompt_ui_planner", 60)
        self.assertIn("`WORK-60-TASK-001` [CORE] Core work (OPEN)", result.stdout)

    def test_driver_follow_up_is_carried_verbatim(self):
        self.seed_record(60, "UI", "Pending", slug="record-60")
        current_ui = self.write_file("current-ui.md", "## UI\n\nUJ-1 current draft.\n")
        result = self.invoke(
            "prompt_ui_planner", 60,
            "--current-journies-path", current_ui,
            "--follow-up", "text:revisit UJ-2's offline flow",
        )
        self.assertIn("revisit UJ-2's offline flow", result.stdout)
        self.assertIn(str(Path(current_ui).resolve()), result.stdout)
        self.assertIn("Revise it to apply the driver follow-up below", result.stdout)

    def test_rework_requires_an_existing_fragment_and_follow_up_together(self):
        self.seed_record(60, "UI", "Pending", slug="record-60")
        current_ui = self.write_file("current-ui.md", "## UI\n")
        follow_up_only = self.invoke("prompt_ui_planner", 60, "--follow-up", "text:revise")
        fragment_only = self.invoke("prompt_ui_planner", 60, "--current-journies-path", current_ui)
        missing_fragment = self.invoke(
            "prompt_ui_planner", 60,
            "--current-journies-path", str(self.work / "missing.md"),
            "--follow-up", "text:revise",
        )
        self.assertNotEqual(follow_up_only.code, 0)
        self.assertIn("must be supplied together", follow_up_only.stderr)
        self.assertNotEqual(fragment_only.code, 0)
        self.assertIn("must be supplied together", fragment_only.stderr)
        self.assertNotEqual(missing_fragment.code, 0)
        self.assertIn("does not exist", missing_fragment.stderr)

    def test_stale_fix_with_unpublished_fragment_keeps_both_inputs_visible(self):
        self.seed_record(60, "UI", "Stale", slug="record-60")
        self.seed_publication(60, "UI")
        self.add_invalidation(60, stage="UI")
        current_ui = self.write_file("current-ui.md", "## UI\n\nUJ-1 fixed draft.\n")
        result = self.invoke(
            "prompt_ui_planner", 60,
            "--current-journies-path", current_ui,
            "--follow-up", "text:also clarify the retry journey",
        )
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("invalidated for this reason:\ndetail", result.stdout)
        self.assertIn(f"An unpublished UI revision is at `{Path(current_ui).resolve()}`", result.stdout)
        self.assertIn("Preserve its fixes for the invalidation reason", result.stdout)
        self.assertIn("also clarify the retry journey", result.stdout)

    def test_first_stale_fix_uses_published_section_and_invalidation_reason(self):
        self.seed_record(60, "UI", "Stale", slug="record-60")
        self.seed_publication(60, "UI")
        self.add_invalidation(60, stage="UI")
        result = self.invoke("prompt_ui_planner", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("previously published UI section", result.stdout)
        self.assertIn("invalidated for this reason:\ndetail", result.stdout)
        self.assertIn("This is the first rework pass", result.stdout)
        self.assertNotIn("unpublished UI revision", result.stdout)

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

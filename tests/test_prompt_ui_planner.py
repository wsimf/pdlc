"""`pdlc prompt ui-planner` renders the brief for a record's UI section."""

from __future__ import annotations

from tests._support import FileBackendTest


class PromptUiPlannerTest(FileBackendTest):
    def test_a_first_pass_carries_no_stale_reason_or_tasks(self):
        self.seed_record(60, "UI", "Pending", slug="record-60")
        result = self.invoke("prompt_ui_planner", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Author the `UI` section for this PDLC record", result.stdout)
        self.assertIn("No ux-design skill is configured for this project.", result.stdout)
        self.assertIn("`60` — full body:", result.stdout)
        self.assertIn("FR-1: The record lands.", result.stdout)
        self.assertIn("`Gate State`: `Pending`.", result.stdout)
        self.assertIn("n/a — first pass", result.stdout)
        self.assertIn("Existing task tree, if any: none.", result.stdout)
        self.assertIn("## Driver follow-up\n\nnone", result.stdout)
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
        self.assertIn("stale — no invalidation comment recorded", result.stdout)

    def test_an_invalidation_for_another_stage_is_not_mistaken_for_this_ones(self):
        self.seed_record(60, "UI", "Stale", slug="record-60")
        self.add_invalidation(60, "Implementation")
        result = self.invoke("prompt_ui_planner", 60)
        self.assertIn("stale — no invalidation comment recorded", result.stdout)

    def test_existing_delivery_tasks_render_as_the_task_tree(self):
        self.seed_record(60, "UI", "Stale", slug="record-60")
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work")
        result = self.invoke("prompt_ui_planner", 60)
        self.assertIn("`WORK-60-TASK-001` [CORE] Core work (OPEN)", result.stdout)

    def test_driver_follow_up_is_carried_verbatim(self):
        self.seed_record(60, "UI", "Pending", slug="record-60")
        result = self.invoke("prompt_ui_planner", 60, "--follow-up", "text:revisit UJ-2's offline flow")
        self.assertIn("revisit UJ-2's offline flow", result.stdout)

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

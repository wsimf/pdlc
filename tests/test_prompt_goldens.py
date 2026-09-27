"""Whole-brief goldens: the assembled output is the contract a sub-agent acts
on, so its wording, section order, and spacing are checked in full rather than
sampled with substring assertions.

A diff here is the point — it makes a prompt change reviewable as a prompt
change. Regenerate after an intended edit with:

    PDLC_UPDATE_GOLDENS=1 uv run python -m unittest tests.test_prompt_goldens

then read the resulting diff before committing it.
"""

from __future__ import annotations

from pathlib import Path

from tests._goldens import GoldenMixin
from tests._prompts import PromptHarness


class PromptGoldenTest(GoldenMixin, PromptHarness):
    GOLDENS = Path(__file__).parent / "fixtures" / "prompts"

    def _implementer(self):
        return self.invoke("prompt_task_implementer", 60)

    def _reviewer(self):
        return self.invoke("prompt_task_reviewer", 60, "--commits", "HEAD~1..HEAD")

    def _test_writer(self, *extra: str):
        return self.invoke(
            "prompt_task_test_writer", 60, "--commits", "HEAD~1..HEAD",
            "--report", "text:Built the seam; criteria verified.",
            "--traceability", "text:FR-1 -> loads -> src/a.py",
            *extra,
        )

    def _ui_planner(self, *extra: str):
        return self.invoke("prompt_ui_planner", 60, *extra)

    # --- implement ---

    def test_implement_first_task(self):
        self._eligible_task()
        self.assertGolden("implement-first-task", self._implementer())

    def test_implement_with_verify_step(self):
        self._eligible_task()
        self._build_run("build-run-ios")
        self.assertGolden("implement-with-verify", self._implementer())

    def test_implement_later_task_with_upstream(self):
        self._second_task_eligible()
        self.assertGolden("implement-later-task", self._implementer())

    def test_implement_after_invalidation(self):
        self._invalidated_task()
        self.assertGolden("implement-invalidated", self._implementer())

    def test_implement_with_a_requirement_the_record_lacks(self):
        self._eligible_task(body="## Scope\nCovers FR-9.\n\n## Acceptance criteria\n- it works\n")
        self.assertGolden("implement-missing-requirement", self._implementer())

    def test_implement_from_red_checks_alone(self):
        self._implemented_stack()
        self._prs([
            {"number": 40, "title": "t", "url": "u40", "state": "OPEN", "isDraft": False,
             "branch": "b", "mergedAt": None, "checks": "FAILURE"},
        ])
        self.assertGolden("implement-red-checks", self._implementer())

    # --- pr-fix ---

    def test_pr_fix_single_thread(self):
        self._implemented_stack()
        self._threads([
            {"pr": 40, "author": "reviewer", "path": "src/a.py", "line": 4, "body": "drops retry", "url": "u"},
        ])
        self.assertGolden("pr-fix-single-thread", self._implementer())

    def test_pr_fix_several_threads(self):
        self._implemented_stack()
        self._threads([
            {"pr": 40, "author": "reviewer", "path": "src/a.py", "line": 4, "body": "drops retry", "url": "u1"},
            {"pr": 40, "author": "other", "path": "src/b.py", "line": 12, "body": "name is misleading", "url": "u2"},
        ])
        self.assertGolden("pr-fix-several-threads", self._implementer())

    def test_pr_fix_with_failing_checks(self):
        self._implemented_stack()
        self._threads([{"pr": 40, "author": "r", "path": "a", "line": 1, "body": "b", "url": "u"}])
        self._prs([
            {"number": 40, "title": "t", "url": "u40", "state": "OPEN", "isDraft": False,
             "branch": "b", "mergedAt": None, "checks": "FAILURE"},
        ])
        self.assertGolden("pr-fix-failing-checks", self._implementer())

    # --- triage ---

    def test_triage_two_task_stack(self):
        self._implemented_stack()
        self.add_rework_review(60)
        self.assertGolden("triage-two-task-stack", self._implementer())

    def test_triage_single_task_stack(self):
        self.seed_record(60, "Implementation", "Changes Required", slug="record-60")
        self.seed_task(60, 601, "TASK-001", "CLOSED", "WORK-60-TASK-001 [CORE] First")
        self._plan(60, 601)
        self.seed_implementation_comment(60, 601, "Shipped.")
        self.register_prs(601, [40])
        self.add_rework_review(60)
        self.assertGolden("triage-single-task-stack", self._implementer())

    # --- review ---

    def test_review_first_task(self):
        self._eligible_task()
        self._git()
        self.assertGolden("review-first-task", self._reviewer())

    def test_review_later_task_with_dependencies(self):
        self._second_task_eligible()
        self._git()
        self.assertGolden("review-later-task", self._reviewer())

    def test_review_of_a_larger_diff(self):
        self._eligible_task()
        self._git(
            stat="abc1234 impl\n 3 files changed, 40 insertions(+), 2 deletions(-)",
            diff="diff --git a/src/a.py b/src/a.py\n@@\n+added line\n",
        )
        self.assertGolden("review-larger-diff", self._reviewer())

    # --- test ---

    def test_test_writer_without_findings(self):
        self._eligible_task()
        self._git()
        self.assertGolden("test-no-findings", self._test_writer())

    def test_test_writer_with_accepted_findings(self):
        self._eligible_task()
        self._git()
        self.assertGolden("test-with-findings", self._test_writer("--findings", "text:Naming nit on the loader."))

    def test_test_writer_with_a_configured_authoring_skill(self):
        self._eligible_task()
        self._git()
        self._capabilities(**{"test-authoring": "acme-test-writer"})
        self.assertGolden("test-with-authoring-skill", self._test_writer())

    def test_test_writer_with_authoring_skill_and_framework(self):
        self._eligible_task()
        self._git()
        self._capabilities(**{"test-authoring": "acme-test-writer", "test-framework": "swift-testing"})
        self.assertGolden("test-with-framework", self._test_writer())

    # --- acceptance test ---

    def _acceptance(self, *extra: str):
        return self.invoke(
            "prompt_acceptance_test_writer", 60, "--traceability", "text:FR-1 -> loads -> src/a.py", *extra,
        )

    def test_acceptance_first_pass(self):
        self._testing_stack()
        self.assertGolden("acceptance-test-first-pass", self._acceptance())

    def test_acceptance_with_findings(self):
        self._testing_stack(gate="Changes Required")
        self.add_rework_review(60, stage="Testing")
        self._capabilities(**{"test-authoring": "acme-test-writer", "test-framework": "swift-testing"})
        self.assertGolden(
            "acceptance-test-with-findings",
            self._acceptance("--findings", "text:unit-tests: assertion failed at test_a.py:12"),
        )

    # --- task planner ---

    def test_task_planner_first_pass(self):
        self._tasks_stage_pending()
        self.assertGolden("task-planner-first-pass", self.invoke("prompt_task_planner", 60))

    def test_task_planner_unpublished_revision_with_follow_up(self):
        self._tasks_stage_pending()
        manifest = self.write_file("current-tasks.json", '[{"id":"TASK-001","body":"task-001.md"}]\n')
        self.write_file("task-001.md", "## Scope\nCurrent unpublished task.\n")
        self.assertGolden(
            "task-planner-unpublished-follow-up",
            self.invoke(
                "prompt_task_planner", 60,
                "--current-tasks-manifest-path", manifest,
                "--follow-up", "text:split the export task in two",
            ),
        )

    def test_task_planner_stale_with_existing_tree(self):
        self._tasks_stage_stale_with_existing_tree()
        self.assertGolden("task-planner-stale", self.invoke("prompt_task_planner", 60))

    def test_task_planner_stale_with_unpublished_revision_and_follow_up(self):
        self._tasks_stage_stale_with_existing_tree()
        self.seed_publication(60, "Tasks")
        manifest = self.write_file("current-tasks.json", '[{"id":"TASK-001","body":"task-001.md"}]\n')
        self.write_file("task-001.md", "## Scope\nInvalidation fixes already applied.\n")
        self.assertGolden(
            "task-planner-stale-unpublished-follow-up",
            self.invoke(
                "prompt_task_planner", 60,
                "--current-tasks-manifest-path", manifest,
                "--follow-up", "text:also split the export task in two",
            ),
        )

    # --- UI planner ---

    def test_ui_planner_first_pass(self):
        self.seed_record(60, "UI", "Pending", slug="record-60")
        self.assertGolden("ui-planner-first-pass", self._ui_planner())

    def test_ui_planner_unpublished_revision_with_follow_up(self):
        self.seed_record(60, "UI", "Pending", slug="record-60")
        fragment = self.write_file("current-ui.md", "## UI\n\nUJ-1 current draft.\n")
        self.assertGolden(
            "ui-planner-unpublished-follow-up",
            self._ui_planner(
                "--current-journeys-path", fragment,
                "--follow-up", "text:revisit UJ-2's offline flow",
            ),
        )

    def test_ui_planner_stale_published_section_on_first_rework_pass(self):
        self.seed_record(60, "UI", "Stale", slug="record-60")
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work")
        self.seed_publication(60, "UI")
        self.add_invalidation(60, stage="UI")
        self.assertGolden("ui-planner-stale-first-rework", self._ui_planner())

    def test_ui_planner_stale_unpublished_revision_with_follow_up(self):
        self.seed_record(60, "UI", "Stale", slug="record-60")
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work")
        self.seed_publication(60, "UI")
        self.add_invalidation(60, stage="UI")
        fragment = self.write_file("current-ui.md", "## UI\n\nUJ-1 invalidation fixes applied.\n")
        self.assertGolden(
            "ui-planner-stale-unpublished-follow-up",
            self._ui_planner(
                "--current-journeys-path", fragment,
                "--follow-up", "text:also clarify the retry journey",
            ),
        )

    # --- tech planner ---

    def test_tech_planner_first_pass(self):
        self._plan_stage()
        self.assertGolden("tech-planner-first-pass", self.invoke("prompt_tech_planner", 60))

    def test_tech_planner_stale_with_follow_up(self):
        self._plan_stage(gate="Stale")
        self.add_invalidation(60, stage="Technical Plan")
        self.assertGolden(
            "tech-planner-stale",
            self.invoke("prompt_tech_planner", 60, "--follow-up", "text:re-spike TASK-001 against the cache"),
        )

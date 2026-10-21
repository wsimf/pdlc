"""Whole-brief goldens: the assembled output is the contract a sub-agent acts
on, so its wording, section order, and spacing are checked in full rather than
sampled with substring assertions.

A diff here is the point — it makes a prompt change reviewable as a prompt
change. Regenerate after an intended edit with:

    PDLC_UPDATE_GOLDENS=1 uv run python -m unittest tests.test_prompt_goldens

then read the resulting diff before committing it.
"""

from __future__ import annotations

import json
from pathlib import Path

from pdlc.domain.model import remove_section
from pdlc.domain.product_draft import Stamp, fingerprint, product_content
from pdlc.internal import product_draft
from tests._goldens import GoldenMixin
from tests._prompts import PromptHarness
from tests._support import APPROACH_DEFAULT, BODY_DEFAULT

NO_UI_BODY = remove_section(BODY_DEFAULT, "UI")

DRAFT = "## Product\n\n### Functional requirements\n- FR-1: The route sheet opens at the medium detent.\n\n## Decisions\n- d\n"
WITH_APPROACH = DRAFT.replace("## Decisions", APPROACH_DEFAULT + "\n## Decisions")
FINDING = "- F1 [P1] FR-1 — \"medium detent\"\n  Evidence: no detent API in src/ui/Sheet\n  Recommendation: name the sheet's detent\n"


class PromptGoldenTest(GoldenMixin, PromptHarness):
    GOLDENS = Path(__file__).parent / "fixtures" / "prompts"

    def _implementer(self, *extra: str):
        return self.invoke("prompt_task_implementer", "--inline", 60, *extra)

    def _reviewer(self):
        return self.invoke("prompt_task_reviewer", "--inline", 60, "--commits", "HEAD~1..HEAD")

    def _test_writer(self, *extra: str):
        return self.invoke(
            "prompt_task_test_writer", "--inline", 60, "--commits", "HEAD~1..HEAD",
            "--report", "text:Built the seam; criteria verified.",
            "--traceability", "text:FR-1 -> loads -> src/a.py",
            *extra,
        )

    def _attach(self) -> None:
        """Attach a described mockup and an undescribed screenshot to record 60."""
        from pdlc.hosts.lib.file.attachment_host import FileAttachmentHost

        host = FileAttachmentHost()
        host.save_for("60", self.write_file("nav.png", "nav mockup\n"), "Primary navigation mockup")
        host.save_for("60", self.write_file("empty.png", "empty state\n"))

    def _ui_planner(self, *extra: str):
        return self.invoke("prompt_ui_planner", "--inline", 60, *extra)

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


    def test_implement_with_review_findings(self):
        self._eligible_task()
        self.assertGolden("implement-review-findings", self._implementer(
            "--findings", self._review(implementation="- F1 [P1] [blocking] src/a.py:4 — drops retry"),
        ))

    def test_implement_with_uncommitted_work(self):
        self._eligible_task()
        self._uncommitted(" M src/a.py\n?? src/b.py")
        self.assertGolden("implement-uncommitted-work", self._implementer())

    def test_implement_after_upstream_changes(self):
        self._eligible_task()
        self._log("PDLC-IMPLEMENTATION\n\nshipped")
        self._patch_back_to_ui("FR-1 now lands atomically")
        self.assertGolden("implement-upstream-changes", self._implementer())

    def test_implement_ui_task_lists_attachments(self):
        self.seed_record(60, "Implementation", "Pending", slug="record-60")
        self.seed_task(
            60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [UI] Screen",
            body="## Scope\nBuild the screen.\n\nCovers FR-1.\n\n## Acceptance criteria\n- it works\n",
        )
        self._plan(60, 601)
        self._attach()
        self.assertGolden("implement-ui-attachments", self._implementer())

    def test_implement_core_task_omits_attachments(self):
        self._eligible_task()
        self._attach()
        result = self._implementer()
        self.assertEqual(result.code, 0, result.stderr)
        self.assertNotIn("## Attachments", result.stdout)

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
        self.assertGolden("test-with-findings", self._test_writer("--findings", self._review(
            implementation="- F1 [P1] [blocking] src/a.py:4 — drops retry",
            test="- F2 [P2] [blocking] tests/test_a.py — asserts a mock",
        )))

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
            "prompt_acceptance_test_writer", "--inline", 60, "--traceability", "text:FR-1 -> loads -> src/a.py", *extra,
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


    def test_acceptance_after_upstream_changes(self):
        self._testing_stack()
        self._log("PDLC-TESTING\n\ncovered")
        self._patch_back_to_ui("FR-1 now lands atomically")
        self.assertGolden("acceptance-test-upstream-changes", self._acceptance())

    # --- patch reviewer ---

    def test_patch_reviewer_product_patch(self):
        self.seed_record(60, "Technical Plan", "Pending", slug="record-60")
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] First")
        draft = self.write_file(
            "product.md",
            NO_UI_BODY.replace("The record lands.", "The record lands atomically."),
        )
        self.assertGolden(
            "patch-reviewer-product",
            self.invoke("prompt_patch_reviewer", "--inline", 60, "--stage", "Product", "--body", draft),
        )

    # --- task planner ---

    def test_task_planner_first_pass(self):
        self._tasks_stage_pending()
        self.assertGolden("task-planner-first-pass", self.invoke("prompt_task_planner", "--inline", 60))

    def test_task_planner_unpublished_revision_with_follow_up(self):
        self._tasks_stage_pending()
        manifest = self.write_file("current-tasks.json", '[{"id":"TASK-001","body":"task-001.md"}]\n')
        self.write_file("task-001.md", "## Scope\nCurrent unpublished task.\n")
        self.assertGolden(
            "task-planner-unpublished-follow-up",
            self.invoke(
                "prompt_task_planner", "--inline", 60,
                "--current-tasks-manifest-path", manifest,
                "--follow-up", "text:split the export task in two",
            ),
        )

    def test_task_planner_stale_with_existing_tree(self):
        self._tasks_stage_stale_with_existing_tree()
        self.assertGolden("task-planner-stale", self.invoke("prompt_task_planner", "--inline", 60))

    def test_task_planner_stale_with_unpublished_revision_and_follow_up(self):
        self._tasks_stage_stale_with_existing_tree()
        self.seed_publication(60, "Tasks")
        manifest = self.write_file("current-tasks.json", '[{"id":"TASK-001","body":"task-001.md"}]\n')
        self.write_file("task-001.md", "## Scope\nInvalidation fixes already applied.\n")
        self.assertGolden(
            "task-planner-stale-unpublished-follow-up",
            self.invoke(
                "prompt_task_planner", "--inline", 60,
                "--current-tasks-manifest-path", manifest,
                "--follow-up", "text:also split the export task in two",
            ),
        )


    # UI -> Tasks -> Technical Plan, then a Product patch returns the record to UI.

    def _tasks_published_then_patched_back_to_ui(self) -> None:
        self.seed_record(60, "Tasks", "Pending", slug="record-60")
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work")
        self._log("PDLC-UI\n\nui", "PDLC-TASKS\n\ntasks", "PDLC-PLAN\n\nplans")
        self._patch_back_to_ui("impact A")

    def test_task_planner_after_a_patch_back_to_ui(self):
        self._tasks_published_then_patched_back_to_ui()
        self.assertGolden("task-planner-upstream-changes", self.invoke("prompt_task_planner", "--inline", 60))

    def test_task_planner_after_a_rewind_to_tasks(self):
        # Tasks and Technical Plan republish past impact A; Tasks is then invalidated itself.
        self._tasks_published_then_patched_back_to_ui()
        self._log(
            "PDLC-TASKS\n\ntasks again",
            "PDLC-PLAN\n\nplans again",
            "PDLC-INVALIDATED\n\nInvalidated stage: Tasks\n\nsplit the export task",
        )
        self._at("Tasks", "Stale")
        self.assertGolden("task-planner-rewind-to-tasks", self.invoke("prompt_task_planner", "--inline", 60))

    def test_task_planner_after_a_second_patch_back_to_ui(self):
        self._tasks_published_then_patched_back_to_ui()
        self._log("PDLC-TASKS\n\ntasks again", "PDLC-PLAN\n\nplans again")
        self._patch_back_to_ui("impact B")
        self.assertGolden("task-planner-second-upstream-patch", self.invoke("prompt_task_planner", "--inline", 60))

    # --- tasks reviewer ---

    def test_tasks_reviewer_fragment_first_pass(self):
        self.seed_record(60, "UI", "Pending", slug="record-60", body=NO_UI_BODY)
        fragment = self.write_file("ui.md", "**UI Phase:** Required.\n\n### UJ-1 — Land the record\n\nDraft journey.\n")
        self.assertGolden("tasks-review-fragment-first-pass", self.invoke("prompt_tasks_reviewer", "--inline", 60, "--fragment", fragment))

    def test_tasks_reviewer_fragment_revision(self):
        self.seed_record(60, "UI", "Stale", slug="record-60")
        self.seed_publication(60, "UI")
        fragment = self.write_file("ui.md", "**UI Phase:** Required.\n\n### UJ-1 — Land the record\n\nRevised journey.\n")
        self.assertGolden(
            "tasks-review-fragment-revision",
            self.invoke("prompt_tasks_reviewer", "--inline", 60, "--fragment", fragment, "--findings", "text:UJ-1 lacks an offline failure state"),
        )

    def test_tasks_reviewer_manifest_first_pass(self):
        self._tasks_stage_pending()
        core = self.write_file("task-001.md", "## Scope\nBuild the seam.\n\nCovers FR-1.\n\n## Acceptance criteria\n- it works\n")
        ui = self.write_file("task-002.md", "## Scope\nShow it.\n\nCovers FR-2, UJ-1.\n\n## Acceptance criteria\n- it shows\n")
        manifest = self.write_file("manifest.json", json.dumps([
            {"id": "TASK-001", "title": "Core work", "body": core, "type": "core", "covers": ["FR-1"], "depends": []},
            {"id": "TASK-002", "title": "Show it", "body": ui, "type": "ui", "covers": ["FR-2", "UJ-1"], "depends": ["TASK-001"]},
        ]))
        self.assertGolden("tasks-review-manifest-first-pass", self.invoke("prompt_tasks_reviewer", "--inline", 60, "--manifest", manifest))

    def test_tasks_reviewer_manifest_reconcile_with_findings(self):
        self.seed_record(60, "Tasks", "Stale", slug="record-60")
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work")
        self.seed_task(60, 602, "TASK-002", "OPEN", "WORK-60-TASK-002 [UI] Show it")
        self.seed_task(60, 603, "TASK-003", "OPEN", "WORK-60-TASK-003 [CORE] Export")
        revised = self.write_file("task-002.md", "## Scope\nShow it offline too.\n\nCovers FR-2, UJ-1.\n\n## Acceptance criteria\n- it shows offline\n")
        added = self.write_file("task-004.md", "## Scope\nRetry the sync.\n\nCovers FR-1.\n\n## Acceptance criteria\n- it retries\n")
        retained = self.write_file("task-001.md", "## Scope\nBuild the seam.\n\nCovers FR-1.\n\n## Acceptance criteria\n- it works\n")
        manifest = self.write_file("manifest.json", json.dumps([
            {"id": "TASK-001", "number": 601, "action": "retain", "body": retained, "type": "core", "covers": ["FR-1"], "depends": []},
            {"id": "TASK-002", "number": 602, "title": "Show it", "body": revised, "type": "ui", "covers": ["FR-2", "UJ-1"], "depends": ["TASK-001"]},
            {"id": "TASK-003", "number": 603, "action": "remove", "reason": "Folded into TASK-001"},
            {"title": "Retry sync", "body": added, "type": "core", "covers": ["FR-1"], "depends": ["TASK-001"]},
        ]))
        self.assertGolden(
            "tasks-review-manifest-reconcile",
            self.invoke("prompt_tasks_reviewer", "--inline", 60, "--manifest", manifest, "--findings", "text:TASK-002 lacks offline criteria"),
        )

    # --- UI planner ---

    def test_ui_planner_first_pass(self):
        self.seed_record(60, "UI", "Pending", slug="record-60", body=NO_UI_BODY)
        self.assertGolden("ui-planner-first-pass", self._ui_planner())

    def test_ui_planner_lists_attachments(self):
        self.seed_record(60, "UI", "Pending", slug="record-60", body=NO_UI_BODY)
        self._attach()
        self.assertGolden("ui-planner-attachments", self._ui_planner())

    def test_ui_planner_unpublished_revision_with_follow_up(self):
        self.seed_record(60, "UI", "Pending", slug="record-60", body=NO_UI_BODY)
        fragment = self.write_file("current-ui.md", "## UI\n\nUJ-1 current draft.\n")
        self.assertGolden(
            "ui-planner-unpublished-follow-up",
            self._ui_planner(
                "--current-journeys-path", fragment,
                "--follow-up", "text:revisit UJ-2's offline flow",
            ),
        )

    def test_ui_planner_stale_with_published_section(self):
        self.seed_record(60, "UI", "Stale", slug="record-60")
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work")
        self.seed_publication(60, "UI")
        self.add_invalidation(60, stage="UI")
        self.assertGolden("ui-planner-stale", self._ui_planner())

    def test_ui_planner_changes_required_with_published_section(self):
        self.seed_record(60, "UI", "Changes Required", slug="record-60")
        self.add_rework_review(60, stage="UI")
        self.assertGolden("ui-planner-changes-required", self._ui_planner())

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


    def test_ui_planner_stale_after_a_product_patch(self):
        # The patch's own UI invalidation is the stale reason; the Product patch is upstream.
        self.seed_record(60, "UI", "Stale", slug="record-60")
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work")
        self._log("PDLC-UI\n\nui")
        self._log(
            "PDLC-PRODUCT\n\npatched product",
            "PDLC-PATCHED\n\nPatched stage: Product\nActive stage: Tasks / Pending\nReturned to: UI / Stale\n\nimpact A",
            "PDLC-INVALIDATED\n\nInvalidated stage: UI\n\nReturned by a patch of Product; impact A",
        )
        self.assertGolden("ui-planner-upstream-changes", self._ui_planner())

    # --- tech planner ---

    def test_tech_planner_first_pass(self):
        self._plan_stage()
        self.assertGolden("tech-planner-first-pass", self.invoke("prompt_tech_planner", "--inline", 60))

    def test_tech_planner_stale_with_follow_up(self):
        self._plan_stage(gate="Stale")
        self.add_invalidation(60, stage="Technical Plan")
        self.assertGolden(
            "tech-planner-stale",
            self.invoke("prompt_tech_planner", "--inline", 60, "--follow-up", "text:re-spike TASK-001 against the cache"),
        )


    def test_tech_planner_after_a_patch_back_to_ui(self):
        self._plan_stage()
        self._log("PDLC-PLAN\n\nplans")
        self._patch_back_to_ui("impact A")
        self._log("PDLC-TASKS\n\ntasks again")
        self.assertGolden("tech-planner-upstream-changes", self.invoke("prompt_tech_planner", "--inline", 60))

    def test_tech_planner_revision_with_findings(self):
        self._plan_stage()
        manifest = self.plan_manifest(60, {"TASK-002": "Own src/b.py; render the list."})
        self.assertGolden(
            "tech-planner-revision",
            self.invoke(
                "prompt_tech_planner", "--inline", 60, "--current-plan-manifest-path", manifest,
                "--follow-up", "text:Needs Revision: TASK-002 names no test for the empty list.",
            ),
        )

    # --- plan reviewer ---

    def test_plan_reviewer_first_pass(self):
        self._plan_stage()
        manifest = self.plan_manifest(60, {"TASK-002": "Own src/b.py; render the list."})
        self.assertGolden("plan-review-first-pass", self.invoke("prompt_plan_reviewer", "--inline", 60, "--manifest", manifest))

    def test_plan_reviewer_replacing_a_plan_with_findings(self):
        self._plan_stage(gate="Stale")
        manifest = self.plan_manifest(60, {"TASK-001": "Touch two modules.", "TASK-002": "Own src/b.py."})
        self.assertGolden(
            "plan-review-replace-with-findings",
            self.invoke("prompt_plan_reviewer", "--inline", 60, "--manifest", manifest, "--findings", "text:TASK-001 skips the cache"),
        )

    # --- product writer ---

    def _writer(self, *args: object):
        return self.invoke("prompt_product_writer", "--inline", *args)

    def _draft_at(
        self, text: str, key: str = "new-route-sheet", *, product: bool = True, spiked: bool = False,
        technical: bool | None = False, product_findings: str | None = None, technical_findings: str | None = None,
    ) -> Path:
        """Put the draft for `key` in a given phase: `text` as the draft, each
        stamp matching it when set, a stale stamp when `technical` is None, and
        each findings file holding the text given."""
        path = product_draft.draft_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        content = fingerprint(product_content(text))
        product_draft.write_stamp(key, Stamp(
            product=content if product else "stale",
            spiked=content if spiked else None,
            technical=fingerprint(text) if technical else ("stale" if technical is None else None),
        ))
        for findings, body in (
            (product_draft.product_findings_path(key), product_findings),
            (product_draft.technical_findings_path(key), technical_findings),
        ):
            if body is not None:
                findings.write_text(body, encoding="utf-8")
        return path

    def test_product_writer_fresh(self):
        self.assertGolden("product-writer-fresh", self._writer("--slug", "route-sheet"))

    def test_product_writer_uninitialized(self):
        self.seed_record(60, "", "", body="Open the route sheet faster.\n")
        self.assertGolden("product-writer-uninitialized", self._writer("--work-item", 60))

    def test_product_writer_changes_required(self):
        self.seed_record(60, "Product", "Changes Required", slug="record-60")
        self.add_rework_review(60, stage="Product")
        self.assertGolden("product-writer-changes-required", self._writer("--work-item", 60))

    def test_product_writer_stale(self):
        self.seed_record(60, "Product", "Stale", slug="record-60")
        self.seed_publication(60, "Product")
        self.add_invalidation(60, stage="Product")
        self.assertGolden("product-writer-stale", self._writer("--work-item", 60))

    def test_product_writer_review_only(self):
        self.seed_record(60, "Product", "Review Required", slug="record-60")
        self.assertGolden("product-writer-review-only", self._writer("--work-item", 60))

    def test_product_writer_reauthor(self):
        self.seed_record(60, "Product", "Approval Required", slug="record-60")
        self.assertGolden("product-writer-reauthor", self._writer("--work-item", 60, "--reauthor"))

    def test_product_writer_patch(self):
        self.seed_record(60, "Technical Plan", "Pending", slug="record-60")
        self.assertGolden("product-writer-patch", self._writer("--work-item", 60, "--patch"))

    def test_product_writer_product_review(self):
        self._draft_at(DRAFT, product=False)
        self.assertGolden("product-writer-product-review", self._writer("--slug", "route-sheet"))

    def test_product_writer_product_findings(self):
        self._draft_at(DRAFT, product_findings=FINDING + "Verdict: Needs Revision\n")
        self.assertGolden("product-writer-product-findings", self._writer("--slug", "route-sheet"))

    def test_product_writer_spike(self):
        self._draft_at(DRAFT, product_findings="Verdict: Ready to Land\n")
        self.assertGolden("product-writer-spike", self._writer("--slug", "route-sheet"))

    def test_product_writer_not_feasible(self):
        self._draft_at(
            WITH_APPROACH.replace("Verdict: Feasible", "Verdict: Not feasible"),
            spiked=True, product_findings="Verdict: Ready to Land\n",
        )
        self.assertGolden("product-writer-not-feasible", self._writer("--slug", "route-sheet"))

    def test_product_writer_technical_review_after_a_fresh_spike(self):
        with_assumptions = WITH_APPROACH.replace(
            "### Technical approach", "### Assumptions\n- The sheet exposes detents.\n\n### Technical approach",
        )
        self._draft_at(with_assumptions, spiked=True, product_findings="Verdict: Ready to Land\n")
        self.assertGolden("product-writer-technical-review-fresh-spike", self._writer("--slug", "route-sheet"))

    def test_product_writer_technical_re_review(self):
        self._draft_at(WITH_APPROACH, spiked=True, technical=None, product_findings="Verdict: Ready to Land\n")
        self.assertGolden("product-writer-technical-re-review", self._writer("--slug", "route-sheet"))

    def test_product_writer_technical_findings(self):
        self._draft_at(
            WITH_APPROACH, spiked=True, technical=True, product_findings="Verdict: Ready to Land\n",
            technical_findings=FINDING + "Verdict: Needs Revision\n",
        )
        self.assertGolden("product-writer-technical-findings", self._writer("--slug", "route-sheet"))

    def test_product_writer_ready_new(self):
        mockup = self.write_file("sheet.png", "sheet mockup\n")
        self._writer("--slug", "route-sheet", "--attachment", mockup, "--attachment-description", "Route sheet mockup")
        self._draft_at(
            WITH_APPROACH, spiked=True, technical=True,
            product_findings="Verdict: Ready to Land\n", technical_findings="Verdict: Ready to Land\n",
        )
        self.assertGolden("product-writer-ready-new", self._writer("--slug", "route-sheet"))

    def test_product_writer_ready_existing(self):
        self.seed_record(60, "Product", "Changes Required", slug="record-60")
        self.add_rework_review(60, stage="Product")
        self._attach()
        self._draft_at(
            WITH_APPROACH, "60", spiked=True, technical=True,
            product_findings="Verdict: Ready to Land\n", technical_findings="Verdict: Ready to Land\n",
        )
        self.assertGolden("product-writer-ready-existing", self._writer("--work-item", 60))

    def test_product_writer_ready_patch(self):
        self.seed_record(60, "Technical Plan", "Pending", slug="record-60")
        self._draft_at(
            WITH_APPROACH, "60", spiked=True, technical=True,
            product_findings="Verdict: Ready to Land\n", technical_findings="Verdict: Ready to Land\n",
        )
        self.assertGolden("product-writer-ready-patch", self._writer("--work-item", 60, "--patch"))

    # --- tech feasibility ---

    def _spike(self, *args: object):
        return self.invoke("prompt_tech_feasibility", "--inline", product_draft.draft_path("new-route-sheet"), *args)

    def test_tech_feasibility_new_work_item(self):
        self._draft_at(DRAFT, product_findings="Verdict: Ready to Land\n")
        self.assertGolden("tech-feasibility-new", self._spike())

    def test_tech_feasibility_existing_record_with_attachments(self):
        self.seed_record(60, "Product", "Changes Required", slug="record-60")
        self._attach()
        draft = self._draft_at(DRAFT, "60", product_findings="Verdict: Ready to Land\n")
        self.assertGolden(
            "tech-feasibility-existing-attachments", self.invoke("prompt_tech_feasibility", "--inline", draft),
        )

    def test_tech_feasibility_re_spike_with_findings(self):
        self._draft_at(
            WITH_APPROACH, spiked=True, technical=True, product_findings="Verdict: Ready to Land\n",
            technical_findings=FINDING + "Verdict: Needs Revision\n",
        )
        findings = product_draft.technical_findings_path("new-route-sheet")
        self.assertGolden("tech-feasibility-re-spike", self._spike("--findings", findings))

"""`pdlc prompt` renders the brief for the unit the Implementation loop is on."""

from __future__ import annotations

from tests._prompts import PromptHarness


class PromptCommandTest(PromptHarness):
    # --- implement ---

    def test_eligible_task_renders_the_implementation_brief(self):
        self._eligible_task()
        result = self.invoke("prompt_task_implementer", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("You are implementing one delivery task's production code.", result.stdout)
        self.assertIn("`WORK-60-TASK-001` (tag included) — `[CORE] Core work`", result.stdout)
        self.assertIn("Touch one module.", result.stdout)
        self.assertIn("Build the seam.", result.stdout)

    def test_the_brief_never_leaves_an_unfilled_placeholder(self):
        self._eligible_task()
        result = self.invoke("prompt_task_implementer", 60)
        self.assertNotIn("{{", result.stdout)

    def test_the_brief_names_no_pdlc_command_or_stage(self):
        self._eligible_task()
        result = self.invoke("prompt_task_implementer", 60)
        for leak in ("pdlc inspect", "pdlc post", "pdlc checkout", "Gate State"):
            self.assertNotIn(leak, result.stdout)

    def test_covered_requirements_are_carried_in_full(self):
        self._eligible_task()
        result = self.invoke("prompt_task_implementer", 60)
        # BODY_DEFAULT lists requirements as bullets, not headings.
        self.assertIn("FR-1: The record lands.", result.stdout)
        self.assertNotIn("FR-2", result.stdout)

    def test_a_cited_requirement_missing_from_the_record_is_reported_not_dropped(self):
        self._eligible_task(body="## Scope\nCovers FR-9.\n")
        result = self.invoke("prompt_task_implementer", 60)
        self.assertIn("FR-9 — not found in the record's `## Product`", result.stdout)

    def test_a_first_task_carries_no_findings_and_no_upstream(self):
        self._eligible_task()
        result = self.invoke("prompt_task_implementer", 60)
        self.assertNotIn("## Findings to address", result.stdout)
        self.assertIn("Upstream tasks it depends on, and what each shipped: none", result.stdout)

    def test_an_invalidated_task_carries_the_invalidation_as_findings(self):
        self._invalidated_task()
        result = self.invoke("prompt_task_implementer", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("## Findings to address", result.stdout)
        self.assertIn("Invalidated stage: Implementation", result.stdout)

    def test_the_verify_section_appears_only_with_a_build_run_capability(self):
        self._eligible_task()
        without = self.invoke("prompt_task_implementer", 60)
        self.assertNotIn("## Verify", without.stdout)

        self._build_run("build-run-ios")
        with_skill = self.invoke("prompt_task_implementer", 60)
        self.assertIn("## Verify", with_skill.stdout)
        self.assertIn("invoke the `build-run-ios` skill", with_skill.stdout)

    def test_a_later_task_summarises_what_upstream_shipped(self):
        self._second_task_eligible()
        result = self.invoke("prompt_task_implementer", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("`WORK-60-TASK-002` (tag included) — `[UI] Second`", result.stdout)
        self.assertIn("- `WORK-60-TASK-001` [CORE] Core work: Added the loader.", result.stdout)

    # --- pr-fix ---

    def test_an_unresolved_thread_renders_the_review_comment_brief(self):
        self._implemented_stack()
        self._threads([
            {"pr": 40, "author": "reviewer", "path": "src/a.py", "line": 4, "body": "drops retry", "url": "u"},
        ])
        result = self.invoke("prompt_task_implementer", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("unresolved review comments on pull request `40` in `acme/widgets`", result.stdout)
        self.assertIn("-f owner='acme' -f repo='widgets' -F pr=40", result.stdout)
        self.assertIn("No previously recorded decisions.", result.stdout)
        self.assertNotIn("## Failing checks", result.stdout)
        self.assertNotIn("{{", result.stdout)

    def test_a_thread_with_red_checks_appends_the_failing_checks(self):
        self._implemented_stack()
        self._threads([{"pr": 40, "author": "r", "path": "a", "line": 1, "body": "b", "url": "u"}])
        self._prs([
            {"number": 40, "title": "t", "url": "u40", "state": "OPEN", "isDraft": False,
             "branch": "b", "mergedAt": None, "checks": "FAILURE"},
        ])
        result = self.invoke("prompt_task_implementer", 60)
        self.assertIn("## Failing checks", result.stdout)
        self.assertIn("PR #40: FAILURE", result.stdout)

    def test_red_checks_without_a_thread_use_the_implementation_brief(self):
        self._implemented_stack()
        self._prs([
            {"number": 40, "title": "t", "url": "u40", "state": "OPEN", "isDraft": False,
             "branch": "b", "mergedAt": None, "checks": "FAILURE"},
        ])
        result = self.invoke("prompt_task_implementer", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("You are implementing one delivery task's production code.", result.stdout)
        self.assertIn("## Findings to address", result.stdout)
        self.assertIn("PR #40: FAILURE", result.stdout)

    # --- triage ---

    def test_open_change_requests_render_the_triage_brief_with_the_whole_stack(self):
        self._implemented_stack()
        self.add_rework_review(60)
        result = self.invoke("prompt_task_implementer", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("The branches below are a stack of pull requests", result.stdout)
        self.assertIn("### pdlc/record-60/task-001 — `WORK-60-TASK-001` `[CORE] First`", result.stdout)
        self.assertIn("### pdlc/record-60/task-002 — `WORK-60-TASK-002` `[UI] Second`", result.stdout)
        self.assertIn("The last entry above is the top branch", result.stdout)
        self.assertNotIn("{{", result.stdout)

    # --- reviewer ---

    def test_reviewer_brief_carries_the_task_and_the_diff(self):
        self._eligible_task()
        self._git()
        result = self.invoke("prompt_task_reviewer", 60, "--commits", "HEAD~1..HEAD")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("You are reviewing one delivery task's implementation, read-only.", result.stdout)
        self.assertIn("leaf worker for this one review.", result.stdout)
        self.assertIn("`WORK-60-TASK-001` (tag included) — `[CORE] Core work`", result.stdout)
        self.assertIn("1 file changed", result.stdout)
        self.assertIn("diff --git a/x b/x", result.stdout)
        self.assertIn("Task review complete: WORK-60-TASK-001", result.stdout)
        self.assertNotIn("{{", result.stdout)

    def test_reviewer_requires_the_commits_to_read(self):
        self._eligible_task()
        result = self.invoke("prompt_task_reviewer", 60)
        self.assertNotEqual(result.code, 0)
        self.assertIn("--commits", result.stderr)

    # --- test-writer ---

    def _test_brief(self, *extra: str):
        return self.invoke(
            "prompt_task_test_writer", 60, "--commits", "HEAD~1..HEAD",
            "--report", "text:Built the seam; criteria verified.",
            "--traceability", "text:FR-1 -> loads -> src/a.py",
            *extra,
        )

    def test_test_writer_brief_carries_the_map_report_and_touched_files(self):
        self._eligible_task()
        self._git()
        result = self._test_brief()
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Write unit coverage for the one delivery task", result.stdout)
        self.assertIn("FR-1 -> loads -> src/a.py", result.stdout)
        self.assertIn("Built the seam; criteria verified.", result.stdout)
        self.assertIn("- src/a.py", result.stdout)
        self.assertIn("`601` in `60`", result.stdout)
        self.assertIn("non-blocking, verbatim: none", result.stdout)
        self.assertNotIn("{{", result.stdout)

    def test_test_writer_carries_accepted_findings_when_given(self):
        self._eligible_task()
        self._git()
        result = self._test_brief("--findings", "text:Naming nit on the loader.")
        self.assertIn("Naming nit on the loader.", result.stdout)

    def test_test_writer_requires_its_report_and_map(self):
        self._eligible_task()
        self._git()
        result = self.invoke("prompt_task_test_writer", 60, "--commits", "HEAD~1..HEAD")
        self.assertNotEqual(result.code, 0)
        self.assertIn("--report", result.stderr)

    def test_every_agent_briefs_the_same_task(self):
        self._eligible_task()
        self._git()
        for brief in (
            self.invoke("prompt_task_implementer", 60),
            self.invoke("prompt_task_reviewer", 60, "--commits", "HEAD~1..HEAD"),
            self._test_brief(),
        ):
            self.assertEqual(brief.code, 0, brief.stderr)
            self.assertIn("`WORK-60-TASK-001` (tag included) — `[CORE] Core work`", brief.stdout)

    # --- acceptance test writer ---

    def _acceptance_brief(self, *extra: str):
        return self.invoke(
            "prompt_acceptance_test_writer", 60, "--traceability", "text:FR-1 -> loads -> src/a.py", *extra,
        )

    def test_acceptance_brief_carries_the_map_and_the_whole_implemented_scope(self):
        self._testing_stack()
        result = self._acceptance_brief()
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Write requirement-to-source-traceable acceptance coverage", result.stdout)
        self.assertIn("FR-1 -> loads -> src/a.py", result.stdout)
        self.assertIn("- src/a.py\n- src/shared.py\n- src/b.py\n", result.stdout)
        self.assertEqual(result.stdout.count("src/shared.py"), 1)
        self.assertIn("- `WORK-60-TASK-001` [CORE] First", result.stdout)
        self.assertIn("`601`, `602` in `60`", result.stdout)
        self.assertIn("Implementation PRs: `#40`, `#41`.", result.stdout)
        self.assertNotIn("## Findings to address", result.stdout)
        self.assertNotIn("{{", result.stdout)

    def test_acceptance_brief_carries_the_stages_open_change_requests(self):
        self._testing_stack(gate="Changes Required")
        self.add_rework_review(60, stage="Testing")
        result = self._acceptance_brief()
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("## Findings to address", result.stdout)
        self.assertIn("### Change request", result.stdout)
        self.assertIn("- detail", result.stdout)

    def test_acceptance_brief_appends_caller_findings(self):
        self._testing_stack()
        result = self._acceptance_brief("--findings", "text:unit-tests: assertion failed at test_a.py:12")
        self.assertIn("### Additional findings\n\nunit-tests: assertion failed at test_a.py:12", result.stdout)

    def test_acceptance_brief_refuses_outside_testing(self):
        self._implemented_stack()
        result = self._acceptance_brief()
        self.assertEqual(result.code, 1)
        self.assertIn("Not ready", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_acceptance_brief_requires_the_map(self):
        self._testing_stack()
        result = self.invoke("prompt_acceptance_test_writer", 60)
        self.assertNotEqual(result.code, 0)
        self.assertIn("--traceability", result.stderr)

    # --- refusals ---

    def test_a_record_that_is_not_due_refuses_rather_than_briefing(self):
        self.seed_record(60, "Testing", "Pending", slug="record-60")
        result = self.invoke("prompt_task_implementer", 60)
        self.assertEqual(result.code, 1)
        self.assertIn("Not ready", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_nothing_due_refuses_rather_than_briefing_an_empty_unit(self):
        self._implemented_stack(gate="Pending")
        result = self.invoke("prompt_task_implementer", 60)
        self.assertEqual(result.code, 1)
        self.assertIn("no unit is due", result.stderr)

    def test_an_unknown_brief_command_is_rejected(self):
        self._eligible_task()
        result = self.invoke("prompt", "bogus-command", 60)
        self.assertEqual(result.code, 1)
        self.assertIn("task-implementer", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_prompt_alone_names_the_brief_it_can_build(self):
        result = self.invoke("prompt", "--help")
        self.assertEqual(result.code, 0, result.stderr)
        for command in (
            "task-implementer", "task-reviewer", "task-test-writer", "acceptance-test-writer", "task-planner",
            "tech-planner",
        ):
            self.assertIn(command, result.stdout)

    # --- task planner ---

    def _planner_brief(self, *extra: str):
        return self.invoke("prompt_task_planner", 60, *extra)

    def test_first_pass_tasks_record_renders_the_brief(self):
        self._tasks_stage_pending()
        result = self._planner_brief()
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn(
            "Break this work item into the smallest dependency-ordered set of independently verifiable delivery tasks.",
            result.stdout,
        )
        self.assertIn("## Work item `60`", result.stdout)
        self.assertIn("FR-1: The record lands.", result.stdout)
        self.assertEqual(result.stdout.count("--- BEGIN WORK ITEM ---"), 1)
        self.assertEqual(result.stdout.count("--- END WORK ITEM ---"), 1)
        self.assertLess(
            result.stdout.index("--- BEGIN WORK ITEM ---"),
            result.stdout.index("FR-1: The record lands."),
        )
        self.assertLess(
            result.stdout.index("FR-1: The record lands."),
            result.stdout.index("--- END WORK ITEM ---"),
        )
        self.assertNotIn("## Existing tasks", result.stdout)
        self.assertNotIn("## Changes needed", result.stdout)
        self.assertIn("## Return\n\nReturn one body file for each new or rewritten task", result.stdout)
        self.assertNotIn("{{", result.stdout)

    def test_first_pass_brief_names_no_pdlc_command_or_stage(self):
        self._tasks_stage_pending()
        result = self._planner_brief()
        for leak in ("pdlc inspect", "pdlc post", "pdlc prompt"):
            self.assertNotIn(leak, result.stdout)

    def test_stale_record_carries_the_reason_and_existing_tree(self):
        self._tasks_stage_stale_with_existing_tree()
        result = self._planner_brief()
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("## Existing tasks", result.stdout)
        self.assertIn("## Changes needed", result.stdout)
        self.assertIn("Invalidated stage: Tasks", result.stdout)
        self.assertIn("number: 601", result.stdout)
        self.assertIn('title: "WORK-60-TASK-001 [CORE] Core work"', result.stdout)
        self.assertIn("--- BEGIN TASK BODY ---\n\n## Scope\nx\n\n## Acceptance criteria\n- ok\n\n--- END TASK BODY ---", result.stdout)
        self.assertIn("--- BEGIN CHANGE REQUESTS ---", result.stdout)

    def test_follow_up_is_carried_verbatim(self):
        self._tasks_stage_pending()
        result = self._planner_brief("--follow-up", "text:split the export task in two")
        self.assertIn("## Changes needed", result.stdout)
        self.assertNotIn("### Change requests", result.stdout)
        self.assertIn(
            "### Driver follow-up\n\nA change the driver asked for, or findings from a review of the breakdown, "
            "verbatim.\n\nsplit the export task in two",
            result.stdout,
        )
        self.assertNotIn("DRIVER FOLLOW-UP ---", result.stdout)

    def test_changes_required_record_carries_open_review_findings(self):
        self.seed_record(60, "Tasks", "Changes Required", slug="record-60")
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work")
        self.add_rework_review(60, stage="Tasks")
        result = self._planner_brief()
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("## Changes needed", result.stdout)
        self.assertIn("## Findings\n\n- detail", result.stdout)

    def test_a_record_not_at_tasks_refuses(self):
        self.seed_record(60, "Testing", "Pending", slug="record-60")
        result = self._planner_brief()
        self.assertEqual(result.code, 1)
        self.assertIn("not Tasks", result.stderr)
        self.assertEqual(result.stdout, "")

    # --- tech planner ---

    def _tech_brief(self, *extra: str):
        return self.invoke("prompt_tech_planner", 60, *extra)

    def test_tech_planner_carries_open_tasks_and_skips_implemented_ones(self):
        self._plan_stage()
        result = self._tech_brief()
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("### `WORK-60-TASK-001` [CORE] Core work (#601)\n\n--- BEGIN TASK ---", result.stdout)
        self.assertIn("--- BEGIN EXISTING PLAN ---\n\nTouch one module.\n\n--- END EXISTING PLAN ---", result.stdout)
        self.assertIn("### `WORK-60-TASK-002` [UI] Second (#602)\n\n--- BEGIN TASK ---", result.stdout)
        self.assertEqual(result.stdout.count("--- BEGIN EXISTING PLAN ---"), 1)
        self.assertIn("- No plan yet (TASK-002): plan these from scratch.", result.stdout)
        # Nothing to check a planned task against, so it is left alone.
        self.assertIn("- Already planned (TASK-001): leave these alone.", result.stdout)
        self.assertNotIn("WORK-60-TASK-003", result.stdout)
        self.assertIn("## Designing the plan", result.stdout)
        self.assertNotIn("## Shape of the change", result.stdout)
        self.assertNotIn("## Changes needed", result.stdout)
        self.assertNotIn("{{", result.stdout)
        for leak in ("pdlc inspect", "pdlc post", "pdlc prompt"):
            self.assertNotIn(leak, result.stdout)

    def test_tech_planner_carries_the_stage_evidence_and_follow_up(self):
        self._plan_stage(gate="Stale")
        self.add_invalidation(60, stage="Technical Plan")
        result = self._tech_brief("--follow-up", "text:re-spike TASK-001")
        self.assertIn("Invalidated stage: Technical Plan", result.stdout)
        self.assertIn("--- BEGIN CHANGE REQUESTS ---", result.stdout)
        self.assertIn("- Already planned (TASK-001): check each against the change requests and driver follow-up below.", result.stdout)
        self.assertIn("The change requests and driver follow-up below apply to this pass.", result.stdout)
        self.assertIn("### Driver follow-up\n\nA change the driver asked for, or findings from a review of your plans, verbatim.\n\nre-spike TASK-001\n", result.stdout)

    def test_tech_planner_refuses_a_record_not_at_technical_plan(self):
        self._tasks_stage_pending()
        result = self._tech_brief()
        self.assertEqual(result.code, 1)
        self.assertIn("not Technical Plan", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_tech_planner_refuses_when_every_task_is_implemented(self):
        self.seed_record(60, "Technical Plan", "Pending", slug="record-60")
        self.seed_task(60, 601, "TASK-001", "CLOSED", "WORK-60-TASK-001 [CORE] Done")
        result = self._tech_brief()
        self.assertEqual(result.code, 1)
        self.assertIn("nothing to plan", result.stderr)

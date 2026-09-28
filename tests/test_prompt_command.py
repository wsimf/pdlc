"""`pdlc prompt` renders the brief for the unit the Implementation loop is on."""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests._prompts import PromptHarness


class PromptCommandTest(PromptHarness):
    def test_brief_is_written_to_the_work_item_cache_by_default_and_not_reused(self):
        self._eligible_task()
        first_result = self.invoke("prompt_task_implementer", 60)
        second_result = self.invoke("prompt_task_implementer", 60)
        self.assertEqual(first_result.code, 0, first_result.stderr)
        self.assertEqual(second_result.code, 0, second_result.stderr)
        first = Path(first_result.stdout.strip())
        second = Path(second_result.stdout.strip())
        self.assertEqual(first.parent, self.work / ".pdlc" / "cache" / "60")
        self.assertNotEqual(first, second)
        self.assertIn("You are implementing", first.read_text())

    def test_inline_prints_the_brief_and_stays_out_of_help(self):
        self._eligible_task()
        inline = self.invoke("prompt_task_implementer", 60, "--inline")
        self.assertEqual(inline.code, 0, inline.stderr)
        self.assertIn("You are implementing", inline.stdout)
        for command in ("prompt", "prompt_task_implementer", "prompt_product_reviewer", "prompt_cumulative_reviewer"):
            with self.subTest(command=command):
                self.assertNotIn("--inline", self.invoke(command, "--help").stdout)

    # --- implement ---

    def test_eligible_task_renders_the_implementation_brief(self):
        self._eligible_task()
        result = self.invoke("prompt_task_implementer", "--inline", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("You are implementing one delivery task's production code.", result.stdout)
        self.assertIn("`WORK-60-TASK-001` (tag included) — `[CORE] Core work`", result.stdout)
        self.assertIn("Touch one module.", result.stdout)
        self.assertIn("Build the seam.", result.stdout)

    def test_the_brief_never_leaves_an_unfilled_placeholder(self):
        self._eligible_task()
        result = self.invoke("prompt_task_implementer", "--inline", 60)
        self.assertNotIn("{{", result.stdout)

    def test_the_brief_names_no_pdlc_command_or_stage(self):
        self._eligible_task()
        result = self.invoke("prompt_task_implementer", "--inline", 60)
        for leak in ("pdlc inspect", "pdlc post", "pdlc checkout", "Gate State"):
            self.assertNotIn(leak, result.stdout)

    def test_covered_requirements_are_carried_in_full(self):
        self._eligible_task()
        result = self.invoke("prompt_task_implementer", "--inline", 60)
        # BODY_DEFAULT lists requirements as bullets, not headings.
        self.assertIn("FR-1: The record lands.", result.stdout)
        self.assertNotIn("FR-2", result.stdout)

    def test_a_cited_requirement_missing_from_the_record_is_reported_not_dropped(self):
        self._eligible_task(body="## Scope\nCovers FR-9.\n")
        result = self.invoke("prompt_task_implementer", "--inline", 60)
        self.assertIn("FR-9 — not found in the record's `## Product`", result.stdout)

    def test_a_first_task_carries_no_findings_and_no_upstream(self):
        self._eligible_task()
        result = self.invoke("prompt_task_implementer", "--inline", 60)
        self.assertNotIn("## Findings to address", result.stdout)
        self.assertIn("Upstream tasks it depends on, and what each shipped: none", result.stdout)

    def test_uncommitted_changes_reach_every_implementer_form(self):
        self._eligible_task()
        self._uncommitted(" M src/a.py\n?? src/b.py")
        result = self.invoke("prompt_task_implementer", "--inline", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("## Uncommitted work on this branch", result.stdout)
        self.assertIn(" M src/a.py\n?? src/b.py", result.stdout)
        self.assertIn("Leave any other\nchanged file exactly as it is", result.stdout)

    def test_a_clean_tree_adds_no_uncommitted_section(self):
        self._eligible_task()
        result = self.invoke("prompt_task_implementer", "--inline", 60)
        self.assertNotIn("## Uncommitted work on this branch", result.stdout)

    def test_an_invalidated_task_carries_the_invalidation_as_findings(self):
        self._invalidated_task()
        result = self.invoke("prompt_task_implementer", "--inline", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("## Findings to address", result.stdout)
        self.assertIn("Invalidated stage: Implementation", result.stdout)

    def test_the_verify_section_appears_only_with_a_build_run_capability(self):
        self._eligible_task()
        without = self.invoke("prompt_task_implementer", "--inline", 60)
        self.assertNotIn("## Verify", without.stdout)

        self._build_run("build-run-ios")
        with_skill = self.invoke("prompt_task_implementer", "--inline", 60)
        self.assertIn("## Verify", with_skill.stdout)
        self.assertIn("invoke the `build-run-ios` skill", with_skill.stdout)

    def test_a_later_task_summarises_what_upstream_shipped(self):
        self._second_task_eligible()
        result = self.invoke("prompt_task_implementer", "--inline", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("`WORK-60-TASK-002` (tag included) — `[UI] Second`", result.stdout)
        self.assertIn("- `WORK-60-TASK-001` [CORE] Core work: Added the loader.", result.stdout)

    # --- pr-fix ---

    def test_an_unresolved_thread_renders_the_review_comment_brief(self):
        self._implemented_stack()
        self._threads([
            {"pr": 40, "author": "reviewer", "path": "src/a.py", "line": 4, "body": "drops retry", "url": "u"},
        ])
        result = self.invoke("prompt_task_implementer", "--inline", 60)
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
        result = self.invoke("prompt_task_implementer", "--inline", 60)
        self.assertIn("## Failing checks", result.stdout)
        self.assertIn("PR #40: FAILURE", result.stdout)

    def test_red_checks_without_a_thread_use_the_implementation_brief(self):
        self._implemented_stack()
        self._prs([
            {"number": 40, "title": "t", "url": "u40", "state": "OPEN", "isDraft": False,
             "branch": "b", "mergedAt": None, "checks": "FAILURE"},
        ])
        result = self.invoke("prompt_task_implementer", "--inline", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("You are implementing one delivery task's production code.", result.stdout)
        self.assertIn("## Findings to address", result.stdout)
        self.assertIn("PR #40: FAILURE", result.stdout)

    # --- triage ---

    def test_open_change_requests_render_the_triage_brief_with_the_whole_stack(self):
        self._implemented_stack()
        self.add_rework_review(60)
        result = self.invoke("prompt_task_implementer", "--inline", 60)
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
        result = self.invoke("prompt_task_reviewer", "--inline", 60, "--commits", "HEAD~1..HEAD")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("You are reviewing one delivery task's implementation and its unit tests,", result.stdout)
        self.assertIn("leaf worker for this one review.", result.stdout)
        self.assertIn("`WORK-60-TASK-001` (tag included) — `[CORE] Core work`", result.stdout)
        self.assertIn("1 file changed", result.stdout)
        self.assertIn("diff --git a/x b/x", result.stdout)
        self.assertNotIn("{{", result.stdout)

    def test_reviewer_writes_a_fresh_findings_file_and_names_it(self):
        self._eligible_task()
        self._git()
        result = self.invoke("prompt_task_reviewer", "--inline", 60, "--commits", "HEAD~1..HEAD")
        self.assertEqual(result.code, 0, result.stderr)
        match = re.search(r"Write your review into `([^`]+)`", result.stdout)
        assert match is not None
        path = Path(match.group(1))
        self.assertEqual(path.parent, self.work / ".pdlc" / "cache" / "60")
        outline = path.read_text()
        self.assertIn("Task review complete: WORK-60-TASK-001", outline)
        for heading in ("### Implementation findings", "### Test findings", "### Verdict"):
            self.assertIn(heading, outline)

        path.write_text("stale review")
        self.invoke("prompt_task_reviewer", "--inline", 60, "--commits", "HEAD~1..HEAD")
        self.assertEqual(path.read_text(), outline)

    # --- implementer with review findings ---

    def test_implementer_carries_blocking_implementation_findings(self):
        self._eligible_task()
        review = self._review(
            implementation="- F1 [P1] [blocking] src/a.py:4 — drops retry",
            test="- F2 [P2] [blocking] tests/test_a.py — asserts a mock",
        )
        result = self.invoke("prompt_task_implementer", "--inline", 60, "--findings", review)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("## Findings to address", result.stdout)
        self.assertIn("F1 [P1] [blocking] src/a.py:4 — drops retry", result.stdout)
        self.assertNotIn("asserts a mock", result.stdout)

    def test_implementer_findings_reach_the_pr_fix_and_triage_forms(self):
        self._implemented_stack()
        self._threads([{"pr": 40, "author": "r", "path": "a", "line": 1, "body": "b", "url": "u"}])
        review = self._review(implementation="- F1 [P1] [blocking] a:1 — still wrong")
        pr_fix = self.invoke("prompt_task_implementer", "--inline", 60, "--findings", review)
        self.assertEqual(pr_fix.code, 0, pr_fix.stderr)
        self.assertIn("unresolved review comments on pull request `40`", pr_fix.stdout)
        self.assertIn("## Review findings", pr_fix.stdout)
        self.assertIn("F1 [P1] [blocking] a:1 — still wrong", pr_fix.stdout)

        self._threads([])
        self.add_rework_review(60)
        triage = self.invoke("prompt_task_implementer", "--inline", 60, "--findings", review)
        self.assertEqual(triage.code, 0, triage.stderr)
        self.assertIn("The branches below are a stack of pull requests", triage.stdout)
        self.assertIn("## Review findings", triage.stdout)
        self.assertIn("F1 [P1] [blocking] a:1 — still wrong", triage.stdout)

    def test_implementer_without_blocking_findings_exits_3_and_writes_no_brief(self):
        self._eligible_task()
        review = self._review(
            implementation="- F1 [P3] [non-blocking] src/a.py:9 — naming",
            test="- F2 [P1] [blocking] tests/test_a.py — misses the retry path",
        )
        result = self.invoke("prompt_task_implementer", 60, "--findings", review)
        self.assertEqual(result.code, 3, result.stderr)
        self.assertIn("the implementation agent is not needed and no brief was written", result.stdout)
        self.assertIn("Continue with the skill's next step.", result.stdout)
        self.assertFalse(list((self.work / ".pdlc" / "cache" / "60").glob("*prompt-task-implementer*")))

    def test_implementer_refuses_a_malformed_or_unfilled_findings_file(self):
        self._eligible_task()
        for findings, reason in (
            ("text:F1 [blocking] something", "missing `### Implementation findings`"),
            (self._review(verdict="<Changes Required|Approval Required>"), "has no verdict"),
        ):
            with self.subTest(reason=reason):
                result = self.invoke("prompt_task_implementer", "--inline", 60, "--findings", findings)
                self.assertEqual(result.code, 1)
                self.assertIn(reason, result.stderr)

    def test_reviewer_requires_the_commits_to_read(self):
        self._eligible_task()
        result = self.invoke("prompt_task_reviewer", "--inline", 60)
        self.assertNotEqual(result.code, 0)
        self.assertIn("--commits", result.stderr)

    # --- test-writer ---

    def _test_brief(self, *extra: str):
        return self.invoke(
            "prompt_task_test_writer", "--inline", 60, "--commits", "HEAD~1..HEAD",
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
        self.assertNotIn("## Review findings to address", result.stdout)
        self.assertNotIn("## Production code changed for review", result.stdout)
        self.assertNotIn("{{", result.stdout)

    def test_test_writer_carries_both_sections_of_the_review(self):
        self._eligible_task()
        self._git()
        result = self._test_brief("--findings", self._review(
            implementation="- F1 [P1] [blocking] src/a.py:4 — drops retry",
            test="- F2 [P2] [blocking] tests/test_a.py — asserts a mock",
        ))
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("## Review findings to address\n", result.stdout)
        self.assertIn("F2 [P2] [blocking] tests/test_a.py — asserts a mock", result.stdout)
        self.assertIn("## Production code changed for review\n", result.stdout)
        self.assertIn("F1 [P1] [blocking] src/a.py:4 — drops retry", result.stdout)
        self.assertIn("may not have applied it", result.stdout)

    def test_test_writer_takes_findings_without_a_report(self):
        self._eligible_task()
        self._git()
        result = self.invoke(
            "prompt_task_test_writer", "--inline", 60, "--commits", "HEAD~1..HEAD",
            "--traceability", "text:FR-1 -> loads -> src/a.py",
            "--findings", self._review(
                implementation="- F1 [P3] [non-blocking] src/a.py:4 — rename",
                test="- F2 [P2] [blocking] tests/test_a.py — thin",
            ),
        )
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("No production code changed on this pass.", result.stdout)
        self.assertIn("F2 [P2] [blocking] tests/test_a.py — thin", result.stdout)
        self.assertNotIn("## Production code changed for review", result.stdout)
        self.assertNotIn("src/a.py:4 — rename", result.stdout)

    def test_test_writer_requires_a_report_or_findings_and_its_map(self):
        self._eligible_task()
        self._git()
        result = self.invoke(
            "prompt_task_test_writer", "--inline", 60, "--commits", "HEAD~1..HEAD", "--traceability", "text:m",
        )
        self.assertEqual(result.code, 1)
        self.assertIn("--report is required unless --findings is given", result.stderr)
        result = self.invoke(
            "prompt_task_test_writer", "--inline", 60, "--commits", "HEAD~1..HEAD", "--report", "text:r",
        )
        self.assertNotEqual(result.code, 0)
        self.assertIn("--traceability", result.stderr)

    def test_every_agent_briefs_the_same_task(self):
        self._eligible_task()
        self._git()
        for brief in (
            self.invoke("prompt_task_implementer", "--inline", 60),
            self.invoke("prompt_task_reviewer", "--inline", 60, "--commits", "HEAD~1..HEAD"),
            self._test_brief(),
        ):
            self.assertEqual(brief.code, 0, brief.stderr)
            self.assertIn("`WORK-60-TASK-001` (tag included) — `[CORE] Core work`", brief.stdout)

    # --- acceptance test writer ---

    def _acceptance_brief(self, *extra: str):
        return self.invoke(
            "prompt_acceptance_test_writer", "--inline", 60, "--traceability", "text:FR-1 -> loads -> src/a.py", *extra,
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
        result = self.invoke("prompt_acceptance_test_writer", "--inline", 60)
        self.assertNotEqual(result.code, 0)
        self.assertIn("--traceability", result.stderr)

    # --- refusals ---

    def test_a_record_that_is_not_due_refuses_rather_than_briefing(self):
        self.seed_record(60, "Testing", "Pending", slug="record-60")
        result = self.invoke("prompt_task_implementer", "--inline", 60)
        self.assertEqual(result.code, 1)
        self.assertIn("Not ready", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_nothing_due_refuses_rather_than_briefing_an_empty_unit(self):
        self._implemented_stack(gate="Pending")
        result = self.invoke("prompt_task_implementer", "--inline", 60)
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
        return self.invoke("prompt_task_planner", "--inline", 60, *extra)

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
        self.assertIn("## Return\n\nReturn the revised manifest and its task files", result.stdout)
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
        self.assertNotIn("## Changes needed", result.stdout)
        self.assertIn("Findings recorded against this stage since it last published. Reconcile them against the work item", result.stdout)
        self.assertLess(result.stdout.index("### Change requests"), result.stdout.index("## Existing tasks"))
        self.assertIn("The published Tasks stage was invalidated for this reason. Reconcile the breakdown against it.\n\n--- BEGIN INVALIDATION REASON ---\n\ndetail\n\n--- END INVALIDATION REASON ---", result.stdout)
        self.assertIn("- `TASK-001` — [CORE] Core work (open, unplanned, unimplemented)", result.stdout)
        self.assertNotIn("--- BEGIN TASK BODY ---", result.stdout)
        self.assertIn("task-planner-manifest", result.stdout)
        self.assertIn("--- BEGIN CHANGE REQUESTS ---", result.stdout)
        match = re.search(r"Revise the task breakdown at `([^`]+)`", result.stdout)
        self.assertIsNotNone(match)
        manifest = json.loads(Path(match.group(1)).read_text(encoding="utf-8"))
        self.assertEqual(manifest[0]["action"], "retain")
        self.assertEqual(manifest[0]["id"], "TASK-001")
        self.assertEqual(manifest[0]["type"], "core")
        self.assertEqual(len(manifest[0]["baseline"]), 64)
        self.assertIn("## Scope\nx", Path(manifest[0]["body"]).read_text(encoding="utf-8"))

    def test_follow_up_is_carried_verbatim(self):
        self._tasks_stage_pending()
        manifest = self.write_file("current-tasks.json", "[]\n")
        result = self._planner_brief(
            "--current-tasks-manifest-path", manifest,
            "--follow-up", "text:split the export task in two",
        )
        self.assertNotIn("## Changes needed", result.stdout)
        self.assertNotIn("### Change requests", result.stdout)
        self.assertIn(
            "### Driver follow-up\n\nA change the driver asked for, or findings from a review of the breakdown, "
            "verbatim. Apply it to the tasks it affects; if it conflicts with the work item, stop and report it."
            "\n\n--- BEGIN DRIVER FOLLOW-UP ---\n\nsplit the export task in two\n\n--- END DRIVER FOLLOW-UP ---",
            result.stdout,
        )

    def test_follow_up_alone_revises_the_published_tasks_or_a_first_breakdown(self):
        self._tasks_stage_pending()
        first = self._planner_brief("--follow-up", "text:split the export task")
        self.assertEqual(first.code, 0, first.stderr)
        self.assertIn("No delivery tasks exist yet.", first.stdout)
        self.assertIn("### Driver follow-up", first.stdout)
        self.assertIn("split the export task", first.stdout)

        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work")
        published = self._planner_brief("--follow-up", "text:split the export task")
        self.assertEqual(published.code, 0, published.stderr)
        self.assertRegex(published.stdout, r"Revise the task breakdown at `[^`]*task-planner-manifest[^`]*`")
        self.assertIn("split the export task", published.stdout)

    def test_supplied_manifest_is_revised_with_or_without_follow_up(self):
        self._tasks_stage_pending()
        manifest = self.write_file("current-tasks.json", "[]\n")
        manifest_only = self._planner_brief("--current-tasks-manifest-path", manifest)
        self.assertEqual(manifest_only.code, 0, manifest_only.stderr)
        self.assertIn(f"Revise the task breakdown at `{Path(manifest).resolve()}`", manifest_only.stdout)
        self.assertNotIn("### Driver follow-up", manifest_only.stdout)
        missing_manifest = self._planner_brief(
            "--current-tasks-manifest-path", str(self.work / "missing.json"),
            "--follow-up", "text:revise",
        )
        self.assertNotEqual(missing_manifest.code, 0)
        self.assertIn("does not exist", missing_manifest.stderr)

    def test_changes_required_record_carries_open_review_findings(self):
        self.seed_record(60, "Tasks", "Changes Required", slug="record-60")
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work")
        self.add_rework_review(60, stage="Tasks")
        result = self._planner_brief()
        self.assertEqual(result.code, 0, result.stderr)
        self.assertNotIn("## Changes needed", result.stdout)
        self.assertIn("Findings recorded against this stage since it last published. Reconcile them against the work item", result.stdout)
        self.assertIn("## Findings\n\n- detail", result.stdout)

    def test_a_record_not_at_tasks_refuses(self):
        self.seed_record(60, "Testing", "Pending", slug="record-60")
        result = self._planner_brief()
        self.assertEqual(result.code, 1)
        self.assertIn("not Tasks", result.stderr)
        self.assertEqual(result.stdout, "")

    # --- tech planner ---

    def _tech_brief(self, *extra: str):
        return self.invoke("prompt_tech_planner", "--inline", 60, *extra)

    def test_tech_planner_writes_a_file_per_open_task_and_skips_implemented_ones(self):
        self._plan_stage()
        result = self._tech_brief()
        self.assertEqual(result.code, 0, result.stderr)
        manifest = Path(re.search(r"The manifest at `([^`]+)`", result.stdout).group(1))
        entries = json.loads(manifest.read_text())
        self.assertEqual([entry["id"] for entry in entries], ["TASK-001", "TASK-002"])
        self.assertEqual(entries[0]["number"], 601)
        planned = Path(entries[0]["file"]).read_text()
        self.assertTrue(planned.startswith("--- BEGIN TASK ---\n\n## Scope\nBuild the seam."))
        self.assertIn("--- BEGIN TECH PLAN ---\n\nTouch one module.\n\n--- END TECH PLAN ---\n", planned)
        self.assertIn("<!-- Tech plan is empty", Path(entries[1]["file"]).read_text())
        self.assertIn(f"- `TASK-001` — [CORE] Core work (planned): `{entries[0]['file']}`", result.stdout)
        self.assertIn(f"- `TASK-002` — [UI] Second (no plan yet): `{entries[1]['file']}`", result.stdout)
        # Bodies and plans live in the files, not the brief.
        self.assertNotIn("Build the seam.", result.stdout)
        self.assertNotIn("Touch one module.", result.stdout)
        self.assertIn("- No plan yet (TASK-002): plan these from scratch.", result.stdout)
        # Nothing to check a planned task against, so it is left alone.
        self.assertIn("- Already planned (TASK-001): leave their plans unchanged.", result.stdout)
        self.assertNotIn("TASK-003", result.stdout)
        self.assertIn("## Designing the plan", result.stdout)
        self.assertNotIn("## Shape of the change", result.stdout)
        self.assertNotIn("## Changes needed", result.stdout)
        self.assertNotIn("{{", result.stdout)
        for leak in ("pdlc inspect", "pdlc post", "pdlc prompt"):
            self.assertNotIn(leak, result.stdout)

    def test_tech_planner_revises_an_earlier_passes_files(self):
        self._plan_stage()
        first = self._tech_brief()
        manifest = re.search(r"The manifest at `([^`]+)`", first.stdout).group(1)
        result = self._tech_brief("--current-plan-manifest-path", manifest, "--follow-up", "text:tighten TASK-002")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn(f"The manifest at `{Path(manifest).resolve()}`", result.stdout)
        self.assertIn("tighten TASK-002", result.stdout)

    def test_tech_planner_revision_reads_unlanded_drafts_from_the_task_files(self):
        # Neither task has a recorded plan; the first pass drafted TASK-001 only.
        self.seed_record(60, "Technical Plan", "Pending", slug="record-60")
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work", body="## Scope\nBuild.\n")
        self.seed_task(60, 602, "TASK-002", "OPEN", "WORK-60-TASK-002 [UI] Second", body="## Scope\nShow.\n")
        manifest = self.plan_manifest(60, {"TASK-001": "Own src/a.py."})
        entries = json.loads(Path(manifest).read_text())
        result = self._tech_brief("--current-plan-manifest-path", manifest, "--follow-up", "text:tighten TASK-001")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn(f"- `TASK-001` — [CORE] Core work (drafted, not yet landed): `{entries[0]['file']}`", result.stdout)
        self.assertIn(f"- `TASK-002` — [UI] Second (no plan yet): `{entries[1]['file']}`", result.stdout)
        self.assertIn("- No plan yet (TASK-002): plan these from scratch.", result.stdout)
        self.assertIn("- Drafted, not yet landed (TASK-001): the plan in each file is an earlier pass's draft.", result.stdout)
        self.assertNotIn("Already planned", result.stdout)
        # The draft is left for the planner to revise, not reset.
        self.assertIn("Own src/a.py.", Path(entries[0]["file"]).read_text())

    def test_tech_planner_revision_tells_a_revised_recorded_plan_from_an_unchanged_one(self):
        self.seed_record(60, "Technical Plan", "Pending", slug="record-60")
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work", body="## Scope\nBuild.\n")
        self.seed_plan_comment(60, 601, "Touch one module.")
        self.seed_task(60, 602, "TASK-002", "OPEN", "WORK-60-TASK-002 [UI] Second", body="## Scope\nShow.\n")
        self.seed_plan_comment(60, 602, "Render the list.")
        manifest = self.plan_manifest(60, {"TASK-001": "Touch two modules."})
        result = self._tech_brief("--current-plan-manifest-path", manifest, "--follow-up", "text:tighten TASK-001")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("- `TASK-001` — [CORE] Core work (drafted, not yet landed):", result.stdout)
        self.assertIn("- `TASK-002` — [UI] Second (planned):", result.stdout)
        self.assertIn("- Drafted, not yet landed (TASK-001):", result.stdout)
        self.assertIn("- Already planned (TASK-002): check each against the driver follow-up below.", result.stdout)
        self.assertNotIn("No plan yet", result.stdout)

    def test_tech_planner_carries_the_stage_evidence_and_follow_up(self):
        self._plan_stage(gate="Stale")
        self.add_invalidation(60, stage="Technical Plan")
        result = self._tech_brief("--follow-up", "text:re-spike TASK-001")
        self.assertIn("Invalidated stage: Technical Plan", result.stdout)
        self.assertIn("--- BEGIN CHANGE REQUESTS ---", result.stdout)
        self.assertIn("- Already planned (TASK-001): check each against the change requests and driver follow-up below.", result.stdout)
        self.assertIn("The change requests and driver follow-up below apply to this pass.", result.stdout)
        self.assertIn("### Driver follow-up\n\nA change the driver asked for, or findings from a review of your plans, verbatim.\n\n--- BEGIN DRIVER FOLLOW-UP ---\n\nre-spike TASK-001\n\n--- END DRIVER FOLLOW-UP ---\n", result.stdout)

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


class ChangedSinceLastPublishTest(PromptHarness):
    """A planning stage re-running over its own published work sees exactly
    the upstream patches and invalidations newer than its latest publication."""

    def setUp(self) -> None:
        super().setUp()
        self.seed_record(60, "Tasks", "Pending", slug="record-60")
        self.seed_task(
            60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work",
            body="## Scope\nBuild the seam.\n\nCovers FR-1.\n\n## Acceptance criteria\n- it works\n",
        )
        self._plan(60, 601)

    def _brief(self, command: str) -> str:
        result = self.invoke(command, "--inline", 60)
        self.assertEqual(result.code, 0, result.stderr)
        return result.stdout

    def _first_pass_through_technical_plan(self) -> None:
        self._log("PDLC-UI\n\nui", "PDLC-TASKS\n\ntasks", "PDLC-PLAN\n\nplans")
        self._patch_back_to_ui("impact A")
        self._at("Tasks", "Pending")
        brief = self._brief("prompt_task_planner")
        self.assertIn("### Changed since last publish", brief)
        self.assertIn("Patched stage: Product", brief)
        self.assertIn("impact A", brief)
        self._log("PDLC-TASKS\n\ntasks again")
        self._at("Technical Plan", "Pending")
        # Technical Plan last published before the rewind, so it sees the same change.
        plan = self._brief("prompt_tech_planner")
        self.assertIn("### Changed since last publish", plan)
        self.assertIn("impact A", plan)
        self.assertIn("check each against the upstream changes below", plan)
        self._log("PDLC-PLAN\n\nplans again")

    def test_rewind_to_tasks_shows_only_its_own_invalidation(self):
        self._first_pass_through_technical_plan()
        self._log("PDLC-INVALIDATED\n\nInvalidated stage: Tasks\n\nsplit the export task")
        self._at("Tasks", "Stale")
        brief = self._brief("prompt_task_planner")
        self.assertNotIn("### Changed since last publish", brief)
        self.assertNotIn("impact A", brief)
        self.assertIn("### Invalidation reason", brief)
        self.assertIn("split the export task", brief)

    def test_second_patch_back_to_ui_shows_only_the_second_change(self):
        self._first_pass_through_technical_plan()
        self._patch_back_to_ui("impact B")
        self._at("Tasks", "Pending")
        brief = self._brief("prompt_task_planner")
        self.assertIn("### Changed since last publish", brief)
        self.assertIn("impact B", brief)
        self.assertNotIn("impact A", brief)

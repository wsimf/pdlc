"""`pdlc prompt` renders the brief for the unit the Implementation loop is on."""

from __future__ import annotations

from tests._prompts import PromptHarness


class PromptCommandTest(PromptHarness):
    # --- implement ---

    def test_eligible_task_renders_the_implementation_brief(self):
        self._eligible_task()
        result = self.invoke("prompt", 60, "--agent", "implementer")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("You are implementing one delivery task's production code.", result.stdout)
        self.assertIn("`WORK-60-TASK-001` (tag included) — `[CORE] Core work`", result.stdout)
        self.assertIn("Touch one module.", result.stdout)
        self.assertIn("Build the seam.", result.stdout)

    def test_the_brief_never_leaves_an_unfilled_placeholder(self):
        self._eligible_task()
        result = self.invoke("prompt", 60, "--agent", "implementer")
        self.assertNotIn("{{", result.stdout)

    def test_the_brief_names_no_pdlc_command_or_stage(self):
        self._eligible_task()
        result = self.invoke("prompt", 60, "--agent", "implementer")
        for leak in ("pdlc inspect", "pdlc post", "pdlc checkout", "Gate State"):
            self.assertNotIn(leak, result.stdout)

    def test_covered_requirements_are_carried_in_full(self):
        self._eligible_task()
        result = self.invoke("prompt", 60, "--agent", "implementer")
        # BODY_DEFAULT lists requirements as bullets, not headings.
        self.assertIn("FR-1: The record lands.", result.stdout)
        self.assertNotIn("FR-2", result.stdout)

    def test_a_cited_requirement_missing_from_the_record_is_reported_not_dropped(self):
        self._eligible_task(body="## Scope\nCovers FR-9.\n")
        result = self.invoke("prompt", 60, "--agent", "implementer")
        self.assertIn("FR-9 — not found in the record's `## Product`", result.stdout)

    def test_a_first_task_carries_no_findings_and_no_upstream(self):
        self._eligible_task()
        result = self.invoke("prompt", 60, "--agent", "implementer")
        self.assertNotIn("## Findings to address", result.stdout)
        self.assertIn("Upstream tasks it depends on, and what each shipped: none", result.stdout)

    def test_an_invalidated_task_carries_the_invalidation_as_findings(self):
        self._invalidated_task()
        result = self.invoke("prompt", 60, "--agent", "implementer")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("## Findings to address", result.stdout)
        self.assertIn("Invalidated stage: Implementation", result.stdout)

    def test_the_verify_section_appears_only_with_a_build_run_capability(self):
        self._eligible_task()
        without = self.invoke("prompt", 60, "--agent", "implementer")
        self.assertNotIn("## Verify", without.stdout)

        self._build_run("build-run-ios")
        with_skill = self.invoke("prompt", 60, "--agent", "implementer")
        self.assertIn("## Verify", with_skill.stdout)
        self.assertIn("invoke the `build-run-ios` skill", with_skill.stdout)

    def test_a_later_task_summarises_what_upstream_shipped(self):
        self._second_task_eligible()
        result = self.invoke("prompt", 60, "--agent", "implementer")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("`WORK-60-TASK-002` (tag included) — `[UI] Second`", result.stdout)
        self.assertIn("- `WORK-60-TASK-001` [CORE] Core work: Added the loader.", result.stdout)

    # --- pr-fix ---

    def test_an_unresolved_thread_renders_the_review_comment_brief(self):
        self._implemented_stack()
        self._threads([
            {"pr": 40, "author": "reviewer", "path": "src/a.py", "line": 4, "body": "drops retry", "url": "u"},
        ])
        result = self.invoke("prompt", 60, "--agent", "implementer")
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
        result = self.invoke("prompt", 60, "--agent", "implementer")
        self.assertIn("## Failing checks", result.stdout)
        self.assertIn("PR #40: FAILURE", result.stdout)

    def test_red_checks_without_a_thread_use_the_implementation_brief(self):
        self._implemented_stack()
        self._prs([
            {"number": 40, "title": "t", "url": "u40", "state": "OPEN", "isDraft": False,
             "branch": "b", "mergedAt": None, "checks": "FAILURE"},
        ])
        result = self.invoke("prompt", 60, "--agent", "implementer")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("You are implementing one delivery task's production code.", result.stdout)
        self.assertIn("## Findings to address", result.stdout)
        self.assertIn("PR #40: FAILURE", result.stdout)

    # --- triage ---

    def test_open_change_requests_render_the_triage_brief_with_the_whole_stack(self):
        self._implemented_stack()
        self.add_rework_review(60)
        result = self.invoke("prompt", 60, "--agent", "implementer")
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
        result = self.invoke("prompt", 60, "--agent", "reviewer", "--commits", "HEAD~1..HEAD")
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
        result = self.invoke("prompt", 60, "--agent", "reviewer")
        self.assertEqual(result.code, 1)
        self.assertIn("--commits is required", result.stderr)

    # --- test-writer ---

    def _test_brief(self, *extra: str):
        return self.invoke(
            "prompt", 60, "--agent", "test-writer", "--commits", "HEAD~1..HEAD",
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
        result = self.invoke("prompt", 60, "--agent", "test-writer", "--commits", "HEAD~1..HEAD")
        self.assertEqual(result.code, 1)
        self.assertIn("--report is required", result.stderr)

    def test_every_agent_briefs_the_same_task(self):
        self._eligible_task()
        self._git()
        for brief in (
            self.invoke("prompt", 60, "--agent", "implementer"),
            self.invoke("prompt", 60, "--agent", "reviewer", "--commits", "HEAD~1..HEAD"),
            self._test_brief(),
        ):
            self.assertEqual(brief.code, 0, brief.stderr)
            self.assertIn("`WORK-60-TASK-001` (tag included) — `[CORE] Core work`", brief.stdout)

    # --- refusals ---

    def test_a_record_that_is_not_due_refuses_rather_than_briefing(self):
        self.seed_record(60, "Testing", "Pending", slug="record-60")
        result = self.invoke("prompt", 60, "--agent", "implementer")
        self.assertEqual(result.code, 1)
        self.assertIn("Not ready", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_nothing_due_refuses_rather_than_briefing_an_empty_unit(self):
        self._implemented_stack(gate="Pending")
        result = self.invoke("prompt", 60, "--agent", "implementer")
        self.assertEqual(result.code, 1)
        self.assertIn("no unit is due", result.stderr)

    def test_an_unknown_agent_is_rejected(self):
        self._eligible_task()
        result = self.invoke("prompt", 60, "--agent", "planner")
        self.assertNotEqual(result.code, 0)

    def test_the_agent_flag_is_required(self):
        self._eligible_task()
        result = self.invoke("prompt", 60)
        self.assertNotEqual(result.code, 0)

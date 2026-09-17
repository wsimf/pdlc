"""Read-only inspectors on the file backend: `pdlc inspect`, `pdlc inspect
task`, `pdlc inspect timeline`, and the per-stage readiness reports."""

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from _support import FileBackendTest, _file_config
from pdlc.config import install_config, load_config


class InspectTests(FileBackendTest):
    def setUp(self):
        super().setUp()
        self.seed_record(20, "Implementation", "Pending", body=(
            "## Product\n\nThe shell ships.\n\n## UI\n\nUJ-1.\n\n"
            "## Decisions\n- none\n\n## Open Questions\n- none\n"
        ))
        self.seed_task(20, 201, "TASK-001", "OPEN", "WORK-20-TASK-001 Build core")
        self.seed_prs(20, [{
            "number": 148, "title": "Implement record 20", "url": "https://x/148",
            "state": "OPEN", "isDraft": False, "branch": "feature/x",
            "mergedAt": None, "checks": "SUCCESS", "relation": "closes",
        }])

    def test_compact_inspection_points_at_a_temp_file_and_renders_the_pr(self):
        result = self.invoke("inspect", 20)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("# Work Item", result.stdout)
        self.assertIn("number: 148", result.stdout)
        self.assertNotIn("The shell ships", result.stdout)

    def test_full_inspection_includes_the_body(self):
        result = self.invoke("inspect", 20, "--full")
        self.assertIn("The shell ships", result.stdout)

    def test_due_next_verification_approved_gate_is_curated(self):
        # Verification is fully curated like every other stage now, so its
        # Approved gate renders the same plain heal text the rest use, not
        # the generic `pdlc continue — self-heals to X` fallback.
        self.seed_record(21, "Verification", "Approved")
        out = self.invoke("inspect", 21, "--full").stdout
        self.assertIn("Due next: Verification.Approved → This work item has been approved to continue.", out)
        self.assertIn("Call `pdlc next 21` to continue this work item.", out)

    def test_due_next_verification_decision_required_gate_is_curated(self):
        self.seed_record(22, "Verification", "Decision Required")
        out = self.invoke("inspect", 22, "--full").stdout
        self.assertIn("Due next: Verification.DecisionRequired → This work item is pending user decision.", out)
        self.assertIn("pdlc inspect timeline", out)

    def test_due_next_ci_pending_hint_only_fires_for_a_ci_gated_stage(self):
        self.seed_record(23, "Product", "CI Pending")
        out = self.invoke("inspect", 23, "--full").stdout
        self.assertNotIn("resolve-ci", out)
        self.assertIn("pdlc next", out)

    def test_inspect_task_renders_one_task(self):
        result = self.invoke("inspect_task", 201)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("## Scope", result.stdout)

    def test_inspect_task_puts_attachments_after_the_front_matter(self):
        result = self.invoke("inspect_task", 201)
        out = result.stdout
        self.assertLess(out.index("number: 201"), out.index("## Attachments"))
        self.assertLess(out.index("## Attachments"), out.index("# Task"))

    def _seed_comments(self):
        log = self.records_dir() / "20" / "comments.jsonl"
        entries = [
            {"body": "PDLC-PRODUCT\n\nMARKED_BODY_TEXT", "createdAt": "2026-01-01T00:00:00Z",
             "url": "file://x/20#c1", "author": {"login": "bot"}},
            {"body": "does this cover the offline case?", "createdAt": "2026-01-02T00:00:00Z",
             "url": "file://x/20#c2", "author": {"login": "sudara"}},
        ]
        log.write_text("".join(json.dumps(entry) + "\n" for entry in entries))

    def test_inspect_surfaces_unmarked_user_comments(self):
        self._seed_comments()
        out = self.invoke("inspect", 20, "--full").stdout
        self.assertIn("## User Comments", out)
        self.assertIn("does this cover the offline case?", out)
        self.assertNotIn("MARKED_BODY_TEXT", out)
        # Section order: Work Item, Attachments, User Comments, Tasks.
        self.assertLess(out.index("# Work Item"), out.index("## Attachments"))
        self.assertLess(out.index("## Attachments"), out.index("## User Comments"))
        self.assertLess(out.index("## User Comments"), out.index("# Tasks"))

    def _seed_task_comments(self):
        log = self.records_dir() / "20" / "tasks" / "201" / "comments.jsonl"
        entries = [
            {"body": "PDLC-REVIEW\n\nMARKED_TASK_TEXT", "createdAt": "2026-01-01T00:00:00Z",
             "url": "file://x/201#c1", "author": {"login": "bot"}},
            {"body": "is the retry budget shared with the parent?", "createdAt": "2026-01-02T00:00:00Z",
             "url": "file://x/201#c2", "author": {"login": "sudara"}},
        ]
        log.write_text("".join(json.dumps(entry) + "\n" for entry in entries))

    def test_inspect_task_surfaces_its_own_unmarked_comments_not_the_parents(self):
        self._seed_comments()
        self._seed_task_comments()
        out = self.invoke("inspect_task", 201).stdout
        self.assertIn("## User Comments", out)
        self.assertLess(out.index("## User Comments"), out.index("# Task"))
        # The task's own discussion, not the parent Work Item's.
        self.assertIn("is the retry budget shared with the parent?", out)
        self.assertNotIn("does this cover the offline case?", out)
        # Marker comments stay out of the user-comment section.
        self.assertNotIn("MARKED_TASK_TEXT", out)

    def test_inspect_task_does_not_leak_plan_or_implementation_into_user_comments(self):
        log = self.records_dir() / "20" / "tasks" / "201" / "comments.jsonl"
        entries = [
            {"body": "## Technical Plan\n\nPLAN_BODY_TEXT", "createdAt": "2026-01-01T00:00:00Z",
             "url": "file://x/201#p", "author": {"login": "planner"}},
            {"body": "## Implementation\n\nIMPL_BODY_TEXT", "createdAt": "2026-01-02T00:00:00Z",
             "url": "file://x/201#i", "author": {"login": "impl"}},
            {"body": "is the retry budget shared with the parent?", "createdAt": "2026-01-03T00:00:00Z",
             "url": "file://x/201#c", "author": {"login": "sudara"}},
        ]
        log.write_text("".join(json.dumps(entry) + "\n" for entry in entries))

        out = self.invoke("inspect_task", 201).stdout
        user_section = out[out.index("## User Comments"):out.index("# Task")]
        self.assertNotIn("PLAN_BODY_TEXT", user_section)
        self.assertNotIn("IMPL_BODY_TEXT", user_section)
        self.assertIn("is the retry budget shared with the parent?", user_section)
        # The plan still renders through its own section further down.
        self.assertIn("PLAN_BODY_TEXT", out)

    def test_inspect_task_renders_user_comments_none_when_the_task_has_none(self):
        out = self.invoke("inspect_task", 201).stdout
        self.assertIn("## User Comments\n\nNone", out)

    def test_missing_record_is_a_hard_stop(self):
        result = self.invoke("inspect", 999)
        self.assertEqual(result.code, 1)
        self.assertIn("no PDLC record for #999", result.stderr)


class TimelineTests(FileBackendTest):
    def _seed_with_comments(self):
        self.seed_record(30, "Testing", "Pending")
        log = self.records_dir() / "30" / "comments.jsonl"
        entries = [
            {"body": "PDLC-PRODUCT\n\nProduct authored.", "createdAt": "2026-01-01T00:00:00Z",
             "url": "file://x/30#comment-1", "author": {"login": "a"}},
            {"body": "PDLC-APPROVED\n\nProduct approved.", "createdAt": "2026-01-02T00:00:00Z",
             "url": "file://x/30#comment-2", "author": {"login": "b"}},
        ]
        log.write_text("".join(json.dumps(entry) + "\n" for entry in entries))

    def test_compact_timeline_indexes_and_points_at_a_temp_file(self):
        self._seed_with_comments()
        result = self.invoke("inspect_timeline", 30)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("## PRODUCT", result.stdout)
        self.assertIn("## APPROVED", result.stdout)

    def test_full_timeline_streams_the_whole_log(self):
        self._seed_with_comments()
        result = self.invoke("inspect_timeline", 30, "--full")
        self.assertIn("# Timeline", result.stdout)
        self.assertIn("Product authored.", result.stdout)


class ReadinessReportTests(FileBackendTest):
    def test_inspect_review_reports_a_ready_stage(self):
        self.seed_record(40, "Implementation", "Review Required")
        self.seed_prs(40, [{
            "number": 5, "title": "impl", "url": "u", "state": "OPEN", "isDraft": False,
            "branch": "b", "mergedAt": None, "checks": "SUCCESS", "relation": "closes",
        }])
        result = self.invoke("inspect_review", 40)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Reviewer Target", result.stdout)

    def test_inspect_review_refuses_a_skipped_stage(self):
        self.seed_record(41, "Testing", "Review Required", skipped="Testing")
        result = self.invoke("inspect_review", 41)
        self.assertIn("Skipped States", result.stdout)

    def test_inspect_test_reports_readiness(self):
        self.seed_record(42, "Testing", "Pending")
        result = self.invoke("inspect_test", 42)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Readiness", result.stdout)

    def test_inspect_verify_reports_readiness(self):
        self.seed_record(43, "Verification", "Pending")
        result = self.invoke("inspect_verify", 43)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Readiness", result.stdout)

    def test_inspect_complete_reports_not_ready_for_an_unfinished_record(self):
        self.seed_record(44, "Implementation", "Pending")
        result = self.invoke("inspect_complete", 44)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Not ready", result.stdout)


class InspectTaskAgentTests(FileBackendTest):
    """`pdlc inspect task`: the per-task implementer routing section."""

    def _capabilities(self, config: str | None = None) -> None:
        """Point capability resolution at a throwaway repo root for this test."""
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / ".git").mkdir()
        if config is not None:
            (root / ".pdlc").mkdir()
            (root / ".pdlc" / "config.toml").write_text(config)
        # `load_config` merges the throwaway repo's capability tables into the
        # process; re-pin the file backend so the inspectors still run locally.
        load_config(root)
        install_config(_file_config())
        self.addCleanup(load_config)

    def test_agent_section_names_the_configured_implementer_for_the_phase(self):
        self._capabilities('[agents]\ncore-implementer = "my-core-implementer"\nui-implementer = "my-ui-implementer"\n')
        self.seed_record(70, "Implementation", "Pending", slug="record-70")
        self.seed_task(70, 701, "TASK-001", "OPEN", "WORK-70-TASK-001 [UI] UI work")

        result = self.invoke("inspect_task", 701)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("## Agent", result.stdout)
        self.assertIn("my-ui-implementer — the project's implementer for a [UI] task.", result.stdout)

    def test_core_task_routes_to_the_core_slot(self):
        self._capabilities('[agents]\ncore-implementer = "my-core-implementer"\n')
        self.seed_record(71, "Implementation", "Pending", slug="record-71")
        self.seed_task(71, 711, "TASK-001", "OPEN", "WORK-71-TASK-001 [CORE] Core work")

        result = self.invoke("inspect_task", 711)
        self.assertIn("my-core-implementer — the project's implementer for a [CORE] task.", result.stdout)

    def test_agent_section_falls_back_to_general_purpose(self):
        self._capabilities()
        self.seed_record(72, "Implementation", "Pending", slug="record-72")
        self.seed_task(72, 721, "TASK-001", "OPEN", "WORK-72-TASK-001 [CORE] Core work")

        result = self.invoke("inspect_task", 721)
        self.assertIn("general-purpose — the project's implementer", result.stdout)


class InspectImplementTests(FileBackendTest):
    """`pdlc inspect implement`: readiness + the single next eligible task."""

    def _plan(self, record: int, task_number: int, text: str = "## Technical Plan\n\nDo the thing.\n") -> None:
        log = self.records_dir() / str(record) / "tasks" / str(task_number) / "comments.jsonl"
        entry = {"body": text, "createdAt": "2026-03-01T00:00:00Z", "url": "", "author": {"login": "t"}}
        with log.open("a") as handle:
            handle.write(json.dumps(entry) + "\n")

    def _implemented(self, record: int, task_number: int) -> None:
        self._plan(record, task_number, "## Implementation\n\nShipped.\n")

    def _seed(self, record: int = 60, slug: str = "record-60", **kw) -> None:
        self.seed_record(record, "Implementation", "Pending", slug=slug, **kw)

    def _github_code_host(self) -> None:
        """Stack setup lines come from the code host, and only GitHub has a
        stacked-PR mechanism; the suite's default file host has none."""
        self.configure(code_host="github")

    def setUp(self) -> None:
        super().setUp()
        # Isolate from the developer checkout's own worktree config.
        self._after(None)

    def _after(self, value: str | None) -> None:
        patcher = patch("pdlc.commands.inspect_implement.worktree_after", return_value=value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _predecessor(self, status: str = "Implementation", gate: str = "Pending", *, prs: bool = True) -> None:
        self.seed_record(50, status, gate, slug="record-50")
        self.seed_task(50, 501, "TASK-001", "CLOSED", "WORK-50-TASK-001 [CORE] Base")
        self.seed_task(50, 502, "TASK-002", "CLOSED", "WORK-50-TASK-002 [CORE] Top")
        self._implemented(50, 501)
        self._implemented(50, 502)
        if prs:
            self.register_prs(501, [29])
            self.register_prs(502, [30])

    def _first_task(self) -> None:
        self._seed()
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work")
        self._plan(60, 601)

    def test_first_task_after_a_predecessor_enters_its_latest_task_pr(self):
        self._github_code_host()
        self._predecessor()
        self._first_task()
        self._after("50")

        result = self.invoke("inspect_implement", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("stackSetup: gh stack checkout 30 && gh stack add pdlc/record-60/task-001", result.stdout)
        self.assertIn("stackAfter: 50", result.stdout)

    def test_predecessor_without_a_task_pr_blocks_the_first_task(self):
        self._github_code_host()
        self._predecessor(prs=False)
        self._first_task()
        self._after("50")

        result = self.invoke("inspect_implement", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("blocked: this worktree stacks after work item 50", result.stdout)
        self.assertNotIn("stackSetup", result.stdout)

    def test_complete_predecessor_falls_back_to_a_fresh_stack(self):
        self._github_code_host()
        self._predecessor(status="Complete", gate="Approved")
        self._first_task()
        self._after("50")

        result = self.invoke("inspect_implement", 60)
        self.assertIn("stackSetup: gh stack init pdlc/record-60/task-001", result.stdout)
        self.assertNotIn("stackAfter", result.stdout)

    def test_own_previous_task_pr_wins_over_the_predecessor(self):
        self._github_code_host()
        self._seed()
        self.seed_task(60, 601, "TASK-001", "CLOSED", "WORK-60-TASK-001 [CORE] First")
        self.seed_task(60, 602, "TASK-002", "OPEN", "WORK-60-TASK-002 [CORE] Second")
        self._implemented(60, 601)
        self._plan(60, 602)
        self.register_prs(601, [40])
        self._after("50")

        result = self.invoke("inspect_implement", 60)
        self.assertIn("stackSetup: gh stack checkout 40 && gh stack add pdlc/record-60/task-002", result.stdout)
        self.assertNotIn("stackAfter", result.stdout)

    def test_reports_the_next_eligible_core_task_before_ui(self):
        self._github_code_host()
        self._seed()
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work")
        self.seed_task(60, 602, "TASK-002", "OPEN", "WORK-60-TASK-002 [UI] UI work")
        self._plan(60, 601)
        self._plan(60, 602)

        result = self.invoke("inspect_implement", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Ready — Gate State: Pending.", result.stdout)
        self.assertIn("### WORK-60-TASK-001 [CORE] Core work", result.stdout)
        self.assertIn("taskId: TASK-001", result.stdout)
        self.assertIn("branch: pdlc/record-60/task-001", result.stdout)
        self.assertIn("stackSetup: gh stack init pdlc/record-60/task-001", result.stdout)
        # The Technical Plan is not rendered here; the handoff routes to `inspect task` for it.
        self.assertNotIn("Do the thing.", result.stdout)
        self.assertIn("its `## Technical Plan`", result.stdout)
        self.assertIn("Judgment Required", result.stdout)

    def test_stack_entry_is_the_previous_implemented_tasks_pull_request(self):
        self._github_code_host()
        self._seed()
        self.seed_task(60, 601, "TASK-001", "CLOSED", "WORK-60-TASK-001 [CORE] First")
        self.seed_task(60, 602, "TASK-002", "OPEN", "WORK-60-TASK-002 [CORE] Second")
        self._implemented(60, 601)
        self._plan(60, 602)
        self.register_prs(601, [40])

        result = self.invoke("inspect_implement", 60)
        self.assertIn("### WORK-60-TASK-002 [CORE] Second", result.stdout)
        self.assertIn("stackSetup: gh stack checkout 40 && gh stack add pdlc/record-60/task-002", result.stdout)
        self.assertIn("stackEntryPr: 40", result.stdout)
        self.assertIn("1 of 2 delivery tasks closed.", result.stdout)

    def test_predecessor_without_a_registered_pr_gives_no_entry_point(self):
        # `gh stack checkout` needs a PR to discover the stack from. An
        # implemented task that never registered one cannot serve as one, so the
        # inspector says so by falling back to `init` rather than guessing.
        self._github_code_host()
        self._seed()
        self.seed_task(60, 601, "TASK-001", "CLOSED", "WORK-60-TASK-001 [CORE] First")
        self.seed_task(60, 602, "TASK-002", "OPEN", "WORK-60-TASK-002 [CORE] Second")
        self._implemented(60, 601)
        self._plan(60, 602)

        result = self.invoke("inspect_implement", 60)
        self.assertIn("stackSetup: gh stack init pdlc/record-60/task-002", result.stdout)
        self.assertNotIn("stackEntryPr", result.stdout)

    def test_unplanned_task_is_not_eligible(self):
        self._seed()
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] No plan yet")

        result = self.invoke("inspect_implement", 60)
        self.assertIn("no task is OPEN, planned, and not yet implemented", result.stdout)
        self.assertIn("not yet planned", result.stdout)
        self.assertNotIn("Judgment Required", result.stdout)

    def test_implementation_invalidated_task_is_still_eligible(self):
        # A PR stays attached across invalidation, so `hasImplementation` alone
        # would wrongly hide the task; `implementationInvalidated` (comment
        # missing while the PR is attached) is what re-offers it for rework.
        self._seed()
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Rework me")
        self._plan(60, 601)
        self.register_prs(601, [40])

        result = self.invoke("inspect_implement", 60)
        self.assertIn("### WORK-60-TASK-001 [CORE] Rework me", result.stdout)

    def test_task_filter_scopes_to_one_task(self):
        self._seed()
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] One")
        self.seed_task(60, 602, "TASK-002", "OPEN", "WORK-60-TASK-002 [CORE] Two")
        self._plan(60, 601)
        self._plan(60, 602)

        result = self.invoke("inspect_implement", 60, "--task", "2")
        self.assertIn("### WORK-60-TASK-002 [CORE] Two", result.stdout)
        self.assertNotIn("### WORK-60-TASK-001", result.stdout)

    def test_phase_filter_selects_ui(self):
        self._seed()
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core")
        self.seed_task(60, 602, "TASK-002", "OPEN", "WORK-60-TASK-002 [UI] Interface")
        self._plan(60, 601)
        self._plan(60, 602)

        result = self.invoke("inspect_implement", 60, "--phase", "ui")
        self.assertIn("### WORK-60-TASK-002 [UI] Interface", result.stdout)

    def test_a_code_host_without_a_stack_contributes_no_setup_line(self):
        # The suite's default file code host cannot submit stacked PRs, so it
        # offers no setup vocabulary either — the branch is still named.
        self._seed()
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work")
        self._plan(60, 601)

        result = self.invoke("inspect_implement", 60)
        self.assertIn("branch: pdlc/record-60/task-001", result.stdout)
        self.assertNotIn("stackSetup", result.stdout)

    def test_output_ends_by_handing_off_to_inspect_task(self):
        self._seed()
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work")
        self._plan(60, 601)

        result = self.invoke("inspect_implement", 60)
        self.assertIn("Next: run `pdlc inspect task 601`", result.stdout.strip().splitlines()[-1])

    def test_no_handoff_line_when_nothing_is_eligible(self):
        self._seed()
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] No plan yet")

        result = self.invoke("inspect_implement", 60)
        self.assertNotIn("pdlc inspect task", result.stdout)

    def test_not_ready_when_stage_is_not_implementation(self):
        self.seed_record(61, "Testing", "Pending", slug="record-61")
        result = self.invoke("inspect_implement", 61)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Not ready: Status is 'Testing'", result.stdout)
        self.assertNotIn("Next Task", result.stdout)

    def test_not_ready_at_review_required(self):
        self.seed_record(62, "Implementation", "Review Required", slug="record-62")
        result = self.invoke("inspect_implement", 62)
        self.assertIn("Not ready: Gate State is 'Review Required'", result.stdout)

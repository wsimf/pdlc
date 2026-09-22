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

    def test_inspect_test_names_the_top_task_when_head_is_below_it(self):
        self.seed_record(45, "Testing", "Pending")
        self.seed_task(45, 451, "TASK-001", "CLOSED", "WORK-45-TASK-001 [CORE] Core")
        (self.records_dir() / "45" / "tasks" / "451" / "comments.jsonl").write_text(json.dumps({
            "body": "## Implementation\n\nShipped.", "createdAt": "2026-01-01T00:00:00Z",
            "url": "u", "author": {"login": "x"},
        }) + "\n")
        pr = {"number": 150, "title": "t", "url": "u", "state": "OPEN", "isDraft": False,
              "branch": "pdlc/record-45/task-001", "mergedAt": None, "checks": "SUCCESS", "headSha": self.head_sha()}
        self.seed_prs(45, [pr])
        self.register_prs(451, [150])

        at_top = self.invoke("inspect_test", 45)
        self.assertEqual(at_top.code, 0, at_top.stderr)
        self.assertIn(f"Testing at HEAD {self.head_sha()} — every open task PR's head is included.", at_top.stdout)

        self.seed_prs(45, [{**pr, "headSha": "0" * 40}])
        below = self.invoke("inspect_test", 45).stdout
        self.assertIn("run `pdlc checkout WORK-45-TASK-001` to move to the top of the task stack", below)
        self.assertIn("- #150 (pdlc/record-45/task-001) @ 000000000000", below)

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
    """`pdlc inspect implement`: readiness, the mode, and the one unit to work next."""

    def _plan(self, record: int, task_number: int, text: str = "## Technical Plan\n\nDo the thing.\n") -> None:
        log = self.records_dir() / str(record) / "tasks" / str(task_number) / "comments.jsonl"
        entry = {"body": text, "createdAt": "2026-03-01T00:00:00Z", "url": "", "author": {"login": "t"}}
        with log.open("a") as handle:
            handle.write(json.dumps(entry) + "\n")

    def _implemented(self, record: int, task_number: int) -> None:
        self._plan(record, task_number, "## Implementation\n\nShipped.\n")

    def _seed(self, record: int = 60, slug: str = "record-60", gate: str = "Pending", **kw) -> None:
        self.seed_record(record, "Implementation", gate, slug=slug, **kw)

    def _github_code_host(self) -> None:
        """Stack setup lines come from the code host, and only GitHub has a
        stacked-PR mechanism; the suite's default file host has none. Live
        review-thread and PR state would need a real `gh`, so both read as
        clean unless a test says otherwise, and the checkout is on no stack."""
        self.configure(code_host="github")
        for target, value in (
            ("pdlc.commands.inspect_implement.record_open_review_comments", []),
            ("pdlc.commands.inspect_implement.record_pull_requests", []),
            ("pdlc.hosts.lib.github.code_host.GitHubCodeHost._current_stack", None),
        ):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _threads(self, threads: list[dict]) -> None:
        patcher = patch("pdlc.commands.inspect_implement.record_open_review_comments", return_value=threads)
        patcher.start()
        self.addCleanup(patcher.stop)

    def setUp(self) -> None:
        super().setUp()
        # Isolate from the developer checkout's own worktree config.
        self._after(None)

    def _after(self, value: str | None) -> None:
        patcher = patch("pdlc.internal.stack.worktree_after", return_value=value)
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

    def _implemented_stack(self, gate: str = "Changes Required", checks: tuple[str, str] = ("SUCCESS", "SUCCESS")) -> None:
        """Two closed, implemented tasks on PRs 40 (bottom) and 41 (top), with
        the record itself also registering the top PR as `post implement` does."""
        self._seed(gate=gate)
        self.seed_task(60, 601, "TASK-001", "CLOSED", "WORK-60-TASK-001 [CORE] First")
        self.seed_task(60, 602, "TASK-002", "CLOSED", "WORK-60-TASK-002 [UI] Second")
        self._implemented(60, 601)
        self._implemented(60, 602)
        self.seed_prs(60, [
            {"number": 40, "title": "First", "url": "u40", "state": "OPEN", "isDraft": True, "branch": "pdlc/record-60/task-001", "mergedAt": None, "checks": checks[0]},
            {"number": 41, "title": "Second", "url": "u41", "state": "OPEN", "isDraft": True, "branch": "pdlc/record-60/task-002", "mergedAt": None, "checks": checks[1]},
        ], register=False)
        self.register_prs(601, [40])
        self.register_prs(602, [41])
        self.register_prs(60, [41])

    def _sections(self, output: str) -> list[str]:
        return [line[3:] for line in output.splitlines() if line.startswith("## ")]

    # --- section layout ---

    def test_sections_come_in_a_fixed_order_ending_with_publish(self):
        self._first_task()
        result = self.invoke("inspect_implement", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(
            self._sections(result.stdout),
            ["Readiness", "Mode", "Attachments", "Next Task", "Publish"],
        )
        self.assertNotIn("## Remaining", result.stdout)
        self.assertNotIn("## Open Comments", result.stdout)

    def test_the_scoping_flags_are_gone(self):
        self._first_task()
        for flag in (("--task", "1"), ("--phase", "ui")):
            with self.subTest(flag=flag[0]):
                result = self.invoke("inspect_implement", 60, *flag)
                self.assertNotEqual(result.code, 0)

    # --- mode: implement ---

    def test_implement_mode_names_the_next_core_task_before_ui(self):
        self._github_code_host()
        self._seed()
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work")
        self.seed_task(60, 602, "TASK-002", "OPEN", "WORK-60-TASK-002 [UI] UI work")
        self._plan(60, 601)
        self._plan(60, 602)

        result = self.invoke("inspect_implement", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Ready — Gate State: Pending.", result.stdout)
        self.assertIn("mode: implement", result.stdout)
        self.assertIn("### WORK-60-TASK-001 [CORE] Core work", result.stdout)
        self.assertNotIn("### WORK-60-TASK-002", result.stdout)
        self.assertIn("taskId: TASK-001", result.stdout)
        self.assertIn("branch: pdlc/record-60/task-001", result.stdout)
        # The Technical Plan is not rendered here; the handoff routes to `inspect task` for it.
        self.assertNotIn("Do the thing.", result.stdout)
        self.assertIn("Next: Run `pdlc inspect task 601`", result.stdout)
        self.assertIn("then `pdlc checkout 601` and dispatch that sub-agent to implement the task", result.stdout)
        self.assertIn("run `pdlc post implement-task 601 SUMMARY` to record the implementation, open the task's PR, and close the task.", result.stdout)

    def test_implement_mode_ignores_open_threads_while_a_task_is_eligible(self):
        # New tasks come first under Pending; threads are picked up once none is left.
        self._first_task()
        self._threads([{"pr": 151, "author": "reviewer", "body": "this drops the retry", "url": "u1", "path": "src/chart.py", "line": 42}])

        result = self.invoke("inspect_implement", 60)
        self.assertIn("mode: implement", result.stdout)
        self.assertNotIn("this drops the retry", result.stdout)

    def test_first_task_after_a_predecessor_with_a_task_pr_is_not_blocked(self):
        self._github_code_host()
        self._predecessor()
        self._first_task()
        self._after("50")

        result = self.invoke("inspect_implement", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertNotIn("blocked:", result.stdout)
        self.assertNotIn("gh stack", result.stdout)
        self.assertIn("Next: Run `pdlc inspect task", result.stdout)

    def test_predecessor_without_a_task_pr_blocks_the_first_task(self):
        self._github_code_host()
        self._predecessor(prs=False)
        self._first_task()
        self._after("50")

        result = self.invoke("inspect_implement", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("blocked: this worktree stacks after work item 50", result.stdout)
        self.assertNotIn("Next: Run", result.stdout)

    def test_complete_predecessor_falls_back_to_a_fresh_stack(self):
        self._github_code_host()
        self._predecessor(status="Complete", gate="Approved")
        self._first_task()
        self._after("50")

        result = self.invoke("inspect_implement", 60)
        self.assertNotIn("blocked:", result.stdout)
        self.assertIn("Next: Run `pdlc inspect task", result.stdout)

    def test_stale_task_is_eligible_and_carries_its_invalidation(self):
        # A PR stays attached across invalidation, so `hasImplementation` alone
        # would wrongly hide the task; `implementationInvalidated` (comment
        # missing while the PR is attached) is what re-offers it for rework,
        # with the task's own PDLC-INVALIDATED comment inline for the brief.
        self._seed(gate="Stale")
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Rework me")
        self._plan(60, 601)
        self._plan(60, 601, "PDLC-INVALIDATED\n\nInvalidated stage: Implementation\n\nThe loader contract changed.\n")
        self.register_prs(601, [40])

        result = self.invoke("inspect_implement", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("mode: implement", result.stdout)
        self.assertIn("### WORK-60-TASK-001 [CORE] Rework me", result.stdout)
        self.assertIn("reconcile: implementation invalidated on ", result.stdout)
        self.assertIn("#### Invalidation\nInvalidated stage: Implementation\n\nThe loader contract changed.", result.stdout)
        self.assertLess(result.stdout.index("#### Invalidation"), result.stdout.index("Next: Run"))

    # --- mode: none ---

    def test_unplanned_task_waits_on_planning(self):
        self._seed()
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] No plan yet")

        result = self.invoke("inspect_implement", 60)
        self.assertIn("mode: none", result.stdout)
        self.assertIn("None. WORK-60-TASK-001 [CORE] No plan yet has no technical plan yet.", result.stdout)
        self.assertIn("Nothing to publish yet.", result.stdout)
        self.assertNotIn("## Checks", result.stdout)
        self.assertNotIn("pdlc inspect task", result.stdout)

    def test_all_settled_names_the_stage_publish(self):
        self._implemented_stack(gate="Pending")

        result = self.invoke("inspect_implement", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("mode: none", result.stdout)
        self.assertEqual(
            self._sections(result.stdout),
            ["Readiness", "Mode", "Attachments", "Checks", "Next Task", "Publish"],
        )
        self.assertIn("- PR #40: green\n- PR #41: green", result.stdout)
        self.assertIn("None. Every delivery task is closed. Continue the workflow with the command under `## Publish`.", result.stdout)
        self.assertIn("Run `pdlc post implement 60 EVIDENCE` to publish the stage at Review Required.", result.stdout)

    def test_pending_checks_are_never_a_unit_or_a_publish_blocker(self):
        self._implemented_stack(gate="Pending", checks=("SUCCESS", "IN_PROGRESS"))

        result = self.invoke("inspect_implement", 60)
        self.assertIn("mode: none", result.stdout)
        self.assertIn("- PR #41: pending", result.stdout)
        self.assertIn("None. Every delivery task is closed. Continue the workflow with the command under `## Publish`.", result.stdout)
        self.assertIn("Run `pdlc post implement 60 EVIDENCE` to publish the stage at Review Required.", result.stdout)

    def test_no_checks_configured_counts_as_settled(self):
        self._implemented_stack(gate="Pending", checks=("NONE", "NONE"))
        result = self.invoke("inspect_implement", 60)
        self.assertIn("mode: none", result.stdout)
        self.assertIn("Run `pdlc post implement 60 EVIDENCE`", result.stdout)

    # --- mode: rework ---

    def test_rework_takes_the_lowest_task_with_an_open_thread_first(self):
        self._implemented_stack()
        self._threads([
            {"pr": 41, "author": "reviewer", "body": "top comment", "url": "u2", "path": None, "line": None},
            {"pr": 40, "author": "reviewer", "body": "this drops the retry", "url": "u1", "path": "src/chart.py", "line": 42},
        ])

        result = self.invoke("inspect_implement", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Ready — Gate State: Changes Required.", result.stdout)
        self.assertIn("mode: rework", result.stdout)
        self.assertEqual(
            self._sections(result.stdout),
            ["Readiness", "Mode", "Attachments", "Next Fix", "Publish"],
        )
        self.assertIn("### WORK-60-TASK-001 [CORE] First\nnumber: 601\ntaskId: TASK-001\npr: 40\nbranch: pdlc/record-60/task-001\nstate: CLOSED", result.stdout)
        self.assertIn("published in PR #40. Run `pdlc checkout 601`", result.stdout)
        self.assertIn("#### Unresolved threads (1)\n- @reviewer on src/chart.py:42 — this drops the retry (u1)", result.stdout)
        self.assertNotIn("top comment", result.stdout)
        self.assertNotIn("#### Failing checks", result.stdout)
        self.assertIn("Next: Run `pdlc inspect task 601` for the implementer sub-agent under `## Agent`, then dispatch that sub-agent", result.stdout)
        self.assertIn("run `pdlc post implement-task 601 SUMMARY` to re-land the fix on the task's PR; the task stays closed.", result.stdout)

    def test_rework_takes_a_red_check_as_a_unit(self):
        self._implemented_stack(checks=("SUCCESS", "FAILURE"))

        result = self.invoke("inspect_implement", 60)
        self.assertIn("mode: rework", result.stdout)
        self.assertIn("### WORK-60-TASK-002 [UI] Second", result.stdout)
        self.assertIn("#### Failing checks (1)\n- PR #41: FAILURE (u41)", result.stdout)
        self.assertNotIn("#### Unresolved threads", result.stdout)

    def test_rework_runs_under_pending_once_every_task_is_closed(self):
        self._implemented_stack(gate="Pending")
        self._threads([{"pr": 40, "author": "reviewer", "body": "early comment", "url": "u1", "path": None, "line": None}])

        result = self.invoke("inspect_implement", 60)
        self.assertIn("Ready — Gate State: Pending.", result.stdout)
        self.assertIn("mode: rework", result.stdout)
        self.assertIn("- @reviewer — early comment (u1)", result.stdout)

    def test_a_thread_on_a_pr_no_task_owns_is_charged_to_the_top_task(self):
        self._implemented_stack()
        self.register_prs(60, [42])
        self.seed_prs(60, [
            {"number": 40, "title": "First", "url": "u40", "state": "OPEN", "isDraft": True, "branch": "b1", "mergedAt": None, "checks": "SUCCESS"},
            {"number": 41, "title": "Second", "url": "u41", "state": "OPEN", "isDraft": True, "branch": "b2", "mergedAt": None, "checks": "SUCCESS"},
            {"number": 42, "title": "Stray", "url": "u42", "state": "OPEN", "isDraft": True, "branch": "b3", "mergedAt": None, "checks": "SUCCESS"},
        ], register=False)
        self._threads([{"pr": 42, "author": "reviewer", "body": "stray", "url": "u3", "path": None, "line": None}])

        result = self.invoke("inspect_implement", 60)
        self.assertIn("mode: rework", result.stdout)
        self.assertIn("### WORK-60-TASK-002 [UI] Second", result.stdout)
        self.assertIn("- @reviewer — stray (u3)", result.stdout)

    def test_rework_carries_open_decision_resolutions_with_the_unit(self):
        # An escalated thread stays open on the host, so its unit comes round
        # again after the driver answers; the answer must ride with it.
        self._implemented_stack()
        log = self.records_dir() / "60" / "comments.jsonl"
        with log.open("a") as handle:
            handle.write(json.dumps({
                "body": "PDLC-RESOLUTION\n\nResolved stage: Implementation\n\n### Retry on load\nDecision: keep the retry\nRationale: offline-first\nAffects: TASK-001\n",
                "createdAt": "2026-04-02T00:00:00Z", "url": "r1", "author": {"login": "driver"},
            }) + "\n")
        self._threads([{"pr": 40, "author": "reviewer", "body": "this drops the retry", "url": "u1", "path": None, "line": None}])

        result = self.invoke("inspect_implement", 60)
        self.assertIn("mode: rework", result.stdout)
        self.assertIn("#### Decisions (1)", result.stdout)
        self.assertIn("##### Decision resolution — ", result.stdout)
        self.assertIn("(r1)", result.stdout)
        self.assertIn("###### Retry on load\nDecision: keep the retry\nRationale: offline-first\nAffects: TASK-001", result.stdout)
        self.assertLess(result.stdout.index("#### Decisions"), result.stdout.index("Next: Run"))
        self.assertNotIn("## Open Requests", result.stdout)

    def test_rework_without_a_resolution_prints_no_decisions_block(self):
        self._implemented_stack()
        self.add_rework_review(60)
        self._threads([{"pr": 40, "author": "reviewer", "body": "fix me", "url": "u1", "path": None, "line": None}])
        result = self.invoke("inspect_implement", 60)
        self.assertIn("mode: rework", result.stdout)
        self.assertNotIn("#### Decisions", result.stdout)

    def test_rework_comes_before_triage(self):
        self._implemented_stack()
        self.add_rework_review(60)
        self._threads([{"pr": 40, "author": "reviewer", "body": "fix me", "url": "u1", "path": None, "line": None}])

        result = self.invoke("inspect_implement", 60)
        self.assertIn("mode: rework", result.stdout)
        self.assertNotIn("## Open Requests", result.stdout)

    # --- mode: triage ---

    def test_triage_prints_every_open_request_in_full_with_the_stack(self):
        self._implemented_stack()
        self.add_rework_review(60)

        result = self.invoke("inspect_implement", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("mode: triage", result.stdout)
        self.assertEqual(
            self._sections(result.stdout),
            ["Readiness", "Mode", "Attachments", "Open Requests", "Publish"],
        )
        self.assertIn("Every delivery task is already implemented and published in the PR stack below", result.stdout)
        self.assertIn("### Verification bounce — ", result.stdout)
        self.assertIn("#### Findings\n\n- detail", result.stdout)
        self.assertNotIn("\n## Findings", result.stdout)
        self.assertIn("#### Stack\n- WORK-60-TASK-001 [CORE] First (number 601, PR #40)\n- WORK-60-TASK-002 [UI] Second (number 602, PR #41, top)", result.stdout)
        self.assertIn("These requests stay listed until the stage publishes", result.stdout)
        self.assertIn("dispatch that sub-agent once with every request above and the stack", result.stdout)
        self.assertIn("run `pdlc post implement 60 EVIDENCE` from the top branch to push the whole stack", result.stdout)
        self.assertNotIn("post implement-task", result.stdout)

    def test_a_published_request_is_not_triaged_again(self):
        self._implemented_stack(gate="Pending")
        self.add_rework_review(60)
        self.seed_publication(60, "Implementation", passed_review=False)

        result = self.invoke("inspect_implement", 60)
        self.assertIn("mode: none", result.stdout)
        self.assertNotIn("## Open Requests", result.stdout)

    # --- readiness ---

    def test_an_open_task_with_a_live_implementation_is_not_routed_around(self):
        self._seed()
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Half landed")
        self._plan(60, 601)
        self._implemented(60, 601)
        self.register_prs(601, [40])

        result = self.invoke("inspect_implement", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Not ready: WORK-60-TASK-001 [CORE] Half landed (number 601) has an implementation recorded but is still open.", result.stdout)
        self.assertIn("`pdlc post implement-task 601 SUMMARY`", result.stdout)
        self.assertNotIn("## Mode", result.stdout)

    def test_not_ready_skips_the_live_host_reads(self):
        # Another stage owns the record, so its PR threads are not this
        # command's business — and the host is not queried for them.
        self.seed_record(63, "Testing", "Pending", slug="record-63")
        with patch("pdlc.commands.inspect_implement.record_open_review_comments") as threads, \
                patch("pdlc.commands.inspect_implement.record_pull_requests") as prs:
            result = self.invoke("inspect_implement", 63)
        threads.assert_not_called()
        prs.assert_not_called()
        self.assertNotIn("## Mode", result.stdout)

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

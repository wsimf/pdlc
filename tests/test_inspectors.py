"""Read-only inspectors on the file backend: `pdlc inspect`, `pdlc inspect
task`, `pdlc inspect timeline`, and the per-stage readiness reports."""

import json

from _support import FileBackendTest


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

    def test_inspect_task_renders_one_task(self):
        result = self.invoke("inspect_task", 201)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("## Scope", result.stdout)

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

    def test_reports_the_next_eligible_core_task_before_ui(self):
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
        self.assertIn("Do the thing.", result.stdout)
        self.assertIn("Judgment Required", result.stdout)

    def test_stack_entry_is_the_previous_implemented_tasks_pull_request(self):
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

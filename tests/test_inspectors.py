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

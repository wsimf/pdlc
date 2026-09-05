"""Explicit task pull-request registration: the machine-owned metadata block on
a delivery task's body, the `pdlc post attach-pr` command, and the automatic
registration `pdlc post implement-task` performs for every task."""

import unittest

from _support import FileBackendTest

from pdlc.domain.model import read_task_meta, strip_task_meta, task_prs, write_task_meta

BODY = "## Scope\nDo the thing.\n\n## Acceptance criteria\n- ok\n"


class TaskMetaBlockTests(unittest.TestCase):
    def test_round_trips_pr_numbers_without_touching_the_body(self):
        stamped = write_task_meta(BODY, {"prs": ["148", "152"]})
        self.assertTrue(stamped.startswith("<!-- pdlc:meta\n"))
        self.assertEqual(task_prs(stamped), [148, 152])
        self.assertEqual(strip_task_meta(stamped), BODY)

    def test_plain_body_has_no_metadata(self):
        self.assertEqual(read_task_meta(BODY), {})
        self.assertEqual(task_prs(BODY), [])
        self.assertEqual(strip_task_meta(BODY), BODY)

    def test_rewrite_replaces_the_block_and_dedupes(self):
        once = write_task_meta(BODY, {"prs": ["148"]})
        twice = write_task_meta(once, {"prs": ["148", "160"]})
        self.assertEqual(task_prs(twice), [148, 160])
        self.assertEqual(strip_task_meta(twice), BODY)

    def test_empty_meta_removes_the_block(self):
        stamped = write_task_meta(BODY, {"prs": ["148"]})
        self.assertEqual(write_task_meta(stamped, {"prs": []}), BODY)


class AttachPrCommandTests(FileBackendTest):
    def setUp(self):
        super().setUp()
        self.seed_record(70, "Implementation", "Pending")
        self.seed_task(70, 701, "TASK-001", "OPEN", "WORK-70-TASK-001 [CORE] Core", body=BODY)

    def _body(self):
        return (self.records_dir() / "70" / "tasks" / "701" / "body.md").read_text()

    def test_attaches_and_is_idempotent(self):
        first = self.invoke("post_attach_pr", 701, 148)
        self.assertEqual(first.json, {"task": 701, "prs": [148]})

        again = self.invoke("post_attach_pr", 701, "#148")
        self.assertEqual(again.json, {"task": 701, "prs": [148]})

        second = self.invoke("post_attach_pr", 701, 160)
        self.assertEqual(second.json, {"task": 701, "prs": [148, 160]})
        self.assertEqual(strip_task_meta(self._body()), BODY)

    def test_rejects_a_non_delivery_work_item(self):
        result = self.invoke("post_attach_pr", 70, 148)
        self.assertEqual(result.code, 1)

    def test_rejects_a_non_numeric_pr(self):
        result = self.invoke("post_attach_pr", 701, "feature")
        self.assertEqual(result.code, 1)

    def test_inspect_task_reports_prs_and_hides_the_block(self):
        self.invoke("post_attach_pr", 701, 148)
        rendered = self.invoke("inspect_task", 701).stdout
        self.assertIn("prs:", rendered)
        self.assertIn("- 148", rendered)
        self.assertNotIn("pdlc:meta", rendered)


class MetaSurvivesRePlanTests(FileBackendTest):
    def setUp(self):
        super().setUp()
        self.seed_record(70, "Implementation", "Pending", slug="record-70")
        self.seed_task(70, 701, "TASK-001", "OPEN", "WORK-70-TASK-001 [CORE] Core", body=BODY)

    def test_upsert_keeps_registered_prs_and_reports_unchanged(self):
        from pdlc.hosts.workitem_host import get_backend
        from pdlc.internal.workitem import task_tree

        self.invoke("post_attach_pr", 701, 148)

        backend = get_backend()
        existing = task_tree("70")
        body_file = self.write_file("task.md", BODY)
        results = backend.upsert_tasks("70", [{"id": "TASK-001", "title": "[CORE] Core", "body": body_file}], existing)

        self.assertEqual(results[0]["action"], "unchanged")
        self.assertEqual(task_tree("70")[0]["prs"], [148])
        self.assertEqual(
            strip_task_meta((self.records_dir() / "70" / "tasks" / "701" / "body.md").read_text()),
            BODY,
        )


class RecordPullRequestsTests(FileBackendTest):
    def setUp(self):
        super().setUp()
        self.seed_record(70, "Verification", "Pending")
        self.seed_task(70, 701, "TASK-001", "CLOSED", "WORK-70-TASK-001 [CORE] Core", body=BODY)
        self.seed_prs(70, [
            {"number": 148, "title": "task pr", "url": "u", "state": "MERGED",
             "isDraft": False, "branch": "pdlc/record-70/task-001", "mergedAt": "x", "checks": "SUCCESS"},
            {"number": 900, "title": "stray", "url": "u", "state": "OPEN",
             "isDraft": False, "branch": "other", "mergedAt": None, "checks": "FAILURE"},
        ], register=False)

    def test_only_registered_prs_are_returned(self):
        from pdlc.internal.pull_requests import record_pull_requests

        self.invoke("post_attach_pr", 701, 148)
        prs = record_pull_requests("70")
        self.assertEqual([pr["number"] for pr in prs], [148])


if __name__ == "__main__":
    unittest.main()

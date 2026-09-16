"""`pdlc post tasks` reopening delivery tasks a re-landed breakdown rewrites."""

import json

from _support import BODY_DEFAULT, TASK_BODY_DEFAULT, FileBackendTest

# No journey to cover, so each case can land a single CORE task.
NO_UI_BODY = BODY_DEFAULT.replace("UJ-1 covers the first run.", "No UI is required.")


class TasksReopenTests(FileBackendTest):
    def setUp(self):
        super().setUp()
        self.seed_record(40, "Tasks", "Pending", body=NO_UI_BODY)
        self.body_file = self.write_file("task-body.md", "reworked task body\n")
        self.unchanged_body = self.write_file("unchanged-body.md", TASK_BODY_DEFAULT)

    def _land(self, tasks):
        manifest = self.write_file("m.json", json.dumps(tasks))
        return self.invoke("post_tasks", "--work-item", 40, "--stage", "Tasks",
                           "--manifest", manifest, "--evidence", self.evidence_file())

    def test_rewriting_a_closed_task_reopens_it_and_retires_its_evidence(self):
        self.seed_task(40, 401, "TASK-001", "CLOSED", "WORK-40-TASK-001 [CORE] one")
        self.seed_plan_comment(40, 401, "Add the validation helper.")
        self.seed_implementation_comment(40, 401, "Shipped the endpoint.")
        self.register_prs(401, [900])

        result = self._land([
            {"id": "TASK-001", "title": "one", "body": self.body_file,
             "ui": False, "covers": ["FR-1", "FR-2", "C-1"]},
        ])
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["reopened"], ["TASK-001"])
        self.assertEqual(self.task_meta(40, 401)["state"], "OPEN")

        task = self.invoke("inspect_task", 401).stdout
        self.assertIn("hasPlan: false", task)
        # `hasImplementation` tracks the attached pull request, which this never
        # touches; retiring the comment is what flips `implementationInvalidated`.
        self.assertIn("hasImplementation: true", task)
        self.assertIn("implementationInvalidated: true", task)

        comments = self.task_comments_text(40, 401)
        self.assertNotIn("Add the validation helper.", comments)
        self.assertNotIn("Shipped the endpoint.", comments)
        self.assertIn("Invalidated stage: Technical Plan", comments)
        self.assertIn(
            "Reopened for rework, their plan and implementation retired: TASK-001",
            self.comments_text(40),
        )

    def test_an_unchanged_closed_task_stays_closed(self):
        self.seed_task(40, 402, "TASK-002", "CLOSED", "WORK-40-TASK-002 [CORE] two")
        self.seed_implementation_comment(40, 402, "Shipped the endpoint.")

        result = self._land([
            {"id": "TASK-002", "title": "two", "body": self.unchanged_body,
             "ui": False, "covers": ["FR-1", "FR-2", "C-1"]},
        ])
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["unchanged"], ["TASK-002"])
        self.assertEqual(result.json["reopened"], [])
        self.assertEqual(self.task_meta(40, 402)["state"], "CLOSED")
        self.assertIn("Shipped the endpoint.", self.task_comments_text(40, 402))
        self.assertNotIn("Reopened for rework", self.comments_text(40))

    def test_rewriting_an_open_task_leaves_its_evidence_alone(self):
        self.seed_task(40, 403, "TASK-003", "OPEN", "WORK-40-TASK-003 [CORE] three")
        self.seed_plan_comment(40, 403, "Add the validation helper.")

        result = self._land([
            {"id": "TASK-003", "title": "three reworded", "body": self.body_file,
             "ui": False, "covers": ["FR-1", "FR-2", "C-1"]},
        ])
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["retitled"], ["TASK-003"])
        self.assertEqual(result.json["reopened"], [])
        self.assertEqual(self.task_meta(40, 403)["state"], "OPEN")
        self.assertIn("Add the validation helper.", self.task_comments_text(40, 403))

    def test_dry_run_reports_the_closed_tasks_the_breakdown_lands_onto(self):
        self.seed_task(40, 404, "TASK-004", "CLOSED", "WORK-40-TASK-004 [CORE] four")
        self.seed_task(40, 405, "TASK-005", "OPEN", "WORK-40-TASK-005 [CORE] five")
        manifest = self.write_file("m.json", json.dumps([
            {"id": "TASK-004", "title": "four", "body": self.body_file,
             "ui": False, "covers": ["FR-1", "FR-2", "C-1"]},
            {"id": "TASK-005", "title": "five", "body": self.body_file,
             "ui": False, "covers": ["FR-1"]},
        ]))
        result = self.invoke("post_tasks", "--work-item", 40, "--stage", "Tasks",
                             "--manifest", manifest, "--dry-run")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["reopenCandidates"], ["TASK-004"])
        self.assertEqual(self.task_meta(40, 404)["state"], "CLOSED")

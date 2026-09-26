"""`pdlc post tasks` reopening delivery tasks a re-landed breakdown rewrites,
and carrying landed tasks forward untouched with `"unchanged": true`."""

import json

from _support import BODY_DEFAULT, FileBackendTest

# No journey to cover, so each case can land a single CORE task.
NO_UI_BODY = BODY_DEFAULT.replace("UJ-1 covers the first run.", "No UI is required.")


class TasksReopenTests(FileBackendTest):
    def setUp(self):
        super().setUp()
        self.seed_record(40, "Tasks", "Pending", body=NO_UI_BODY)
        self.body_file = self.write_file("task-body.md", "**Blocked by:** None\n**Type:** AFK\n**Requirements Covered:** FR-1, FR-2, C-1\n\n**Scope:**\nRework the task.\n\n**Acceptance Criteria:**\n- [ ] The new behavior works.\n")
        self.fr1_body_file = self.write_file("fr1-body.md", "**Blocked by:** None\n**Type:** AFK\n**Requirements Covered:** FR-1\n\n**Scope:**\nKeep the first task.\n\n**Acceptance Criteria:**\n- [ ] The first behavior works.\n")
        self.unchanged_text = "**Blocked by:** None\n**Type:** AFK\n**Requirements Covered:** FR-1, FR-2, C-1\n\n**Scope:**\nKeep the shipped task.\n\n**Acceptance Criteria:**\n- [ ] The shipped behavior works.\n"
        self.unchanged_body = self.write_file("unchanged-body.md", self.unchanged_text)

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
        self.seed_task(40, 402, "TASK-002", "CLOSED", "WORK-40-TASK-002 [CORE] two", body=self.unchanged_text)
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
            {"id": "TASK-005", "title": "five", "body": self.fr1_body_file,
             "ui": False, "covers": ["FR-1"]},
        ]))
        result = self.invoke("post_tasks", "--work-item", 40, "--stage", "Tasks",
                             "--manifest", manifest, "--dry-run")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["reopenCandidates"], ["TASK-004"])
        self.assertEqual(self.task_meta(40, 404)["state"], "CLOSED")


class TasksCarryForwardTests(FileBackendTest):
    def setUp(self):
        super().setUp()
        self.seed_record(41, "Tasks", "Pending", body=NO_UI_BODY)
        self.body_file = self.write_file("task-body.md", "**Blocked by:** TASK-001\n**Type:** AFK\n**Requirements Covered:** FR-2\n\n**Scope:**\nRework the task.\n\n**Acceptance Criteria:**\n- [ ] The new behavior works.\n")
        self.seed_task(41, 411, "TASK-001", "CLOSED", "WORK-41-TASK-001 [CORE] one")
        self.seed_plan_comment(41, 411, "Add the validation helper.")
        self.seed_implementation_comment(41, 411, "Shipped the endpoint.")

    def _land(self, tasks):
        manifest = self.write_file("m.json", json.dumps(tasks))
        return self.invoke("post_tasks", "--work-item", 41, "--stage", "Tasks",
                           "--manifest", manifest, "--evidence", self.evidence_file())

    def test_carried_task_keeps_its_state_title_and_evidence(self):
        result = self._land([
            {"id": "TASK-001", "unchanged": True, "ui": False, "covers": ["FR-1", "FR-2", "C-1"]},
            {"title": "two", "body": self.body_file, "ui": False,
             "covers": ["FR-2"], "depends": ["TASK-001"]},
        ])
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["unchanged"], ["TASK-001"])
        self.assertEqual(result.json["created"], ["TASK-002"])
        self.assertEqual(result.json["reopened"], [])
        self.assertEqual(result.json["orphans"], [])
        self.assertEqual(result.json["order"], ["TASK-001", "TASK-002"])

        meta = self.task_meta(41, 411)
        self.assertEqual(meta["state"], "CLOSED")
        self.assertEqual(meta["title"], "WORK-41-TASK-001 [CORE] one")
        comments = self.task_comments_text(41, 411)
        self.assertIn("Add the validation helper.", comments)
        self.assertIn("Shipped the endpoint.", comments)

    def test_carried_task_reads_its_title_back_for_duplicate_detection(self):
        result = self._land([
            {"id": "TASK-001", "unchanged": True, "ui": False, "covers": ["FR-1", "FR-2", "C-1"]},
            {"title": "one", "body": self.body_file, "ui": False, "covers": ["FR-2"]},
        ])
        self.assertEqual(result.code, 1)
        self.assertIn("duplicate task title: one", result.stderr)

    def test_carried_task_rejections(self):
        cases = [
            ("the record has no such delivery task",
             [{"id": "TASK-009", "unchanged": True, "ui": False, "covers": ["FR-1"]}]),
            ("cannot also set a title",
             [{"id": "TASK-001", "unchanged": True, "title": "renamed", "ui": False, "covers": ["FR-1"]}]),
            ("unchanged must be true or false",
             [{"id": "TASK-001", "unchanged": "yes", "ui": False, "covers": ["FR-1"]}]),
        ]
        for expected, tasks in cases:
            with self.subTest(expected=expected):
                result = self._land(tasks)
                self.assertEqual(result.code, 1)
                self.assertIn(expected, result.stderr)
                self.assertEqual(self.task_meta(41, 411)["state"], "CLOSED")

    def test_carried_task_cannot_also_name_a_body(self):
        result = self._land([
            {"id": "TASK-001", "unchanged": True, "body": self.body_file,
             "ui": False, "covers": ["FR-1"]},
        ])
        self.assertEqual(result.code, 1)
        self.assertIn("cannot also set a body", result.stderr)

    def test_dry_run_flags_the_carried_entry_and_omits_it_from_candidates(self):
        manifest = self.write_file("m.json", json.dumps([
            {"id": "TASK-001", "unchanged": True, "ui": False, "covers": ["FR-1", "FR-2", "C-1"]},
        ]))
        result = self.invoke("post_tasks", "--work-item", 41, "--stage", "Tasks",
                             "--manifest", manifest, "--dry-run")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["tasks"][0]["unchanged"], True)
        self.assertEqual(result.json["tasks"][0]["title"], "[CORE] one")
        self.assertEqual(result.json["reopenCandidates"], [])

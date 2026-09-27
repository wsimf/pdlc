"""`pdlc post tasks` reopening delivery tasks a re-landed breakdown rewrites,
and carrying landed tasks forward untouched via `"action": "retain"`."""

import json
from unittest.mock import patch

from _support import BODY_DEFAULT, TASK_BODY_DEFAULT, FileBackendTest
from pdlc.domain.task_artifact import baseline_matches, same_task_body, snapshot, stored_fields
from pdlc.internal.workitem import subissues_for

# No journey to cover, so each case can land a single CORE task.
NO_UI_BODY = BODY_DEFAULT.replace("UJ-1 covers the first run.", "No UI is required.")


def _retain_entry(record: int, task_id: str, *, title: str, body: str, task_type: str = "core",
                   covers: list[str] | None = None, depends: list[str] | None = None) -> dict:
    """A retain entry naming an already-seeded task by its current stored
    content's baseline, so a re-land is recognised as an edit to that task
    rather than a new or unrelated one."""
    stored = next(task for task in subissues_for(str(record)) if task.get("taskId") == task_id)
    return {
        "id": task_id, "number": stored["number"], "action": "retain",
        "baseline": snapshot(stored_fields(stored)),
        "title": title, "body": body, "type": task_type,
        "covers": covers or [], "depends": depends or [],
    }


class TasksReopenTests(FileBackendTest):
    def test_task_body_comparison_ignores_only_line_endings_and_trailing_whitespace(self):
        self.assertTrue(same_task_body("one\r\ntwo\r\n", "one\ntwo\n"))
        self.assertFalse(same_task_body("one\n two\n", "one\ntwo\n"))
        self.assertTrue(same_task_body("one\ntwo\n", "one\ntwo"))
        self.assertTrue(same_task_body("one\ntwo  \n\n", "one\ntwo\n"))
        self.assertEqual(snapshot({"title": "one", "type": "core", "body": "one\ntwo\n"}),
                         snapshot({"title": "one", "type": "core", "body": "one\ntwo"}))
        fields = {"title": "one", "type": "core", "body": "one\r\ntwo\r\n"}
        self.assertEqual(snapshot(fields), snapshot({**fields, "body": "one\ntwo\n"}))
        self.assertTrue(baseline_matches(snapshot(fields), {**fields, "body": "one\ntwo\n"}))

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
            _retain_entry(40, "TASK-001", title="one", body=self.body_file, covers=["FR-1", "FR-2", "C-1"]),
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
            _retain_entry(40, "TASK-002", title="two", body=self.unchanged_body, covers=["FR-1", "FR-2", "C-1"]),
        ])
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["unchanged"], ["TASK-002"])
        self.assertEqual(result.json["reopened"], [])
        self.assertEqual(self.task_meta(40, 402)["state"], "CLOSED")
        self.assertIn("Shipped the endpoint.", self.task_comments_text(40, 402))
        self.assertNotIn("Reopened for rework", self.comments_text(40))

    def test_crlf_only_difference_does_not_rewrite_or_reopen_retained_task(self):
        self.seed_task(40, 402, "TASK-002", "CLOSED", "WORK-40-TASK-002 [CORE] two", body=self.unchanged_text)
        self.seed_plan_comment(40, 402, "Add the validation helper.")
        self.seed_implementation_comment(40, 402, "Shipped the endpoint.")
        stored = subissues_for("40")[0]
        baseline = snapshot(stored_fields(stored))
        manifest = self.write_file("m.json", json.dumps([
            {"id": "TASK-002", "number": 402, "action": "retain", "baseline": baseline,
             "title": "two", "body": self.unchanged_body, "type": "core",
             "covers": ["FR-1", "FR-2", "C-1"], "depends": []},
        ]))

        def crlf_task(issue):
            tasks = subissues_for(issue)
            return [{**task, "body": task["body"].replace("\n", "\r\n")} for task in tasks]

        with patch("pdlc.commands.post_tasks.subissues_for", side_effect=crlf_task):
            result = self.invoke("post_tasks", "--work-item", 40, "--stage", "Tasks",
                                 "--manifest", manifest, "--evidence", self.evidence_file())

        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["unchanged"], ["TASK-002"])
        self.assertEqual(result.json["reopened"], [])
        self.assertEqual(self.task_meta(40, 402)["state"], "CLOSED")
        self.assertIn("Add the validation helper.", self.task_comments_text(40, 402))
        self.assertIn("Shipped the endpoint.", self.task_comments_text(40, 402))

    def test_rewriting_an_open_task_leaves_its_evidence_alone(self):
        self.seed_task(40, 403, "TASK-003", "OPEN", "WORK-40-TASK-003 [CORE] three")
        self.seed_plan_comment(40, 403, "Add the validation helper.")

        result = self._land([
            _retain_entry(40, "TASK-003", title="three reworded", body=self.body_file, covers=["FR-1", "FR-2", "C-1"]),
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
            _retain_entry(40, "TASK-004", title="four", body=self.body_file, covers=["FR-1", "FR-2", "C-1"]),
            _retain_entry(40, "TASK-005", title="five", body=self.fr1_body_file, covers=["FR-1"]),
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
        self.retained_body_file = self.write_file("retained-body.md", TASK_BODY_DEFAULT)
        self.seed_task(41, 411, "TASK-001", "CLOSED", "WORK-41-TASK-001 [CORE] one")
        self.seed_plan_comment(41, 411, "Add the validation helper.")
        self.seed_implementation_comment(41, 411, "Shipped the endpoint.")

    def _land(self, tasks):
        manifest = self.write_file("m.json", json.dumps(tasks))
        return self.invoke("post_tasks", "--work-item", 41, "--stage", "Tasks",
                           "--manifest", manifest, "--evidence", self.evidence_file())

    def _retained_task_001(self, **overrides):
        """A retain entry that reproduces TASK-001's stored content exactly, so
        the command carries it forward as unchanged."""
        stored = subissues_for("41")[0]
        entry = {
            "id": "TASK-001", "number": stored["number"], "action": "retain",
            "baseline": snapshot(stored_fields(stored)),
            "title": "one", "body": self.retained_body_file, "type": "core",
            "covers": ["FR-1", "FR-2", "C-1"], "depends": [],
        }
        entry.update(overrides)
        return entry

    def test_carried_task_keeps_its_state_title_and_evidence(self):
        result = self._land([
            self._retained_task_001(),
            {"title": "two", "body": self.body_file, "type": "core",
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
            self._retained_task_001(),
            {"title": "one", "body": self.body_file, "type": "core", "covers": ["FR-2"], "depends": ["TASK-001"]},
        ])
        self.assertEqual(result.code, 1)
        self.assertIn("duplicate task title: one", result.stderr)

    def test_carried_task_rejections(self):
        cases = [
            ("it is not a task of work item #41",
             [{"id": "TASK-009", "action": "retain", "number": 999, "baseline": "x", "covers": ["FR-1"]}]),
            ('uses "unchanged"',
             [{"id": "TASK-001", "unchanged": True, "ui": False, "covers": ["FR-1"]}]),
        ]
        for expected, tasks in cases:
            with self.subTest(expected=expected):
                result = self._land(tasks)
                self.assertEqual(result.code, 1)
                self.assertIn(expected, result.stderr)
                self.assertEqual(self.task_meta(41, 411)["state"], "CLOSED")

    def test_dry_run_flags_the_carried_entry_and_omits_it_from_candidates(self):
        manifest = self.write_file("m.json", json.dumps([self._retained_task_001()]))
        result = self.invoke("post_tasks", "--work-item", 41, "--stage", "Tasks",
                             "--manifest", manifest, "--dry-run")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["tasks"][0]["unchanged"], True)
        self.assertEqual(result.json["tasks"][0]["title"], "[CORE] one")
        self.assertEqual(result.json["reopenCandidates"], [])

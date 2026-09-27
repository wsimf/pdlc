"""Every task breakdown validation error has a stable, actionable message."""

import copy
import json
import re
import unittest
from pathlib import Path
from unittest import mock

from _support import BODY_DEFAULT, FileBackendTest
from pdlc.domain.task_artifact import task_body_errors
from pdlc.domain.task_plan import build_plan


VALID_BODY = (
    "**Blocked by:** None\n"
    "**Type:** AFK\n"
    "**Requirements Covered:** FR-1, FR-2, C-1\n"
    "**UI Journeys:** UJ-1\n\n"
    "**Scope:**\nDeliver the task.\n\n"
    "**Acceptance Criteria:**\n- [ ] The task works.\n"
)


class TaskBodyErrorTests(unittest.TestCase):
    def test_each_required_body_field_has_its_own_error(self):
        cases = [
            (VALID_BODY.replace("**Blocked by:** None\n", ""), "add **Blocked by:** None or the TASK-NNN IDs this task depends on"),
            (VALID_BODY.replace("**Blocked by:** None", "**Blocked by:** later"), "**Blocked by:** must say None or name at least one TASK-NNN dependency"),
            (VALID_BODY.replace("**Requirements Covered:** FR-1, FR-2, C-1\n", ""), "add **Requirements Covered:** with the FR-*/C-* IDs this task delivers"),
            (VALID_BODY.replace("**UI Journeys:** UJ-1\n", ""), "add **UI Journeys:** with the UJ-* IDs this UI task delivers"),
            (VALID_BODY.replace("**Type:** AFK\n", ""), "add **Type:** AFK or HITL to classify whether implementation needs a human"),
            (VALID_BODY.replace("**Type:** AFK", "**Type:** maybe"), "add **Type:** AFK or HITL to classify whether implementation needs a human"),
            (VALID_BODY.replace("Deliver the task.", ""), "add a nonempty **Scope:** section describing what this task changes"),
            (VALID_BODY.replace("- [ ] The task works.", "- [ ] "), "add at least one nonempty `- [ ]` item under **Acceptance Criteria:** stating a verifiable outcome"),
            (VALID_BODY.replace("**Acceptance Criteria:**\n- [ ] The task works.\n", ""), "add at least one nonempty `- [ ]` item under **Acceptance Criteria:** stating a verifiable outcome"),
        ]
        for body, expected in cases:
            with self.subTest(expected=expected, body=body):
                self.assertEqual(task_body_errors(body, is_ui=True), [expected])

    def test_optional_fields_and_both_task_types_are_accepted(self):
        self.assertEqual(task_body_errors(VALID_BODY, is_ui=True), [])
        self.assertEqual(task_body_errors(VALID_BODY.replace("AFK", "HITL"), is_ui=True), [])
        core = VALID_BODY.replace("**UI Journeys:** UJ-1\n", "")
        self.assertEqual(task_body_errors(core, is_ui=False), [])


class TaskPlanErrorTests(unittest.TestCase):
    def setUp(self):
        self.tasks = [
            {"id": "TASK-001", "title": "Core", "ui": False, "covers": ["FR-1", "C-1"], "depends": []},
            {"id": "TASK-002", "title": "UI", "ui": True, "covers": ["FR-2", "UJ-1"], "depends": ["TASK-001"]},
        ]

    def _errors(self, tasks=None, existing=None):
        return build_plan(
            self.tasks if tasks is None else tasks,
            [] if existing is None else existing,
            ["FR-1", "FR-2", "C-1"], ["UJ-1"],
        )["errors"]

    def test_manifest_boundary_types(self):
        cases = [
            ("id", 1, "manifest entry 1 id must be a string"),
            ("title", 1, "manifest entry 1 title must be a string"),
            ("covers", "FR-1", "manifest entry 1 covers must be an array of strings"),
            ("depends", [1], "manifest entry 1 depends must be an array of strings"),
        ]
        for field, value, expected in cases:
            with self.subTest(field=field):
                tasks = copy.deepcopy(self.tasks)
                tasks[0][field] = value
                self.assertEqual(self._errors(tasks), [expected])

    def test_identity_coverage_and_dependency_errors(self):
        cases = [
            (0, "id", "TASK-nope", "malformed task id: TASK-nope; use TASK-NNN, such as TASK-001"),
            (1, "id", "TASK-001", "duplicate task id: TASK-001; give each task a distinct TASK-NNN identity"),
            (1, "title", "Core", "duplicate task title: Core; give each task a title that identifies its own scope"),
            (0, "title", "", "TASK-001 has no title; add a human-readable title for this task"),
            (0, "ui", "yes", "TASK-001 ui must be true or false, not 'yes'"),
            (0, "covers", ["FR-99", "C-1"], "TASK-001 covers FR-99, which the parent does not declare; use FR-*/C-* from Product and UJ-* from UI"),
            (1, "covers", ["UJ-1"], "TASK-002 covers no FR-* or C-*; map every task to at least one Product requirement or constraint"),
            (1, "covers", ["FR-2"], "TASK-002 is a UI task but covers no UJ-*; map it to a journey in the parent UI section"),
            (0, "covers", ["FR-1", "C-1", "UJ-1"], 'TASK-001 covers a UJ-* but is not marked "ui": true; mark the task as UI or remove the journey claim'),
            (0, "covers", ["FR-1"], "no task covers C-1; add it to a task's covers and Requirements Covered line, or report that Product needs revision"),
            (1, "covers", ["FR-1", "UJ-1"], "no task covers FR-2; add it to a task's covers and Requirements Covered line, or report that Product needs revision"),
            (1, "ui", False, "no UI task covers UJ-1; add it to a UI task's covers and UI Journeys line, or report that UI needs revision"),
            (1, "depends", ["TASK-999"], "TASK-002 depends on unknown TASK-999; add the missing task or remove the dependency"),
            (0, "depends", ["TASK-001"], "TASK-001 depends on itself; remove its own ID from depends"),
            (0, "depends", ["TASK-002"], "dependency cycle: TASK-001, TASK-002; change depends so every task has an order"),
        ]
        for index, field, value, expected in cases:
            with self.subTest(field=field, value=value, expected=expected):
                tasks = copy.deepcopy(self.tasks)
                tasks[index][field] = value
                self.assertIn(expected, self._errors(tasks))

    def test_carried_task_reads_its_title_back_from_the_record(self):
        # Only `land_tasks` sets this marker, and only for a task already
        # confirmed stored, so build_plan trusts it rather than re-validating.
        tasks = copy.deepcopy(self.tasks)
        del tasks[0]["title"]
        tasks[0]["unchanged"] = True
        existing = [{"taskId": "TASK-001", "title": "WORK-30-TASK-001 [CORE] Core"}]
        plan = build_plan(tasks, existing, ["FR-1", "FR-2", "C-1"], ["UJ-1"])
        self.assertEqual(plan["errors"], [])
        self.assertEqual(next(task for task in plan["tasks"] if task["id"] == "TASK-001")["title"], "Core")


class TaskValidationCliTests(FileBackendTest):
    def setUp(self):
        super().setUp()
        no_ui = BODY_DEFAULT.replace("UJ-1 covers the first run.", "No UI is required.")
        self.seed_record(70, "Tasks", "Pending", body=no_ui)
        self.body = self.write_file("task-body.md", VALID_BODY.replace("**UI Journeys:** UJ-1\n", ""))

    def _dry_run(self, entry):
        manifest = self.write_file("manifest.json", json.dumps([entry]))
        return self.invoke("post_tasks", "--work-item", 70, "--stage", "Tasks", "--manifest", manifest, "--dry-run")

    def test_direct_manifest_errors(self):
        base = {"action": "create", "title": "Core", "body": self.body, "type": "core", "covers": ["FR-1", "FR-2", "C-1"], "depends": []}
        cases = [
            ("id", 1, "pdlc: manifest entry 1 id must be a string\n"),
            ("body", 1, "pdlc: manifest entry 1 body must be a file path string\n"),
            ("title", 1, "pdlc: manifest entry 1 title must be a string\n"),
        ]
        for field, value, expected in cases:
            with self.subTest(field=field):
                entry = {**base, field: value}
                result = self._dry_run(entry)
                self.assertEqual(result.code, 1)
                self.assertEqual(result.stderr, expected)

        malformed = self._dry_run({**base, "id": "TASK-nope"})
        self.assertEqual(malformed.stderr, "pdlc: malformed task id: TASK-nope\n")
        legacy_unchanged = self._dry_run({**base, "unchanged": True})
        self.assertEqual(legacy_unchanged.stderr, 'pdlc: manifest entry 1 uses "unchanged"; use "action": "retain" instead\n')
        invalid_type = self._dry_run({**base, "type": "service"})
        self.assertEqual(invalid_type.stderr, "pdlc: manifest entry 1 type must be core or ui\n")
        invalid_action = self._dry_run({**base, "action": "skip"})
        self.assertEqual(invalid_action.stderr, "pdlc: manifest entry 1 action must be create, retain, or remove\n")

    def test_manifest_and_body_file_input_errors(self):
        missing_manifest = self.work / "missing.json"
        missing_result = self.invoke("post_tasks", "--work-item", 70, "--stage", "Tasks",
                                     "--manifest", str(missing_manifest), "--dry-run")
        self.assertEqual(missing_result.stderr, f"pdlc: --manifest file does not exist: {missing_manifest}\n")
        for content, expected in (
            ("[]", "must be a non-empty JSON array"),
            ("{}", "must be a non-empty JSON array"),
            ('["not an object"]', "every --manifest entry must be a JSON object"),
            ("[", "--manifest is not valid JSON"),
        ):
            with self.subTest(content=content):
                path = self.write_file("invalid-manifest.json", content)
                result = self.invoke("post_tasks", "--work-item", 70, "--stage", "Tasks", "--manifest", path, "--dry-run")
                self.assertEqual(result.code, 1)
                self.assertIn(expected, result.stderr)

        missing = self._dry_run({"action": "create", "title": "Core", "body": str(self.work / "missing.md"),
                                 "type": "core", "covers": ["FR-1", "FR-2", "C-1"], "depends": []})
        self.assertEqual(missing.stderr, f"pdlc: task body file does not exist: {self.work / 'missing.md'}\n")
        empty_path = self.write_file("empty.md", "")
        empty = self._dry_run({"action": "create", "title": "Core", "body": empty_path,
                               "type": "core", "covers": ["FR-1", "FR-2", "C-1"], "depends": []})
        self.assertEqual(empty.stderr, f"pdlc: task body file is empty: {empty_path}\n")
        directory = self._dry_run({"action": "create", "title": "Core", "body": str(self.work),
                                   "type": "core", "covers": ["FR-1", "FR-2", "C-1"], "depends": []})
        self.assertEqual(directory.stderr, f"pdlc: task body file is not a regular file: {self.work}\n")

    def test_body_manifest_mismatches_show_exact_error(self):
        base = {"action": "create", "title": "Core", "body": self.body, "type": "core", "covers": ["FR-1", "FR-2", "C-1"], "depends": []}
        covers = self._dry_run({**base, "covers": ["FR-1"]})
        self.assertEqual(covers.code, 1)
        self.assertEqual(covers.stderr, "pdlc: manifest entry 1 covers must match its task body: ['C-1', 'FR-1', 'FR-2']; update the manifest or the labelled body lines so they declare the same IDs\n")

        body = self.write_file("dependent.md", VALID_BODY.replace("**Blocked by:** None", "**Blocked by:** TASK-001").replace("**UI Journeys:** UJ-1\n", ""))
        depends = self._dry_run({**base, "body": body})
        self.assertEqual(depends.code, 1)
        self.assertEqual(depends.stderr, "pdlc: manifest entry 1 depends must match its task body: ['TASK-001']; update the manifest or the labelled body lines so they declare the same IDs\n")

    def test_grouped_body_errors_print_all_missing_fields(self):
        body = self.write_file("empty-details.md", "Just a sentence.\n")
        result = self._dry_run({"action": "create", "title": "Core", "body": body, "type": "core", "covers": ["FR-1", "FR-2", "C-1"], "depends": []})
        self.assertEqual(result.code, 1)
        self.assertEqual(result.stderr, (
            "pdlc: the task breakdown is invalid:\n"
            "  - TASK-001 body: add **Blocked by:** None or the TASK-NNN IDs this task depends on\n"
            "  - TASK-001 body: add **Requirements Covered:** with the FR-*/C-* IDs this task delivers\n"
            "  - TASK-001 body: add **Type:** AFK or HITL to classify whether implementation needs a human\n"
            "  - TASK-001 body: add a nonempty **Scope:** section describing what this task changes\n"
            "  - TASK-001 body: add at least one nonempty `- [ ]` item under **Acceptance Criteria:** stating a verifiable outcome\n"
        ))


REGENERATE = ("run `pdlc prompt task-planner 71` for a fresh brief and manifest, re-dispatch"
              " the task planner agent with it, and post the manifest it returns\n")
STALE = "pdlc: TASK-001 was changed after this manifest was generated; " + REGENERATE
MISSING = "pdlc: TASK-001 {action} requires its generated baseline; " + REGENERATE


class TaskManifestActionErrorTests(FileBackendTest):
    def setUp(self):
        super().setUp()
        no_ui = BODY_DEFAULT.replace("UJ-1 covers the first run.", "No UI is required.")
        self.seed_record(71, "Tasks", "Pending", body=no_ui)
        self.seed_task(71, 711, "TASK-001", "OPEN", "WORK-71-TASK-001 [CORE] Existing",
                       body=VALID_BODY.replace("**UI Journeys:** UJ-1\n", ""))

    def _generated(self):
        brief = self.invoke("prompt_task_planner", "--inline", 71)
        self.assertEqual(brief.code, 0, brief.stderr)
        match = re.search(r"Revise the task breakdown at `([^`]+)`", brief.stdout)
        self.assertIsNotNone(match)
        return json.loads(Path(match.group(1)).read_text(encoding="utf-8"))[0]

    def _dry_run(self, entries):
        manifest = self.write_file("action-manifest.json", json.dumps(entries))
        return self.invoke("post_tasks", "--work-item", 71, "--stage", "Tasks", "--manifest", manifest, "--dry-run")

    def test_action_refusals_print_exact_repair_instruction(self):
        missing = {key: value for key, value in self._generated().items() if key != "baseline"}
        retained = self._generated()
        removed = {"id": retained["id"], "number": retained["number"], "action": "remove",
                   "baseline": retained["baseline"], "reason": "No longer needed"}
        new = {"id": "TASK-002", "action": "create", "title": "New", "body": retained["body"],
               "type": "core", "covers": retained["covers"], "depends": []}
        cases = [
            ([retained, retained], "pdlc: duplicate task id: TASK-001\n"),
            ([{key: value for key, value in retained.items() if key != "action"}],
             "pdlc: manifest entry 1 names id TASK-001; set its action to create, retain, or remove\n"),
            ([{**retained, "id": "TASK-999"}],
             "pdlc: manifest entry 1 cannot retain TASK-999: it is not a task of work item #71;"
             " the manifest is out of date or was edited by hand, so " + REGENERATE),
            ([{**removed, "id": "TASK-999", "number": None}],
             "pdlc: manifest entry 1 cannot remove TASK-999: it is not a task of work item #71;"
             " the manifest is out of date or was edited by hand, so " + REGENERATE),
            ([{**removed, "id": "TASK-999", "number": 9999}],
             "pdlc: manifest entry 1 cannot remove TASK-999: it is not a task of work item #71, and task #9999"
             " is not one it already descoped; the manifest is out of date or was edited by hand, so " + REGENERATE),
            ([{**removed, "baseline": "stale"}], STALE),
            ([missing], MISSING.format(action="retain")),
            ([{key: value for key, value in removed.items() if key != "baseline"}], MISSING.format(action="remove")),
            ([{**removed, "reason": " "}], "pdlc: TASK-001 removal requires a reason\n"),
            ([{**removed, "number": 999}], "pdlc: TASK-001 removal requires its generated task number\n"),
            ([{**removed, "title": "Extra"}], "pdlc: TASK-001 removal must contain only id, number, action, baseline, and reason\n"),
            ([{**retained, "action": "create", "title": "Changed"}], "pdlc: TASK-001 already exists with different content; use a new id\n"),
            ([removed], "pdlc: a Tasks breakdown must retain or create at least one task\n"),
            ([new], "pdlc: existing tasks missing from the manifest: TASK-001; retain or remove each explicitly\n"),
        ]
        for entries, expected in cases:
            with self.subTest(expected=expected):
                result = self._dry_run(entries)
                self.assertEqual(result.code, 1)
                self.assertEqual(result.stderr, expected)

    def test_stale_retain_reserved_id_and_implemented_removal(self):
        retained = self._generated()
        Path(retained["body"]).write_text(
            Path(retained["body"]).read_text(encoding="utf-8").replace("Deliver the task.", "Deliver the revised task."),
            encoding="utf-8",
        )
        stale = self._dry_run([{**retained, "baseline": "stale"}])
        self.assertEqual(stale.stderr, STALE)

        new = {"id": "TASK-002", "action": "create", "title": "New", "body": retained["body"],
               "type": "core", "covers": retained["covers"], "depends": []}
        with mock.patch("pdlc.commands.post_tasks._descope_ids", return_value={"TASK-002"}):
            reserved = self._dry_run([new])
        self.assertEqual(reserved.stderr, "pdlc: TASK-002 was descoped; use a new id\n")

        self.register_prs(711, [900])
        removal = {"id": "TASK-001", "number": retained["number"], "action": "remove",
                   "baseline": retained["baseline"], "reason": "No longer needed"}
        implemented = self._dry_run([removal])
        self.assertEqual(implemented.stderr, "pdlc: TASK-001 has a registered pull request; resolve it before removal\n")


if __name__ == "__main__":
    unittest.main()

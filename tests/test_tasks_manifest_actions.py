"""Generated task manifests distinguish retention, edits, and descope."""

import json
import re
from pathlib import Path

from _support import BODY_DEFAULT, FileBackendTest
from pdlc.internal.workitem import subissues_for


NO_UI_BODY = BODY_DEFAULT.replace("UJ-1 covers the first run.", "No UI is required.")
TASK_BODY = "**Blocked by:** None\n**Requirements Covered:** FR-1\n\n**Scope:**\nKeep the seam.\n"


class TaskManifestActionsTests(FileBackendTest):
    def setUp(self):
        super().setUp()
        self.seed_record(40, "Tasks", "Pending", body=NO_UI_BODY)
        self.seed_task(40, 401, "TASK-001", "OPEN", "WORK-40-TASK-001 [CORE] Keep seam", body=TASK_BODY)
        self.seed_task(40, 402, "TASK-002", "OPEN", "WORK-40-TASK-002 [CORE] Drop seam", body=TASK_BODY)

    def _generated(self):
        brief = self.invoke("prompt_task_planner", 40)
        self.assertEqual(brief.code, 0, brief.stderr)
        match = re.search(r"editable copy of the published breakdown is at `([^`]+)`", brief.stdout)
        self.assertIsNotNone(match)
        path = Path(match.group(1))
        return path, json.loads(path.read_text(encoding="utf-8"))

    def _land(self, path, entries):
        path.write_text(json.dumps(entries), encoding="utf-8")
        return self.invoke("post_tasks", "--work-item", 40, "--stage", "Tasks",
                           "--manifest", str(path), "--evidence", self.evidence_file())

    def test_unedited_generated_tasks_are_carried(self):
        path, entries = self._generated()
        result = self._land(path, entries)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["unchanged"], ["TASK-001", "TASK-002"])
        self.assertEqual(result.json["removed"], [])

    def test_editing_a_generated_body_updates_its_task(self):
        path, entries = self._generated()
        body = Path(entries[0]["body"])
        body.write_text(TASK_BODY + "\nOne more behavior.\n", encoding="utf-8")
        result = self._land(path, entries)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["updated"], ["TASK-001"])
        self.assertEqual(result.json["unchanged"], ["TASK-002"])

    def test_new_entry_creates_the_next_task(self):
        path, entries = self._generated()
        body = self.write_file("third.md", "**Blocked by:** TASK-001\n**Requirements Covered:** FR-2\n\n**Scope:**\nAdd the next seam.\n")
        entries.append({"title": "Add next seam", "body": body,
                        "type": "core", "covers": ["FR-2"], "depends": ["TASK-001"]})
        result = self._land(path, entries)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["created"], ["TASK-003"])
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved[-1]["id"], "TASK-003")
        self.assertEqual(saved[-1]["action"], "create")
        self.assertEqual(saved[0]["action"], "retain")

    def test_retry_after_a_created_task_uses_its_saved_id(self):
        path, entries = self._generated()
        body = self.write_file("third.md", "**Blocked by:** None\n**Requirements Covered:** FR-2\n\n**Scope:**\nNext seam.\n")
        entries.append({"title": "Next seam", "body": body, "type": "core", "covers": ["FR-2"], "depends": []})
        self.assertEqual(self._land(path, entries).code, 0)
        record_meta = self.records_dir() / "40" / "meta.json"
        metadata = json.loads(record_meta.read_text(encoding="utf-8"))
        metadata["fields"]["Gate State"] = "Stale"
        record_meta.write_text(json.dumps(metadata), encoding="utf-8")
        result = self._land(path, json.loads(path.read_text(encoding="utf-8")))
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(set(result.json["unchanged"]), {"TASK-001", "TASK-002", "TASK-003"})

    def test_retry_after_saved_edit_finishes_reopening(self):
        path, entries = self._generated()
        body = Path(entries[0]["body"])
        edited = TASK_BODY + "\nOne more behavior.\n"
        body.write_text(edited, encoding="utf-8")
        task_dir = self.records_dir() / "40" / "tasks" / "401"
        (task_dir / "body.md").write_text(edited, encoding="utf-8")
        metadata = self.task_meta(40, 401)
        metadata["state"] = "CLOSED"
        (task_dir / "meta.json").write_text(json.dumps(metadata), encoding="utf-8")
        result = self._land(path, entries)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["reopened"], ["TASK-001"])
        self.assertEqual(self.task_meta(40, 401)["state"], "OPEN")

    def test_remove_descopes_a_task_without_deleting_its_history(self):
        path, entries = self._generated()
        entries[1] = {"id": entries[1]["id"], "number": entries[1]["number"], "action": "remove",
                      "baseline": entries[1]["baseline"], "reason": "Superseded by TASK-001"}
        result = self._land(path, entries)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["removed"], ["TASK-002"])
        self.assertEqual([task["taskId"] for task in subissues_for("40")], ["TASK-001"])
        self.assertEqual(self.task_meta(40, 402)["state"], "CLOSED")

    def test_dry_run_lists_removal_without_touching_the_task(self):
        path, entries = self._generated()
        entries[1] = {"id": entries[1]["id"], "number": entries[1]["number"], "action": "remove",
                      "baseline": entries[1]["baseline"], "reason": "Superseded"}
        path.write_text(json.dumps(entries), encoding="utf-8")
        result = self.invoke("post_tasks", "--work-item", 40, "--stage", "Tasks",
                             "--manifest", str(path), "--dry-run")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["removed"], ["TASK-002"])
        self.assertEqual(self.task_meta(40, 402)["state"], "OPEN")

    def test_reviewer_sees_the_removed_tasks_original_scope(self):
        path, entries = self._generated()
        entries[1] = {"id": entries[1]["id"], "number": entries[1]["number"], "action": "remove",
                      "baseline": entries[1]["baseline"], "reason": "Superseded"}
        path.write_text(json.dumps(entries), encoding="utf-8")
        review = self.invoke("prompt_tasks_reviewer", 40, "--manifest", str(path))
        self.assertEqual(review.code, 0, review.stderr)
        self.assertIn("remove: Superseded", review.stdout)
        self.assertIn("WORK-40-TASK-002 [CORE] Drop seam", review.stdout)
        self.assertIn("Keep the seam.", review.stdout)

    def test_retry_after_detachment_finishes_publication(self):
        path, entries = self._generated()
        entries[1] = {"id": entries[1]["id"], "number": entries[1]["number"], "action": "remove",
                      "baseline": entries[1]["baseline"], "reason": "Superseded by TASK-001"}
        from pdlc.internal.workitem import post_comment, remove_task
        post_comment("402", "Descoped from work item #40: Superseded by TASK-001\n")
        remove_task("40", "402")
        result = self._land(path, entries)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["removed"], ["TASK-002"])

    def test_descoped_id_is_never_reassigned(self):
        path, entries = self._generated()
        entries[1] = {"id": entries[1]["id"], "number": entries[1]["number"], "action": "remove",
                      "baseline": entries[1]["baseline"], "reason": "Superseded"}
        self.assertEqual(self._land(path, entries).code, 0)

        path, entries = self._generated()
        body = self.write_file("next.md", "**Blocked by:** None\n**Requirements Covered:** FR-2\n\n**Scope:**\nNext seam.\n")
        entries.append({"title": "Next seam", "body": body, "type": "core", "covers": ["FR-2"], "depends": []})
        result = self._land(path, entries)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["created"], ["TASK-003"])

    def test_stale_generated_manifest_refuses_to_overwrite(self):
        path, entries = self._generated()
        metadata = self.task_meta(40, 401)
        metadata["title"] = "WORK-40-TASK-001 [CORE] Changed elsewhere"
        (self.records_dir() / "40" / "tasks" / "401" / "meta.json").write_text(json.dumps(metadata))
        result = self._land(path, entries)
        self.assertEqual(result.code, 1)
        self.assertIn("changed since its planner artifact was generated", result.stderr)

    def test_registered_pr_blocks_removal(self):
        path, entries = self._generated()
        self.register_prs(402, [900])
        entries[1] = {"id": entries[1]["id"], "number": entries[1]["number"], "action": "remove",
                      "baseline": entries[1]["baseline"], "reason": "Superseded"}
        result = self._land(path, entries)
        self.assertEqual(result.code, 1)
        self.assertIn("registered pull request", result.stderr)

    def test_covers_and_depends_are_order_insensitive(self):
        path, entries = self._generated()
        body = self.write_file("third.md", "**Blocked by:** TASK-002, TASK-001\n**Requirements Covered:** FR-2, FR-1\n\n**Scope:**\nNext seam.\n")
        entries.append({"title": "Next seam", "body": body, "type": "core",
                        "covers": ["FR-2", "FR-1"], "depends": ["TASK-002", "TASK-001"]})
        result = self._land(path, entries)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["created"], ["TASK-003"])

    def test_unlabelled_body_is_not_checked_against_the_manifest(self):
        path, entries = self._generated()
        body = self.write_file("third.md", "**Scope:**\nNext seam, unlike FR-1 and TASK-001.\n")
        entries.append({"title": "Next seam", "body": body, "type": "core", "covers": ["FR-2"], "depends": []})
        result = self._land(path, entries)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["created"], ["TASK-003"])

    def test_labelled_covers_must_match_the_manifest(self):
        path, entries = self._generated()
        body = self.write_file("third.md", "**Blocked by:** None\n**Requirements Covered:** FR-1\n\n**Scope:**\nNext seam.\n")
        entries.append({"title": "Next seam", "body": body, "type": "core", "covers": ["FR-2"], "depends": []})
        result = self._land(path, entries)
        self.assertEqual(result.code, 1)
        self.assertIn("covers must match its task body", result.stderr)

    def test_existing_id_without_action_is_refused_with_a_clear_reason(self):
        path, entries = self._generated()
        entries[0].pop("action")
        result = self._land(path, entries)
        self.assertEqual(result.code, 1)
        self.assertIn("names id TASK-001; set its action", result.stderr)

    def test_retry_after_descope_note_does_not_repeat_it(self):
        path, entries = self._generated()
        entries[1] = {"id": entries[1]["id"], "number": entries[1]["number"], "action": "remove",
                      "baseline": entries[1]["baseline"], "reason": "Superseded"}
        from pdlc.internal.workitem import post_comment
        post_comment("402", "Descoped from work item #40: Superseded\n")
        result = self._land(path, entries)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["removed"], ["TASK-002"])
        self.assertEqual(self.task_comments_text(40, 402).count("Descoped from work item #40"), 1)
        self.assertNotIn("PDLC-TASKS", self.task_comments_text(40, 402))

"""Generated task manifests distinguish retention, edits, and descope."""

import json
import re
from pathlib import Path
from unittest import mock

from _support import BODY_DEFAULT, FileBackendTest
from pdlc.domain.lifecycle import PdlcError, TransientError
from pdlc.hosts.lib import process
from pdlc.internal.workitem import subissues_for


NO_UI_BODY = BODY_DEFAULT.replace("UJ-1 covers the first run.", "No UI is required.").replace("- C-1: Commands own every mutation.\n", "")
TASK_BODY = "**Blocked by:** None\n**Type:** AFK\n**Requirements Covered:** FR-1, FR-2\n\n**Scope:**\nKeep the seam.\n\n**Acceptance Criteria:**\n- [ ] The seam persists.\n"


def task_body(requirements="FR-2", blocked="None", scope="Next seam."):
    return f"**Blocked by:** {blocked}\n**Type:** AFK\n**Requirements Covered:** {requirements}\n\n**Scope:**\n{scope}\n\n**Acceptance Criteria:**\n- [ ] The seam works.\n"


class TaskManifestActionsTests(FileBackendTest):
    def setUp(self):
        super().setUp()
        self.seed_record(40, "Tasks", "Pending", body=NO_UI_BODY)
        self.seed_task(40, 401, "TASK-001", "OPEN", "WORK-40-TASK-001 [CORE] Keep seam", body=TASK_BODY)
        self.seed_task(40, 402, "TASK-002", "OPEN", "WORK-40-TASK-002 [CORE] Drop seam", body=TASK_BODY)

    def _generated(self):
        brief = self.invoke("prompt_task_planner", "--inline", 40)
        self.assertEqual(brief.code, 0, brief.stderr)
        match = re.search(r"Revise the task breakdown at `([^`]+)`", brief.stdout)
        self.assertIsNotNone(match)
        path = Path(match.group(1))
        return path, json.loads(path.read_text(encoding="utf-8"))

    def _land(self, path, entries):
        path.write_text(json.dumps(entries), encoding="utf-8")
        self.mark_tasks_reviewed(40, path)
        return self.invoke("post_tasks", "--work-item", 40, "--stage", "Tasks",
                           "--manifest", str(path), "--evidence", self.evidence_file())

    def _post(self, path):
        return self.invoke("post_tasks", "--work-item", 40, "--stage", "Tasks",
                           "--manifest", str(path), "--evidence", self.evidence_file())

    def test_an_unreviewed_breakdown_is_refused_without_writing(self):
        path, _ = self._generated()
        result = self._post(path)
        self.assertEqual(result.code, 1)
        self.assertIn("has not been reviewed since its last planning pass", result.stderr)
        self.assertIn(f"pdlc prompt tasks-reviewer 40 --manifest {path.resolve()}", result.stderr)
        self.assertEqual(self.state(40), ("Tasks", "Pending"))

    def test_a_reviewer_edit_is_restored_and_the_review_redone(self):
        path, entries = self._generated()
        self.assertEqual(self.invoke("prompt_tasks_reviewer", "--inline", 40, "--manifest", str(path)).code, 0)
        body = Path(entries[0]["body"])
        reviewed = body.read_text()
        body.write_text(reviewed + "\nReviewer's own scope.\n")
        result = self._post(path)
        self.assertEqual(result.code, 1)
        self.assertIn("changed after its brief was written", result.stderr)
        self.assertEqual(body.read_text(), reviewed)
        self.assertIn("Reviewer's own scope.", body.with_name(f"{body.stem}.rejected.md").read_text())
        rereview = self.invoke("prompt_tasks_reviewer", "--inline", 40, "--manifest", str(path))
        self.assertEqual(rereview.code, 0)
        findings = Path(re.search(r"Write your review into `([^`]+)`", rereview.stdout).group(1))
        self.assertTrue(findings.exists())
        landed = self._post(path)
        self.assertEqual(landed.code, 0, landed.stderr)
        self.assertEqual(landed.json["unchanged"], ["TASK-001", "TASK-002"])
        # The landing spends the review, so its findings file goes too.
        self.assertFalse(findings.exists())

    def test_without_a_manifest_the_published_breakdown_is_reviewed_and_lands_unchanged(self):
        self.seed_record(41, "Tasks", "Review Required", body=NO_UI_BODY)
        self.seed_task(41, 411, "TASK-001", "OPEN", "WORK-41-TASK-001 [CORE] Keep seam", body=TASK_BODY)
        brief = self.invoke("prompt_tasks_reviewer", "--inline", 41)
        self.assertEqual(brief.code, 0, brief.stderr)
        match = re.search(r"task breakdown at `([^`]+)`", brief.stdout)
        self.assertIsNotNone(match, brief.stdout)
        landed = self.invoke("post_tasks", "--work-item", 41, "--stage", "Tasks",
                             "--manifest", match.group(1), "--evidence", self.evidence_file())
        self.assertEqual(landed.code, 0, landed.stderr)
        self.assertEqual(landed.json["unchanged"], ["TASK-001"])
        self.assertEqual(self.state(41), ("Tasks", "Approval Required"))

    def test_a_new_planning_pass_needs_a_new_review(self):
        path, entries = self._generated()
        self.assertEqual(self.invoke("prompt_tasks_reviewer", "--inline", 40, "--manifest", str(path)).code, 0)
        brief = self.invoke("prompt_task_planner", "--inline", 40, "--current-tasks-manifest-path", str(path))
        self.assertEqual(brief.code, 0, brief.stderr)
        Path(entries[0]["body"]).write_text(TASK_BODY + "\nOne more behavior.\n", encoding="utf-8")
        self.assertIn("has not been reviewed", self._post(path).stderr)
        self.assertEqual(self.invoke("prompt_tasks_reviewer", "--inline", 40, "--manifest", str(path)).code, 0)
        landed = self._post(path)
        self.assertEqual(landed.code, 0, landed.stderr)
        self.assertEqual(landed.json["updated"], ["TASK-001"])

    def test_saved_ids_keep_the_breakdown_reviewed_for_a_retry(self):
        path, entries = self._generated()
        body = self.write_file("third.md", task_body())
        entries.append({"title": "Next seam", "body": body, "type": "core", "covers": ["FR-2"], "depends": []})
        with mock.patch("pdlc.commands.post_tasks.upsert_tasks", side_effect=PdlcError("host down")):
            self.assertEqual(self._land(path, entries).code, 1)
        # The retry reuses the manifest the failed run rewrote, without another review.
        retry = self._post(path)
        self.assertEqual(retry.code, 0, retry.stderr)
        self.assertEqual(retry.json["created"], ["TASK-003"])

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
        body = self.write_file("third.md", task_body(blocked="TASK-001", scope="Add the next seam."))
        entries.append({"title": "Add next seam", "body": body,
                        "type": "core", "covers": ["FR-2"], "depends": ["TASK-001"]})
        result = self._land(path, entries)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["created"], ["TASK-003"])
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved[-1]["id"], "TASK-003")
        self.assertEqual(saved[-1]["action"], "retain")
        self.assertIsInstance(saved[-1]["number"], int)

    def test_assigned_id_is_saved_before_the_first_remote_write(self):
        path, entries = self._generated()
        body = self.write_file("third.md", task_body())
        entries.append({"title": "Next seam", "body": body, "type": "core", "covers": ["FR-2"], "depends": []})
        with mock.patch("pdlc.commands.post_tasks.upsert_tasks", side_effect=PdlcError("host down")):
            result = self._land(path, entries)
        self.assertEqual(result.code, 1)
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual((saved[-1]["id"], saved[-1]["action"]), ("TASK-003", "create"))

    def test_assigned_id_save_failure_makes_no_remote_write(self):
        path, entries = self._generated()
        body = self.write_file("third.md", task_body())
        entries.append({"title": "Next seam", "body": body, "type": "core", "covers": ["FR-2"], "depends": []})
        with mock.patch("pdlc.commands.post_tasks._save_manifest", side_effect=OSError("disk full")), \
             mock.patch("pdlc.commands.post_tasks.upsert_tasks") as upsert:
            result = self._land(path, entries)
        self.assertEqual(result.code, 1)
        self.assertIn(f"cannot save assigned task ids in {path}: disk full", result.stderr)
        upsert.assert_not_called()

    def test_retry_after_a_created_task_uses_its_saved_id(self):
        path, entries = self._generated()
        body = self.write_file("third.md", task_body())
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
        review = self.invoke("prompt_tasks_reviewer", "--inline", 40, "--manifest", str(path))
        self.assertEqual(review.code, 0, review.stderr)
        self.assertIn("(remove): leaves scope: Superseded", review.stdout)
        self.assertIn("#### `TASK-002` — WORK-40-TASK-002 [CORE] Drop seam", review.stdout)
        self.assertIn("Reason: Superseded", review.stdout)
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
        body = self.write_file("next.md", task_body())
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
        self.assertIn("was changed after this manifest was generated; run `pdlc prompt task-planner 40`", result.stderr)

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
        body = self.write_file("third.md", task_body(requirements="FR-2, FR-1", blocked="TASK-002, TASK-001"))
        entries.append({"title": "Next seam", "body": body, "type": "core",
                        "covers": ["FR-2", "FR-1"], "depends": ["TASK-002", "TASK-001"]})
        result = self._land(path, entries)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["created"], ["TASK-003"])

    def test_unlabelled_body_is_refused_with_required_labels(self):
        path, entries = self._generated()
        body = self.write_file("third.md", "**Type:** AFK\n**Scope:**\nNext seam, unlike FR-1 and TASK-001.\n\n**Acceptance Criteria:**\n- [ ] The seam works.\n")
        entries.append({"title": "Next seam", "body": body, "type": "core", "covers": ["FR-2"], "depends": []})
        result = self._land(path, entries)
        self.assertEqual(result.code, 1)
        self.assertIn("add **Blocked by:** None", result.stderr)
        self.assertIn("add **Requirements Covered:**", result.stderr)

    def test_labelled_covers_must_match_the_manifest(self):
        path, entries = self._generated()
        body = self.write_file("third.md", task_body(requirements="FR-1"))
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

    def test_published_manifest_is_rebased_onto_the_stored_tasks(self):
        path, entries = self._generated()
        Path(entries[0]["body"]).write_text(TASK_BODY + "\nOne more behavior.\n", encoding="utf-8")
        entries[1] = {"id": entries[1]["id"], "number": entries[1]["number"], "action": "remove",
                      "baseline": entries[1]["baseline"], "reason": "Superseded"}
        body = self.write_file("third.md", task_body())
        entries.append({"title": "Next seam", "body": body, "type": "core", "covers": ["FR-2"], "depends": []})
        self.assertEqual(self._land(path, entries).code, 0)
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual([entry["id"] for entry in saved], ["TASK-001", "TASK-003"])
        self.assertEqual({entry["action"] for entry in saved}, {"retain"})
        _, fresh = self._generated()
        self.assertEqual({entry["id"]: entry["baseline"] for entry in saved},
                         {entry["id"]: entry["baseline"] for entry in fresh})

    def test_reused_published_manifest_does_not_reopen_delivered_work(self):
        path, entries = self._generated()
        Path(entries[0]["body"]).write_text(TASK_BODY + "\nOne more behavior.\n", encoding="utf-8")
        self.assertEqual(self._land(path, entries).code, 0)
        metadata = self.task_meta(40, 401)
        metadata["state"] = "CLOSED"
        (self.records_dir() / "40" / "tasks" / "401" / "meta.json").write_text(json.dumps(metadata))
        record_meta = self.records_dir() / "40" / "meta.json"
        record = json.loads(record_meta.read_text(encoding="utf-8"))
        record["fields"]["Gate State"] = "Stale"
        record_meta.write_text(json.dumps(record), encoding="utf-8")
        result = self._land(path, json.loads(path.read_text(encoding="utf-8")))
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["reopened"], [])
        self.assertEqual(self.task_meta(40, 401)["state"], "CLOSED")

    def test_retain_without_baseline_never_reopens_delivered_work(self):
        path, entries = self._generated()
        self.seed_plan_comment(40, 401, "Plan the seam.")
        self.seed_implementation_comment(40, 401, "Seam shipped.")
        metadata = self.task_meta(40, 401)
        metadata["state"] = "CLOSED"
        (self.records_dir() / "40" / "tasks" / "401" / "meta.json").write_text(json.dumps(metadata))
        comments = self.task_comments_text(40, 401)
        del entries[0]["baseline"]
        result = self._land(path, entries)
        self.assertEqual(result.code, 1)
        self.assertIn("TASK-001 retain requires its generated baseline", result.stderr)
        self.assertEqual(self.task_meta(40, 401)["state"], "CLOSED")
        self.assertEqual(self.task_comments_text(40, 401), comments)

    def test_transient_lookup_of_a_removed_task_stays_retryable(self):
        path, entries = self._generated()
        entries[1] = {"id": "TASK-009", "number": 409, "action": "remove",
                      "baseline": entries[1]["baseline"], "reason": "Superseded"}
        # The harness bypasses cli.main, which resets this per run; another test may have left it set.
        process.reset_run_state()
        with mock.patch("pdlc.commands.post_tasks.tasks_by_number", side_effect=TransientError("timeout")):
            result = self._land(path, entries)
        self.assertEqual(result.code, 75, result.stderr)

    def test_failed_rebase_warns_without_failing_the_publication(self):
        path, entries = self._generated()
        with mock.patch("pdlc.commands.post_tasks._consume_manifest", side_effect=OSError("read-only")):
            result = self._land(path, entries)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertTrue(result.json["published"])
        self.assertIn("do not reuse it", result.stderr)

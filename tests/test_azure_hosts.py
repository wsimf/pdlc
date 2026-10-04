"""The Azure DevOps Boards work-item backend, driven entirely through a fake
``az`` CLI. Every behaviour asserted here was first confirmed against a live
organization; the routes replay those payloads offline.
"""

from __future__ import annotations

import unittest

from _az_replay import ORGANIZATION, PROJECT, AzureHostTest, work_item
from pdlc.config import Config, ConfigurationError
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.workflow import WorkType
from pdlc.hosts.lib.azure.workitems import (
    AREA_PATH_FIELD,
    ASSIGNED_TO_FIELD,
    DESCRIPTION_FIELD,
    GATE_FIELD,
    LIFECYCLE_FIELD,
    PRS_FIELD,
    SKIPPED_FIELD,
    SLUG_FIELD,
    STATE_FIELD,
    STATUS_FIELD,
    TITLE_FIELD,
    TYPE_FIELD,
)
from pdlc.hosts.lib.azure.workitem_backend import AzureWorkItemBackend

RECORD = work_item(
    7,
    **{
        TITLE_FIELD: "Retry failed uploads",
        TYPE_FIELD: "Product Backlog Item",
        DESCRIPTION_FIELD: "## Product\n\nShip **retries**.\n",
        STATUS_FIELD: "Implementation",
        GATE_FIELD: "Review Required",
        LIFECYCLE_FIELD: "Planning",
        SKIPPED_FIELD: "UI",
        SLUG_FIELD: "retry-uploads",
        PRS_FIELD: "152 148",
    },
)


class ResolutionTest(AzureHostTest):
    def test_resolve_maps_custom_fields_onto_the_port_shape(self):
        self.az.az("boards", "work-item", "show", response=RECORD)
        item = AzureWorkItemBackend().resolve("7")

        self.assertEqual(item["id"], "7")
        self.assertEqual(item["content"], {
            "number": 7,
            "title": "Retry failed uploads",
            # `show` reports an `_apis/...` URL; a human-facing board link is
            # what lands in evidence, so the backend builds one.
            "url": f"{ORGANIZATION}/{PROJECT}/_workitems/edit/7",
        })
        self.assertEqual(item["issueBody"], "## Product\n\nShip **retries**.\n")
        self.assertEqual(item["Status"], "Implementation")
        self.assertEqual(item["Gate State"], "Review Required")
        self.assertEqual(item["Lifecycle"], "Planning")
        self.assertEqual(item["Skipped States"], "UI")
        self.assertEqual(item["Slug"], "retry-uploads")
        self.assertEqual(item["workType"], "feature")
        self.assertEqual(item["prs"], [148, 152])

    def test_unset_custom_fields_are_absent_rather_than_empty(self):
        # Azure omits a never-written custom field from `fields` entirely; the
        # port promises a string either way.
        self.az.az("boards", "work-item", "show", response=work_item(
            9, **{TITLE_FIELD: "New record", TYPE_FIELD: "Product Backlog Item"}
        ))
        item = AzureWorkItemBackend().resolve("9")
        self.assertEqual(
            [item["Status"], item["Gate State"], item["Lifecycle"], item["Skipped States"], item["Slug"]],
            ["", "", "", "", ""],
        )
        self.assertEqual(item["prs"], [])
        self.assertEqual(item["issueBody"], "")

    def test_a_non_record_work_item_type_is_not_silently_a_feature(self):
        self.az.az("boards", "work-item", "show", response=work_item(
            9, **{TITLE_FIELD: "Crash on launch", TYPE_FIELD: "Bug"}
        ))
        # Routing blocks an unknown work type; guessing `feature` here would
        # run the wrong pipeline.
        self.assertEqual(AzureWorkItemBackend().resolve("9")["workType"], "bug")

    def test_a_configured_record_type_defines_the_feature_pipeline(self):
        self.configure(azure_record_type="User Story")
        self.az.az("boards", "work-item", "show", response=work_item(
            9, **{TITLE_FIELD: "Agile record", TYPE_FIELD: "User Story"}
        ))
        self.assertEqual(AzureWorkItemBackend().resolve("9")["workType"], "feature")

    def test_resolve_by_slug_queries_then_shows(self):
        self.az.wiql("Custom.PdlcSlug] = 'retry-uploads'", response=[{"id": 7}])
        self.az.az("boards", "work-item", "show", response=RECORD)
        self.assertEqual(AzureWorkItemBackend().resolve("retry-uploads")["number"], 7)

    def test_an_unknown_slug_fails_rather_than_returning_nothing(self):
        # An empty WIQL result set prints zero bytes, not `[]`.
        self.az.wiql("Custom.PdlcSlug] = 'ghost'", response="")
        with self.assertRaisesRegex(PdlcError, "no PDLC record with slug: ghost"):
            AzureWorkItemBackend().resolve("ghost")

    def test_an_ambiguous_slug_is_a_hard_failure(self):
        self.az.wiql("Custom.PdlcSlug] = 'twin'", response=[{"id": 7}, {"id": 8}])
        with self.assertRaisesRegex(PdlcError, "slug is ambiguous: twin"):
            AzureWorkItemBackend().resolve("twin")

    def test_mixed_quotes_in_a_slug_are_refused_before_wiql(self):
        with self.assertRaisesRegex(PdlcError, "both single and double quotes"):
            AzureWorkItemBackend().resolve("o'b\"rien")
        self.assertEqual(self.az.calls, [])


class QueueScanTest(AzureHostTest):
    def test_queue_scan_is_one_query(self):
        self.az.wiql("FROM workitems", response=[
            work_item(7, **{
                TITLE_FIELD: "Retry failed uploads",
                TYPE_FIELD: "Product Backlog Item",
                STATUS_FIELD: "Implementation",
                GATE_FIELD: "Review Required",
                LIFECYCLE_FIELD: "Planning",
                SKIPPED_FIELD: "UI",
                SLUG_FIELD: "retry-uploads",
            }),
        ])
        summaries = AzureWorkItemBackend().queue_items()

        # WIQL returns exactly the SELECTed fields, so the scan needs no
        # follow-up read per item.
        self.assertEqual(len(self.az.calls), 1)
        self.assertEqual(summaries, [{
            "id": "7",
            "content": {
                "number": 7,
                "title": "Retry failed uploads",
                "url": f"{ORGANIZATION}/{PROJECT}/_workitems/edit/7",
            },
            "Status": "Implementation",
            "Gate State": "Review Required",
            "Lifecycle": "Planning",
            "Skipped States": "UI",
            "workType": "feature",
        }])

    def test_an_empty_board_returns_no_items_rather_than_failing(self):
        # Regression: `az boards query` prints nothing at all when nothing
        # matches, which a naive json.loads would reject.
        self.az.wiql("FROM workitems", response="")
        self.assertEqual(AzureWorkItemBackend().queue_items(), [])

    def test_queue_scan_is_unfiltered_when_no_assignee_is_configured(self):
        self.az.wiql("FROM workitems", response="")
        AzureWorkItemBackend().queue_items()
        wiql = " ".join(self.az.calls_matching("boards", "query")[0])
        self.assertNotIn("System.AssignedTo", wiql)

    def test_a_configured_assignee_narrows_the_queue_wiql(self):
        self.configure(azure_assigned_to="Ada Lovelace")
        self.az.wiql("System.AssignedTo] = 'Ada Lovelace'", response="")
        self.assertEqual(AzureWorkItemBackend().queue_items(), [])

    def test_the_at_me_shorthand_becomes_the_wiql_macro(self):
        self.configure(azure_assigned_to="@me")
        self.az.wiql("System.AssignedTo] = @Me", response="")
        self.assertEqual(AzureWorkItemBackend().queue_items(), [])


class StateWriteTest(AzureHostTest):
    def setUp(self) -> None:
        super().setUp()
        self.az.az("boards", "work-item", "update", response=RECORD)

    def test_set_state_writes_all_three_fields_in_one_call(self):
        AzureWorkItemBackend().set_state("7", "Testing", "Pending", "Planning")
        self.assertEqual(len(self.az.calls), 1)
        self.assertEqual(self.az.fields_written("boards", "work-item", "update"), {
            STATUS_FIELD: "Testing",
            GATE_FIELD: "Pending",
            LIFECYCLE_FIELD: "Planning",
        })

    def test_single_field_writes_touch_only_their_own_field(self):
        backend = AzureWorkItemBackend()
        backend.set_gate("7", "Approved")
        self.assertEqual(self.az.fields_written("boards", "work-item", "update"), {GATE_FIELD: "Approved"})

    def test_skipped_states_can_be_cleared_to_empty(self):
        AzureWorkItemBackend().set_skipped_states("7", "")
        self.assertEqual(self.az.fields_written("boards", "work-item", "update"), {SKIPPED_FIELD: ""})

    def test_close_record_moves_the_record_to_the_configured_closed_state(self):
        self.az.az("boards", "work-item", "show", response=RECORD)
        self.configure(azure_closed_state="Closed", azure_task_closed_state="Done")
        AzureWorkItemBackend().close_record("7")
        call = self.az.calls[-1]
        self.assertEqual(call[call.index("--id") + 1], "7")
        self.assertEqual(call[call.index("--state") + 1], "Closed")

    def test_write_body_replaces_the_description_as_markdown_and_nothing_else(self):
        self.az.az("boards", "work-item", "show", response=RECORD)
        self.az.invoke("wit", "batch", response={"value": [{"code": 200, "body": "{}"}]})
        AzureWorkItemBackend().write_body("7", "## Product\n\nRewritten.\n")
        # Attached pull requests live in their own field, so a body write
        # cannot drop them the way a body-embedded registry could.
        self.assertEqual(self.az.body_of("devops", "invoke"), [{
            "method": "PATCH",
            "uri": "/_apis/wit/workitems/7?api-version=7.1",
            "headers": {"Content-Type": "application/json-patch+json"},
            "body": [
                {"op": "add", "path": f"/fields/{DESCRIPTION_FIELD}", "value": "## Product\n\nRewritten.\n"},
                {"op": "add", "path": f"/multilineFieldsFormat/{DESCRIPTION_FIELD}", "value": "Markdown"},
            ],
        }])
        call = self.az.calls_matching("devops", "invoke")[0]
        self.assertEqual(call[call.index("--resource") + 1], "batch")
        self.assertEqual(call[call.index("--http-method") + 1], "PATCH")

    def test_field_values_travel_as_files_so_a_long_body_fits_windows_cmd(self):
        # On Windows `az` is a batch file and `cmd.exe` refuses a command line
        # over 8191 characters, so no value may be passed inline.
        self.az.az("boards", "work-item", "show", response=RECORD)
        self.az.invoke("wit", "batch", response={"value": [{"code": 200, "body": "{}"}]})
        body = "## Product\n\n" + "x" * 20_000
        AzureWorkItemBackend().write_body("7", body)
        raw = next(args for args in self.az.raw_calls if args[:2] == ["devops", "invoke"])
        self.assertLess(len(" ".join(raw)), 8191)
        self.assertIn("--in-file", raw)
        self.assertEqual(self.az.body_of("devops", "invoke")[0]["body"][0]["value"], body)

    def test_a_failed_batch_update_is_reported(self):
        self.az.az("boards", "work-item", "show", response=RECORD)
        self.az.invoke("wit", "batch", response={
            "value": [{"code": 400, "body": "Description format rejected"}],
        })
        with self.assertRaisesRegex(PdlcError, "Description format rejected"):
            AzureWorkItemBackend().write_body("7", "## Product\n\nRewritten.")

    def test_a_rejected_picklist_value_surfaces_azure_own_message(self):
        self.az._routes.clear()
        self.az.az("boards", "work-item", "update", response=PdlcError(
            "ERROR: The field 'PdlcGateState' contains the value 'Bogus Gate' "
            "that is not in the list of supported values"
        ))
        with self.assertRaisesRegex(PdlcError, "not in the list of supported values"):
            AzureWorkItemBackend().set_gate("7", "Bogus Gate")


class AttachedPullRequestTest(AzureHostTest):
    def _stored(self, value: str) -> None:
        self.state = {PRS_FIELD: value} if value else {}
        self.az.az("boards", "work-item", "show", response=lambda _args: work_item(8, **self.state))

        def _update(args):
            for pair in args[args.index("-f") + 1:]:
                name, _, text = pair.partition("=")
                self.state[name] = text
            return work_item(8, **self.state)

        self.az.az("boards", "work-item", "update", response=_update)

    def test_attaching_is_idempotent_and_returns_the_full_list(self):
        self._stored("")
        backend = AzureWorkItemBackend()
        self.assertEqual(backend.attach_pr("8", 152), [152])
        self.assertEqual(backend.attach_pr("8", 148), [148, 152])
        self.assertEqual(backend.attach_pr("8", 148), [148, 152])
        self.assertEqual(backend.attached_prs("8"), [148, 152])

    def test_re_attaching_writes_nothing(self):
        self._stored("148 152")
        AzureWorkItemBackend().attach_pr("8", 148)
        self.assertEqual([args[:3] for args in self.az.calls], [["boards", "work-item", "show"]])

    def test_numbers_are_stored_space_separated_and_ascending(self):
        self._stored("152")
        AzureWorkItemBackend().attach_pr("8", 148)
        self.assertEqual(self.az.fields_written("boards", "work-item", "update"), {PRS_FIELD: "148 152"})

    def test_a_hand_edited_field_does_not_break_a_read(self):
        # The field is editable in the Azure UI; a stray word must not make the
        # record unreadable.
        self._stored("148 oops 152")
        self.assertEqual(AzureWorkItemBackend().attached_prs("8"), [148, 152])


class DeliveryTaskTest(AzureHostTest):
    TASK = work_item(8, **{
        TITLE_FIELD: "WORK-7-TASK-001 [CORE] retry queue",
        STATE_FIELD: "Active",
        DESCRIPTION_FIELD: "do the thing",
        PRS_FIELD: "148",
    })

    def setUp(self) -> None:
        super().setUp()
        self.az.wiql("Custom.PdlcSlug", response=[{"id": 7}])
        self.az.az("boards", "work-item", "show", response=RECORD)
        self.az.invoke("wit", "comments", response={"comments": [
            {"id": 2, "text": "## Implementation\n\ndone", "createdDate": "2026-09-07T06:38:17Z",
             "createdBy": {"uniqueName": "dev@acme.test"}, "url": "https://az/comments/2"},
            {"id": 1, "text": "## Technical Plan\n\nplan", "createdDate": "2026-09-07T06:30:00Z",
             "createdBy": {"uniqueName": "dev@acme.test"}, "url": "https://az/comments/1"},
        ]})

    def test_tasks_map_state_identity_and_pull_requests(self):
        self.az.wiql("System.Parent", response=[self.TASK])
        [task] = AzureWorkItemBackend().tasks("7")
        self.assertEqual(task["number"], 8)
        self.assertEqual(task["taskId"], "TASK-001")
        self.assertEqual(task["state"], "OPEN")
        self.assertEqual(task["body"], "do the thing")
        self.assertEqual(task["prs"], [148])
        self.assertEqual(task["url"], f"{ORGANIZATION}/{PROJECT}/_workitems/edit/8")

    def test_closed_and_removed_tasks_both_read_as_closed(self):
        self.az.wiql("System.Parent", response=[
            work_item(8, **{TITLE_FIELD: "WORK-7-TASK-001 a", STATE_FIELD: "Closed"}),
            work_item(9, **{TITLE_FIELD: "WORK-7-TASK-002 b", STATE_FIELD: "Removed"}),
            work_item(10, **{TITLE_FIELD: "WORK-7-TASK-003 c", STATE_FIELD: "New"}),
        ])
        self.assertEqual(
            [task["state"] for task in AzureWorkItemBackend().tasks("7")],
            ["CLOSED", "CLOSED", "OPEN"],
        )

    def test_a_child_without_the_task_prefix_has_no_task_identity(self):
        self.az.wiql("System.Parent", response=[
            work_item(8, **{TITLE_FIELD: "Ad-hoc child", STATE_FIELD: "New"}),
        ])
        self.assertIsNone(AzureWorkItemBackend().tasks("7")[0]["taskId"])

    def test_task_comments_come_back_oldest_first(self):
        self.az.wiql("System.Parent", response=[self.TASK])
        # Azure returns newest first; the plan/implementation flags are derived
        # from comment order, so the backend restores it.
        self.assertEqual(
            AzureWorkItemBackend().tasks("7")[0]["comments"],
            ["## Technical Plan\n\nplan", "## Implementation\n\ndone"],
        )

    def test_task_carries_full_comment_objects_for_its_own_user_comments(self):
        self.az.wiql("System.Parent", response=[self.TASK])
        objects = AzureWorkItemBackend().tasks("7")[0]["commentObjects"]
        self.assertEqual([c["body"] for c in objects], ["## Technical Plan\n\nplan", "## Implementation\n\ndone"])
        self.assertEqual(objects[0]["createdAt"], "2026-09-07T06:30:00Z")
        self.assertEqual(objects[0]["url"], "https://az/comments/1")
        self.assertEqual(objects[0]["author"]["login"], "dev@acme.test")

    def test_close_task_moves_the_work_item_state(self):
        self.az.az("boards", "work-item", "update", response=self.TASK)
        AzureWorkItemBackend().close_task("8")
        self.assertIn("--state", self.az.calls[-1])
        self.assertEqual(self.az.calls[-1][self.az.calls[-1].index("--state") + 1], "Done")

    def test_remove_task_closes_and_detaches_it(self):
        self.az.az("boards", "work-item", "update", response=self.TASK)
        self.az.az("boards", "work-item", "show", response=RECORD)
        self.az.az("boards", "work-item", "relation", "remove", response={})
        AzureWorkItemBackend().remove_task("7", "8")
        relation = self.az.calls_matching("boards", "work-item", "relation", "remove")[0]
        self.assertEqual(relation[relation.index("--target-id") + 1], "7")
        self.assertIn("--yes", relation)

    def test_remove_task_uses_the_configured_removed_state(self):
        self.az.az("boards", "work-item", "update", response=self.TASK)
        self.az.az("boards", "work-item", "show", response=RECORD)
        self.az.az("boards", "work-item", "relation", "remove", response={})
        self.configure(azure_task_removed_state="Cut")
        AzureWorkItemBackend().remove_task("7", "8")
        update = self.az.calls_matching("boards", "work-item", "update")[0]
        self.assertEqual(update[update.index("--state") + 1], "Cut")

    def test_remove_task_retry_is_idempotent_after_the_state_update_lands(self):
        # A retry after a run that updated state but crashed before detaching
        # the parent relation: calling remove_task again re-applies the same
        # (already-applied) state update and still removes the relation.
        self.az.az("boards", "work-item", "update", response=self.TASK)
        self.az.az("boards", "work-item", "show", response=RECORD)
        self.az.az("boards", "work-item", "relation", "remove", response={})
        AzureWorkItemBackend().remove_task("7", "8")
        AzureWorkItemBackend().remove_task("7", "8")
        updates = self.az.calls_matching("boards", "work-item", "update")
        relations = self.az.calls_matching("boards", "work-item", "relation", "remove")
        self.assertEqual(len(updates), 2)
        self.assertEqual(len(relations), 2)
        self.assertEqual(updates[1][updates[1].index("--state") + 1], "Done")
        self.assertEqual(relations[1][relations[1].index("--target-id") + 1], "7")

    def test_remove_task_falls_back_to_the_task_closed_state(self):
        self.az.az("boards", "work-item", "update", response=self.TASK)
        self.az.az("boards", "work-item", "show", response=RECORD)
        self.az.az("boards", "work-item", "relation", "remove", response={})
        AzureWorkItemBackend().remove_task("7", "8")
        update = self.az.calls_matching("boards", "work-item", "update")[0]
        self.assertEqual(update[update.index("--state") + 1], "Done")

    def test_a_custom_removed_state_reads_as_closed(self):
        self.configure(azure_task_removed_state="Cut")
        self.az.wiql("System.Parent", response=[
            work_item(8, **{TITLE_FIELD: "WORK-7-TASK-001 a", STATE_FIELD: "Cut"}),
        ])
        self.assertEqual(AzureWorkItemBackend().tasks("7")[0]["state"], "CLOSED")

    def test_reopen_task_moves_the_work_item_state_back(self):
        self.az.az("boards", "work-item", "update", response=self.TASK)
        AzureWorkItemBackend().reopen_task("8")
        self.assertIn("--state", self.az.calls[-1])
        self.assertEqual(self.az.calls[-1][self.az.calls[-1].index("--state") + 1], "To Do")


class UpsertTaskTest(AzureHostTest):
    TASK_INPUT = {"id": "TASK-001", "title": "[CORE] retry queue", "body": None, "bodyText": "do the thing"}
    EXISTING = {
        "number": 8,
        "title": "WORK-7-TASK-001 [CORE] retry queue",
        "body": "do the thing",
        "taskId": "TASK-001",
    }

    def setUp(self) -> None:
        super().setUp()
        self.az.az("boards", "work-item", "show", response=RECORD)
        self.az.wiql("CONTAINS", response=[])

    def test_an_unchanged_task_is_not_rewritten(self):
        [result] = AzureWorkItemBackend().upsert_tasks("7", [self.TASK_INPUT], [self.EXISTING])
        self.assertEqual(result["action"], "unchanged")
        self.assertNotIn(["boards", "work-item", "update"], [args[:3] for args in self.az.calls])

    def test_a_reworded_task_keeps_its_number(self):
        self.az.invoke("wit", "batch", response={"value": [{"code": 200, "body": "{}"}]})
        [result] = AzureWorkItemBackend().upsert_tasks(
            "7", [{**self.TASK_INPUT, "title": "[CORE] retry pipeline"}], [self.EXISTING]
        )
        self.assertEqual((result["action"], result["number"]), ("retitled", 8))
        self.assertEqual(self.az.body_of("devops", "invoke")[0]["body"], [
            {"op": "add", "path": f"/fields/{TITLE_FIELD}", "value": "WORK-7-TASK-001 [CORE] retry pipeline"},
            {"op": "add", "path": f"/fields/{DESCRIPTION_FIELD}", "value": "do the thing"},
            {"op": "add", "path": f"/multilineFieldsFormat/{DESCRIPTION_FIELD}", "value": "Markdown"},
        ])

    def test_a_changed_body_updates_without_retitling(self):
        self.az.invoke("wit", "batch", response={"value": [{"code": 200, "body": "{}"}]})
        [result] = AzureWorkItemBackend().upsert_tasks(
            "7", [{**self.TASK_INPUT, "bodyText": "do the other thing"}], [self.EXISTING]
        )
        self.assertEqual(result["action"], "updated")

    def test_a_new_task_is_created_and_linked_to_its_parent(self):
        self.az.az("boards", "work-item", "relation", "add", response={})
        self.az.invoke("wit", "workitems", response=work_item(11))
        [result] = AzureWorkItemBackend().upsert_tasks("7", [self.TASK_INPUT], [])

        self.assertEqual(result, {
            "action": "created", "taskId": "TASK-001", "number": 11,
            "title": "WORK-7-TASK-001 [CORE] retry queue",
            "url": f"{ORGANIZATION}/{PROJECT}/_workitems/edit/11",
        })
        create = next(args for args in self.az.calls if args[:2] == ["devops", "invoke"])
        self.assertEqual(create[create.index("--route-parameters") + 2], "type=Task")
        # A delivery task body is Markdown too, so it takes the same format op.
        self.assertIn(
            {"op": "add", "path": f"/multilineFieldsFormat/{DESCRIPTION_FIELD}", "value": "Markdown"},
            self.az.body_of("devops", "invoke"),
        )
        link = next(args for args in self.az.calls if args[:4] == ["boards", "work-item", "relation", "add"])
        self.assertEqual(link[link.index("--relation-type") + 1], "parent")
        self.assertEqual(link[link.index("--target-id") + 1], "7")
        self.assertIn(
            {"op": "add", "path": f"/fields/{ASSIGNED_TO_FIELD}", "value": "probe@example.com"},
            self.az.body_of("devops", "invoke"),
        )

    def test_a_new_task_inherits_its_parents_area_path(self):
        self.az.az("boards", "work-item", "show", response=work_item(7, **{
            **RECORD["fields"], AREA_PATH_FIELD: f"{PROJECT}\\Payments",
        }))
        self.az.az("boards", "work-item", "relation", "add", response={})
        self.az.invoke("wit", "workitems", response=work_item(11))
        AzureWorkItemBackend().upsert_tasks("7", [self.TASK_INPUT], [])
        self.assertIn(
            {"op": "add", "path": f"/fields/{AREA_PATH_FIELD}", "value": f"{PROJECT}\\Payments"},
            self.az.body_of("devops", "invoke"),
        )

    def test_the_task_title_carries_the_parents_number_not_its_slug(self):
        # `upsert_tasks` is reachable by slug; the stable identity must still
        # read WORK-<number>-TASK-NNN so it matches on the next pass.
        self.az.wiql("Custom.PdlcSlug", response=[{"id": 7}])
        self.az.az("boards", "work-item", "relation", "add", response={})
        self.az.invoke("wit", "workitems", response=work_item(11))
        [result] = AzureWorkItemBackend().upsert_tasks("retry-uploads", [self.TASK_INPUT], [])
        self.assertEqual(result["title"], "WORK-7-TASK-001 [CORE] retry queue")


class CommentTest(AzureHostTest):
    def test_comments_are_mapped_and_ordered_oldest_first(self):
        self.az.invoke("wit", "comments", response={"comments": [
            {"id": 2, "text": "PDLC-REVIEW\n\nclean", "createdDate": "2026-09-07T07:00:00Z",
             "createdBy": {"uniqueName": "dev@acme.test", "displayName": "Dev"},
             "url": "https://az/comments/2"},
            {"id": 1, "text": "PDLC-IMPLEMENTATION\n\nlanded", "createdDate": "2026-09-07T06:00:00Z",
             "createdBy": {"uniqueName": "dev@acme.test", "displayName": "Dev"},
             "url": "https://az/comments/1"},
        ]})
        self.assertEqual(AzureWorkItemBackend().comments("7"), [
            {"body": "PDLC-IMPLEMENTATION\n\nlanded", "createdAt": "2026-09-07T06:00:00Z",
             "url": "https://az/comments/1", "author": {"login": "dev@acme.test"}},
            {"body": "PDLC-REVIEW\n\nclean", "createdAt": "2026-09-07T07:00:00Z",
             "url": "https://az/comments/2", "author": {"login": "dev@acme.test"}},
        ])

    def test_comments_html_decode_their_text(self):
        self.az.invoke("wit", "comments", response={"comments": [
            {"id": 1, "text": "he said &quot;retry &amp; back off&quot; &lt;here&gt;",
             "createdDate": "2026-09-07T06:00:00Z", "createdBy": {"uniqueName": "dev@acme.test"},
             "url": "https://az/comments/1"},
        ]})
        [comment] = AzureWorkItemBackend().comments("7")
        self.assertEqual(comment["body"], 'he said "retry & back off" <here>')

    def test_comments_page_html_decodes_its_text(self):
        self.az.invoke("wit", "comments", response={
            "comments": [{"id": 1, "text": "a &amp; b"}], "totalCount": 1,
        })
        page = AzureWorkItemBackend().comments_page("7")
        self.assertEqual([comment["body"] for comment in page.comments], ["a & b"])

    def test_comments_follow_a_continuation_token(self):
        pages = [
            {"comments": [{"id": 1, "text": "first"}], "continuationToken": "next"},
            {"comments": [{"id": 2, "text": "second"}]},
        ]
        self.az.invoke("wit", "comments", response=lambda _args: pages.pop(0))
        self.assertEqual(
            [comment["body"] for comment in AzureWorkItemBackend().comments("7")],
            ["first", "second"],
        )

    def test_comments_page_reads_newest_first_with_exact_total_and_continuation(self):
        self.az.invoke("wit", "comments", response={
            "comments": [{"id": 3, "text": "newest"}, {"id": 2, "text": "middle"}],
            "continuationToken": "older",
            "totalCount": 3,
        })
        page = AzureWorkItemBackend().comments_page("7")
        self.assertEqual([comment["body"] for comment in page.comments], ["newest", "middle"])
        self.assertEqual((page.page, page.per_page, page.total, page.has_next), (1, 100, 3, True))
        args = self.az.calls[0]
        query = args[args.index("--query-parameters") + 1:]
        self.assertIn("$top=100", query)
        self.assertIn("order=desc", query)

    def test_comments_page_replays_only_continuation_metadata_for_older_page(self):
        pages = [
            {"comments": [{"id": 3, "text": "newest"}], "continuationToken": "older", "totalCount": 3},
            {"comments": [{"id": 2, "text": "middle"}], "continuationToken": "oldest", "totalCount": 3},
        ]
        self.az.invoke("wit", "comments", response=lambda _args: pages.pop(0))
        page = AzureWorkItemBackend().comments_page("7", 2)
        self.assertEqual([comment["body"] for comment in page.comments], ["middle"])
        self.assertEqual((page.total, page.has_next), (3, True))
        calls = self.az.calls_matching("devops", "invoke")
        self.assertEqual(len(calls), 2)
        self.assertIn("continuationToken=older", calls[1])

    def test_comments_page_rejects_unbounded_or_invalid_requests(self):
        with self.assertRaises(PdlcError):
            AzureWorkItemBackend().comments_page("7", 0)
        with self.assertRaises(PdlcError):
            AzureWorkItemBackend().comments_page("7", 1, 50)

    def test_the_comment_api_version_carries_no_numeric_suffix(self):
        # `az devops invoke` parses the version as a float after stripping
        # `-preview`, so `7.1-preview.4` fails outright.
        self.az.invoke("wit", "comments", response={"comments": []})
        AzureWorkItemBackend().comments("7")
        args = self.az.calls[0]
        self.assertEqual(args[args.index("--api-version") + 1], "7.1-preview")

    def test_posting_a_comment_sends_the_body_verbatim_as_markdown(self):
        # `az boards work-item update --discussion` posts `format=html`, which
        # renders an evidence comment's headings as literal punctuation.
        self.az.invoke("wit", "comments", response={"id": 42})
        reference = AzureWorkItemBackend().post_comment("7", "PDLC-TESTING\n\ncovered")

        self.assertEqual(self.az.body_of("devops", "invoke"), {"text": "PDLC-TESTING\n\ncovered"})
        args = self.az.calls[0]
        self.assertEqual(args[args.index("--query-parameters") + 1], "format=markdown")
        self.assertEqual(args[args.index("--http-method") + 1], "POST")
        self.assertEqual(reference, f"{ORGANIZATION}/{PROJECT}/_workitems/edit/7?discussionId=42")

    def test_a_comment_reference_falls_back_to_the_work_item(self):
        self.az.invoke("wit", "comments", response={})
        self.assertEqual(
            AzureWorkItemBackend().post_comment("7", "body"),
            f"{ORGANIZATION}/{PROJECT}/_workitems/edit/7",
        )

    def test_a_blocker_goes_to_the_same_channel_as_a_comment(self):
        self.az.invoke("wit", "comments", response={"id": 43})
        AzureWorkItemBackend().post_blocker("7", "PDLC-DECISION\n\npick one")
        self.assertEqual(self.az.body_of("devops", "invoke"), {"text": "PDLC-DECISION\n\npick one"})

    def test_editing_a_comment_patches_the_parsed_discussion_id(self):
        self.az.invoke("wit", "comments", response={"id": 42})
        reference = AzureWorkItemBackend().edit_comment(
            "7", f"{ORGANIZATION}/{PROJECT}/_workitems/edit/7?discussionId=42", "updated plan"
        )

        self.assertEqual(self.az.body_of("devops", "invoke"), {"text": "updated plan"})
        args = self.az.calls[0]
        self.assertEqual(args[args.index("--http-method") + 1], "PATCH")
        self.assertIn("commentId=42", " ".join(args))
        self.assertEqual(reference, f"{ORGANIZATION}/{PROJECT}/_workitems/edit/7?discussionId=42")

    def test_a_comment_read_back_can_be_edited_and_deleted_by_its_url(self):
        # `comments` surfaces each comment's REST `url`, which is what a re-plan
        # hands back as `planCommentUrl` and invalidation hands to delete.
        self.az.invoke("wit", "comments", response={"comments": [
            {"id": 15680861, "text": "## Technical Plan\n\nold",
             "url": f"{ORGANIZATION}/{PROJECT}/_apis/wit/workItems/7/comments/15680861"},
        ]})
        backend = AzureWorkItemBackend()
        url = backend.comments("7")[0]["url"]

        reference = backend.edit_comment("7", url, "updated plan")
        self.assertIn("commentId=15680861", " ".join(self.az.calls[-1]))
        self.assertEqual(reference, f"{ORGANIZATION}/{PROJECT}/_workitems/edit/7?discussionId=15680861")

        backend.delete_comment("7", url)
        args = self.az.calls[-1]
        self.assertEqual(args[args.index("--http-method") + 1], "DELETE")
        self.assertIn("commentId=15680861", " ".join(args))

    def test_editing_a_comment_rejects_an_unparseable_reference(self):
        with self.assertRaisesRegex(PdlcError, "cannot parse an Azure comment id"):
            AzureWorkItemBackend().edit_comment("7", f"{ORGANIZATION}/{PROJECT}/_workitems/edit/7", "updated plan")


class CreationAndIdentityTest(AzureHostTest):
    def test_creating_a_record_sets_body_and_slug_in_the_create_call(self):
        self.az.invoke("wit", "workitems", response=work_item(7))
        created = AzureWorkItemBackend().create("Retry failed uploads", "## Product\n\nBody.\n", "retry-uploads")

        # A work item is on its board the moment it exists — no equivalent of
        # GitHub's separate `project item-add`, beyond the assignee lookup.
        self.assertEqual(len(self.az.calls), 2)
        self.assertEqual(created, {
            "id": "7", "number": 7,
            "url": f"{ORGANIZATION}/{PROJECT}/_workitems/edit/7",
        })
        operations = self.az.body_of("devops", "invoke")
        self.assertIn({"op": "add", "path": f"/fields/{DESCRIPTION_FIELD}", "value": "## Product\n\nBody.\n"}, operations)
        self.assertIn({"op": "add", "path": f"/fields/{SLUG_FIELD}", "value": "retry-uploads"}, operations)
        self.assertIn({"op": "add", "path": f"/fields/{TITLE_FIELD}", "value": "Retry failed uploads"}, operations)
        self.assertIn({"op": "add", "path": f"/fields/{ASSIGNED_TO_FIELD}", "value": "probe@example.com"}, operations)
        args = self.az.calls_matching("devops", "invoke")[0]
        self.assertEqual(args[args.index("--route-parameters") + 2], "type=Product Backlog Item")

    def test_a_configured_area_path_is_set_in_the_create_call(self):
        self.configure(azure_area_path=f"{PROJECT}\\Payments")
        self.az.invoke("wit", "workitems", response=work_item(7))
        AzureWorkItemBackend().create("Retry failed uploads", "body", "retry-uploads")
        self.assertIn(
            {"op": "add", "path": f"/fields/{AREA_PATH_FIELD}", "value": f"{PROJECT}\\Payments"},
            self.az.body_of("devops", "invoke"),
        )

    def test_an_unset_area_path_leaves_azures_default(self):
        self.az.invoke("wit", "workitems", response=work_item(7))
        AzureWorkItemBackend().create("Retry failed uploads", "body", "retry-uploads")
        self.assertNotIn(
            f"/fields/{AREA_PATH_FIELD}",
            [operation["path"] for operation in self.az.body_of("devops", "invoke")],
        )

    def test_a_created_description_is_marked_as_markdown(self):
        # Large text fields default to HTML through the API, which renders
        # `##` and `-` literally in the Azure UI. The choice is one-way, so it
        # has to be made at creation or not at all.
        self.az.invoke("wit", "workitems", response=work_item(7))
        AzureWorkItemBackend().create("Retry failed uploads", "## Product\n\nBody.\n", "retry-uploads")
        self.assertIn(
            {"op": "add", "path": f"/multilineFieldsFormat/{DESCRIPTION_FIELD}", "value": "Markdown"},
            self.az.body_of("devops", "invoke"),
        )

    def test_creation_uses_a_json_patch_body_on_the_non_preview_api(self):
        # The work-item resource rejects the `-preview` suffix the comments
        # resource requires.
        self.az.invoke("wit", "workitems", response=work_item(7))
        AzureWorkItemBackend().create("Retry", "body", "retry")
        args = self.az.calls_matching("devops", "invoke")[0]
        self.assertEqual(args[args.index("--api-version") + 1], "7.1")
        self.assertEqual(args[args.index("--media-type") + 1], "application/json-patch+json")
        self.assertEqual(args[args.index("--http-method") + 1], "POST")

    def test_creating_a_bug_is_refused_while_that_pipeline_is_unavailable(self):
        with self.assertRaisesRegex(PdlcError, "unavailable for work type: bug"):
            AzureWorkItemBackend().create("Crash", "body", "crash", WorkType.BUG)
        self.assertEqual(self.az.calls, [])

    def test_an_unparsed_work_type_is_rejected_before_any_io(self):
        with self.assertRaises(TypeError):
            AzureWorkItemBackend().create("Crash", "body", "crash", "feature")
        self.assertEqual(self.az.calls, [])

    def test_current_actor_is_the_signed_in_account(self):
        self.az.az("account", "show", response="dev@acme.test\n")
        self.assertEqual(AzureWorkItemBackend().current_actor(), "dev@acme.test")

    def test_ref_label_is_the_azure_project(self):
        self.assertEqual(AzureWorkItemBackend().ref_label(), PROJECT)

    def test_a_new_record_is_assigned_to_the_configured_identity(self):
        self.configure(azure_assigned_to="owner@acme.test")
        self.az.invoke("wit", "workitems", response=work_item(7))
        AzureWorkItemBackend().create("Retry", "body", "retry")
        operations = self.az.body_of("devops", "invoke")
        self.assertIn({"op": "add", "path": f"/fields/{ASSIGNED_TO_FIELD}", "value": "owner@acme.test"}, operations)

    def test_at_me_resolves_to_the_signed_in_account_for_assignment(self):
        # `@me` only resolves in a WIQL filter; a field write needs the real
        # identity, so `@me` falls back to `current_actor()` just like unset.
        self.configure(azure_assigned_to="@me")
        self.az.az("account", "show", response="dev@acme.test\n")
        self.az.invoke("wit", "workitems", response=work_item(7))
        AzureWorkItemBackend().create("Retry", "body", "retry")
        operations = self.az.body_of("devops", "invoke")
        self.assertIn({"op": "add", "path": f"/fields/{ASSIGNED_TO_FIELD}", "value": "dev@acme.test"}, operations)


class AzureConfigurationTest(unittest.TestCase):
    def test_the_azure_tracker_requires_its_own_coordinates(self):
        with self.assertRaises(ConfigurationError) as caught:
            Config(tracker_provider="azure", code_provider="none").validate_providers()
        self.assertIn("tracker.azure.organization", str(caught.exception))
        self.assertIn("tracker.azure.project", str(caught.exception))

    def test_a_github_code_provider_still_needs_a_repository(self):
        # The two hosts are independent: Azure Boards + GitHub repos is the
        # target pairing, so neither half's requirements imply the other's.
        with self.assertRaisesRegex(ConfigurationError, "code.github.repository"):
            Config(
                tracker_provider="azure", code_provider="github",
                azure_org="https://dev.azure.com/acme", azure_project="delivery",
            ).validate_providers()

    def test_azure_never_requires_github_project_coordinates(self):
        Config(
            tracker_provider="azure", code_provider="github", code_repository="acme/widgets",
            azure_org="https://dev.azure.com/acme", azure_project="delivery",
        ).validate_providers()

    def test_an_unset_code_provider_requires_no_repository(self):
        # `[code] provider` unset under an azure tracker resolves to `none`, so
        # validation must not demand GitHub coordinates the run will never use.
        Config(
            tracker_provider="azure",
            azure_org="https://dev.azure.com/acme", azure_project="delivery",
        ).validate_providers()

    def test_validation_and_selection_agree_on_the_implied_code_provider(self):
        # One helper feeds both `validate_providers` and the code-provider
        # selector; if they ever diverge, a run validates against one host and
        # then executes against another.
        from pdlc.config import default_code_provider
        from pdlc.hosts.code_host import _default_name

        from pdlc.config import install_config, reset_config

        self.addCleanup(reset_config)
        for backend, expected in (("github", "github"), ("file", "file"), ("azure", "none")):
            with self.subTest(tracker_provider=backend):
                self.assertEqual(default_code_provider(backend), expected)
                install_config(Config(tracker_provider=backend))
                self.assertEqual(_default_name(), expected)

    def test_a_missing_organization_fails_at_the_transport_rather_than_guessing(self):
        from pdlc.config import install_config, reset_config

        install_config(Config(tracker_provider="azure"))
        self.addCleanup(reset_config)
        from pdlc.hosts.lib.azure.transport import azure_config

        with self.assertRaisesRegex(PdlcError, "organization and project"):
            azure_config()


class ConcurrentTaskReadTest(AzureHostTest):
    """Task comments have no batch API, so they are read concurrently. These
    guard the two things concurrency can break: pairing each comment set with
    the right task, and surfacing a failure instead of a partial result."""

    TASKS = [
        work_item(8, **{TITLE_FIELD: "WORK-7-TASK-001 a", STATE_FIELD: "New"}),
        work_item(9, **{TITLE_FIELD: "WORK-7-TASK-002 b", STATE_FIELD: "New"}),
        work_item(10, **{TITLE_FIELD: "WORK-7-TASK-003 c", STATE_FIELD: "New"}),
    ]

    def setUp(self) -> None:
        super().setUp()

        def _show(args):
            item_id = args[args.index("--id") + 1]
            return next((item for item in self.TASKS if str(item["id"]) == item_id), RECORD)

        self.az.az("boards", "work-item", "show", response=_show)

        def _comments(args):
            item_id = next(a for a in args if a.startswith("workItemId=")).partition("=")[2]
            return {"comments": [{"id": 1, "text": f"note for {item_id}"}]}

        self.az.invoke("wit", "comments", response=_comments)

    def test_each_task_keeps_its_own_comments(self):
        # A zip misalignment would silently attribute one task's plan to
        # another, which is exactly the kind of thing `hasPlan` is trusted for.
        self.az.wiql("System.Parent", response=self.TASKS)
        tasks = AzureWorkItemBackend().tasks("7")
        self.assertEqual(
            [(task["number"], task["comments"]) for task in tasks],
            [(8, ["note for 8"]), (9, ["note for 9"]), (10, ["note for 10"])],
        )

    def test_every_task_is_read_exactly_once(self):
        self.az.wiql("System.Parent", response=self.TASKS)
        AzureWorkItemBackend().tasks("7")
        reads = self.az.calls_matching("devops", "invoke")
        self.assertEqual(len(reads), 3)

    def test_tasks_by_number_preserves_the_requested_order(self):
        # Concurrent reads complete in any order; the result must not.
        tasks = AzureWorkItemBackend().tasks_by_number(["10", "8", "9"])
        self.assertEqual([task["number"] for task in tasks], [10, 8, 9])

    def test_one_failed_read_fails_the_whole_call(self):
        # Backend failures are hard failures; a partial task list would let a
        # stage think a task has no plan when its read simply died.
        self.az.wiql("System.Parent", response=self.TASKS)
        self.az._routes = [
            route for route in self.az._routes
            if not route.match(["devops", "invoke", "--area", "wit", "--resource", "comments"])
        ]
        self.az.invoke("wit", "comments", response=PdlcError("ERROR: TF401232: Work item does not exist"))
        with self.assertRaisesRegex(PdlcError, "TF401232"):
            AzureWorkItemBackend().tasks("7")

    def test_a_record_with_no_tasks_reads_nothing(self):
        self.az.wiql("System.Parent", response="")
        self.assertEqual(AzureWorkItemBackend().tasks("7"), [])
        self.assertEqual(self.az.calls_matching("devops", "invoke"), [])

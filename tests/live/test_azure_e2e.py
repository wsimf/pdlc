"""Opt-in end-to-end coverage against the real Azure DevOps Boards host.

Exercises every `WorkItemBackend` method against the exact `az` commands
`AzureWorkItemBackend` issues — `az boards work-item show/update`, `az boards
query`, `az boards work-item relation add`, and `az devops invoke` for
creation and comments — down to their route/query parameters and API
versions, not the compiled Python surface, since that would not catch a wrong
parameter reaching the real API. Skips unless `tests/live/live_config.toml`
carries an `[azure]` table naming a dedicated scratch organization and
project; see `live_config.toml.example`. Deletes every work item it creates
during cleanup, and sweeps any `[LIVE E2E]` work items a prior run left behind
(e.g. a crash before its own cleanup ran) before creating its own.
"""

from __future__ import annotations

import unittest
from collections.abc import Iterable
from uuid import uuid4

from pdlc.config import Config, install_config, reset_config
from pdlc.domain.records import TaskInput
from pdlc.hosts.lib.azure.transport import project_args, run_az
from pdlc.hosts.lib.azure.workitem_backend import AzureWorkItemBackend
from pdlc.hosts.lib.azure.workitems import query, wiql_literal
from pdlc.hosts.workitem_host import reset_backend
from tests.live._config import CONFIG_PATH, load_section

_AZURE = load_section("azure")


@unittest.skipUnless(
    _AZURE is not None,
    f"add an [azure] table to {CONFIG_PATH} to run live Azure tests",
)
class AzureLiveEndToEndTest(unittest.TestCase):
    def setUp(self) -> None:
        assert _AZURE is not None
        self.organization = _AZURE["organization"]
        self.project = _AZURE["project"]

        install_config(Config(
            backend="azure",
            code_host="none",
            azure_org=self.organization,
            azure_project=self.project,
            azure_record_type=_AZURE.get("record_type"),
            azure_closed_state=_AZURE.get("closed_state"),
            azure_open_state=_AZURE.get("open_state"),
        ))
        reset_backend()
        self._sweep_orphaned_live_items()
        self.backend = AzureWorkItemBackend()
        self.created_ids: list[int] = []
        # Cleanups run last-registered-first, and `_cleanup_remote` still
        # needs the installed config's organization/project, so it must be
        # registered after (and therefore run before) the config/backend reset.
        self.addCleanup(reset_backend)
        self.addCleanup(reset_config)
        self.addCleanup(self._cleanup_remote)

    def _sweep_orphaned_live_items(self) -> None:
        """Delete every `[LIVE E2E]` work item already in the project, left
        behind by a run that crashed before its own `_cleanup_remote` ran.
        Runs before this test creates its own work items, so debris never
        accumulates across runs even when one of them fails."""
        stale = query(
            f"SELECT [System.Id] FROM workitems WHERE [System.TeamProject] = {wiql_literal(self.project)} "
            f"AND [System.Title] CONTAINS {wiql_literal('LIVE E2E')}"
        )
        self._delete_items(int(match["id"]) for match in stale)

    def _cleanup_remote(self) -> None:
        self._delete_items(self.created_ids)

    def _delete_items(self, item_ids: Iterable[int]) -> None:
        for item_id in item_ids:
            run_az([
                "boards", "work-item", "delete", *project_args(),
                "--id", str(item_id), "--yes",
            ])

    def test_real_record_and_task_lifecycle(self) -> None:
        marker = uuid4().hex[:12]
        slug = f"live-e2e-{marker}"
        title = f"[LIVE E2E] Azure host {marker}"
        body = f"## Product\n\nLive Azure host probe `{marker}`.\n"

        # --- create / resolve ---
        created = self.backend.create(title, body, slug)
        parent_number = created["number"]
        self.created_ids.append(parent_number)

        item = self.backend.resolve(str(parent_number))
        self.assertEqual(item["content"]["title"], title)
        self.assertEqual(item["issueBody"], body)
        self.assertEqual(item["Slug"], slug)

        # --- state fields ---
        self.backend.set_state(str(parent_number), "Product", "Pending", "Planning")
        self.backend.set_gate(str(parent_number), "Review Required")
        self.backend.set_slug(str(parent_number), slug)
        self.backend.set_skipped_states(str(parent_number), "UI")

        # --- body ---
        rewritten_body = f"## Product\n\nUpdated live probe `{marker}`.\n"
        self.backend.write_body(str(parent_number), rewritten_body)

        # --- comments ---
        comment_body = f"LIVE-E2E comment {marker}"
        comment_ref = self.backend.post_comment(str(parent_number), comment_body)
        edited_body = f"LIVE-E2E comment {marker} (edited)"
        self.backend.edit_comment(str(parent_number), comment_ref, edited_body)
        blocker_ref = self.backend.post_blocker(str(parent_number), f"LIVE-E2E blocker {marker}")
        self.assertTrue(blocker_ref)

        resolved = self.backend.resolve(str(parent_number))
        self.assertEqual(resolved["issueBody"], rewritten_body)
        self.assertEqual(resolved["Skipped States"], "UI")
        self.assertEqual(resolved["Status"], "Product")
        self.assertEqual(resolved["Gate State"], "Review Required")
        self.assertEqual(resolved["Lifecycle"], "Planning")
        comments = self.backend.comments(str(parent_number))
        self.assertTrue(any(comment["body"] == edited_body for comment in comments))
        self.assertFalse(any(comment["body"] == comment_body for comment in comments))

        page = self.backend.comments_page(str(parent_number), page=1, per_page=100)
        self.assertEqual(page.total, len(comments))
        self.assertEqual({comment["body"] for comment in page.comments}, {comment["body"] for comment in comments})

        # --- attached pull requests ---
        numbers = self.backend.attach_pr(str(parent_number), 999999)
        self.assertEqual(numbers, [999999])
        self.assertEqual(self.backend.attached_prs(str(parent_number)), [999999])

        # --- delivery tasks ---
        task_input: list[TaskInput] = [{
            "id": "TASK-001",
            "title": "[CORE] live task",
            "bodyText": f"Acceptance probe `{marker}`.\n",
        }]
        first = self.backend.upsert_tasks(str(parent_number), task_input, [])
        self.assertEqual(first[0]["action"], "created")
        task_number = first[0]["number"]
        self.created_ids.append(task_number)

        tasks = self.backend.tasks(str(parent_number))
        self.assertEqual(tasks[0]["taskId"], "TASK-001")
        self.assertEqual(tasks[0]["body"], task_input[0]["bodyText"])

        second = self.backend.upsert_tasks(str(parent_number), task_input, tasks)
        self.assertEqual(second[0]["action"], "unchanged")

        retitled_input: list[TaskInput] = [{**task_input[0], "title": "[CORE] live task (renamed)"}]
        third = self.backend.upsert_tasks(str(parent_number), retitled_input, tasks)
        self.assertEqual(third[0]["action"], "retitled")

        by_number = self.backend.tasks_by_number([str(task_number)])
        self.assertEqual(by_number[0]["number"], task_number)
        self.assertEqual(self.backend.task_pr_numbers(str(parent_number)), [])

        # --- close / reopen ---
        self.backend.close_task(str(task_number))
        task = self.backend.tasks_by_number([str(task_number)])[0]
        self.assertEqual(task["state"], "CLOSED")

        self.backend.reopen_task(str(task_number))
        task = self.backend.tasks_by_number([str(task_number)])[0]
        self.assertEqual(task["state"], "OPEN")

        # --- identity ---
        self.assertTrue(self.backend.current_actor())
        self.assertEqual(self.backend.ref_label(), self.project)

        # --- queue ---
        queue = self.backend.queue_items()
        self.assertTrue(any(entry["content"]["number"] == parent_number for entry in queue))

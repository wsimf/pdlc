"""One record driven end to end on the file backend: Product authored, every
stage landed and approved, tasks planned and implemented, Testing and
Verification recorded, and the record locked at completion. Also covers the
re-author-in-place behaviour of each pre-publication stage."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

from _support import FileBackendTest
from pdlc.hosts.lib.file.workitem_backend import FileWorkItemBackend


class WorkflowEndToEndTests(FileBackendTest):
    def test_file_backend_rejects_an_unparsed_work_type_before_creation(self):
        with self.assertRaisesRegex(TypeError, "work_type must be a WorkType"):
            FileWorkItemBackend().create("Title", "## Product\n", "title", "feature")  # type: ignore[arg-type]
        self.assertEqual(list(self.records_dir().iterdir()), [])

    def test_full_lifecycle(self):
        evidence = self.evidence_file()

        # --- Product ---
        draft = self.write_file(
            "product.md",
            "## Product\nThe shell ships.\n\n"
            "### 4. Functional requirements\n- FR-1: lands.\n\n"
            "### 5. Constraints\n- C-1: commands own mutations.\n\n"
            "## Decisions\n- Decided to ship.\n\n## Open Questions\n- none\n",
        )
        created = self.invoke(
            "post_write", "--title", "Shell", "--slug", "shell",
            "--evidence", evidence, "--body", draft,
        )
        self.assertEqual(created.code, 0, created.stderr)
        issue = created.json["work_item_number"]
        self.assertEqual(created.json["gateState"], "Approval Required")
        self.assertEqual(self.state(issue), ("Product", "Approval Required"))
        self.assertEqual(self.meta(issue)["workType"], "feature")

        self.assertEqual(self.invoke("post_approve", issue, evidence).code, 0)
        self.assertEqual(self.state(issue), ("UI", "Pending"))

        # --- UI: land, re-author in place before approval, approve ---
        ui = self.write_file("ui.md", "## UI\n\nUJ-1 covers the first run.\n")
        self.mark_ui_reviewed(issue, ui)
        self.assertEqual(
            self.invoke("post_tasks", "--work-item", issue, "--stage", "UI",
                        "--body", ui, "--evidence", evidence).code,
            0,
        )
        self.mark_ui_reviewed(issue, ui)
        reauth = self.invoke("post_tasks", "--work-item", issue, "--stage", "UI",
                             "--body", ui, "--evidence", evidence)
        self.assertEqual(reauth.json["gateState"], "Approval Required")
        self.assertNotIn("PDLC-INVALIDATED", self.comments_text(issue))
        self.invoke("post_approve", issue, evidence)
        self.assertIn("UJ-1 covers the first run", self.body(issue))

        # --- Tasks ---
        task_body = self.write_file(
            "task.md", "**Blocked by:** None\n**Type:** AFK\n**Requirements Covered:** FR-1, C-1\n**UI Journeys:** UJ-1\n\n**Scope:**\nBuild the core.\n\n**Acceptance Criteria:**\n- [ ] FR-1 works.\n"
        )
        manifest = self.write_file(
            "manifest.json",
            json.dumps([{
                "id": "TASK-001", "action": "create", "title": "Build core", "body": task_body,
                "type": "ui", "covers": ["FR-1", "C-1", "UJ-1"],
            }]),
        )
        self.mark_tasks_reviewed(issue, manifest)
        tasks_out = self.invoke("post_tasks", "--work-item", issue, "--stage", "Tasks",
                                "--manifest", manifest, "--evidence", evidence)
        self.assertEqual(tasks_out.code, 0, tasks_out.stderr)
        task_number = tasks_out.json["tasks"][0]["number"]
        self.mark_tasks_reviewed(issue, manifest)
        reauth_tasks = self.invoke("post_tasks", "--work-item", issue, "--stage", "Tasks",
                                   "--manifest", manifest, "--evidence", evidence)
        self.assertEqual(reauth_tasks.json["gateState"], "Approval Required")
        self.assertNotIn("PDLC-INVALIDATED", self.comments_text(issue))
        self.invoke("post_approve", issue, evidence)

        # --- Technical Plan: lands as a comment on the task, never its body ---
        plan_manifest = self.reviewed_plan_manifest(issue, {"TASK-001": "Touch core_service.py."})
        self.assertEqual(
            self.invoke("post_plan", "--work-item", issue,
                        "--manifest", plan_manifest, "--evidence", evidence).code,
            0,
        )
        # Re-planning revises the same files in a new pass, then reviews them again.
        self.invoke("prompt_tech_planner", issue, "--current-plan-manifest-path", plan_manifest)
        self.write_plan(json.loads(Path(plan_manifest).read_text())[0]["file"], "Touch core_service.py and its tests.")
        self.review_plans(issue, plan_manifest)
        reauth_plan = self.invoke("post_plan", "--work-item", issue,
                                  "--manifest", plan_manifest, "--evidence", evidence)
        self.assertEqual(reauth_plan.json["gateState"], "Approval Required")
        self.assertNotIn("PDLC-INVALIDATED", self.comments_text(issue))
        self.invoke("post_approve", issue, evidence)

        task_dir = self.records_dir() / str(issue) / "tasks" / str(task_number)
        self.assertIn("**Scope:**", (task_dir / "body.md").read_text())
        plan_comments = (task_dir / "comments.jsonl").read_text()
        self.assertIn("Technical Plan", plan_comments)
        # The re-land above replaced the existing plan comment in place rather
        # than appending a second one.
        self.assertEqual(plan_comments.count("## Technical Plan"), 1)

        # --- Implementation ---
        impl = self.write_file("impl.md", "## Implementation\n\n" + self.implementation_summary("Shipped. FR-1 covered."))
        stack_host = Mock()
        stack_host.submit_task_stack.return_value = [{
            "number": 147, "title": "Task implementation", "url": "https://x/147",
            "state": "OPEN", "isDraft": True, "branch": "pdlc/shell/task-001",
            "mergedAt": None, "checks": "PENDING",
        }]
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=stack_host):
            impl_out = self.invoke("post_implement_task", task_number, impl)
        self.assertEqual(impl_out.code, 0, impl_out.stderr)
        self.assertTrue(impl_out.json["closed"])
        self.assertEqual(impl_out.json["taskPr"]["number"], 147)
        self.assertEqual(self.task_meta(issue, task_number)["state"], "CLOSED")

        self.seed_prs(issue, [{
            "number": 147, "title": "Task implementation", "url": "https://x/147",
            "state": "OPEN", "isDraft": False, "branch": "feature/task",
            "mergedAt": None, "checks": "SUCCESS", "relation": "closes",
        }, {
            "number": 148, "title": "Implement", "url": "https://x/148",
            "state": "OPEN", "isDraft": False, "branch": "feature/x",
            "mergedAt": None, "checks": "SUCCESS", "relation": "closes",
        }])
        stage_host = Mock()
        with patch("pdlc.commands.post_implement.get_code_host", return_value=stage_host), \
             patch("pdlc.commands.post_implement.check_out"):
            self.assertEqual(self.invoke("post_implement", issue, evidence).code, 0)
        stage_host.submit_task_stack.assert_called_once_with()
        self.invoke("post_review", issue, "approval-required", evidence)
        self.invoke("post_approve", issue, evidence)
        self.assertEqual(self.next("--work-item", issue).front_matter("action"), "pdlc-test")

        # --- Testing ---
        trace = self.write_file("trace.md", "FR-1 -> record lands -> core_service.py lands()\n")
        test_host = Mock()
        test_host.ensure_pull_request_linked.return_value = {
            "number": 147, "title": "Task implementation", "url": "https://x/147",
            "state": "OPEN", "isDraft": False, "branch": "feature/task",
            "mergedAt": None, "checks": "SUCCESS",
        }
        with patch("pdlc.commands.post_test.get_code_host", return_value=test_host):
            self.assertEqual(
                self.invoke("post_test", issue, evidence, "--traceability", trace).code, 0
            )
        test_host.submit_task_stack.assert_called_once_with()
        self.assertIn("## Traceability", self.comments_text(issue))
        self.assertIn("core_service.py lands", self.comments_text(issue))
        self.invoke("post_review", issue, "approval-required", evidence)
        self.invoke("post_approve", issue, evidence)

        # --- Verification (clean) ---
        sha = self.head_sha()
        verified = self.invoke("post_verify", issue, self.verify_report(issue))
        self.assertEqual(verified.code, 0, verified.stderr)
        self.assertEqual(self.state(issue), ("Verification", "Approval Required"))

        # --- Completion ---
        completion = self.write_file(
            "completion.md",
            "## Shipped\n\nThe record shell shipped; linked PR merged.\n\n"
            f"## Verification\n\nclean @ {sha} — claims, journeys, UX reviewed, cumulative review clean.\n\n"
            "## Decisions\n\n- None\n\n## Open Questions\n\n- None\n\n"
            "## Limitations\n\n- None\n\n## Skipped Stages\n\n- None\n",
        )

        # Refuses while the linked closing PR is still open.
        not_ready = self.invoke("post_complete", issue, completion)
        self.assertEqual(not_ready.code, 1)
        self.assertIn("not ready to complete", not_ready.stderr)
        self.assertIn("Not ready", self.invoke("inspect_complete", issue).stdout)

        prs_path = self.records_dir() / str(issue) / "pull_requests.json"
        prs = json.loads(prs_path.read_text())
        for pr in prs:
            pr.update(state="MERGED", mergedAt="2026-01-01T00:00:00Z")
        prs_path.write_text(json.dumps(prs))

        self.assertIn("Ready — Status: Verification", self.invoke("inspect_complete", issue).stdout)
        completed = self.invoke("post_complete", issue, completion)
        self.assertEqual(completed.code, 0, completed.stderr)
        self.assertTrue(completed.json["completed"])
        self.assertEqual(self.fields(issue)["Status"], "Complete")
        self.assertEqual(self.meta(issue)["state"], "CLOSED")
        # The fixture PR reports no head commit, so its branch is never deleted.
        self.assertEqual(completed.json["branches"]["deleted"], [])
        self.assertIn("see the completion comment", self.body(issue))

        # The evidence log is append-only: one comment per stage, none rewritten.
        timeline = self.invoke("inspect_timeline", issue, "--full").stdout
        for marker in ("## PRODUCT", "## REVIEW", "## APPROVED", "## COMPLETE"):
            self.assertIn(marker, timeline)

    def test_malformed_completion_evidence_is_rejected_before_write(self):
        self.seed_record(80, "Verification", "Approval Required")
        bad = self.write_file("bad.md", "just a sentence\n")
        result = self.invoke("post_complete", 80, bad)
        self.assertEqual(result.code, 1)
        self.assertIn("evidence-malformed", result.stderr)
        self.assertEqual(self.state(80), ("Verification", "Approval Required"))
        self.assertNotIn("state", self.meta(80))

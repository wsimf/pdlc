"""Record/replay coverage for the GitHub work-item and code hosts.

These modules only run against a live GitHub Project and are otherwise
unexercised. The harness in ``_gh_replay`` swaps ``run_gh`` for a router so the
transport, JSON shaping, and reconciliation logic are all checked offline.
"""

from __future__ import annotations

import unittest

from pdlc.domain.lifecycle import PdlcError
from pdlc.hosts import github_issues, github_project
from pdlc.hosts.code_host.github import GitHubCodeHost
from pdlc.hosts.workitem_host.github import GitHubWorkItemBackend

from tests._gh_replay import GitHubHostTest, graphql_data


class ProjectItemResolutionTest(GitHubHostTest):
    def test_item_for_issue_selects_the_configured_project(self) -> None:
        self.gh.graphql(
            "issue(number: $issue)",
            graphql_data({
                "repository": {
                    "issue": {
                        "number": 3,
                        "title": "WORK-3 Ship the thing",
                        "url": "https://github.com/wsimf/pdlc/issues/3",
                        "body": "## Product\n",
                        "projectItems": {
                            "nodes": [
                                {
                                    "id": "PVTI_other",
                                    "project": {"number": 99},
                                    "status": {"name": "UI"},
                                    "gate": {"name": "Pending"},
                                    "lifecycle": None,
                                    "skippedStates": None,
                                    "slug": None,
                                },
                                {
                                    "id": "PVTI_match",
                                    "project": {"number": 7},
                                    "status": {"name": "Implementation"},
                                    "gate": {"name": "Review Required"},
                                    "lifecycle": {"name": "Delivery"},
                                    "skippedStates": {"text": "Testing"},
                                    "slug": {"text": "ship-the-thing"},
                                },
                            ]
                        },
                    }
                }
            }),
        )

        item = github_project.item_for_issue("3")

        self.assertEqual(item["id"], "PVTI_match")
        self.assertEqual(item["Status"], "Implementation")
        self.assertEqual(item["Gate State"], "Review Required")
        self.assertEqual(item["Slug"], "ship-the-thing")
        self.assertEqual(item["Skipped States"], "Testing")
        self.assertEqual(item["content"]["number"], 3)

    def test_item_for_issue_rejects_ambiguous_project_membership(self) -> None:
        self.gh.graphql(
            "issue(number: $issue)",
            graphql_data({
                "repository": {
                    "issue": {
                        "number": 3, "title": "t", "url": "u", "body": "",
                        "projectItems": {"nodes": [
                            {"id": "a", "project": {"number": 7}, "status": None,
                             "gate": None, "lifecycle": None, "skippedStates": None, "slug": None},
                            {"id": "b", "project": {"number": 7}, "status": None,
                             "gate": None, "lifecycle": None, "skippedStates": None, "slug": None},
                        ]},
                    }
                }
            }),
        )
        with self.assertRaises(PdlcError):
            github_project.item_for_issue("3")

    def test_item_for_issue_rejects_non_numeric_ref(self) -> None:
        with self.assertRaises(PdlcError):
            github_project.item_for_issue("abc")


class ProjectItemListTest(GitHubHostTest):
    def test_project_items_normalizes_field_names(self) -> None:
        self.gh.gh(
            "project", "item-list",
            response={
                "items": [
                    {
                        "id": "PVTI_1",
                        "content": {"number": 3, "type": "Issue"},
                        "status": "Implementation",
                        "gateState": "Pending",
                        "slug": "ship-it",
                    }
                ],
                "totalCount": 1,
            },
        )

        result = github_project.project_items()

        item = result["items"][0]
        self.assertEqual(item["Status"], "Implementation")
        self.assertEqual(item["Gate State"], "Pending")
        self.assertEqual(item["Slug"], "ship-it")


class ProjectStateTransitionTest(GitHubHostTest):
    def _arm_transition(self, *, settled_status: str, settled_gate: str, settled_lifecycle: str) -> None:
        self.stub_project_metadata()
        self.gh.graphql(
            "updateProjectV2ItemFieldValue",
            graphql_data({
                "status": {"projectV2Item": {"id": "PVTI_1"}},
                "gate": {"projectV2Item": {"id": "PVTI_1"}},
                "lifecycle": {"projectV2Item": {"id": "PVTI_1"}},
            }),
        )
        self.gh.graphql(
            "node(id: $itemId)",
            graphql_data({
                "node": {
                    "status": {"name": settled_status},
                    "gate": {"name": settled_gate},
                    "lifecycle": {"name": settled_lifecycle},
                }
            }),
        )

    def test_set_state_settles_on_matching_readback(self) -> None:
        self._arm_transition(
            settled_status="Implementation", settled_gate="Review Required", settled_lifecycle="Delivery"
        )

        github_project.set_state("PVTI_1", "Implementation", "Review Required", "Delivery")

        variables = self.gh.graphql_variables("updateProjectV2ItemFieldValue")
        self.assertEqual(variables["statusOptionId"], "opt-impl")
        self.assertEqual(variables["gateOptionId"], "opt-review")
        self.assertEqual(variables["lifecycleOptionId"], "opt-delivery")
        self.assertEqual(variables["projectId"], "PVT_project")

    def test_set_state_rejects_unknown_gate(self) -> None:
        with self.assertRaises(PdlcError):
            github_project.set_state("PVTI_1", "Implementation", "Bogus Gate", "Delivery")

    def test_set_state_raises_when_transition_never_settles(self) -> None:
        self._arm_transition(
            settled_status="Implementation", settled_gate="Pending", settled_lifecycle="Delivery"
        )
        with self.assertRaises(PdlcError):
            github_project.set_state("PVTI_1", "Implementation", "Review Required", "Delivery")

    def test_edit_single_select_resolves_field_and_option_ids(self) -> None:
        self.stub_project_metadata()
        self.gh.gh("project", "item-edit", response={"id": "PVTI_1"})

        github_project.edit_single_select("PVTI_1", "Gate State", "Approval Required")

        edit_call = next(
            args for args, _ in self.gh.calls if args[:2] == ["project", "item-edit"]
        )
        self.assertIn("opt-approval", edit_call)
        self.assertIn("F_gate", edit_call)

    def test_set_slug_writes_text_field(self) -> None:
        self.stub_project_metadata()
        self.gh.gh("project", "item-edit", response={"id": "PVTI_1"})

        github_project.set_slug("PVTI_1", "ship-the-thing")

        edit_call = next(
            args for args, _ in self.gh.calls if args[:2] == ["project", "item-edit"]
        )
        self.assertIn("--text", edit_call)
        self.assertIn("ship-the-thing", edit_call)
        self.assertIn("F_slug", edit_call)


class SubIssueReadTest(GitHubHostTest):
    def test_subissues_for_parses_stable_task_identity(self) -> None:
        self.gh.graphql(
            "subIssues(first: 100)",
            graphql_data({
                "repository": {
                    "issue": {
                        "subIssues": {
                            "nodes": [
                                {
                                    "number": 11,
                                    "title": "WORK-3-TASK-001 Wire the seam",
                                    "url": "u11",
                                    "state": "OPEN",
                                    "body": "## Scope",
                                    "comments": {"nodes": [{"body": "## Technical Plan\nx"}]},
                                },
                                {
                                    "number": 12,
                                    "title": "Unrelated chore",
                                    "url": "u12",
                                    "state": "CLOSED",
                                    "body": "",
                                    "comments": {"nodes": []},
                                },
                            ]
                        }
                    }
                }
            }),
        )

        tasks = github_issues.subissues_for("3")

        self.assertEqual(tasks[0]["taskId"], "TASK-001")
        self.assertEqual(tasks[0]["comments"], ["## Technical Plan\nx"])
        self.assertIsNone(tasks[1]["taskId"])

    def test_comments_for_issue_flattens_paginated_rest_pages(self) -> None:
        self.gh.api(
            "issues/3/comments",
            [
                [
                    {
                        "body": "first",
                        "created_at": "2026-01-01T00:00:00Z",
                        "html_url": "h1",
                        "user": {"login": "alice"},
                    }
                ],
                [
                    {
                        "body": "second",
                        "created_at": "2026-01-02T00:00:00Z",
                        "html_url": "h2",
                        "user": {"login": "bob"},
                    }
                ],
            ],
        )

        comments = github_issues.comments_for_issue("3")

        self.assertEqual([c["body"] for c in comments], ["first", "second"])
        self.assertEqual(comments[0]["author"]["login"], "alice")

    def test_post_comment_writes_marker_stamp(self) -> None:
        self.gh.gh("issue", "comment", response="https://github.com/wsimf/pdlc/issues/3#issuecomment-1")

        github_issues.post_comment("3", "verification passed", "VERIFICATION")

        args, _ = next(
            (call for call in self.gh.calls if call[0][:2] == ["issue", "comment"])
        )
        self.assertIn("--body-file", args)


class SubIssueUpsertTest(GitHubHostTest):
    def test_tasks_by_number_batches_issue_lookups(self) -> None:
        self.gh.graphql(
            "issue0: issue(number:",
            graphql_data({
                "repository": {
                    "issue0": {
                        "number": 11, "title": "WORK-3-TASK-001 A", "url": "u11",
                        "state": "OPEN", "body": "b", "comments": {"nodes": [{"body": "c"}]},
                    },
                    "issue1": {
                        "number": 12, "title": "WORK-3-TASK-002 B", "url": "u12",
                        "state": "CLOSED", "body": "b", "comments": {"nodes": []},
                    },
                }
            }),
        )

        tasks = github_issues.tasks_by_number(["11", "12"])

        self.assertEqual([t["taskId"] for t in tasks], ["TASK-001", "TASK-002"])
        self.assertEqual(tasks[0]["comments"], ["c"])

    def test_tasks_by_number_raises_on_missing_issue(self) -> None:
        self.gh.graphql("issue0: issue(number:", graphql_data({"repository": {"issue0": None}}))
        with self.assertRaises(PdlcError):
            github_issues.tasks_by_number(["11"])

    def test_upsert_tasks_creates_and_links_a_new_sub_issue(self) -> None:
        # No pre-existing unlinked Issues to recover.
        self.gh.gh("issue", "list", response=[])
        self.gh.gh(
            "issue", "create",
            response="Creating\nhttps://github.com/wsimf/pdlc/issues/11\n",
        )
        # link_subissues: resolve node ids, then addSubIssue, then verify.
        self.gh.graphql(
            "issue0: issue(number:",
            graphql_data({"repository": {"issue0": {"id": "I_parent"}, "issue1": {"id": "I_child"}}}),
        )
        self.gh.graphql(
            "addSubIssue",
            graphql_data({"link0": {"issue": {"id": "I_parent"}}}),
        )
        self.gh.graphql(
            "subIssues(first: 100)",
            graphql_data({
                "repository": {"issue": {"subIssues": {"nodes": [
                    {"number": 11, "title": "WORK-3-TASK-001 New", "url": "u11",
                     "state": "OPEN", "body": "b", "comments": {"nodes": []}},
                ]}}}
            }),
        )

        results = github_issues.upsert_tasks(
            "3",
            [{"id": "TASK-001", "title": "New", "body": "/tmp/unused", "bodyText": "## Scope\nx\n"}],
            existing=[],
        )

        self.assertEqual(results[0]["action"], "created")
        self.assertEqual(results[0]["number"], 11)
        self.assertTrue(self.gh.graphql_variables("addSubIssue"))


class WorkItemBackendTest(GitHubHostTest):
    def setUp(self) -> None:
        super().setUp()
        self.backend = GitHubWorkItemBackend()

    def test_current_actor_reads_the_authenticated_login(self) -> None:
        self.gh.api("user", {"login": "wsimf"})
        self.assertEqual(self.backend.current_actor(), "wsimf")

    def test_write_body_edits_the_issue_from_a_body_file(self) -> None:
        self.gh.gh("issue", "edit", response="")
        self.backend.write_body("3", "## Product\nnew body\n")
        args, _ = next(call for call in self.gh.calls if call[0][:2] == ["issue", "edit"])
        self.assertIn("--body-file", args)
        self.assertIn("--repo", args)

    def test_create_parses_issue_number_and_adds_project_item(self) -> None:
        self.gh.gh(
            "issue", "create",
            response="Creating issue\nhttps://github.com/wsimf/pdlc/issues/42\n",
        )
        self.gh.gh("project", "item-add", response={"id": "PVTI_new"})

        record = self.backend.create("WORK-42 Title", "## Product\n", "title")

        self.assertEqual(record, {"id": "PVTI_new", "number": 42, "url": "https://github.com/wsimf/pdlc/issues/42"})

    def test_create_rejects_unparseable_issue_url(self) -> None:
        self.gh.gh("issue", "create", response="Creating issue\nnot-a-url\n")
        with self.assertRaises(PdlcError):
            self.backend.create("t", "b", "s")

    def test_close_task_closes_the_sub_issue(self) -> None:
        self.gh.gh("issue", "close", response="")
        self.backend.close_task("11")
        self.assertTrue(any(call[0][:2] == ["issue", "close"] for call in self.gh.calls))


class CodeHostTest(GitHubHostTest):
    def setUp(self) -> None:
        super().setUp()
        self.host = GitHubCodeHost()

    def test_pull_requests_merges_closing_and_referencing_prs(self) -> None:
        self.gh.graphql(
            "closedByPullRequestsReferences",
            graphql_data({
                "repository": {
                    "issue": {
                        "closedByPullRequestsReferences": {
                            "nodes": [
                                {
                                    "number": 5, "title": "impl", "url": "u5", "state": "OPEN",
                                    "isDraft": False, "headRefName": "feat", "mergedAt": None,
                                    "commits": {"nodes": [
                                        {"commit": {"statusCheckRollup": {"state": "SUCCESS"}}}
                                    ]},
                                }
                            ]
                        },
                        "timelineItems": {
                            "nodes": [
                                {"source": {
                                    "number": 4, "title": "spike", "url": "u4", "state": "MERGED",
                                    "isDraft": False, "headRefName": "spike", "mergedAt": "2026-01-01T00:00:00Z",
                                    "commits": {"nodes": []},
                                }},
                                {"source": {}},
                            ]
                        },
                    }
                }
            }),
        )

        prs = self.host.pull_requests("3")

        self.assertEqual([pr["number"] for pr in prs], [5, 4])
        self.assertEqual(prs[0]["checks"], "SUCCESS")
        self.assertEqual(prs[0]["relation"], "closes")
        self.assertEqual(prs[1]["checks"], "NONE")

    def test_pull_request_files_lists_changed_paths(self) -> None:
        self.gh.gh(
            "pr", "view",
            response={"files": [{"path": "a.py"}, {"path": "b.md"}]},
        )
        self.assertEqual(self.host.pull_request_files(7), ["a.py", "b.md"])

    def test_ensure_pull_request_linked_returns_existing_closing_pr(self) -> None:
        self.gh.gh(
            "pr", "view",
            response={
                "number": 5, "title": "impl", "url": "u5", "state": "OPEN",
                "isDraft": False, "headRefName": "feat", "mergedAt": None,
                "commits": {"nodes": [{"commit": {"statusCheckRollup": {"state": "SUCCESS"}}}]},
                "body": "Closes #3\n",
            },
        )
        self.gh.graphql(
            "closedByPullRequestsReferences",
            graphql_data({
                "repository": {
                    "issue": {
                        "closedByPullRequestsReferences": {"nodes": [
                            {
                                "number": 5, "title": "impl", "url": "u5", "state": "OPEN",
                                "isDraft": False, "headRefName": "feat", "mergedAt": None,
                                "commits": {"nodes": [
                                    {"commit": {"statusCheckRollup": {"state": "SUCCESS"}}}
                                ]},
                            }
                        ]},
                        "timelineItems": {"nodes": []},
                    }
                }
            }),
        )

        linked = self.host.ensure_pull_request_linked("3")

        self.assertEqual(linked["number"], 5)
        self.assertFalse(any(call[0][:2] == ["pr", "edit"] for call in self.gh.calls))


if __name__ == "__main__":
    unittest.main()

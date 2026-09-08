"""Record/replay coverage for the GitHub work-item and code hosts.

These modules only run against a live GitHub Project and are otherwise
unexercised. The harness in ``_gh_replay`` swaps ``run_gh`` for a router so the
transport, JSON shaping, and reconciliation logic are all checked offline.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.workflow import WorkType
from pdlc.hosts.lib.github import issues as github_issues, project as github_project, pr_registry as github_pr_registry
from pdlc.hosts.lib.github.code_host import GitHubCodeHost
from pdlc.hosts.lib.github.workitem_backend import GitHubWorkItemBackend

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
                        "issueType": {"name": "Bug"},
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
        self.assertEqual(item["workType"], "bug")

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


class ProjectQueueItemsTest(GitHubHostTest):
    def test_queue_items_matches_repository_case_insensitively_and_ignores_other_content(self) -> None:
        self.gh.gh("project", "view", response={"id": "PVT_project"})
        self.gh.graphql(
            "items(first: 100, after: $after)",
            graphql_data({
                "node": {"items": {
                    "nodes": [
                        {
                            "id": "PVTI_1",
                            "content": {
                                "__typename": "Issue", "number": 3, "title": "Ship it", "url": "u",
                                "repository": {"nameWithOwner": "WSIMF/PDLC"},
                                "issueType": {"name": "Feature"},
                            },
                            "status": {"name": "Implementation"},
                            "gate": {"name": "Pending"},
                            "lifecycle": {"name": "Planning"},
                            "skippedStates": {"text": "Testing"},
                        },
                        {
                            "id": "PVTI_other_repo",
                            "content": {
                                "__typename": "Issue", "number": 4, "title": "Other", "url": "u2",
                                "repository": {"nameWithOwner": "wsimf/other"},
                            },
                        },
                        {"id": "PVTI_draft", "content": {"__typename": "DraftIssue"}},
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }},
            }),
        )

        result = github_project.queue_items()

        self.assertEqual(len(result), 1)
        item = result[0]
        self.assertEqual(item["content"], {"number": 3, "title": "Ship it", "url": "u"})
        self.assertEqual(item["Status"], "Implementation")
        self.assertEqual(item["Gate State"], "Pending")
        self.assertEqual(item["Lifecycle"], "Planning")
        self.assertEqual(item["Skipped States"], "Testing")
        self.assertEqual(item["workType"], "feature")

    def test_queue_items_paginates(self) -> None:
        self.gh.gh("project", "view", response={"id": "PVT_project"})

        def page(number: int, has_next: bool, cursor: str | None) -> dict:
            return graphql_data({"node": {"items": {
                "nodes": [{
                    "id": f"PVTI_{number}",
                    "content": {
                        "__typename": "Issue", "number": number, "title": "t", "url": "u",
                        "repository": {"nameWithOwner": "wsimf/pdlc"}, "issueType": None,
                    },
                    "status": {"name": "Product"}, "gate": {"name": "Pending"},
                    "lifecycle": None, "skippedStates": None,
                }],
                "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
            }}})

        pages = iter([page(3, True, "cursor-1"), page(4, False, None)])
        self.gh.graphql("items(first: 100, after: $after)", response=lambda _args, _input: next(pages))

        result = github_project.queue_items()

        self.assertEqual([item["content"]["number"] for item in result], [3, 4])
        graphql_calls = [call for call, _ in self.gh.calls if call[:2] == ["api", "graphql"]]
        self.assertEqual(len(graphql_calls), 2)
        self.assertTrue(any("after=cursor-1" in argument for argument in graphql_calls[1]))


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

        github_issues.post_comment("3", "PDLC-REVIEW\n\nverification passed")

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


class PrRegistryFormatTest(unittest.TestCase):
    """The GitHub backend's own storage format for attached pull requests."""

    BODY = "## Scope\nDo the thing.\n\n## Acceptance criteria\n- ok\n"

    def test_round_trips_pr_numbers_without_touching_the_body(self) -> None:
        stamped = github_pr_registry.attach(self.BODY, [148, 152])
        self.assertTrue(stamped.startswith("<!-- pdlc:meta\n"))
        self.assertEqual(github_pr_registry.prs(stamped), [148, 152])
        self.assertEqual(github_pr_registry.strip(stamped), self.BODY)

    def test_plain_body_has_no_registry(self) -> None:
        self.assertEqual(github_pr_registry.prs(self.BODY), [])
        self.assertEqual(github_pr_registry.strip(self.BODY), self.BODY)

    def test_with_pr_dedupes_and_sorts(self) -> None:
        once, numbers = github_pr_registry.with_pr(self.BODY, 160)
        self.assertEqual(numbers, [160])
        twice, numbers = github_pr_registry.with_pr(once, 148)
        self.assertEqual(numbers, [148, 160])
        self.assertEqual(github_pr_registry.strip(twice), self.BODY)

    def test_with_pr_returns_the_body_unchanged_when_already_attached(self) -> None:
        once, _ = github_pr_registry.with_pr(self.BODY, 148)
        again, numbers = github_pr_registry.with_pr(once, 148)
        self.assertIs(again, once)
        self.assertEqual(numbers, [148])

    def test_attaching_nothing_removes_the_block(self) -> None:
        stamped = github_pr_registry.attach(self.BODY, [148])
        self.assertEqual(github_pr_registry.attach(stamped, []), self.BODY)

    def test_restore_carries_the_block_onto_a_new_body(self) -> None:
        stored = github_pr_registry.attach("## Scope\nold\n", [148])
        restored = github_pr_registry.restore(stored, self.BODY)
        self.assertEqual(github_pr_registry.prs(restored), [148])
        self.assertEqual(github_pr_registry.strip(restored), self.BODY)

    def test_view_splits_a_raw_node(self) -> None:
        node = github_pr_registry.view({"number": 7, "body": github_pr_registry.attach(self.BODY, [148])})
        self.assertEqual(node["prs"], [148])
        self.assertEqual(node["body"], self.BODY)


class WorkItemBackendTest(GitHubHostTest):
    def setUp(self) -> None:
        super().setUp()
        self.backend = GitHubWorkItemBackend()

    def test_current_actor_reads_the_authenticated_login(self) -> None:
        self.gh.api("user", {"login": "wsimf"})
        self.assertEqual(self.backend.current_actor(), "wsimf")

    def _stored_body(self, body: str) -> None:
        self.gh.gh("issue", "view", response=json.dumps({"body": body}))

    def _capture_edited_body(self) -> list[str]:
        """Read each `issue edit --body-file` payload while its temp file lives."""
        captured: list[str] = []

        def respond(args: list[str], _input: str | None) -> str:
            captured.append(Path(args[args.index("--body-file") + 1]).read_text())
            return ""

        self.gh.gh("issue", "edit", response=respond)
        return captured

    def test_write_body_edits_the_issue_from_a_body_file(self) -> None:
        self._stored_body("## Product\nold\n")
        self.gh.gh("issue", "edit", response="")
        self.backend.write_body("3", "## Product\nnew body\n")
        args, _ = next(call for call in self.gh.calls if call[0][:2] == ["issue", "edit"])
        self.assertIn("--body-file", args)
        self.assertIn("--repo", args)

    def test_resolve_splits_the_registry_out_of_the_body(self) -> None:
        self.gh.graphql(
            "issue(number: $issue)",
            graphql_data({
                "repository": {
                    "issue": {
                        "number": 3,
                        "title": "Record",
                        "url": "https://example.test/3",
                        "body": "<!-- pdlc:meta\nprs: 148 152\n-->\n\n## Product\nkeep\n",
                        "issueType": {"name": "Feature"},
                        "projectItems": {"nodes": [{
                            "id": "PVTI_1",
                            "project": {"number": 7},
                            "status": {"name": "Implementation"},
                            "gate": {"name": "Pending"},
                            "lifecycle": {"name": "Active"},
                            "skippedStates": {"text": ""},
                            "slug": {"text": "record"},
                        }]},
                    }
                }
            }),
        )
        item = self.backend.resolve("3")
        self.assertEqual(item["prs"], [148, 152])
        self.assertEqual(item["issueBody"], "## Product\nkeep\n")
        self.assertNotIn("pdlc:meta", item["issueBody"])

    def test_write_body_preserves_attached_pull_requests(self) -> None:
        # The caller only ever holds human content, so a body round trip must
        # not be able to drop the registry.
        self._stored_body("<!-- pdlc:meta\nprs: 148 152\n-->\n\n## Product\nold\n")
        written = self._capture_edited_body()
        self.backend.write_body("3", "## Product\nnew body\n")
        self.assertEqual(github_pr_registry.prs(written[0]), [148, 152])
        self.assertIn("new body", written[0])

    def test_attach_pr_adds_a_number_and_reports_the_full_list(self) -> None:
        self._stored_body("<!-- pdlc:meta\nprs: 148\n-->\n\n## Scope\n")
        written = self._capture_edited_body()
        self.assertEqual(self.backend.attach_pr("3", 152), [148, 152])
        self.assertEqual(github_pr_registry.prs(written[0]), [148, 152])

    def test_attach_pr_is_idempotent_and_skips_the_write(self) -> None:
        self._stored_body("<!-- pdlc:meta\nprs: 148\n-->\n\n## Scope\n")
        self.assertEqual(self.backend.attach_pr("3", 148), [148])
        self.assertFalse([call for call in self.gh.calls if call[0][:2] == ["issue", "edit"]])

    def test_attached_prs_reads_the_registry(self) -> None:
        self._stored_body("<!-- pdlc:meta\nprs: 152 148\n-->\n\n## Scope\n")
        self.assertEqual(self.backend.attached_prs("3"), [148, 152])

    def test_create_parses_issue_number_and_adds_project_item(self) -> None:
        self.gh.gh(
            "issue", "create",
            response="Creating issue\nhttps://github.com/wsimf/pdlc/issues/42\n",
        )
        self.gh.gh("project", "item-add", response={"id": "PVTI_new"})

        record = self.backend.create("WORK-42 Title", "## Product\n", "title")

        self.assertEqual(record, {"id": "PVTI_new", "number": 42, "url": "https://github.com/wsimf/pdlc/issues/42"})
        create_call = next(call[0] for call in self.gh.calls if call[0][:2] == ["issue", "create"])
        self.assertNotIn("--type", create_call)

    def test_create_rejects_unparseable_issue_url(self) -> None:
        self.gh.gh("issue", "create", response="Creating issue\nnot-a-url\n")
        with self.assertRaises(PdlcError):
            self.backend.create("t", "b", "s")

    def test_create_rejects_an_unparsed_work_type_before_host_io(self) -> None:
        calls_before = len(self.gh.calls)
        with self.assertRaisesRegex(TypeError, "work_type must be a WorkType"):
            self.backend.create("t", "b", "s", "feature")  # type: ignore[arg-type]
        self.assertEqual(len(self.gh.calls), calls_before)

    def test_create_rejects_an_unavailable_work_type_before_host_io(self) -> None:
        calls_before = len(self.gh.calls)
        with self.assertRaisesRegex(PdlcError, "GitHub creation is unavailable for work type: bug"):
            self.backend.create("t", "b", "s", WorkType.BUG)
        self.assertEqual(len(self.gh.calls), calls_before)

    def test_close_task_closes_the_sub_issue(self) -> None:
        self.gh.gh("issue", "close", response="")
        self.backend.close_task("11")
        self.assertTrue(any(call[0][:2] == ["issue", "close"] for call in self.gh.calls))


class CodeHostTest(GitHubHostTest):
    def setUp(self) -> None:
        super().setUp()
        self.host = GitHubCodeHost()

    def test_pull_requests_by_number_fails_closed_on_unknown(self) -> None:
        def view(args, _input):
            number = int(args[2])
            if number == 9:
                raise PdlcError("no pull requests found")
            return {
                "number": number, "title": "impl", "url": f"u{number}", "state": "OPEN",
                "isDraft": False, "headRefName": "feat", "mergedAt": None,
                "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}],
            }

        self.gh.route(lambda args, _input: args[:2] == ["pr", "view"], view)

        with self.assertRaisesRegex(PdlcError, "registered pull request #9"):
            self.host.pull_requests_by_number([5, 9, 4])

    def test_checks_state_handles_check_runs_and_status_contexts(self) -> None:
        from pdlc.hosts.lib.github.code_host import _checks_state
        self.assertEqual(_checks_state({"statusCheckRollup": []}), "NONE")
        self.assertEqual(_checks_state({"statusCheckRollup": [{"status": "IN_PROGRESS", "conclusion": None}]}), "PENDING")
        self.assertEqual(_checks_state({"statusCheckRollup": [{"state": "SUCCESS"}]}), "SUCCESS")
        self.assertEqual(_checks_state({"statusCheckRollup": [{"status": "COMPLETED", "conclusion": "FAILURE"}]}), "FAILURE")

    def test_checks_state_aggregates_failures_independent_of_rollup_order(self) -> None:
        from pdlc.hosts.lib.github.code_host import _checks_state
        success = {"status": "COMPLETED", "conclusion": "SUCCESS"}
        failure = {"status": "COMPLETED", "conclusion": "ACTION_REQUIRED"}
        self.assertEqual(_checks_state({"statusCheckRollup": [success, failure]}), "FAILURE")
        self.assertEqual(_checks_state({"statusCheckRollup": [failure, success]}), "FAILURE")

    def test_checks_state_reports_mixed_success_and_running_as_pending(self) -> None:
        from pdlc.hosts.lib.github.code_host import _checks_state
        self.assertEqual(_checks_state({"statusCheckRollup": [
            {"status": "COMPLETED", "conclusion": "SUCCESS"},
            {"status": "IN_PROGRESS", "conclusion": None},
        ]}), "PENDING")

    def test_checks_state_accepts_neutral_and_skipped_conclusions(self) -> None:
        from pdlc.hosts.lib.github.code_host import _checks_state
        self.assertEqual(_checks_state({"statusCheckRollup": [
            {"status": "COMPLETED", "conclusion": "NEUTRAL"},
            {"status": "COMPLETED", "conclusion": "SKIPPED"},
        ]}), "SUCCESS")

    def test_checks_state_treats_queued_waiting_and_null_conclusions_as_pending(self) -> None:
        from pdlc.hosts.lib.github.code_host import _checks_state
        for entry in (
            {"status": "QUEUED", "conclusion": None},
            {"status": "WAITING", "conclusion": None},
            {"status": "COMPLETED", "conclusion": None},
        ):
            with self.subTest(entry=entry):
                self.assertEqual(_checks_state({"statusCheckRollup": [entry]}), "PENDING")

    def test_checks_state_fails_closed_for_unknown_or_malformed_nonempty_rollups(self) -> None:
        from pdlc.hosts.lib.github.code_host import _checks_state
        for rollup in ([{"state": "MYSTERY"}], [{}], [None], {"state": "SUCCESS"}, "unexpected"):
            with self.subTest(rollup=rollup):
                self.assertEqual(_checks_state({"statusCheckRollup": rollup}), "PENDING")

    def test_pull_requests_by_number_reraises_transient_failure(self) -> None:
        def view(args, _input):
            raise PdlcError("HTTP 401: Bad credentials")

        self.gh.route(lambda args, _input: args[:2] == ["pr", "view"], view)

        with self.assertRaises(PdlcError) as caught:
            self.host.pull_requests_by_number([5])
        self.assertIn("#5", str(caught.exception))

    def test_pull_request_files_lists_changed_paths(self) -> None:
        self.gh.gh(
            "pr", "view",
            response={"files": [{"path": "a.py"}, {"path": "b.md"}]},
        )
        self.assertEqual(self.host.pull_request_files(7), ["a.py", "b.md"])

    def test_ensure_pull_request_linked_returns_the_current_branch_pr_without_editing(self) -> None:
        self.gh.gh(
            "pr", "view",
            response={
                "number": 5, "title": "impl", "url": "u5", "state": "OPEN",
                "isDraft": False, "headRefName": "feat", "mergedAt": None,
                "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}],
            },
        )

        linked = self.host.ensure_pull_request_linked("3")

        self.assertEqual(linked["number"], 5)
        self.assertEqual(linked["branch"], "feat")
        self.assertNotIn("relation", linked)
        self.assertFalse(any(call[0][:2] == ["pr", "edit"] for call in self.gh.calls))
        # The branch fallback must not pass `--repo`; gh (>=2.98) rejects that combination.
        view = next(call[0] for call in self.gh.calls if call[0][:2] == ["pr", "view"])
        self.assertNotIn("--repo", view)


if __name__ == "__main__":
    unittest.main()

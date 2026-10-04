"""Stacked task pull requests: the stack entry point PDLC resolves from its own
registry, the GitHub host's delegation to `gh stack`, and task checkpointing."""

import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from _gh_replay import GitHubHostTest, pull_request_node, pull_requests_graphql
from _support import FileBackendTest

from pdlc.domain.lifecycle import PdlcError
from pdlc.config import Config, install_config, reset_config
from pdlc.domain.records import PullRef
from pdlc.hosts.lib.github.code_host import GitHubCodeHost
from pdlc.internal.stack import stack_entry_pr, stack_pr, task_branch_name


class StackEntryPointTests(unittest.TestCase):
    """PDLC resolves one fact for the stack — where to enter it — from the PR
    registry. `gh stack` owns everything else."""

    def setUp(self):
        install_config(Config(tracker_provider="file", code_provider="file"))
        self.addCleanup(reset_config)

    def _task(self, number, task_id, *, implemented=False, prs=()):
        return {
            "number": number, "taskId": task_id,
            "hasImplementation": implemented,
            "prs": [pr if isinstance(pr, PullRef) else PullRef(pr) for pr in prs],
        }

    def test_a_pull_request_in_another_repository_never_enters_the_stack(self):
        # `gh stack` acts on this checkout only, so a higher-numbered PR
        # registered from another repository is not the entry point.
        delivery = [
            self._task(1, "TASK-001", implemented=True, prs=[40, PullRef(90, "acme/web")]),
            self._task(2, "TASK-002"),
        ]
        self.assertEqual(stack_entry_pr(delivery, delivery[1]), 40)
        self.assertIsNone(stack_pr([PullRef(90, "acme/web")]))

    def test_branch_name_is_derived_from_the_task_identity(self):
        self.assertEqual(task_branch_name("record-9", "TASK-003"), "pdlc/record-9/task-003")

    def test_entry_is_the_previous_implemented_tasks_pull_request(self):
        delivery = [
            self._task(1, "TASK-001", implemented=True, prs=[40]),
            self._task(2, "TASK-002"),
        ]
        self.assertEqual(stack_entry_pr(delivery, delivery[1]), 40)

    def test_first_task_has_no_entry_point(self):
        delivery = [self._task(1, "TASK-001"), self._task(2, "TASK-002")]
        self.assertIsNone(stack_entry_pr(delivery, delivery[0]))

    def test_rerunning_an_earlier_task_enters_below_it_not_above(self):
        # TASK-003 is already implemented; the driver re-runs TASK-002. The entry
        # point must be TASK-001's PR — entering at TASK-003 would put the
        # re-run on top of an already-reviewed PR.
        delivery = [
            self._task(1, "TASK-001", implemented=True, prs=[40]),
            self._task(2, "TASK-002", implemented=True, prs=[41]),
            self._task(3, "TASK-003", implemented=True, prs=[42]),
        ]
        self.assertEqual(stack_entry_pr(delivery, delivery[1]), 40)

    def test_an_implemented_task_without_a_registered_pr_is_not_an_entry_point(self):
        delivery = [
            self._task(1, "TASK-001", implemented=True),
            self._task(2, "TASK-002"),
        ]
        self.assertIsNone(stack_entry_pr(delivery, delivery[1]))

    def test_ignores_entries_without_a_task_identity(self):
        delivery = [
            {"number": 1, "taskId": None, "hasImplementation": True, "prs": [PullRef(40)]},
            self._task(2, "TASK-002"),
        ]
        self.assertIsNone(stack_entry_pr(delivery, delivery[1]))


class GitHubStackSubmitTests(GitHubHostTest):
    """The host runs `gh stack` and reads it back; it never derives stack shape."""

    def setUp(self):
        super().setUp()
        self.host = GitHubCodeHost()

    def _stub_stack(self, *numbers, merged=(), rebase="", without_pr=()):
        branches = [{"name": f"pdlc/record-9/task-{n:03d}"} for n in numbers]
        for branch, number in zip(branches, numbers):
            if number not in without_pr:
                branch["pr"] = {"number": number, "state": "OPEN"}
        self.gh.gh("extension", "list", response="gh\tgithub/gh-stack\tv0.1.0\n")
        self.gh.gh("stack", "sync", response="")
        self.gh.gh("stack", "rebase", "--abort", response="")
        self.gh.gh("stack", "rebase", response=rebase)
        self.gh.gh("stack", "submit", response="")
        self.gh.gh("stack", "view", response={
            "trunk": "main",
            "branches": branches,
        })

        self.gh.graphql("pullRequest(number:", pull_requests_graphql(lambda number: pull_request_node(
            number, contexts=[{"state": "SUCCESS"}], isDraft=True,
            headRefName=f"pdlc/record-9/task-{number:03d}",
            state="MERGED" if number in merged else "OPEN",
        )))

    def _call(self, *prefix):
        return next(args for args, _ in self.gh.calls if args[: len(prefix)] == list(prefix))

    def _calls(self, *prefix):
        return [args for args, _ in self.gh.calls if args[: len(prefix)] == list(prefix)]

    def test_submit_restacks_without_trunk_submits_then_returns_the_stack_bottom_to_top(self):
        self._stub_stack(1, 2)

        with patch("pdlc.hosts.lib.github.code_host.run_gh", wraps=self.gh) as run_gh:
            prs = self.host.submit_task_stack()

        self.assertEqual([pr["number"] for pr in prs], [1, 2])
        self.assertEqual(
            [pr["branch"] for pr in prs],
            ["pdlc/record-9/task-001", "pdlc/record-9/task-002"],
        )
        # Nothing landed, so new trunk commits stay out: branches are only
        # rebased onto each other, never fetched or synced with trunk.
        self.assertEqual(self._calls("stack", "rebase"), [["stack", "rebase", "--no-trunk"]])
        self.assertEqual(self._calls("stack", "sync"), [])
        self.assertEqual(self._call("stack", "submit"), ["stack", "submit", "--auto"])
        submit_call = next(call for call in run_gh.call_args_list if call.args[0][:2] == ["stack", "submit"])
        self.assertEqual(submit_call.kwargs, {"timeout": 360})
        self.assertFalse(any("branches" in " ".join(args) for args, _ in self.gh.calls if args[0] == "api"))
        # The merge check and the read-back are one query each, check rollup included.
        pr_reads = [args for args, _ in self.gh.calls if "pullRequest(number:" in " ".join(args)]
        self.assertEqual(len(pr_reads), 2)
        self.assertIn("statusCheckRollup", " ".join(pr_reads[-1]))
        self.assertEqual([pr["checks"] for pr in prs], ["SUCCESS", "SUCCESS"])

    def test_submit_counts_branches_without_pull_requests(self):
        self._stub_stack(1, 2, 3, without_pr={3})

        with patch("pdlc.hosts.lib.github.code_host.run_gh", wraps=self.gh) as run_gh:
            self.host.submit_task_stack()

        submit_call = next(call for call in run_gh.call_args_list if call.args[0][:2] == ["stack", "submit"])
        self.assertEqual(submit_call.kwargs, {"timeout": 540})

    def test_single_branch_submit_gets_three_minutes(self):
        self._stub_stack(1)

        with patch("pdlc.hosts.lib.github.code_host.run_gh", wraps=self.gh) as run_gh:
            self.host.submit_task_stack()

        submit_call = next(call for call in run_gh.call_args_list if call.args[0][:2] == ["stack", "submit"])
        self.assertEqual(submit_call.kwargs, {"timeout": 180})

    def test_empty_stack_does_not_submit_with_zero_timeout(self):
        self._stub_stack()

        with self.assertRaisesRegex(PdlcError, "no branches to submit"):
            self.host.submit_task_stack()

        self.assertEqual(self._calls("stack", "submit"), [])

    def test_a_landed_branch_still_local_syncs_and_prunes_instead(self):
        self._stub_stack(1, 2, merged={1})

        with patch("pdlc.hosts.lib.github.code_host._local_branch_exists", return_value=True):
            self.host.submit_task_stack()

        # `gh stack sync --prune` drops the landed commits and branch; PDLC never
        # lists remote branches to work that out itself.
        self.assertEqual(self._calls("stack", "sync"), [["stack", "sync", "--prune"]])
        self.assertEqual(self._calls("stack", "rebase"), [])

    def test_a_landed_branch_already_pruned_stays_off_trunk(self):
        self._stub_stack(1, 2, merged={1})

        with patch("pdlc.hosts.lib.github.code_host._local_branch_exists", return_value=False):
            self.host.submit_task_stack()

        self.assertEqual(self._calls("stack", "sync"), [])
        self.assertEqual(self._calls("stack", "rebase"), [["stack", "rebase", "--no-trunk"]])

    def test_a_restack_conflict_aborts_and_submits_nothing(self):
        self._stub_stack(1, 2, rebase=PdlcError("conflict in pdlc/record-9/task-002"))

        with self.assertRaisesRegex(PdlcError, "conflict"):
            self.host.submit_task_stack()

        self.assertEqual(self._calls("stack", "rebase", "--abort"), [["stack", "rebase", "--abort"]])
        self.assertEqual(self._calls("stack", "submit"), [])

    def test_no_repository_default_branch_lookup_is_needed(self):
        # `gh stack` resolves the trunk itself; nothing here asks GitHub for it.
        self._stub_stack(1)
        self.host.submit_task_stack()
        self.assertFalse(any(args[:2] == ["repo", "view"] for args, _ in self.gh.calls))

    def test_stack_pr_refs_reads_only_branch_pr_numbers(self):
        self.gh.gh("stack", "view", response={
            "trunk": "main",
            "currentBranch": "pdlc/record-9/task-002",
            "branches": [
                {"name": "pdlc/record-9/task-001", "isMerged": True, "pr": {"number": 40, "state": "MERGED"}},
                {"name": "pdlc/record-9/task-002", "pr": {"number": 41, "state": "OPEN"}},
                {"name": "pdlc/record-9/task-003"},
            ],
        })
        # A branch with no PR yet is simply absent from the numbers.
        self.assertEqual(self.host.stack_pr_refs(), [PullRef(40, "wsimf/pdlc"), PullRef(41, "wsimf/pdlc")])

    def test_set_pull_request_content_overwrites_title_and_body(self):
        captured: list[tuple[list[str], str]] = []

        def edit(args, _input):
            captured.append((args, Path(args[args.index("--body-file") + 1]).read_text(encoding="utf-8")))
            return ""

        self.gh.route(lambda args, _input: args[:2] == ["pr", "edit"], edit)

        self.host.set_pull_request_content(PullRef(148, "wsimf/pdlc"), "[CORE] Persist geometry", "## Implementation\n\nShipped.\n")

        args, body = captured[0]
        self.assertEqual(args[:3], ["pr", "edit", "148"])
        self.assertIn("--repo", args)
        self.assertEqual(args[args.index("--title") + 1], "[CORE] Persist geometry")
        self.assertEqual(body, "## Implementation\n\nShipped.\n")

    def test_pull_request_calls_name_the_code_repository_not_the_tracker(self):
        # A service repository's pull requests stay in its own repository even
        # when its work items live in a shared tracker.
        self.configure(tracker_repository="acme/product", code_repository="acme/svc-a")
        seen: list[list[str]] = []
        self.gh.route(
            lambda args, _input: args[:2] == ["pr", "ready"],
            lambda args, _input: (seen.append(args), "")[1],
        )

        self.host.mark_pull_requests_ready([PullRef(148, "acme/svc-a")])

        self.assertEqual(seen[0][seen[0].index("--repo") + 1], "acme/svc-a")

    def test_mark_pull_requests_ready_takes_each_number_out_of_draft(self):
        seen: list[list[str]] = []
        self.gh.route(
            lambda args, _input: args[:2] == ["pr", "ready"],
            lambda args, _input: (seen.append(args), "")[1],
        )

        self.host.mark_pull_requests_ready([PullRef(148, "wsimf/pdlc"), PullRef(149, "acme/web")])

        self.assertEqual([args[:3] for args in seen], [["pr", "ready", "148"], ["pr", "ready", "149"]])
        self.assertEqual([args[args.index("--repo") + 1] for args in seen], ["wsimf/pdlc", "acme/web"])

    def test_mark_pull_requests_ready_with_no_numbers_calls_gh_nothing(self):
        self.host.mark_pull_requests_ready([])
        self.assertFalse(any(args[:2] == ["pr", "ready"] for args, _ in self.gh.calls))

    def test_missing_extension_is_a_clear_error(self):
        self.gh.gh("extension", "list", response="gh\tsome/other\tv1\n")
        with self.assertRaises(PdlcError) as caught:
            self.host.submit_task_stack()
        self.assertIn("gh extension install github/gh-stack", str(caught.exception))
        self.assertFalse(any(args[0] == "stack" for args, _ in self.gh.calls))

    def test_link_renames_the_current_branch_then_links_it_onto_the_entry_pr(self):
        # `git branch -m` never runs against the live repo in tests: it is
        # patched out here, just like `run_gh` is faked for every `gh` call.
        self.gh.gh("extension", "list", response="gh\tgithub/gh-stack\tv0.1.0\n")
        linked: list[list[str]] = []
        self.gh.route(
            lambda args, _input: args[:2] == ["stack", "link"],
            lambda args, _input: (linked.append(args), "")[1],
        )
        self.gh.gh("pr", "view", response={
            "number": 148, "title": "stack link", "url": "u148", "state": "OPEN",
            "isDraft": True, "headRefName": "pdlc/record-60/task-001", "mergedAt": None,
            "statusCheckRollup": [],
        })

        renamed: list[list[str]] = []
        with patch(
            "pdlc.hosts.lib.github.code_host.run_process",
            side_effect=lambda args, **kw: (renamed.append(list(args)), "")[1],
        ):
            pr = self.host.link_task_stack(30, "pdlc/record-60/task-001")

        self.assertEqual(renamed, [["git", "branch", "-m", "pdlc/record-60/task-001"]])
        self.assertEqual(linked, [["stack", "link", "30", "pdlc/record-60/task-001"]])
        self.assertEqual(pr["number"], 148)
        self.assertEqual(pr["branch"], "pdlc/record-60/task-001")
        view = next(args for args, _ in self.gh.calls if args[:2] == ["pr", "view"])
        self.assertEqual(view[2], "pdlc/record-60/task-001")

    def test_link_requires_the_stack_extension(self):
        self.gh.gh("extension", "list", response="gh\tsome/other\tv1\n")
        with self.assertRaises(PdlcError) as caught:
            self.host.link_task_stack(30, "pdlc/record-60/task-001")
        self.assertIn("gh extension install github/gh-stack", str(caught.exception))
        self.assertFalse(any(args[0] == "stack" for args, _ in self.gh.calls))


class ImplementTaskStackTests(FileBackendTest):
    """`pdlc post implement-task` always submits and registers the task PR."""

    def _seed(self):
        self.seed_record(70, "Implementation", "Pending", slug="record-70")
        self.seed_task(70, 701, "TASK-001", "OPEN", "WORK-70-TASK-001 [CORE] Core")
        task_dir = self.records_dir() / "70" / "tasks" / "701"
        (task_dir / "comments.jsonl").write_text(json.dumps({"body": "## Technical Plan\n\nImplement the core behavior.\n"}) + "\n")

    def test_off_template_summary_is_refused_with_every_problem_and_the_template(self):
        self._seed()
        before = self.task_comments_text(70, 701)
        host = Mock()
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=host):
            result = self.invoke("post_implement_task", 701, self.evidence_file("### What\n\n- <the result>\n\n### Anything else\n\n### Testing\n"))
        self.assertEqual(result.code, 1)
        self.assertIn("- no content under: ### What", result.stderr)
        self.assertIn("- missing section: ### Why", result.stderr)
        self.assertIn("- missing section: ### How", result.stderr)
        self.assertIn("- no content under: ### Testing", result.stderr)
        self.assertIn("- no content under: ### Anything else (fill it in or drop the heading)", result.stderr)
        self.assertIn("# Implementation summary", result.stderr)
        host.submit_task_stack.assert_not_called()
        self.assertEqual(self.task_comments_text(70, 701), before)
        self.assertEqual(self.task_meta(70, 701)["state"], "OPEN")

    def _assert_rejected_before_stack(self, *, status="Implementation", gate="Pending", work_type=None, skipped="", body=None):
        if not (self.records_dir() / "70").exists():
            self.seed_record(70, status, gate, slug="record-70", work_type=work_type, skipped=skipped, body=body)
            self.seed_task(70, 701, "TASK-001", "OPEN", "WORK-70-TASK-001 [CORE] Core")
        else:
            metadata = self.meta(70)
            metadata["fields"].update({"Status": status, "Gate State": gate, "Skipped States": skipped})
            if work_type is None:
                metadata.pop("workType", None)
            else:
                metadata["workType"] = work_type
            (self.records_dir() / "70" / "meta.json").write_text(json.dumps(metadata) + "\n")
        task_dir = self.records_dir() / "70" / "tasks" / "701"
        plan = json.dumps({"body": "## Technical Plan\n\nImplement the core behavior.\n"})
        (task_dir / "comments.jsonl").write_text(plan + "\n")
        before = self.task_comments_text(70, 701)
        host = Mock()
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=host):
            result = self.invoke("post_implement_task", 701, self.evidence_file(self.implementation_summary("Shipped it.")))
        self.assertEqual(result.code, 1)
        host.submit_task_stack.assert_not_called()
        self.assertEqual(self.task_comments_text(70, 701), before)
        self.assertEqual(self.task_meta(70, 701)["state"], "OPEN")
        return result

    def test_parent_complete_is_locked_before_stack_submission(self):
        result = self._assert_rejected_before_stack(status="Complete", gate="Approved")
        self.assertIn("Complete and locked", result.stderr)

    def test_unknown_work_type_is_rejected_before_stack_submission(self):
        result = self._assert_rejected_before_stack(work_type="unknown")
        self.assertIn("unknown work type", result.stderr)

    def test_unavailable_work_type_is_rejected_before_stack_submission(self):
        result = self._assert_rejected_before_stack(work_type="bug")
        self.assertIn("workflow unavailable", result.stderr)

    def test_malformed_parent_state_is_rejected_before_stack_submission(self):
        self.seed_record(70, "Implementation", "Pending", slug="record-70")
        self.seed_task(70, 701, "TASK-001", "OPEN", "WORK-70-TASK-001 [CORE] Core")
        task_dir = self.records_dir() / "70" / "tasks" / "701"
        before = json.dumps({"body": "## Technical Plan\n\nImplement the core behavior.\n"}) + "\n"
        task_dir.joinpath("comments.jsonl").write_text(before)
        metadata = self.records_dir() / "70" / "meta.json"
        value = json.loads(metadata.read_text())
        value["fields"]["Gate State"] = "Not A Gate"
        metadata.write_text(json.dumps(value) + "\n")
        host = Mock()
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=host):
            result = self.invoke("post_implement_task", 701, self.evidence_file(self.implementation_summary("Shipped it.")))
        self.assertEqual(self.task_comments_text(70, 701), before)
        self.assertEqual(self.task_meta(70, 701)["state"], "OPEN")
        host.submit_task_stack.assert_not_called()
        self.assertIn("invalid workflow state", result.stderr)

    def test_wrong_stage_is_rejected_before_stack_submission(self):
        result = self._assert_rejected_before_stack(status="Testing")
        self.assertIn("implementation is not active", result.stderr)

    def test_blocking_gates_are_rejected_before_stack_submission(self):
        for gate in ("Review Required", "Approval Required", "CI Pending"):
            with self.subTest(gate=gate):
                result = self._assert_rejected_before_stack(gate=gate)
                self.assertIn("implementation is not active", result.stderr)
        result = self._assert_rejected_before_stack(gate="Decision Required")
        self.assertIn("pdlc guide decisions", result.stderr)

    def test_skipped_implementation_is_rejected_before_stack_submission(self):
        result = self._assert_rejected_before_stack(skipped="Implementation")
        self.assertIn("implementation is not active", result.stderr)

    def test_missing_technical_plan_is_rejected_before_stack_submission(self):
        self.seed_record(70, "Implementation", "Pending", slug="record-70")
        self.seed_task(70, 701, "TASK-001", "OPEN", "WORK-70-TASK-001 [CORE] Core")
        task_dir = self.records_dir() / "70" / "tasks" / "701"
        before = task_dir.joinpath("comments.jsonl").read_text()
        host = Mock()
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=host):
            result = self.invoke("post_implement_task", 701, self.evidence_file(self.implementation_summary("Shipped it.")))
        self.assertEqual(result.code, 1)
        self.assertIn("has no Technical Plan", result.stderr)
        host.submit_task_stack.assert_not_called()
        self.assertEqual(task_dir.joinpath("comments.jsonl").read_text(), before)
        self.assertEqual(self.task_meta(70, 701)["state"], "OPEN")

    def test_after_first_task_links_instead_of_submitting(self):
        # A worktree's first task prepared with `pdlc prepare --after` has no
        # local `gh stack` tracking to sync/submit: the predecessor's branch
        # may be checked out in the predecessor's own, still-active worktree.
        self._seed()
        self.seed_record(50, "Implementation", "Pending", slug="record-50")
        self.seed_task(50, 501, "TASK-001", "CLOSED", "WORK-50-TASK-001 [CORE] Base")
        task_dir = self.records_dir() / "50" / "tasks" / "501"
        task_dir.joinpath("comments.jsonl").write_text(
            json.dumps({"body": "## Implementation\n\nShipped.\n"}) + "\n"
        )
        self.register_prs(501, [29])

        host = Mock()
        host.link_task_stack.return_value = {"number": 148, "repository": "", "branch": "pdlc/record-70/task-001"}
        with (
            patch("pdlc.commands.post_implement_task.get_code_host", return_value=host),
            patch("pdlc.internal.stack.worktree_after", return_value="50"),
        ):
            result = self.invoke("post_implement_task", 701, self.evidence_file(self.implementation_summary("Shipped it.")))

        self.assertEqual(result.code, 0, result.stderr)
        host.link_task_stack.assert_called_once_with(29, "pdlc/record-70/task-001")
        host.submit_task_stack.assert_not_called()
        self.assertEqual(result.json["taskPr"]["number"], 148)

    def test_changes_required_remains_eligible(self):
        self._seed()
        metadata = self.meta(70)
        metadata["fields"]["Gate State"] = "Changes Required"
        (self.records_dir() / "70" / "meta.json").write_text(json.dumps(metadata) + "\n")
        host = Mock()
        host.submit_task_stack.return_value = [{"number": 148, "repository": "", "branch": "pdlc/record-70/task-001"}]
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=host):
            result = self.invoke("post_implement_task", 701, self.evidence_file(self.implementation_summary("Shipped it.")))
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["taskPr"]["number"], 148)

    def test_existing_implementation_evidence_can_be_retried_and_closed(self):
        self._seed()
        task_dir = self.records_dir() / "70" / "tasks" / "701"
        prior = (
            json.dumps({"body": "## Implementation\n\nPrior attempt.\n"}) + "\n"
            + json.dumps({"body": "## Technical Plan\n\nImplement the core behavior.\n"}) + "\n"
        )
        task_dir.joinpath("comments.jsonl").write_text(prior)
        host = Mock()
        host.submit_task_stack.side_effect = [
            PdlcError("stack submission failed"),
            [{"number": 148, "repository": "", "branch": "pdlc/record-70/task-001"}],
        ]
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=host):
            failed = self.invoke("post_implement_task", 701, self.evidence_file(self.implementation_summary("Retry failed.")))
            self.assertEqual(failed.code, 1)
            self.assertEqual(self.task_comments_text(70, 701), prior)
            self.assertEqual(self.task_meta(70, 701)["state"], "OPEN")
            result = self.invoke("post_implement_task", 701, self.evidence_file(self.implementation_summary("Retry succeeded.")))
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(self.task_meta(70, 701)["state"], "CLOSED")

    def _implementation_comments(self) -> list[dict]:
        lines = self.task_comments_text(70, 701).splitlines()
        return [c for c in map(json.loads, filter(None, lines)) if c["body"].startswith("## Implementation")]

    def test_relanding_a_closed_task_edits_its_implementation_comment_in_place(self):
        self._seed()
        host = Mock()
        host.submit_task_stack.return_value = [{"number": 148, "repository": "", "branch": "pdlc/record-70/task-001", "checks": "PENDING"}]
        host.unresolved_review_comments.return_value = []
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=host):
            first = self.invoke("post_implement_task", 701, self.evidence_file(self.implementation_summary("Shipped it.")))
            self.assertEqual(first.code, 0, first.stderr)
            self.assertEqual(json.loads(first.stdout)["mode"], "implement")
            self.assertNotIn("relanded", json.loads(first.stdout))
            original = self._implementation_comments()
            metadata = self.meta(70)
            metadata["fields"]["Gate State"] = "Changes Required"
            (self.records_dir() / "70" / "meta.json").write_text(json.dumps(metadata) + "\n")
            second = self.invoke("post_implement_task", 701, self.evidence_file(self.implementation_summary("Shipped it, with the review fix.")))
        self.assertEqual(second.code, 0, second.stderr)
        comments = self._implementation_comments()
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["url"], original[0]["url"])
        self.assertIn("with the review fix", comments[0]["body"])
        self.assertEqual(self.task_meta(70, 701)["state"], "CLOSED")
        payload = json.loads(second.stdout)
        self.assertEqual(payload["mode"], "rework")
        self.assertTrue(payload["relanded"])
        self.assertTrue(payload["closed"])
        self.assertEqual(payload["openThreads"], 0)
        self.assertEqual(payload["checks"], "pending")
        host.unresolved_review_comments.assert_called_once_with(PullRef(148))

    def test_an_open_task_closes_without_a_flag(self):
        # Closing is decided by the task's state, with no flag to ask for it.
        self._seed()
        host = Mock()
        host.submit_task_stack.return_value = [{"number": 148, "repository": "", "branch": "pdlc/record-70/task-001"}]
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=host):
            result = self.invoke("post_implement_task", 701, self.evidence_file(self.implementation_summary("Shipped it.")))
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(self.task_meta(70, 701)["state"], "CLOSED")
        host.unresolved_review_comments.assert_not_called()

    def test_relanding_retires_older_duplicate_implementation_comments(self):
        self._seed()
        task_dir = self.records_dir() / "70" / "tasks" / "701"
        comments = [
            {"body": "## Technical Plan\n\nImplement the core behavior.\n", "url": "t#comment-1"},
            {"body": "## Implementation\n\nFirst attempt.\n", "url": "t#comment-2"},
            {"body": "## Implementation\n\nSecond attempt.\n", "url": "t#comment-3"},
        ]
        task_dir.joinpath("comments.jsonl").write_text("".join(json.dumps(c) + "\n" for c in comments))
        host = Mock()
        host.submit_task_stack.return_value = [{"number": 148, "repository": "", "branch": "pdlc/record-70/task-001"}]
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=host):
            result = self.invoke("post_implement_task", 701, self.evidence_file(self.implementation_summary("Final.")))
        self.assertEqual(result.code, 0, result.stderr)
        remaining = self._implementation_comments()
        self.assertEqual([c["url"] for c in remaining], ["t#comment-3"])
        self.assertIn("Final.", remaining[0]["body"])
        self.assertIn("## Technical Plan", self.task_comments_text(70, 701))

    def test_submits_and_registers_the_task_pr(self):
        self._seed()
        host = Mock()
        host.submit_task_stack.return_value = [{
            "number": 148,
            "repository": "",
            "branch": "pdlc/record-70/task-001",
            "title": "Core",
            "url": "u148",
        }]
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=host):
            result = self.invoke("post_implement_task", 701, self.write_file("impl.md", self.implementation_summary("Shipped it.")))
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["taskPr"]["number"], 148)
        self.assertEqual(result.json["prs"], [148])
        host.submit_task_stack.assert_called_once_with()

    def test_sets_the_pr_title_and_body_from_the_task_and_evidence(self):
        self._seed()
        host = Mock()
        host.submit_task_stack.return_value = [{
            "number": 148, "repository": "", "branch": "pdlc/record-70/task-001", "title": "auto", "url": "u148",
        }]
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=host):
            result = self.invoke("post_implement_task", 701, self.write_file("impl.md", self.implementation_summary("Shipped it.")))
        self.assertEqual(result.code, 0, result.stderr)
        # The `[CORE]`/`[UI]` tag is stripped from the PR title unconditionally.
        host.set_pull_request_content.assert_called_once_with(
            PullRef(148), "Core", "## Implementation\n\n" + self.implementation_summary("Shipped it.").strip()
        )

    def test_pr_title_format_config_resolves_placeholders(self):
        self._seed()
        host = Mock()
        host.submit_task_stack.return_value = [{
            "number": 148, "repository": "", "branch": "pdlc/record-70/task-001", "title": "auto", "url": "u148",
        }]
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=host), \
                patch(
                    "pdlc.commands.post_implement_task.get_config",
                    return_value=Config(pr_title_format="[{work.type} {work.number}] {task.title} ({task.id})"),
                ):
            result = self.invoke("post_implement_task", 701, self.write_file("impl.md", self.implementation_summary("Shipped it.")))
        self.assertEqual(result.code, 0, result.stderr)
        host.set_pull_request_content.assert_called_once_with(
            PullRef(148), "[feature 70] Core (TASK-001)", "## Implementation\n\n" + self.implementation_summary("Shipped it.").strip()
        )

    def test_pr_attachment_config_appends_a_line_with_the_bare_work_number(self):
        self._seed()
        host = Mock()
        host.submit_task_stack.return_value = [{
            "number": 148, "repository": "", "branch": "pdlc/record-70/task-001", "title": "auto", "url": "u148",
        }]
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=host), \
                patch(
                    "pdlc.commands.post_implement_task.get_config",
                    return_value=Config(pr_attachment="Fixes {work.number} / see {work.number}"),
                ):
            result = self.invoke("post_implement_task", 701, self.write_file("impl.md", self.implementation_summary("Shipped it.")))
        self.assertEqual(result.code, 0, result.stderr)
        # The attachment is the first line of the PR body, every `{work.number}`
        # resolved to the parent's bare number; the `## Implementation` comment
        # on the task never carries it.
        host.set_pull_request_content.assert_called_once_with(
            PullRef(148), "Core", "Fixes 70 / see 70\n\n## Implementation\n\n" + self.implementation_summary("Shipped it.").strip()
        )
        self.assertNotIn("Fixes 70", self.task_comments_text(70, 701))

    def _checkpoint_pr(self, config: Config) -> tuple[str, str]:
        """The title and body a checkpoint gives the task PR under ``config``,
        with `{work.ref}` in both the title format and the attachment."""
        self._seed()
        host = Mock()
        host.submit_task_stack.return_value = [{
            "number": 148, "repository": "", "branch": "pdlc/record-70/task-001", "title": "auto", "url": "u148",
        }]
        config = replace(config, pr_attachment="Part of {work.ref}", pr_title_format="{task.title} ({work.ref})")
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=host), \
                patch("pdlc.commands.post_implement_task.get_config", return_value=config):
            result = self.invoke("post_implement_task", 701, self.write_file("impl.md", self.implementation_summary("Shipped it.")))
        self.assertEqual(result.code, 0, result.stderr)
        _, title, body = host.set_pull_request_content.call_args.args
        return title, body.split("\n\n", 1)[0]

    def test_work_ref_is_bare_when_issues_and_prs_share_a_repository(self):
        config = Config(tracker_repository="acme/widgets", code_repository="Acme/Widgets")
        self.assertEqual(self._checkpoint_pr(config), ("Core (#70)", "Part of #70"))

    def test_work_ref_is_qualified_for_a_shared_tracker_repository(self):
        config = Config(tracker_repository="acme/product", code_repository="acme/svc-a")
        self.assertEqual(self._checkpoint_pr(config), ("Core (acme/product#70)", "Part of acme/product#70"))

    def test_work_ref_uses_azure_boards_link_syntax(self):
        config = Config(tracker_provider="azure", code_repository="acme/svc-a")
        self.assertEqual(self._checkpoint_pr(config), ("Core (AB#70)", "Part of AB#70"))

    def test_pr_content_failure_leaves_the_task_rerunnable(self):
        self._seed()
        before = self.task_comments_text(70, 701)
        host = Mock()
        host.submit_task_stack.return_value = [{"number": 148, "repository": "", "branch": "pdlc/record-70/task-001"}]
        host.set_pull_request_content.side_effect = PdlcError("gh pr edit failed")
        with patch("pdlc.commands.post_implement_task.get_code_host", return_value=host):
            result = self.invoke("post_implement_task", 701, self.write_file("impl.md", self.implementation_summary("Shipped it.")))
        self.assertEqual(result.code, 1)
        self.assertIn("gh pr edit failed", result.stderr)
        self.assertEqual(self.task_comments_text(70, 701), before)
        self.assertEqual(self.task_meta(70, 701)["state"], "OPEN")

    def test_file_backend_reports_no_stack_support_without_mutating_the_task(self):
        self._seed()
        before = self.task_comments_text(70, 701)
        result = self.invoke("post_implement_task", 701, self.write_file("impl.md", self.implementation_summary("Shipped it.")))
        self.assertEqual(result.code, 1)
        self.assertIn("cannot submit stacked pull requests", result.stderr)
        self.assertEqual(self.task_meta(70, 701)["state"], "OPEN")
        self.assertEqual(self.task_comments_text(70, 701), before)


class PublishMarksTheStackReadyTests(FileBackendTest):
    """`pdlc post implement` takes the whole registered task PR stack out of
    draft when the last delivery task is closed."""

    def _pr(self, number: int, state: str, *, is_draft: bool) -> dict:
        return {
            "number": number, "repository": "", "title": f"Task {number}", "url": f"https://x/{number}",
            "state": state, "isDraft": is_draft, "branch": f"pdlc/record-70/task-{number:03d}",
            "mergedAt": "2026-01-01T00:00:00Z" if state == "MERGED" else None, "checks": "SUCCESS",
        }

    def setUp(self) -> None:
        super().setUp()
        # The top-of-stack checkout needs a real stack host and a clean tree;
        # record what it was handed instead.
        patcher = patch("pdlc.commands.post_implement.check_out", return_value="checked out")
        self.check_out = patcher.start()
        self.addCleanup(patcher.stop)

    def _host(self, prs: list[dict]) -> Mock:
        host = Mock()
        by_ref = {PullRef(pr["number"]): pr for pr in prs}
        host.pull_requests.side_effect = lambda refs: [by_ref[ref] for ref in refs]
        return host

    def test_only_open_registered_prs_are_marked_ready(self):
        self.seed_record(70, "Implementation", "Pending", slug="record-70")
        self.seed_task(70, 701, "TASK-001", "CLOSED", "WORK-70-TASK-001 [CORE] Core")
        self.register_prs(701, [147, 148, 149])
        evidence = self.evidence_file("implemented from file\n")
        host = self._host([
            self._pr(147, "MERGED", is_draft=False),
            self._pr(148, "OPEN", is_draft=True),
            self._pr(149, "OPEN", is_draft=True),
        ])

        with patch("pdlc.commands.post_implement.get_code_host", return_value=host), \
             patch("pdlc.internal.pull_requests.get_code_host", return_value=host):
            result = self.invoke("post_implement", 70, evidence)

        self.assertEqual(result.code, 0, result.stderr)
        host.submit_task_stack.assert_called_once_with()
        host.mark_pull_requests_ready.assert_called_once_with([PullRef(148), PullRef(149)])
        self.assertEqual(self.state(70), ("Implementation", "Review Required"))
        # The record's pull requests come from the registry its tasks carry, so
        # nothing is resolved from whichever branch of the stack is checked out
        # — publishing right after a fix on a lower task must not register that
        # task's pull request as the stage's.
        host.ensure_pull_request_linked.assert_not_called()
        self.assertEqual(
            result.json["readyPullRequests"],
            [{"number": 148, "url": "https://x/148"}, {"number": 149, "url": "https://x/149"}],
        )
        # Publishing leaves the tree on the top task's branch for Testing.
        self.assertEqual(self.check_out.call_args.args[0].branch, "pdlc/record-70/task-001")
        self.assertEqual(result.json["checkedOut"], "pdlc/record-70/task-001")
        self.assertEqual(
            json.loads(self.comments_text(70))["body"],
            "PDLC-IMPLEMENTATION\n\nimplemented from file\n",
        )

    def test_missing_evidence_fails_before_publishing_the_stack(self):
        self.seed_record(70, "Implementation", "Pending", slug="record-70")
        self.seed_task(70, 701, "TASK-001", "CLOSED", "WORK-70-TASK-001 [CORE] Core")
        self.register_prs(701, [148])
        host = self._host([self._pr(148, "OPEN", is_draft=True)])
        missing = self.work / "missing-evidence.md"

        with patch("pdlc.commands.post_implement.get_code_host", return_value=host), \
             patch("pdlc.internal.pull_requests.get_code_host", return_value=host):
            result = self.invoke("post_implement", 70, missing)

        self.assertEqual(result.code, 1)
        self.assertIn(f"evidence does not exist: {missing}", result.stderr)
        host.submit_task_stack.assert_not_called()
        host.mark_pull_requests_ready.assert_not_called()
        self.assertEqual(self.state(70), ("Implementation", "Pending"))
        self.assertEqual(self.comments_text(70), "")

    def test_publication_pushes_the_stack_before_marking_ready_and_a_failed_push_posts_nothing(self):
        self.seed_record(70, "Implementation", "Pending", slug="record-70")
        self.seed_task(70, 701, "TASK-001", "CLOSED", "WORK-70-TASK-001 [CORE] Core")
        self.register_prs(701, [148])
        host = self._host([self._pr(148, "OPEN", is_draft=True)])
        host.submit_task_stack.side_effect = PdlcError("push refused")

        with patch("pdlc.commands.post_implement.get_code_host", return_value=host), \
             patch("pdlc.internal.pull_requests.get_code_host", return_value=host):
            result = self.invoke("post_implement", 70, self.evidence_file())

        self.assertEqual(result.code, 1)
        self.assertIn("push refused", result.stderr)
        self.check_out.assert_not_called()
        host.mark_pull_requests_ready.assert_not_called()
        self.assertEqual(self.state(70), ("Implementation", "Pending"))
        self.assertEqual(self.comments_text(70), "")

    def test_a_dirty_tree_stops_publication_before_anything_is_marked_ready(self):
        self.seed_record(70, "Implementation", "Pending", slug="record-70")
        self.seed_task(70, 701, "TASK-001", "CLOSED", "WORK-70-TASK-001 [CORE] Core")
        self.register_prs(701, [148])
        host = self._host([self._pr(148, "OPEN", is_draft=True)])
        self.check_out.side_effect = PdlcError("the working tree has uncommitted changes")

        with patch("pdlc.commands.post_implement.get_code_host", return_value=host), \
             patch("pdlc.internal.pull_requests.get_code_host", return_value=host):
            result = self.invoke("post_implement", 70, self.evidence_file())

        self.assertEqual(result.code, 1)
        self.assertIn("uncommitted changes", result.stderr)
        host.mark_pull_requests_ready.assert_not_called()
        self.assertEqual(self.state(70), ("Implementation", "Pending"))
        self.assertEqual(self.comments_text(70), "")

    def test_publication_fails_cleanly_when_marking_ready_errors(self):
        self.seed_record(70, "Implementation", "Pending", slug="record-70")
        self.seed_task(70, 701, "TASK-001", "CLOSED", "WORK-70-TASK-001 [CORE] Core")
        self.register_prs(701, [148])
        host = self._host([self._pr(148, "OPEN", is_draft=True)])
        host.mark_pull_requests_ready.side_effect = PdlcError("gh pr ready failed")

        with patch("pdlc.commands.post_implement.get_code_host", return_value=host), \
             patch("pdlc.internal.pull_requests.get_code_host", return_value=host):
            result = self.invoke("post_implement", 70, self.evidence_file())

        self.assertEqual(result.code, 1)
        self.assertIn("gh pr ready failed", result.stderr)
        self.assertEqual(self.state(70), ("Implementation", "Pending"))
        self.assertEqual(self.comments_text(70), "")


if __name__ == "__main__":
    unittest.main()

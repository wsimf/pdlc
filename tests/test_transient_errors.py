"""Transient host failures: `run_process` classifies them, retries only when a
retry cannot duplicate a write, and tracks whether this run started a write;
`report_failure` turns them into exit 75 (safe to re-run) or 76 (follow the
printed recovery); the provider transports classify each call from argv; and
`next loop` backs off on them instead of stopping."""

from __future__ import annotations

import ast
import errno
import importlib
import io
import json
import re
import subprocess
import threading
import time
import unittest
import contextlib
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from _support import FileBackendTest

from pdlc import cli
from pdlc.domain.lifecycle import PdlcError, TransientError
from pdlc.domain.workflow import Gate
from pdlc.hosts.lib import process
from pdlc.hosts.lib.azure.transport import az_call_kind
from pdlc.hosts.lib.github.transport import gh_call_kind
from pdlc.internal import failure

DOCS = Path(__file__).resolve().parents[1] / "docs"

COMMANDS = Path(__file__).resolve().parents[1] / "src" / "pdlc" / "commands"


def _completed(returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


class _ProcessTest(unittest.TestCase):
    def setUp(self) -> None:
        process.reset_run_state()
        failure.reset()
        self.addCleanup(process.reset_run_state)
        self.addCleanup(failure.reset)
        sleep = mock.patch.object(process, "_sleep")
        self.sleeps = sleep.start()
        self.addCleanup(sleep.stop)
        which = mock.patch.object(process.shutil, "which", return_value="/usr/bin/gh")
        which.start()
        self.addCleanup(which.stop)

    def run_with(self, *results: object, idempotent: bool, **kwargs: bool) -> tuple[mock.Mock, str | BaseException]:
        with mock.patch.object(process.subprocess, "run", side_effect=list(results)) as run:
            try:
                return run, process.run_process(["gh", "issue", "comment"], idempotent=idempotent, **kwargs)
            except PdlcError as error:
                return run, error


class ClassificationTest(unittest.TestCase):
    def test_transient_patterns(self) -> None:
        cases = {
            "dial tcp: lookup api.github.com: no such host": "not-sent",
            "error connecting to api.github.com: connection refused": "not-sent",
            "You have exceeded a secondary rate limit.": "not-sent",
            "HTTP 429: Too Many Requests": "not-sent",
            "read: connection reset by peer": "maybe-sent",
            "HTTP 502: Bad Gateway": "maybe-sent",
            "Post \"https://api.github.com/graphql\": unexpected EOF": "maybe-sent",
            "('Connection aborted.', RemoteDisconnected('Remote end closed connection'))": "maybe-sent",
            "Wsl/Service/CreateInstance/E_UNEXPECTED": "maybe-sent",
            "ERROR: Before you can run Azure DevOps commands, you need to run the login commands": "credential",
        }
        for message, kind in cases.items():
            with self.subTest(message=message):
                self.assertEqual(process._classify(message), kind)

    def test_hard_failures_stay_hard(self) -> None:
        for message in (
            "HTTP 401: Bad credentials",
            "HTTP 403: Resource not accessible by integration",
            "HTTP 404: Not Found",
            "HTTP 422: Validation Failed",
            "GraphQL: Could not resolve to an Issue with the number of 9.",
        ):
            with self.subTest(message=message):
                self.assertIsNone(process._classify(message))


class RetryTest(_ProcessTest):
    def test_idempotent_call_retries_a_maybe_sent_failure_then_succeeds(self) -> None:
        run, result = self.run_with(
            _completed(1, stderr=b"HTTP 502: Bad Gateway"), _completed(0, stdout=b"ok"), idempotent=True,
        )
        self.assertEqual(result, "ok")
        self.assertEqual(run.call_count, 2)
        self.assertEqual(self.sleeps.call_count, 1)
        self.assertFalse(process.write_started())

    def test_write_is_not_retried_after_the_request_may_have_been_sent(self) -> None:
        run, result = self.run_with(_completed(1, stderr=b"connection reset by peer"), idempotent=False)
        self.assertIsInstance(result, TransientError)
        self.assertEqual(run.call_count, 1)
        self.assertTrue(process.write_started())

    def test_timeout_counts_as_maybe_sent(self) -> None:
        run, result = self.run_with(subprocess.TimeoutExpired("gh", 120), idempotent=False)
        self.assertIsInstance(result, TransientError)
        self.assertEqual(run.call_count, 1)

    def test_write_is_retried_when_the_request_never_left(self) -> None:
        run, result = self.run_with(
            _completed(1, stderr=b"could not resolve host: api.github.com"), _completed(0, stdout=b"done"),
            idempotent=False,
        )
        self.assertEqual(result, "done")
        self.assertEqual(run.call_count, 2)
        self.assertTrue(process.write_started())

    def test_exhausted_not_sent_write_leaves_nothing_written(self) -> None:
        refused = _completed(1, stderr=b"connection refused")
        run, result = self.run_with(refused, refused, refused, idempotent=False)
        self.assertIsInstance(result, TransientError)
        assert isinstance(result, TransientError)
        self.assertEqual(result.attempts, process.ATTEMPTS)
        self.assertEqual(run.call_count, process.ATTEMPTS)
        self.assertFalse(process.write_started())

    def test_an_earlier_write_stays_recorded(self) -> None:
        self.run_with(_completed(0, stdout=b"ok"), idempotent=False)
        refused = _completed(1, stderr=b"connection refused")
        self.run_with(refused, refused, refused, idempotent=False)
        self.assertTrue(process.write_started())

    def test_an_idempotent_write_marks_the_run(self) -> None:
        run, result = self.run_with(_completed(0, stdout=b"ok"), idempotent=True, writes=True)
        self.assertEqual(result, "ok")
        self.assertTrue(process.write_started())

    def test_an_idempotent_write_that_may_have_landed_stays_marked(self) -> None:
        reset = _completed(1, stderr=b"connection reset by peer")
        refused = _completed(1, stderr=b"connection refused")
        run, result = self.run_with(reset, refused, refused, idempotent=True, writes=True)
        self.assertIsInstance(result, TransientError)
        self.assertEqual(run.call_count, process.ATTEMPTS)
        self.assertTrue(process.write_started())

    def test_a_multi_request_call_never_counts_as_not_sent(self) -> None:
        run, result = self.run_with(_completed(1, stderr=b"connection refused"), idempotent=False, single_request=False)
        self.assertIsInstance(result, TransientError)
        self.assertEqual(run.call_count, 1)
        self.assertTrue(process.write_started())

    def test_a_conflict_is_never_transient(self) -> None:
        conflict = b"error: could not apply abc123... fix connection reset handling\nCONFLICT (content)"
        run, result = self.run_with(_completed(1, stderr=conflict), idempotent=True)
        self.assertIs(type(result), PdlcError)
        self.assertEqual(run.call_count, 1)

    def test_wsl_launch_error_is_retried(self) -> None:
        run, result = self.run_with(OSError(errno.EIO, "Input/output error"), _completed(0, stdout=b"ok"), idempotent=False)
        self.assertEqual(result, "ok")
        self.assertEqual(run.call_count, 2)

    def test_hard_failure_is_not_retried(self) -> None:
        run, result = self.run_with(_completed(1, stderr=b"HTTP 422: Validation Failed"), idempotent=True)
        self.assertIs(type(result), PdlcError)
        self.assertEqual(run.call_count, 1)

    def test_rate_limit_waits_longer(self) -> None:
        self.run_with(_completed(1, stderr=b"secondary rate limit"), _completed(0, stdout=b"ok"), idempotent=True)
        self.assertGreaterEqual(self.sleeps.call_args.args[0], 5.0)


class CredentialRaceTest(_ProcessTest):
    LOGIN = _completed(1, stderr=(
        b"ERROR: Before you can run Azure DevOps commands, you need to run the login commands"
        b"(az login if using AAD/MSA identity else az devops login if using PAT token) to setup credentials"
    ))

    def delays(self) -> list[float]:
        return [call.args[0] for call in self.sleeps.call_args_list]

    def test_a_login_race_is_retried_then_succeeds(self) -> None:
        run, result = self.run_with(self.LOGIN, _completed(0, stdout=b"ok"), idempotent=True)
        self.assertEqual(result, "ok")
        self.assertEqual(run.call_count, 2)
        [delay] = self.delays()
        self.assertTrue(2.0 <= delay <= 3.0)

    def test_a_write_is_retried_after_a_login_race(self) -> None:
        run, result = self.run_with(self.LOGIN, _completed(0, stdout=b"done"), idempotent=False)
        self.assertEqual(result, "done")
        self.assertEqual(run.call_count, 2)
        self.assertTrue(process.write_started())

    def test_a_persistent_login_failure_is_a_hard_stop_that_wrote_nothing(self) -> None:
        run, result = self.run_with(self.LOGIN, self.LOGIN, self.LOGIN, idempotent=False)
        self.assertIs(type(result), PdlcError)
        self.assertIn("az devops login", str(result))
        self.assertIn("AZURE_DEVOPS_EXT_PAT", str(result))
        self.assertEqual(run.call_count, process.ATTEMPTS)
        first, second = self.delays()
        self.assertTrue(2.0 <= first <= 3.0)
        self.assertTrue(4.0 <= second <= 6.0)
        self.assertFalse(process.write_started())

    def test_a_multi_request_call_is_not_retried(self) -> None:
        run, result = self.run_with(self.LOGIN, idempotent=False, single_request=False)
        self.assertIs(type(result), PdlcError)
        self.assertEqual(run.call_count, 1)
        self.assertTrue(process.write_started())


class AzWarmUpTest(unittest.TestCase):
    def setUp(self) -> None:
        from pdlc.hosts.lib.azure import transport

        self.transport = transport
        transport.reset_warm_up()
        self.addCleanup(transport.reset_warm_up)

    def start(self, count: int) -> list[threading.Thread]:
        threads = [threading.Thread(target=self.call) for _ in range(count)]
        for thread in threads:
            thread.start()
        return threads

    def call(self) -> None:
        with contextlib.suppress(PdlcError):
            self.transport.run_az(["boards", "work-item", "show", "--id", "4"])

    def test_the_first_call_runs_alone(self) -> None:
        started, release = threading.Event(), threading.Event()
        calls: list[str] = []

        def fake(args: object, **kwargs: object) -> str:
            calls.append("call")
            if len(calls) == 1:
                started.set()
                release.wait(5)
            return ""

        with mock.patch.object(self.transport, "run_process", side_effect=fake):
            threads = self.start(4)
            self.assertTrue(started.wait(5))
            time.sleep(0.1)
            # The first call is still running, so no other call has started.
            self.assertEqual(len(calls), 1)
            release.set()
            for thread in threads:
                thread.join(5)
        self.assertEqual(len(calls), 4)

    def test_a_failing_first_call_releases_the_others(self) -> None:
        calls: list[str] = []

        def fake(args: object, **kwargs: object) -> str:
            calls.append("call")
            if len(calls) == 1:
                raise PdlcError("before you can run azure devops commands")
            return ""

        with mock.patch.object(self.transport, "run_process", side_effect=fake):
            threads = self.start(3)
            for thread in threads:
                thread.join(5)
            self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(len(calls), 3)
        self.assertTrue(self.transport._warmed.is_set())


class CallKindTest(unittest.TestCase):
    def test_github(self) -> None:
        cases = {
            "read": [
                ["issue", "view", "4"],
                ["project", "item-list", "1"],
                ["api", "user"],
                ["api", "--method", "GET", "repos/o/r/issues/1/comments", "-f", "page=1"],
                ["api", "graphql", "-f", "query=query($a: Int!) { viewer { login } }"],
                ["api", "graphql", "-f", "query=\n  { viewer { login } }"],
            ],
            "set": [
                ["issue", "edit", "4", "--body-file", "b.md"],
                ["issue", "close", "4"],
                ["pr", "ready", "9"],
                ["api", "--method", "PATCH", "repos/o/r/issues/comments/1", "-f", "body=x"],
                ["api", "--method", "DELETE", "repos/o/r/issues/comments/1"],
                ["api", "graphql", "-f", "query=mutation($p: ID!) {\n  status: updateProjectV2ItemFieldValue(input: {projectId: $p}) { projectV2Item { id } }\n}"],
            ],
            "add": [
                ["issue", "create", "--title", "t"],
                ["issue", "comment", "4", "--body-file", "b.md"],
                ["project", "item-add", "1", "--url", "u"],
                ["stack", "submit", "--auto"],
                ["api", "repos/o/r/issues/1/comments", "-f", "body=x"],
                ["api", "graphql", "-f", "query=mutation($p: ID!) {\n link0: addSubIssue(input: {issueId: $p}) { issue { id } }\n}"],
                [],
            ],
        }
        for kind, calls in cases.items():
            for args in calls:
                with self.subTest(args=args):
                    self.assertEqual(gh_call_kind(args), kind)

    def test_azure(self) -> None:
        cases = {
            "read": [
                ["boards", "work-item", "show", "--id", "4"],
                ["boards", "query", "--wiql", "x"],
                ["devops", "invoke", "--area", "wit"],
            ],
            "set": [
                ["boards", "work-item", "update", "--id", "4"],
                ["devops", "invoke", "--http-method", "PATCH"],
            ],
            "add": [
                ["devops", "invoke", "--http-method", "POST"],
                ["devops", "invoke", "--http-method", "DELETE"],
                ["boards", "work-item", "create", "--title", "t"],
                ["boards", "work-item", "relation", "add", "--id", "4"],
            ],
        }
        for kind, calls in cases.items():
            for args in calls:
                with self.subTest(args=args):
                    self.assertEqual(az_call_kind(args), kind)

    def test_run_gh_marks_an_idempotent_write(self) -> None:
        from pdlc.hosts.lib.github import transport

        with mock.patch.object(transport, "run_process", return_value="") as run:
            transport.run_gh(["issue", "edit", "4"])
            transport.run_gh(["issue", "view", "4"])
            transport.run_gh(["stack", "submit"], timeout=300)
        edit, view, stack = (call.kwargs for call in run.call_args_list)
        self.assertEqual((edit["idempotent"], edit["writes"], edit["single_request"]), (True, True, True))
        self.assertEqual((view["idempotent"], view["writes"]), (True, False))
        self.assertEqual((stack["idempotent"], stack["single_request"]), (False, False))
        self.assertEqual((edit["timeout"], view["timeout"], stack["timeout"]), (120, 120, 300))


class DeleteCommentTest(unittest.TestCase):
    URL = "https://github.com/o/r/issues/4#issuecomment-99"

    def delete(self, error: PdlcError) -> None:
        from pdlc.hosts.lib.github import issues

        with (
            mock.patch.object(issues, "owner_repository", return_value=("o", "r")),
            mock.patch.object(issues, "run_gh", side_effect=error),
        ):
            issues.delete_comment(self.URL)

    def test_an_already_deleted_comment_counts_as_done(self) -> None:
        self.delete(PdlcError("gh: Not Found (HTTP 404)"))

    def test_other_failures_still_raise(self) -> None:
        with self.assertRaises(TransientError):
            self.delete(TransientError("HTTP 404 Not Found while connection reset"))
        with self.assertRaises(PdlcError):
            self.delete(PdlcError("HTTP 403: Forbidden"))


class TransientPreservedTest(_ProcessTest):
    def test_create_names_the_issue_when_the_project_add_fails(self) -> None:
        from pdlc.hosts.lib.github import workitem_backend

        url = "https://github.com/o/r/issues/7"
        config = mock.Mock(project_number="1", project_owner="o")
        with (
            mock.patch.object(workitem_backend, "get_config", return_value=config),
            mock.patch.object(workitem_backend, "body_file", return_value=contextlib.nullcontext("b.md")),
            mock.patch.object(workitem_backend, "repo_args", return_value=[]),
            mock.patch.object(workitem_backend, "assignee_args", return_value=[]),
            mock.patch.object(workitem_backend, "run_gh", return_value=url + "\n"),
            mock.patch.object(workitem_backend, "run_gh_json", side_effect=TransientError("reset", attempts=1)),
            self.assertRaises(TransientError) as raised,
        ):
            workitem_backend.GitHubWorkItemBackend().create("t", "b", "s")
        self.assertIn(f"created {url}", str(raised.exception))

    def test_upsert_tasks_keeps_the_failure_that_stopped_it(self) -> None:
        from pdlc.hosts.lib.github import issues

        original = TransientError("reset", attempts=1)
        with (
            mock.patch.object(issues, "_recover_unlinked_tasks", return_value=[]),
            mock.patch.object(issues, "_upsert_task", side_effect=original),
            mock.patch.object(issues, "link_subissues", side_effect=PdlcError("link failed")),
            self.assertRaises(TransientError) as raised,
        ):
            issues.upsert_tasks("4", [{"id": "T1", "title": "t", "bodyText": "b"}], [])
        self.assertIs(raised.exception, original)

    def test_ci_wait_polls_through_a_transient_read_and_reports_it_on_timeout(self) -> None:
        from pdlc.commands import post_ci

        clock = iter([0.0, 10.0, post_ci.CI_WAIT_TIMEOUT_SECONDS + 1.0])
        polls = [{"state": "pending", "stage": "Implement"}, TransientError("reset", attempts=3)]
        with (
            mock.patch.object(post_ci, "post_ci", side_effect=polls),
            mock.patch.object(post_ci.time, "monotonic", side_effect=lambda: next(clock)),
            mock.patch.object(post_ci.time, "sleep"),
            redirect_stderr(io.StringIO()),
            self.assertRaises(TransientError),
        ):
            post_ci.wait_for_ci("4")

    def test_ci_wait_stops_polling_once_a_write_started(self) -> None:
        from pdlc.commands import post_ci

        def write_then_fail(issue: str) -> dict:
            process._mark_write(True)
            raise TransientError("reset", attempts=1)

        with (
            mock.patch.object(post_ci, "post_ci", side_effect=write_then_fail) as poll,
            mock.patch.object(post_ci.time, "sleep"),
            self.assertRaises(TransientError),
        ):
            post_ci.wait_for_ci("4")
        self.assertEqual(poll.call_count, 1)


class ReportFailureTest(unittest.TestCase):
    def setUp(self) -> None:
        process.reset_run_state()
        failure.reset()
        self.addCleanup(process.reset_run_state)
        self.addCleanup(failure.reset)
        failure.set_invocation(["post", "review", "42", "approval-required", "review.md"])

    def report(self, error: PdlcError, **kwargs: bool) -> tuple[int, str]:
        err = io.StringIO()
        with redirect_stderr(err):
            code = failure.report_failure(error, **kwargs)
        return code, err.getvalue()

    def test_hard_failure_keeps_exit_1_and_its_line(self) -> None:
        self.assertEqual(self.report(PdlcError("record not found")), (1, "pdlc: record not found\n"))

    def test_transient_before_any_write_is_75(self) -> None:
        code, text = self.report(TransientError("gh timed out after 120s", attempts=3))
        self.assertEqual(code, 75)
        self.assertTrue(text.startswith("pdlc: transient: gh timed out after 120s (3 attempts)\n"))
        self.assertIn("re-run: pdlc post review 42 approval-required review.md", text)

    def test_transient_after_a_write_is_76_with_the_recovery(self) -> None:
        process._mark_write(True)
        failure.set_recovery(failure.Recovery(check="pdlc inspect 42", landed="the gate moved", note="may duplicate"))
        code, text = self.report(TransientError("connection reset by peer"))
        self.assertEqual(code, 76)
        self.assertTrue(text.startswith("pdlc: transient: connection reset by peer\n"))
        self.assertIn("1. Run `pdlc inspect 42`.", text)
        self.assertIn("2. If the gate moved, it landed. Continue.", text)
        self.assertIn("3. Otherwise re-run: pdlc post review 42 approval-required review.md", text)
        self.assertIn("Note: may duplicate", text)

    def test_unsafe_recovery_stops_instead_of_re_running(self) -> None:
        process._mark_write(True)
        failure.set_recovery(failure.Recovery(check="pdlc inspect 42", landed="the stage moved", rerun=False))
        code, text = self.report(TransientError("connection reset by peer"))
        self.assertEqual(code, 76)
        self.assertIn("do not re-run it; stop and report", text)
        self.assertNotIn("re-run: pdlc", text)

    def test_otherwise_names_the_rerun_line(self) -> None:
        process._mark_write(True)
        failure.set_recovery(failure.Recovery(check="c", landed="l", otherwise="dry-run first, then {rerun}"))
        _, text = self.report(TransientError("reset"))
        self.assertIn("dry-run first, then pdlc post review 42 approval-required review.md", text)

    def test_rerun_safe_caller_is_75_even_after_a_write(self) -> None:
        process._mark_write(True)
        code, text = self.report(TransientError("reset"), rerun_safe=True)
        self.assertEqual(code, 75)
        self.assertIn("re-running this command is safe", text)
        self.assertNotIn("nothing was changed", text)

    def test_cli_resets_state_and_catches_an_uncaught_transient(self) -> None:
        process._mark_write(True)
        module = mock.Mock()
        module.main.side_effect = TransientError("reset")
        err = io.StringIO()
        with (
            mock.patch.object(cli, "_resolve", return_value=("pdlc.commands.guide", [])),
            mock.patch.object(cli.importlib, "import_module", return_value=module),
            redirect_stderr(err),
        ):
            code = cli.main(["guide"])
        self.assertEqual(code, 75)
        self.assertIn("re-run: pdlc guide", err.getvalue())


class RecoveryRegistrationTest(unittest.TestCase):
    def test_every_mutating_command_registers_a_recovery(self) -> None:
        paths = [p for p in sorted(COMMANDS.glob("post_*.py"))] + [COMMANDS / "continue_.py", COMMANDS / "checkout.py"]
        for path in paths:
            with self.subTest(command=path.stem):
                tree = ast.parse(path.read_text())
                calls = {
                    node.func.id for node in ast.walk(tree)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                }
                self.assertIn("set_recovery", calls)


class RecoveryLandingGateTest(FileBackendTest):
    """A publishing command's recovery must name the gate its successful run
    actually lands at, so an agent checking after a transient failure never
    reads a landed write as missing. Each case runs the command for real and
    compares the recovery it registered against the returned `gateState`."""

    def land(self, command: str, *args: object) -> dict:
        failure.reset()
        result = self.invoke(command, *args)
        self.assertEqual(result.code, 0, result.stderr)
        recovery = failure._recovery
        self.assertIsNotNone(recovery)
        assert recovery is not None
        gate = result.json["gateState"]
        self.assertIn(f"gate is {gate} and", recovery.landed)
        for other in Gate:
            if other.value != gate:
                self.assertNotIn(other.value, recovery.landed)
        return result.json

    def test_post_write_names_the_gate_it_lands(self) -> None:
        evidence = self.evidence_file()
        body = self.write_file("product.md", "## Product\nx\n\n## Decisions\nd\n\n## Open Questions\nq\n")
        created = self.land("post_write", "--title", "Shell", "--slug", "shell", "--evidence", evidence, "--body", body)
        issue = created["work_item_number"]
        # Re-authored in place from the landed gate, and first-published from Stale.
        self.land("post_write", "--work-item", issue, "--evidence", evidence, "--body", body)
        self.seed_record(90, "Product", "Stale")
        self.land("post_write", "--work-item", 90, "--evidence", evidence, "--body", body)

    def test_post_tasks_ui_names_the_gate_it_lands(self) -> None:
        self.seed_record(91, "UI", "Pending")
        fragment = self.write_file("ui.md", "## UI\n\nUJ-1 covers the first run.\n")
        for _ in range(2):  # first publication, then re-authored in place
            self.mark_ui_reviewed(91, fragment)
            self.land("post_tasks", "--work-item", 91, "--stage", "UI", "--body", fragment, "--evidence", self.evidence_file())

    def test_post_tasks_names_the_gate_it_lands(self) -> None:
        self.seed_record(92, "Tasks", "Pending")
        body = self.write_file(
            "task.md", "**Blocked by:** None\n**Type:** AFK\n**Requirements Covered:** FR-1, FR-2, C-1\n"
            "**UI Journeys:** UJ-1\n\n**Scope:**\nBuild.\n\n**Acceptance Criteria:**\n- [ ] FR-1 works.\n",
        )
        manifest = self.write_file("manifest.json", json.dumps([{
            "id": "TASK-001", "action": "create", "title": "Build core", "body": body,
            "type": "ui", "covers": ["FR-1", "FR-2", "C-1", "UJ-1"],
        }]))
        for _ in range(2):  # first publication, then re-authored in place
            self.mark_tasks_reviewed(92, manifest)
            self.land("post_tasks", "--work-item", 92, "--stage", "Tasks", "--manifest", manifest, "--evidence", self.evidence_file())

    def test_post_plan_names_the_gate_it_lands(self) -> None:
        self.seed_record(93, "Technical Plan", "Pending")
        self.seed_task(93, 931, "TASK-001", "OPEN", "WORK-93-TASK-001 One")
        manifest = self.reviewed_plan_manifest(93, {"TASK-001": "Plan one."})
        self.land("post_plan", "--work-item", 93, "--manifest", manifest, "--evidence", self.evidence_file())
        # Re-planned in place from the landed gate.
        self.write_plan(json.loads(Path(manifest).read_text())[0]["file"], "Plan one, revised.")
        self.review_plans(93, manifest)
        self.land("post_plan", "--work-item", 93, "--manifest", manifest, "--evidence", self.evidence_file())

    def test_post_implement_and_post_test_name_the_gate_they_land(self) -> None:
        self.seed_record(94, "Implementation", "Pending")
        with mock.patch("pdlc.commands.post_implement.get_code_host"), \
                mock.patch("pdlc.commands.post_implement.check_out"):
            self.land("post_implement", 94, self.evidence_file())
        self.seed_record(95, "Testing", "Pending")
        host = mock.Mock()
        host.ensure_pull_request_linked.return_value = {"number": 7, "url": "https://x/7"}
        with mock.patch("pdlc.commands.post_test.get_code_host", return_value=host), \
                mock.patch("pdlc.commands.post_test.attach_pr"):
            self.land("post_test", 95, self.evidence_file(), "--traceability", self.write_file("trace.md", "FR-1: covered.\n"))


class RecoveryCatalogGateTest(unittest.TestCase):
    def test_catalog_publish_gates_match_the_pipeline(self) -> None:
        """Every `set_state` → STAGE / GATE line in the recovery catalog that
        names a publication's landing gate matches that stage's result gate."""
        from pdlc.domain.workflows.workflow_feature import FEATURE_PIPELINE

        text = (DOCS / "mutation-recovery.md").read_text(encoding="utf-8")
        landings = re.findall(r"`set_state` → ([A-Za-z ]+?) / (Review Required|Approval Required)", text)
        self.assertTrue(landings)
        for stage, gate in landings:
            with self.subTest(stage=stage):
                result_gate = FEATURE_PIPELINE.stage(stage).result_gate
                self.assertEqual(gate, result_gate.value if result_gate else None)


class LoopTransientTest(FileBackendTest):
    def test_loop_backs_off_on_a_transient_poll_and_recovers(self) -> None:
        self.seed_record(17, "UI", "Pending")
        self.configure(max_attempts=3, initial_delay_seconds=0, max_delay_seconds=0)
        next_command = importlib.import_module("pdlc.commands.next")
        real = next_command.next_once
        calls = iter([TransientError("connection reset by peer")])

        def flaky(selector: str | None) -> dict:
            for error in calls:
                raise error
            return real(selector)

        with mock.patch.object(next_command, "next_once", side_effect=flaky):
            result = self.next("loop")
        self.assertEqual(result.code, 0)
        self.assertEqual(result.front_matter("action"), "pdlc-tasks")
        self.assertIn("pdlc: transient: connection reset by peer; retrying", result.stderr)

    def test_loop_exits_75_when_every_poll_fails_transiently(self) -> None:
        self.configure(max_attempts=2, initial_delay_seconds=0, max_delay_seconds=0)
        next_command = importlib.import_module("pdlc.commands.next")
        process._mark_write(True)
        self.addCleanup(process.reset_run_state)
        with mock.patch.object(next_command, "next_once", side_effect=TransientError("reset")):
            result = self.next("loop")
        self.assertEqual(result.code, 75)


if __name__ == "__main__":
    unittest.main()

"""Failure, retry, and normalized-data contracts shared by the providers."""

import contextlib
import importlib
import io
import subprocess
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from _support import FileBackendTest
from pdlc.commands.post_decision import _defer
from pdlc.config import (
    CONFIG_FIELDS,
    Config,
    ConfigurationError,
    _read_file,
    configuration_guidance,
    install_config,
    reset_config,
)
from pdlc.domain.lifecycle import NotFound, PdlcError
from pdlc.domain.records import validate_task_inputs, validate_task, validate_work_item
from pdlc.hosts.azure_provider import AzureWorkItemBackend
from pdlc.hosts.file_provider import FileCodeHost, FileWorkItemBackend
from pdlc.hosts.github_provider import GitHubCodeHost
from pdlc.hosts.none_provider import NoneCodeHost
from pdlc.hosts.lib.azure import workitems as azure
from pdlc.hosts.lib.file.storage import atomic_write
from pdlc.hosts.lib.github import project
from pdlc.hosts.lib.process import parse_json, run_process
from pdlc.internal import workitem
from pdlc.internal.inputs import resolve_text
from pdlc.internal.pull_requests import registered_pr_numbers


class ConfigurationContractTests(unittest.TestCase):
    def test_false_really_enables_backoff(self):
        next_command = importlib.import_module("pdlc.commands.next")
        self.addCleanup(reset_config)
        for no_sleep in (False,):
            with self.subTest(no_sleep=no_sleep), patch.object(next_command, "next_once", return_value={"action": "none"}), patch.object(next_command.time, "sleep") as sleep, redirect_stderr(io.StringIO()):
                install_config(Config(
                    no_sleep=no_sleep, max_attempts=2,
                    initial_delay_seconds=3, max_delay_seconds=9,
                ))
                next_command.loop_(None)
                sleep.assert_called_once_with(3)

    def test_invalid_runtime_settings_are_configuration_errors(self):
        for name, value in (
            ("no_sleep", "maybe"), ("max_attempts", 0),
            ("max_attempts", 2.5), ("initial_delay_seconds", -1),
            ("max_delay_seconds", "not-a-number"),
        ):
            with self.subTest(name=name, value=value):
                with self.assertRaises(ConfigurationError):
                    Config.from_values({name: value})

    def test_guidance_contains_parseable_grouped_toml(self):
        for names in (
            ["backend.github.repository"],
            ["backend.azure.organization", "backend.azure.project"],
        ):
            guidance = configuration_guidance(names)
            example = guidance.split("for example:\n\n", 1)[1].split("\n\nYou can", 1)[0]
            with tempfile.TemporaryDirectory() as root:
                path = Path(root) / "config.toml"
                path.write_text(example, encoding="utf-8")
                values, _ = _read_file(path)
                expected = {
                    CONFIG_FIELDS[tuple(name.rsplit(".", 1))] for name in names
                }
                self.assertEqual(set(values), expected)


class FailureContractTests(unittest.TestCase):
    def test_defer_does_not_create_after_ambiguous_or_failed_lookup(self):
        for reason in ("slug is ambiguous", "authentication failed", "network unavailable"):
            with self.subTest(reason=reason), patch("pdlc.commands.post_decision.resolve_item", side_effect=PdlcError(reason)), patch("pdlc.commands.post_decision.create_work_item") as create:
                with self.assertRaisesRegex(PdlcError, reason):
                    _defer("7", "Testing", {"title": "Deferred", "slug": "deferred", "body": "unused"})
                create.assert_not_called()

    def test_missing_registered_pr_is_a_failure_for_each_code_host(self):
        for host in (FileCodeHost(), NoneCodeHost(), GitHubCodeHost()):
            with self.subTest(host=type(host).__name__), patch("pdlc.hosts.lib.file.code_host._all_pull_requests", return_value=[]), patch("pdlc.hosts.lib.github.code_host.run_graphql", side_effect=PdlcError("Could not resolve to a PullRequest with the number of 123.")), patch("pdlc.hosts.lib.github.code_host.owner_repository", return_value=("wsimf", "pdlc")):
                with self.assertRaises(PdlcError):
                    host.pull_requests_by_number([123])
                self.assertEqual(host.pull_requests_by_number([]), [])

    def test_pr_auth_failure_keeps_its_diagnostic(self):
        with patch("pdlc.hosts.lib.github.code_host.run_gh_json", side_effect=PdlcError("authentication expired")):
            with self.assertRaisesRegex(PdlcError, "authentication expired"):
                GitHubCodeHost().ensure_pull_request_linked("7")

    def test_transports_translate_timeout_and_missing_binary(self):
        for error in (FileNotFoundError("missing executable"), subprocess.TimeoutExpired("az", 2)):
            with self.subTest(error=type(error).__name__), patch("pdlc.hosts.lib.process.shutil.which", return_value="/tools/az"), patch("pdlc.hosts.lib.process.subprocess.run", side_effect=error):
                with self.assertRaises(PdlcError):
                    run_process(["az", "version"], timeout=2)

    def test_transport_bounds_execution_and_decodes_utf8(self):
        result = subprocess.CompletedProcess(["gh"], 0, stdout="Māori".encode(), stderr=b"")
        with patch("pdlc.hosts.lib.process.shutil.which", return_value="/tools/gh"), patch("pdlc.hosts.lib.process.subprocess.run", return_value=result) as run:
            self.assertEqual(run_process(["gh", "version"]), "Māori")
        self.assertEqual(run.call_args.kwargs["timeout"], 120)
        # The child is pinned to a UTF-8 locale so a POSIX `az` emits UTF-8
        # regardless of the host locale.
        child_env = run.call_args.kwargs["env"]
        self.assertEqual(child_env["LC_ALL"], "C.UTF-8")
        self.assertEqual(child_env["PYTHONUTF8"], "1")
        self.assertEqual(child_env["PYTHONIOENCODING"], "utf-8")

    def test_transport_recovers_a_cp1252_response(self):
        # The Windows `az` build ignores the locale and emits its ANSI code page,
        # so an em dash arrives as the lone byte 0x97 with CRLF line endings.
        raw = "first — line\r\nsecond\r\n".encode("cp1252")
        result = subprocess.CompletedProcess(["az"], 0, stdout=raw, stderr=b"")
        with patch("pdlc.hosts.lib.process.shutil.which", return_value="/tools/az"), patch("pdlc.hosts.lib.process.subprocess.run", return_value=result):
            self.assertEqual(run_process(["az", "version"]), "first — line\nsecond\n")

    def test_azure_launches_resolved_windows_cmd_path(self):
        from pdlc.hosts.lib.azure.transport import run_az

        executable = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
        arguments = ["boards", "query", "--project", "My Project"]
        result = subprocess.CompletedProcess([executable], 0, stdout=b"[]", stderr=b"")
        with patch("pdlc.hosts.lib.process.shutil.which", return_value=executable) as which, patch("pdlc.hosts.lib.process.subprocess.run", return_value=result) as run:
            self.assertEqual(run_az(arguments), "[]")
        which.assert_called_once_with("az")
        self.assertEqual(run.call_args.args[0], [executable, *arguments])
        self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_missing_executable_fails_before_launch(self):
        with patch("pdlc.hosts.lib.process.shutil.which", return_value=None), patch("pdlc.hosts.lib.process.subprocess.run") as run:
            with self.assertRaisesRegex(PdlcError, "required command not found: az"):
                run_process(["az", "version"])
        run.assert_not_called()

    def test_malformed_json_is_a_contextual_error(self):
        with self.assertRaisesRegex(PdlcError, "az returned invalid JSON"):
            parse_json("<html>sign in</html>", "az")

    def test_empty_evidence_rejected_equally_for_file_and_stdin(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "evidence.md"
            path.write_text(" \n ", encoding="utf-8")
            with self.assertRaisesRegex(PdlcError, "empty"):
                resolve_text(str(path), label="evidence")
        with patch("sys.stdin", io.StringIO(" \n ")):
            with self.assertRaisesRegex(PdlcError, "empty"):
                resolve_text("-", label="evidence")

    def test_stdin_device_paths_read_stdin_not_a_file(self):
        # Agents reach for /dev/stdin in place of `-`; it must resolve to the
        # stream, never be posted verbatim as the body.
        for alias in ("-", "/dev/stdin", "/dev/fd/0", "/proc/self/fd/0"):
            with patch("sys.stdin", io.StringIO("real body\n")):
                self.assertEqual(resolve_text(alias, label="evidence"), "real body\n")

    def test_text_prefix_is_a_literal_body(self):
        self.assertEqual(resolve_text("text:User approved the plan.", label="evidence"), "User approved the plan.")
        with self.assertRaisesRegex(PdlcError, "empty"):
            resolve_text("text:   ", label="evidence")

    def test_unknown_path_errors_rather_than_becoming_a_literal(self):
        with self.assertRaisesRegex(PdlcError, "does not exist"):
            resolve_text("not-a-real-file.md", label="evidence")

    def test_invalid_normalized_payloads_fail_at_the_boundary(self):
        for validate, value in (
            (validate_work_item, {"id": "7"}),
            (validate_task, {"number": "7"}),
            (validate_task_inputs, [{"id": "TASK-001", "title": "Title", "body": "file.md"}]),
        ):
            with self.subTest(validate=validate.__name__), self.assertRaises(PdlcError):
                validate(value)


class AzureRecoveryTests(unittest.TestCase):
    task = {"id": "TASK-001", "title": "Title", "bodyText": "Body"}
    candidate = {
        "id": 8,
        "fields": {
            azure.TITLE_FIELD: "WORK-7-TASK-001 Title",
            azure.DESCRIPTION_FIELD: "Body", azure.STATE_FIELD: "New",
        },
    }

    def test_link_failure_retry_recovers_the_same_task(self):
        with patch("pdlc.hosts.lib.azure.workitem_backend.azure.tasks_with_identity", side_effect=[[], [self.candidate]]), patch("pdlc.hosts.lib.azure.workitem_backend.azure.create", return_value={"id": 8}) as create, patch("pdlc.hosts.lib.azure.workitem_backend.azure.add_parent", side_effect=[PdlcError("link failed"), None]) as link, patch("pdlc.hosts.lib.azure.workitem_backend.azure.item_url", return_value="url"), patch("pdlc.hosts.lib.azure.workitem_backend._assignee", return_value="probe@example.com"):
            backend = AzureWorkItemBackend()
            with self.assertRaisesRegex(PdlcError, "link failed"):
                backend._upsert(7, self.task, None)
            result = backend._upsert(7, self.task, None)
        self.assertEqual(result["number"], 8)
        create.assert_called_once()
        self.assertEqual(link.call_count, 2)

    def test_duplicate_or_foreign_identity_never_creates(self):
        foreign = {**self.candidate, "fields": {**self.candidate["fields"], azure.PARENT_FIELD: 99}}
        for candidates in ([self.candidate, self.candidate], [foreign]):
            with self.subTest(candidates=candidates), patch("pdlc.hosts.lib.azure.workitem_backend.azure.tasks_with_identity", return_value=candidates), patch("pdlc.hosts.lib.azure.workitem_backend.azure.create") as create:
                with self.assertRaises(PdlcError):
                    AzureWorkItemBackend()._upsert(7, self.task, None)
                create.assert_not_called()

    def test_recovery_does_not_repeat_an_existing_parent_link(self):
        linked = {**self.candidate, "fields": {**self.candidate["fields"], azure.PARENT_FIELD: 7}}
        with patch.object(azure, "tasks_with_identity", return_value=[linked]), patch.object(azure, "add_parent") as link, patch.object(azure, "item_url", return_value="url"):
            result = AzureWorkItemBackend()._upsert(7, self.task, None)
        self.assertEqual(result["number"], 8)
        link.assert_not_called()

    def test_quote_handling_applies_to_project_type_and_slug(self):
        with patch.object(azure, "azure_config", return_value=("org", "O'Brien")), patch.object(azure, "query", return_value=[{"id": 7}]) as query, patch.object(azure, "show", return_value={"id": 7}):
            azure.by_slug("team's-slug", "Team's Story")
        statement = query.call_args.args[0]
        for value in ("O'Brien", "Team's Story", "team's-slug"):
            self.assertIn('"' + value + '"', statement)

    def test_pr_registry_read_does_not_hydrate_comments(self):
        with patch.object(AzureWorkItemBackend, "_record_id", return_value=7), patch.object(azure, "children", return_value=[{"fields": {azure.PRS_FIELD: "3 9"}}]) as children, patch.object(azure, "comments") as comments:
            self.assertEqual(AzureWorkItemBackend().task_pr_numbers("7"), [3, 9])
        comments.assert_not_called()
        children.assert_called_once_with(7, ("System.Id", azure.PRS_FIELD))


class FileStoreContractTests(FileBackendTest):
    def test_completion_uses_one_comment_snapshot_and_one_git_diff(self):
        from pdlc.commands import inspect_complete
        from pdlc.domain.evidence import ReviewVerdict, compose_review
        from pdlc.domain.verification import Report, Row, render
        from pdlc.internal import verification

        self.seed_record(70, "Verification", "Approval Required")
        report = Report(
            head=self.head_sha(), run_at="2026-09-16 10:42 UTC", recommendation="Approval Required",
            claims=(Row("TASK-001", "confirmed", "first"), Row("TASK-002", "confirmed", "second")),
            journeys=None, ux=Row("ux", "not_applicable"), cumulative=Row("cumulative", "clean"),
        )
        comments = [{"body": "PDLC-REVIEW\n\n" + compose_review("Verification", ReviewVerdict.PASS, render(report)),
                     "createdAt": "2026-09-16T10:42:00Z", "url": "", "author": {"login": "v"}}]
        with patch.object(inspect_complete, "comments_for_issue", return_value=comments) as fetch, \
                patch.object(verification, "changed_files", return_value=set()) as git, \
                patch.object(inspect_complete, "completion_blockers", return_value=[]):
            output = inspect_complete.inspect("70")
        fetch.assert_called_once_with("70")
        git.assert_called_once_with(report.head)
        self.assertIn("- claims TASK-001 · confirmed — first", output)
        self.assertIn("- claims TASK-002 · confirmed — second", output)

    def test_reading_an_absent_store_does_not_create_it(self):
        root = self.work / "absent"
        self.set_home(root)
        backend = FileWorkItemBackend()
        self.assertEqual(backend.queue_items(), [])
        for ref in ("1", "missing-slug"):
            with self.assertRaises(NotFound):
                backend.resolve(ref)
        self.assertFalse(root.exists())

    def test_active_writer_rejects_other_mutations_and_preserves_lock(self):
        self.seed_record(70, "Product", "Pending")
        lock = self.home / ".writer.lock"
        lock.mkdir()
        with self.assertRaisesRegex(PdlcError, "file store is locked"):
            FileWorkItemBackend().set_slug("FILE-70", "changed")
        self.assertTrue(lock.exists())
        self.assertNotEqual(FileWorkItemBackend().resolve("70")["Slug"], "changed")

    def test_failed_replace_preserves_old_file_and_cleans_temporary(self):
        path = self.work / "state.json"
        path.write_text("old", encoding="utf-8")
        with patch.object(Path, "replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                atomic_write(path, "new")
        self.assertEqual(path.read_text(), "old")
        self.assertEqual(list(self.work.glob("state.json.*.tmp")), [])

    def test_unicode_task_input_needs_no_file_and_releases_lock(self):
        self.seed_record(70, "Tasks", "Pending")
        backend = FileWorkItemBackend()
        [task] = backend.upsert_tasks("70", [{"id": "TASK-001", "title": "Māori", "bodyText": "日本語"}], [])
        stored = backend.tasks("70")[0]
        self.assertEqual(stored["body"], "日本語")
        self.assertEqual(stored["number"], task["number"])
        self.assertFalse((self.home / ".writer.lock").exists())

    def test_pr_registry_read_uses_metadata_only(self):
        self.seed_record(70, "Implementation", "CI Pending")
        self.seed_task(70, 71, "TASK-001", "CLOSED", "WORK-70-TASK-001 Title")
        self.register_prs(71, [3])
        with patch.object(FileWorkItemBackend, "_task_view", side_effect=AssertionError("hydrated task")):
            self.assertEqual(registered_pr_numbers("70"), [3])


class GitHubSlugTests(unittest.TestCase):
    def test_slug_scan_paginates_and_rejects_ambiguity(self):
        def page(number, more=False):
            return {"data": {"node": {"items": {
                "nodes": [{"slug": {"text": "same"}, "content": {"number": number, "repository": {"nameWithOwner": "o/r"}}}],
                "pageInfo": {"hasNextPage": more, "endCursor": "next" if more else None},
            }}}}
        with patch.object(project, "_project_id", return_value="P"), patch.object(project, "get_config", return_value=Config(repository="o/r")), patch.object(project, "run_graphql", side_effect=[page(1, True), page(2)]) as query:
            with self.assertRaisesRegex(PdlcError, "ambiguous"):
                project.issue_for_slug("same")
            self.assertEqual(query.call_args.kwargs["after"], "next")

    def test_missing_slug_is_distinct_from_transport_failure(self):
        empty = {"data": {"node": {"items": {"nodes": [], "pageInfo": {"hasNextPage": False}}}}}
        with patch.object(project, "_project_id", return_value="P"), patch.object(project, "get_config", return_value=Config(repository="o/r")), patch.object(project, "run_graphql", return_value=empty):
            with self.assertRaises(NotFound):
                project.issue_for_slug("missing")


class ConcurrentSnapshotTests(unittest.TestCase):
    """`record_snapshot` and `comments_and_tasks` overlap their backend reads
    rather than queueing them, whichever backend is configured."""

    def _patched(self, **reads):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(workitem, "get_backend"))
        for name, read in reads.items():
            stack.enter_context(patch.object(workitem, name, side_effect=read))

    def test_record_snapshot_runs_its_three_reads_at_once(self):
        # Each read waits for the other two; a sequential fetch would time out.
        barrier = threading.Barrier(3, timeout=5)

        def read(value):
            return lambda _ref: (barrier.wait(), value)[1]

        self._patched(resolve_item=read({"id": "item"}), task_tree=read(["task"]), comments_for_issue=read(["comment"]))
        self.assertEqual(workitem.record_snapshot("7"), ({"id": "item"}, ["task"], ["comment"]))

    def test_comments_and_tasks_runs_both_reads_at_once(self):
        barrier = threading.Barrier(2, timeout=5)
        self._patched(
            comments_for_issue=lambda _ref: (barrier.wait(), ["comment"])[1],
            task_tree=lambda _ref: (barrier.wait(), ["task"])[1],
        )
        self.assertEqual(workitem.comments_and_tasks("7"), (["comment"], ["task"]))

    def test_record_resolution_failure_wins_over_the_other_reads(self):
        self._patched(
            resolve_item=NotFound("Issue #7 has no item in the configured Project"),
            task_tree=PdlcError("sub-issue read failed"),
            comments_for_issue=PdlcError("comment read failed"),
        )
        with self.assertRaisesRegex(NotFound, "no item in the configured Project"):
            workitem.record_snapshot("7")

"""Shared harness for exercising pdlc commands against the on-disk file backend.

Every test seeds a temporary ``PDLC_HOME`` record store, invokes a command
module's ``main()`` exactly the way the CLI dispatcher would (argv + stdin +
captured stdout/stderr), and inspects the resulting record directory. This is
the Python port of the former ``agent/skills/pdlc/tests/test-pdlc.sh`` suite:
the file backend only ever calls the ``workitem`` / ``code_host`` facades, so
driving it on a real store proves the same contract without a GitHub round-trip.
"""

from __future__ import annotations

import importlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from unittest import mock
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from pdlc.config import Capabilities, Config, install_config, reset_config, set_config
from pdlc.domain.evidence import ReviewVerdict, compose_review
from pdlc.hosts import attachment_host, code_host, workitem_host

BODY_DEFAULT = """## Product

### 4. Functional requirements
- FR-1: The record lands.
- FR-2: The record publishes.

### 5. Constraints
- C-1: Commands own every mutation.

## UI

UJ-1 covers the first run.

## Decisions
- none

## Open Questions
- none
"""

TASK_BODY_DEFAULT = "## Scope\nx\n\n## Acceptance criteria\n- ok\n"

def _file_config() -> Config:
    return Config(
        backend="file",
        code_host="file",
        attachment_host="file",
        actor="tester",
        no_sleep=True,
    )


class Result:
    """The outcome of one command invocation."""

    def __init__(self, code: int, stdout: str, stderr: str):
        self.code = code
        self.stdout = stdout
        self.stderr = stderr

    @property
    def json(self) -> dict:
        return json.loads(self.stdout)

    def front_matter(self, key: str) -> str | None:
        match = re.search(rf"^{re.escape(key)}: (.*)$", self.stdout, re.MULTILINE)
        if match is None:
            return None
        return match.group(1).strip().strip('"')


class FileBackendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp(prefix="pdlc-home-"))
        self.work = Path(tempfile.mkdtemp(prefix="pdlc-work-"))
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)

        self._saved_env: dict[str, str | None] = {}
        # `PDLC_HOME` still points the file backend at its store; every other
        # setting now comes from the installed Config.
        for key in ("PDLC_HOME", "PDLC_REPOSITORY", "PDLC_DEBUG"):
            self._saved_env[key] = os.environ.get(key)
        os.environ["PDLC_HOME"] = str(self.home)
        os.environ.pop("PDLC_REPOSITORY", None)
        os.environ.pop("PDLC_DEBUG", None)
        install_config(replace(_file_config(), cache_root=str(self.work)))
        capabilities = mock.patch("pdlc.config._capabilities", Capabilities.empty())
        capabilities.start()
        self.addCleanup(capabilities.stop)

        (self.home / "records").mkdir(parents=True)
        (self.home / "seq").write_text("40")

        self._reset_hosts()
        # The suite runs inside a developer checkout whose own uncommitted edits
        # must not trip `pdlc post verify`'s clean-tree guard.
        clean_tree = mock.patch("pdlc.commands.post_verify.has_tracked_changes", return_value=False)
        clean_tree.start()
        self.addCleanup(clean_tree.stop)
        self.addCleanup(self._restore_env)
        self.addCleanup(reset_config)
        self.addCleanup(self._reset_hosts)

    # --- environment / singletons ---

    def _reset_hosts(self) -> None:
        workitem_host.reset_backend()
        code_host.reset_code_host()
        attachment_host.reset_host()

    def _restore_env(self) -> None:
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def configure(self, **fields: object) -> None:
        """Override settings on the installed Config and rebuild the hosts."""
        set_config(**fields)
        self._reset_hosts()

    def set_home(self, path: object) -> None:
        os.environ["PDLC_HOME"] = str(path)

    # --- seeding ---

    def records_dir(self) -> Path:
        return self.home / "records"

    def seed_record(
        self,
        number: int,
        status: str,
        gate: str,
        *,
        slug: str | None = None,
        skipped: str = "",
        body: str | None = None,
        work_type: str | None = None,
    ) -> Path:
        directory = self.records_dir() / str(number)
        (directory / "tasks").mkdir(parents=True)
        (directory / "comments.jsonl").write_text("")
        (directory / "body.md").write_text(BODY_DEFAULT if body is None else body)
        metadata = {
            "id": f"FILE-{number}",
            "number": number,
            "title": f"Record {number}",
            "url": f"file://x/{number}",
            "fields": {
                "Status": status,
                "Gate State": gate,
                "Lifecycle": "Completed" if status == "Complete" else "Planning",
                "Skipped States": skipped,
                "Slug": slug or f"record-{number}",
            },
        }
        if work_type is not None:
            metadata["workType"] = work_type
        (directory / "meta.json").write_text(json.dumps(metadata, indent=2) + "\n")
        return directory

    def seed_task(
        self,
        record: int,
        number: int,
        task_id: str,
        state: str,
        title: str,
        *,
        body: str | None = None,
    ) -> Path:
        directory = self.records_dir() / str(record) / "tasks" / str(number)
        directory.mkdir(parents=True)
        (directory / "comments.jsonl").write_text("")
        (directory / "body.md").write_text(TASK_BODY_DEFAULT if body is None else body)
        (directory / "meta.json").write_text(
            json.dumps(
                {
                    "number": number,
                    "title": title,
                    "url": "file://x",
                    "state": state,
                    "taskId": task_id,
                }
            )
            + "\n"
        )
        return directory

    def _seed_task_comment(self, record: int, task_number: int, body: str) -> None:
        """Append one comment directly onto a seeded task's log, matching the
        file backend's own append shape (including its `commentSeq` counter,
        so a later real append or delete never collides with a seeded id).
        Lets a test seed pre-existing plan/implementation evidence without
        exercising the full `pdlc post plan`/`pdlc post implement-task` path."""
        directory = self.records_dir() / str(record) / "tasks" / str(task_number)
        comments_path = directory / "comments.jsonl"
        existing = [json.loads(line) for line in comments_path.read_text().splitlines() if line.strip()]
        meta_path = directory / "meta.json"
        meta = json.loads(meta_path.read_text())
        next_id = int(meta.get("commentSeq") or 0) + 1
        meta_path.write_text(json.dumps({**meta, "commentSeq": next_id}) + "\n")
        comment = {
            "body": body,
            "createdAt": f"2026-01-{next_id:02d}T00:00:00Z",
            "url": f"file://x#comment-{next_id}",
            "author": {"login": "tester"},
        }
        comments_path.write_text("".join(json.dumps(entry) + "\n" for entry in [*existing, comment]))

    def seed_implementation_comment(self, record: int, task_number: int, body: str) -> None:
        self._seed_task_comment(record, task_number, f"## Implementation\n\n{body}")

    def seed_plan_comment(self, record: int, task_number: int, body: str) -> None:
        self._seed_task_comment(record, task_number, f"## Technical Plan\n\n{body}")

    def seed_prs(self, record: int, pull_requests: list[dict], *, register: bool = True) -> None:
        path = self.records_dir() / str(record) / "pull_requests.json"
        path.write_text(json.dumps(pull_requests))
        if register:
            self.register_prs(record, [pr["number"] for pr in pull_requests])

    def register_prs(self, ref: int, numbers: list[int]) -> None:
        """Attach PR numbers to a record (or task) the way `pdlc post attach-pr`
        / `pdlc post implement` do — the registry the gates read. The file
        backend keeps them in the entity's own meta.json."""
        candidates = [self.records_dir() / str(ref)]
        task_path = self._task_path(ref)
        if task_path is not None:
            candidates.append(task_path)
        for base in candidates:
            meta_path = base / "meta.json"
            if meta_path.exists():
                break
        else:
            raise AssertionError(f"no record or task #{ref}")
        meta = json.loads(meta_path.read_text())
        meta["prs"] = sorted({*meta.get("prs", []), *numbers})
        meta_path.write_text(json.dumps(meta) + "\n")

    def _task_path(self, number: int):
        for record in self.records_dir().glob("*"):
            candidate = record / "tasks" / str(number)
            if candidate.is_dir():
                return candidate
        return None

    def green_pr(self, record: int, *, number: int = 900, checks: str = "SUCCESS") -> None:
        self.seed_prs(
            record,
            [
                {
                    "number": number,
                    "title": "impl",
                    "url": "u",
                    "state": "OPEN",
                    "isDraft": False,
                    "branch": "b",
                    "mergedAt": None,
                    "checks": checks,
                    "relation": "closes",
                }
            ],
        )

    def add_invalidation(self, record: int, stage: str = "Implementation") -> None:
        """Append one explicit driver invalidation."""
        log = self.records_dir() / str(record) / "comments.jsonl"
        entry = {
            "body": f"PDLC-INVALIDATED\n\nInvalidated stage: {stage}\ndetail",
            "createdAt": "2026-04-01T00:00:00Z",
            "url": "",
            "author": {"login": "t"},
        }
        with log.open("a") as handle:
            handle.write(json.dumps(entry) + "\n")

    def add_rework_review(self, record: int, stage: str = "Implementation", loop: str = "delivery-rework") -> None:
        """Append one structured Verification bounce into a named rework loop."""
        log = self.records_dir() / str(record) / "comments.jsonl"
        entry = {
            "body": (
                "PDLC-REVIEW\n\n---\nstage: Verification\nverdict: Changes Required\n"
                f"bounce: {stage}\nloop: {loop}\n---\n\n## Findings\n\n- detail\n"
            ),
            "createdAt": "2026-04-01T00:00:00Z",
            "url": "",
            "author": {"login": "t"},
        }
        with log.open("a") as handle:
            handle.write(json.dumps(entry) + "\n")

    def seed_publication(self, record: int, stage: str, *, passed_review: bool | None = None) -> None:
        """Append `stage`'s publication comment — the evidence approval reads —
        dated after every other seeded record comment. Implementation and
        Testing, reviewed only after they publish, also get a passing review
        unless `passed_review` is False."""
        marker = {
            "Product": "PRODUCT", "UI": "UI", "Tasks": "TASKS", "Technical Plan": "PLAN",
            "Implementation": "IMPLEMENTATION", "Testing": "TESTING",
        }[stage]
        entries = [(f"PDLC-{marker}\n\n{stage} published.\n", "2026-05-01T00:00:00Z")]
        if passed_review if passed_review is not None else stage in ("Implementation", "Testing"):
            entries.append((
                "PDLC-REVIEW\n\n" + compose_review(stage, ReviewVerdict.PASS, "## Findings\n\n- none"),
                "2026-05-02T00:00:00Z",
            ))
        log = self.records_dir() / str(record) / "comments.jsonl"
        with log.open("a") as handle:
            for body, created in entries:
                handle.write(json.dumps({"body": body, "createdAt": created, "url": "", "author": {"login": "t"}}) + "\n")

    # --- scratch files ---

    def write_file(self, name: str, content: str) -> str:
        path = self.work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return str(path)

    def evidence_file(self, content: str = "evidence body\n") -> str:
        return self.write_file("evidence.md", content)

    @staticmethod
    def implementation_summary(line: str = "Shipped it.") -> str:
        """A body that satisfies the implementation-summary template, carrying `line`."""
        return f"### Why\n\n- {line}\n\n### What changed\n\n- {line}\n\n### Verified\n\n- Tests pass.\n"

    def head_sha(self) -> str:
        """The real repository HEAD — verification/completion freshness checks
        shell out to git, and only a resolvable commit survives them."""
        import subprocess

        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()

    def verify_report(self, record: int, **overrides: object) -> str:
        """A `pdlc.verify/1` report file for `record`: `pdlc inspect verify`'s
        own pre-filled report with every open result settled clean, then
        `overrides` applied over its top-level fields."""
        inspected = self.invoke("inspect_verify", record)
        match = re.search(r"Filled in at (\S+\.json)", inspected.stdout)
        if match is None:
            raise AssertionError(f"inspect verify wrote no report:\n{inspected.stdout}{inspected.stderr}")
        report = json.loads(Path(match.group(1)).read_text())
        for row in report["claims"]:
            row["result"] = row["result"] or "confirmed"
        for row in report["journeys"] or []:
            row["result"] = row["result"] or "accepted"
        report["ux"]["result"] = report["ux"]["result"] or "clean"
        report["cumulativeReview"]["result"] = report["cumulativeReview"]["result"] or "clean"
        for comment in report["openComments"]:
            comment.update(action=comment["action"] or "no_action", note=comment["note"] or "out of scope")
        report.update(overrides)
        return self.write_file(f"verify-{record}.json", json.dumps(report))

    # --- invocation ---

    def invoke(self, command: str, *args: object, stdin: str | None = None) -> Result:
        module = importlib.import_module(f"pdlc.commands.{command}")
        out, err = io.StringIO(), io.StringIO()
        saved_argv, saved_stdin = sys.argv, sys.stdin
        sys.argv = [f"pdlc {command}", *[str(argument) for argument in args]]
        if stdin is not None:
            sys.stdin = io.StringIO(stdin)
        try:
            with redirect_stdout(out), redirect_stderr(err):
                try:
                    code = int(module.main())
                except SystemExit as exit_error:  # some commands exit rather than return
                    code = int(exit_error.code or 0)
        finally:
            sys.argv, sys.stdin = saved_argv, saved_stdin
        return Result(code, out.getvalue(), err.getvalue())

    def next(self, *args: object, stdin: str | None = None) -> Result:
        # `next` is a module name, not the builtin, inside pdlc.commands.
        return self.invoke("next", *args, stdin=stdin)

    # --- record inspection ---

    def meta(self, number: int) -> dict:
        return json.loads((self.records_dir() / str(number) / "meta.json").read_text())

    def fields(self, number: int) -> dict:
        return self.meta(number)["fields"]

    def state(self, number: int) -> tuple[str, str]:
        fields = self.fields(number)
        return fields["Status"], fields["Gate State"]

    def body(self, number: int) -> str:
        return (self.records_dir() / str(number) / "body.md").read_text()

    def comments_text(self, number: int) -> str:
        return (self.records_dir() / str(number) / "comments.jsonl").read_text()

    def task_meta(self, record: int, task_number: int) -> dict:
        path = self.records_dir() / str(record) / "tasks" / str(task_number) / "meta.json"
        return json.loads(path.read_text())

    def task_comments_text(self, record: int, task_number: int) -> str:
        path = self.records_dir() / str(record) / "tasks" / str(task_number) / "comments.jsonl"
        return path.read_text()

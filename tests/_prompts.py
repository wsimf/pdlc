"""Shared seeding and host-state patching for the `pdlc prompt` suites.

Not named `test_*.py` on purpose: this is a harness, not a suite, so discovery
leaves it alone and both the behavioural tests and the golden tests inherit the
same record, task, and pull-request fixtures. A brief that two suites disagree
about the setup of would prove nothing.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from tests._support import FileBackendTest


class _Capabilities:
    """The subset of the capability facade the briefs touch."""

    def __init__(self, skills: dict[str, str]):
        self.skills = skills
        self.agents: dict[str, str] = {}

    def skill(self, slot: str) -> str:
        return self.skills.get(slot, "")

    def agent(self, slot: str) -> str:
        return self.agents.get(slot) or "general-purpose"


class PromptHarness(FileBackendTest):
    def setUp(self) -> None:
        super().setUp()
        self.configure(code_host="github", repository="acme/widgets")
        # Live PR and review-thread state would need a real `gh`; every test
        # states the host state it needs, and reads clean otherwise.
        self._prs([])
        self._threads([])
        self._uncommitted("")

    # --- host state ---

    # Every command that reads live PR or thread state imports the reader by
    # name, so each one is patched; the brief and the inspector it mirrors then
    # always see the same host state.
    _PR_READERS = ("prompt", "inspect", "inspect_implement", "inspect_test", "inspect_verify", "inspect_complete")
    _THREAD_READERS = ("prompt", "inspect_implement", "inspect_verify")

    def _prs(self, pull_requests: list[dict]) -> None:
        for module in self._PR_READERS:
            patcher = patch(f"pdlc.commands.{module}.record_pull_requests", return_value=pull_requests)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _threads(self, threads: list[dict]) -> None:
        for module in self._THREAD_READERS:
            patcher = patch(f"pdlc.commands.{module}.record_open_review_comments", return_value=threads)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _uncommitted(self, status: str) -> None:
        """The working tree's `git status --short`; clean unless a test says so."""
        patcher = patch("pdlc.commands.prompt.uncommitted_changes", return_value=status)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _capabilities(self, **skills: str) -> None:
        """Route skill slots the briefs read, which otherwise read unconfigured.

        Both seams are patched because the briefs resolve capabilities two ways:
        the implementation brief asks the config facade directly, while the test
        brief goes through `pdlc inspect capability`'s own resolution to get the
        sentence it prints. Slot names are dashed, so pass them as a mapping.
        """
        slots = {slot.replace("_", "-"): name for slot, name in skills.items()}
        capabilities = _Capabilities(slots)
        for target in ("pdlc.commands.prompt.get_capabilities", "pdlc.commands.inspect_capability.get_capabilities"):
            patcher = patch(target, return_value=capabilities)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _build_run(self, name: str) -> None:
        self._capabilities(**{"build-run": name})

    def _git(self, stat: str = "abc1234 impl\n 1 file changed", diff: str = "diff --git a/x b/x") -> None:
        for target, value in (
            ("pdlc.commands.prompt.diff_stat", stat),
            ("pdlc.commands.prompt.diff_text", diff),
            ("pdlc.commands.prompt.touched_files", ["src/a.py", "src/b.py"]),
        ):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def _review(implementation: str = "None", test: str = "None", verdict: str = "Changes Required") -> str:
        """A filled task review findings file, as `text:` input."""
        return (
            "text:Task review complete: WORK-60-TASK-001\n\n"
            f"### Implementation findings\n\n{implementation}\n\n"
            f"### Test findings\n\n{test}\n\n"
            f"### Verdict\n\n{verdict}\n"
        )

    # --- seeding ---

    def _plan(self, record: int, task: int, body: str = "## Technical Plan\n\nTouch one module.\n") -> None:
        self.seed_plan_comment(record, task, body.split("\n\n", 1)[1].strip())

    def _eligible_task(self, *, body: str | None = None) -> None:
        self.seed_record(60, "Implementation", "Pending", slug="record-60")
        self.seed_task(
            60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work",
            body=body or "## Scope\nBuild the seam.\n\nCovers FR-1.\n\n## Acceptance criteria\n- it works\n",
        )
        self._plan(60, 601)

    def _implemented_stack(self, gate: str = "Changes Required", status: str = "Implementation") -> None:
        self.seed_record(60, status, gate, slug="record-60")
        self.seed_task(60, 601, "TASK-001", "CLOSED", "WORK-60-TASK-001 [CORE] First")
        self.seed_task(60, 602, "TASK-002", "CLOSED", "WORK-60-TASK-002 [UI] Second")
        for number in (601, 602):
            self._plan(60, number)
            self.seed_implementation_comment(60, number, "Shipped.")
        self.register_prs(601, [40])
        self.register_prs(602, [41])

    def _second_task_eligible(self) -> None:
        """TASK-001 implemented and closed, so TASK-002 is the unit and has an
        upstream predecessor to summarise."""
        self._eligible_task()
        self.seed_task(60, 602, "TASK-002", "OPEN", "WORK-60-TASK-002 [UI] Second")
        self._plan(60, 602)
        self.seed_implementation_comment(60, 601, "Added the loader.")
        self.register_prs(601, [40])
        path = self.records_dir() / "60" / "tasks" / "601" / "meta.json"
        path.write_text(path.read_text().replace('"OPEN"', '"CLOSED"'))

    def _invalidated_task(self) -> None:
        """An implemented task returned for rework: the PR survives, the
        `## Implementation` comment does not."""
        self._eligible_task()
        self.seed_implementation_comment(60, 601, "Shipped.")
        self.register_prs(601, [40])
        self.add_invalidation(60)
        path = self.records_dir() / "60" / "tasks" / "601" / "comments.jsonl"
        kept = [line for line in path.read_text().splitlines() if "## Implementation" not in line]
        path.write_text("".join(f"{line}\n" for line in kept))

    def _tasks_stage_pending(self) -> None:
        """A first-pass Tasks record with no delivery tasks yet."""
        self.seed_record(60, "Tasks", "Pending", slug="record-60")

    def _tasks_stage_stale_with_existing_tree(self) -> None:
        """A Tasks record returned for rework, with one existing task to
        reconcile against and a recorded reason it went Stale."""
        self.seed_record(60, "Tasks", "Stale", slug="record-60")
        self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work")
        self.add_invalidation(60, stage="Tasks")

    def _plan_stage(self, gate: str = "Pending") -> None:
        """A Technical Plan record: one task planned, one needing a plan, and
        one already implemented that the brief must leave out."""
        self.seed_record(60, "Technical Plan", gate, slug="record-60")
        self.seed_task(
            60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work",
            body="## Scope\nBuild the seam.\n\nCovers FR-1.\n\n## Acceptance criteria\n- it works\n",
        )
        self._plan(60, 601)
        self.seed_task(
            60, 602, "TASK-002", "OPEN", "WORK-60-TASK-002 [UI] Second",
            body="## Scope\nShow it.\n\nCovers FR-2, UJ-1.\n\n## Acceptance criteria\n- it shows\n",
        )
        self.seed_task(60, 603, "TASK-003", "CLOSED", "WORK-60-TASK-003 [CORE] Done")
        self._plan(60, 603)
        self.seed_implementation_comment(60, 603, "Shipped.")

    def _testing_stack(self, gate: str = "Pending") -> None:
        """Both tasks implemented and the record at Testing, each PR touching
        its own files plus one shared file, so the brief's source list must
        de-duplicate."""
        self._implemented_stack(gate, status="Testing")
        self._prs([
            {"number": number, "title": "t", "url": f"u{number}", "state": "OPEN", "isDraft": False,
             "branch": "b", "mergedAt": None, "checks": "SUCCESS"}
            for number in (40, 41)
        ])
        files = {40: ["src/a.py", "src/shared.py"], 41: ["src/b.py", "src/shared.py"]}
        patcher = patch("pdlc.commands.inspect_test._files_for_pull_request", side_effect=lambda pr: files[pr["number"]])
        patcher.start()
        self.addCleanup(patcher.stop)

    # --- upstream changes ---

    def _log(self, *bodies: str) -> None:
        """Append record comments dated in order after every other seeded one,
        so a scenario reads as the sequence it was written in."""
        self.logged = getattr(self, "logged", 0)
        log = self.records_dir() / "60" / "comments.jsonl"
        with log.open("a") as handle:
            for body in bodies:
                self.logged += 1
                entry = {"body": body, "createdAt": f"2026-06-{self.logged:02d}T00:00:00Z", "url": "", "author": {"login": "t"}}
                handle.write(json.dumps(entry) + "\n")

    def _at(self, status: str, gate: str) -> None:
        path = self.records_dir() / "60" / "meta.json"
        meta = json.loads(path.read_text())
        meta["fields"].update({"Status": status, "Gate State": gate})
        path.write_text(json.dumps(meta))

    def _patch_back_to_ui(self, impact: str) -> None:
        """A Product patch from Technical Plan that returned the record to UI,
        then the reworked UI landing and approved."""
        self._log(
            "PDLC-PRODUCT\n\npatched product",
            "PDLC-PATCHED\n\nPatched stage: Product\nActive stage: Technical Plan / Pending\n"
            f"Returned to: UI / Stale\n\n{impact}",
            f"PDLC-INVALIDATED\n\nInvalidated stage: UI\n\nReturned by a patch of Product; {impact}",
        )
        self._log("PDLC-UI\n\nreworked", "PDLC-APPROVED\n\nUI approved")

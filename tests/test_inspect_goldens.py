"""Whole-output goldens for the `pdlc inspect` family: what an inspector prints
is the contract a skill reads and routes on, so its wording, section order, and
spacing are checked in full rather than sampled with substring assertions.

Each case seeds one record shape through the same fixtures the prompt goldens
use, so an inspector and the brief built from it are pinned against identical
state. Commands with a compact index are rendered with `--full`, since the
full text is what the index points at. Regenerate after an intended edit with:

    PDLC_UPDATE_GOLDENS=1 uv run python -m unittest tests.test_inspect_goldens

then read the resulting diff before committing it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

from pdlc.domain.evidence import ReviewVerdict, compose_review
from pdlc.domain.stages import Gate
from pdlc.domain.verification import Report, Row, render
from tests._goldens import GoldenMixin
from tests._prompts import PromptHarness

HEAD = "0" * 40

BODY_WITH_JOURNEY = """## Product

### 4. Functional requirements
- FR-1: The record lands.

## UI

### UJ-1: First run

- Entry: cold launch
- Flow: the app opens to the map
- Criteria: the map is interactive within 2s

## Decisions
- none

## Open Questions
- Q-1: Should the cache survive a relaunch?
"""


def _pr(number: int, *, state: str = "OPEN", checks: str = "SUCCESS") -> dict:
    return {
        "number": number, "title": "t", "url": f"u{number}", "state": state, "isDraft": False,
        "branch": "b", "mergedAt": "2026-01-02T00:00:00Z" if state == "MERGED" else None, "checks": checks,
    }


class InspectHarness(GoldenMixin, PromptHarness):
    """The pinned host state and record shapes both inspect golden suites seed."""

    GOLDENS = Path(__file__).parent / "fixtures" / "inspect"

    def setUp(self) -> None:
        super().setUp()
        # Pin every live git and stack read so a golden never depends on the
        # developer checkout it happens to run in.
        for target, value in (
            ("pdlc.internal.stack.worktree_after", None),
            ("pdlc.hosts.lib.github.code_host.GitHubCodeHost._current_stack", None),
            ("pdlc.commands.inspect_test.head_commit", HEAD),
            ("pdlc.commands.inspect_verify.head_commit", HEAD),
            ("pdlc.internal.verification.changed_files", set()),
            ("pdlc.hosts.lib.github.code_host.GitHubCodeHost.pull_request_files", ["src/a.py"]),
        ):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _user_comment(self, record: int, body: str) -> None:
        with (self.records_dir() / str(record) / "comments.jsonl").open("a") as handle:
            handle.write(json.dumps({
                "body": body, "createdAt": "2026-03-01T00:00:00Z", "url": "file://x#c", "author": {"login": "driver"},
            }) + "\n")

    def _verification_stack(self, gate: str = "Pending") -> None:
        """Both tasks implemented, merged, and green, with the record at
        Verification and a journey plus a live Open Question to disposition."""
        self._implemented_stack(gate, status="Verification")
        (self.records_dir() / "60" / "body.md").write_text(BODY_WITH_JOURNEY)
        self._prs([_pr(40, state="MERGED"), _pr(41, state="MERGED")])

    def _ready_to_complete(self) -> None:
        """A Verification record every completion check passes: each stage
        published and approved, and a clean verification report at HEAD."""
        self._verification_stack(gate="Approval Required")
        for stage in ("Product", "UI", "Tasks", "Technical Plan", "Implementation", "Testing"):
            self.seed_publication(60, stage)
            self._user_comment(60, f"PDLC-APPROVED\n\n{stage} approved.")
        report = Report(
            head=HEAD, run_at="2026-06-01 00:00 UTC", recommendation="Approval Required",
            claims=(Row("TASK-001", "confirmed"), Row("TASK-002", "confirmed")),
            journeys=(Row("UJ-1", "accepted"),), ux=Row("ux", "clean"), cumulative=Row("cumulative", "clean"),
        )
        self._user_comment(60, "PDLC-REVIEW\n\n" + compose_review("Verification", ReviewVerdict.PASS, render(report)))


class InspectGoldenTest(InspectHarness):
    """Targeted cases: one record shape per command-specific branch."""

    # --- inspect (overview) ---

    def test_overview_product_pending(self):
        self.seed_record(60, "Product", "Pending", slug="record-60")
        self.assertGolden("overview-product-pending", self.invoke("inspect", 60, "--full"))

    def test_overview_plan_stage_mixed_tasks(self):
        self._plan_stage()
        self._user_comment(60, "Please keep the loader behind a flag.")
        self.assertGolden("overview-plan-stage", self.invoke("inspect", 60, "--full"))

    def test_overview_implementation_with_red_checks(self):
        self._implemented_stack()
        self._prs([_pr(40, checks="FAILURE"), _pr(41)])
        self.assertGolden("overview-implementation-red-checks", self.invoke("inspect", 60, "--full"))

    def test_overview_compact_index(self):
        self._plan_stage()
        self.assertGolden("overview-compact", self.invoke("inspect", 60))

    # --- inspect task ---

    def test_task_planned(self):
        self._eligible_task()
        self.assertGolden("task-planned", self.invoke("inspect_task", 601))

    def test_task_several(self):
        self._plan_stage()
        self.assertGolden("task-several", self.invoke("inspect_task", 601, 602, 603))

    def test_task_invalidated(self):
        self._invalidated_task()
        self.assertGolden("task-invalidated", self.invoke("inspect_task", 601))

    # --- inspect task timeline ---

    def test_task_timeline_implemented(self):
        self._implemented_stack()
        self.assertGolden("task-timeline-implemented", self.invoke("inspect_task_timeline", 601, "--full"))

    def test_task_timeline_unplanned(self):
        self._plan_stage()
        self.assertGolden("task-timeline-unplanned", self.invoke("inspect_task_timeline", 602, "--full"))

    # --- inspect timeline ---

    def test_timeline_published_and_reviewed(self):
        self.seed_record(60, "Implementation", "Changes Required", slug="record-60")
        self.seed_publication(60, "Implementation")
        self.add_rework_review(60)
        self.assertGolden("timeline-published-and-reviewed", self.invoke("inspect_timeline", 60, "--full"))

    def test_timeline_empty(self):
        self.seed_record(60, "Product", "Pending", slug="record-60")
        self.assertGolden("timeline-empty", self.invoke("inspect_timeline", 60, "--full"))

    # --- inspect comments ---

    def test_comments_mixed(self):
        self.seed_record(60, "Implementation", "Changes Required", slug="record-60")
        self.seed_publication(60, "Implementation")
        self._user_comment(60, "Looks close; one nit.")
        self.assertGolden("comments-mixed", self.invoke("inspect_comments", 60))

    # --- inspect changes ---

    def test_changes_never_published(self):
        self.seed_record(60, "Implementation", "Changes Required", slug="record-60")
        self.add_rework_review(60)
        self.add_invalidation(60)
        self.assertGolden("changes-never-published", self.invoke("inspect_changes", 60))

    def test_changes_all_addressed(self):
        self.seed_record(60, "Implementation", "Changes Required", slug="record-60")
        self.add_rework_review(60)
        self.seed_publication(60, "Implementation", passed_review=False)
        self.assertGolden("changes-all-addressed", self.invoke("inspect_changes", 60))

    def test_changes_for_another_stage(self):
        self.seed_record(60, "Implementation", "Pending", slug="record-60")
        self.add_invalidation(60, stage="Technical Plan")
        self.assertGolden("changes-other-stage", self.invoke("inspect_changes", 60, "--stage", "Technical Plan"))

    # --- inspect implement ---

    def test_implement_first_task(self):
        self._eligible_task()
        self.assertGolden("implement-first-task", self.invoke("inspect_implement", 60))

    def test_implement_later_task(self):
        self._second_task_eligible()
        self.assertGolden("implement-later-task", self.invoke("inspect_implement", 60))

    def test_implement_invalidated(self):
        self._invalidated_task()
        self.assertGolden("implement-invalidated", self.invoke("inspect_implement", 60))

    def test_implement_rework_threads(self):
        self._implemented_stack()
        self._threads([
            {"pr": 40, "author": "reviewer", "path": "src/a.py", "line": 4, "body": "drops retry", "url": "u1"},
        ])
        self.assertGolden("implement-rework-threads", self.invoke("inspect_implement", 60))

    def test_implement_rework_red_checks(self):
        self._implemented_stack()
        self._prs([_pr(40, checks="FAILURE")])
        self.assertGolden("implement-rework-red-checks", self.invoke("inspect_implement", 60))

    def test_implement_triage(self):
        self._implemented_stack()
        self.add_rework_review(60)
        self.assertGolden("implement-triage", self.invoke("inspect_implement", 60))

    def test_implement_publish(self):
        self._implemented_stack(gate="Pending")
        self.assertGolden("implement-publish", self.invoke("inspect_implement", 60))

    def test_implement_not_due(self):
        self._plan_stage()
        self.assertGolden("implement-not-due", self.invoke("inspect_implement", 60))

    # --- inspect review ---

    def test_review_implementation_due(self):
        self._implemented_stack(gate="Review Required")
        self.assertGolden("review-implementation-due", self.invoke("inspect_review", 60))

    def test_review_testing_due(self):
        self._testing_stack(gate="Review Required")
        self.assertGolden("review-testing-due", self.invoke("inspect_review", 60))

    def test_review_not_due(self):
        self._implemented_stack(gate="Pending")
        self.assertGolden("review-not-due", self.invoke("inspect_review", 60))

    def test_review_product_due(self):
        self.seed_record(60, "Product", "Review Required", slug="record-60")
        self.assertGolden("review-product-due", self.invoke("inspect_review", 60))

    def test_review_skipped_stage(self):
        self.seed_record(60, "Testing", "Review Required", slug="record-60", skipped="Testing")
        self.assertGolden("review-skipped-stage", self.invoke("inspect_review", 60))

    # --- inspect test ---

    def test_test_first_pass(self):
        self._testing_stack()
        self.assertGolden("test-first-pass", self.invoke("inspect_test", 60))

    def test_test_after_findings(self):
        self._testing_stack(gate="Changes Required")
        self.add_rework_review(60, stage="Testing")
        self.assertGolden("test-after-findings", self.invoke("inspect_test", 60))

    def test_test_not_due(self):
        self._implemented_stack(gate="Pending")
        self.assertGolden("test-not-due", self.invoke("inspect_test", 60))

    # --- inspect verify ---

    def _verify(self, name: str) -> None:
        result = self.invoke("inspect_verify", 60)
        self.assertGolden(name, result)
        match = re.search(r"Filled in at (\S+\.json)", result.stdout)
        if match is not None:
            # The pre-filled report is as much the contract as stdout; its run
            # time is the one field that moves on every call.
            report = json.loads(Path(match.group(1)).read_text())
            report["runAt"] = "<run-at>"
            self.assertGolden(name, json.dumps(report, indent=2) + "\n", suffix=".json")

    def test_verify_first_pass(self):
        self._verification_stack()
        self._verify("verify-first-pass")

    def test_verify_with_open_thread(self):
        self._verification_stack(gate="Changes Required")
        self._threads([
            {"pr": 40, "author": "reviewer", "path": "src/a.py", "line": 4, "body": "fix the null case", "url": "u1"},
        ])
        self._verify("verify-open-thread")

    def test_verify_not_due(self):
        self._implemented_stack(gate="Pending")
        self._verify("verify-not-due")

    # --- inspect complete ---

    def test_complete_not_due(self):
        self._verification_stack()
        self.assertGolden("complete-not-due", self.invoke("inspect_complete", 60))

    def test_complete_awaiting_approval(self):
        self._verification_stack(gate="Approval Required")
        self.assertGolden("complete-awaiting-approval", self.invoke("inspect_complete", 60))

    def test_complete_ready(self):
        self._ready_to_complete()
        self.assertGolden("complete-ready", self.invoke("inspect_complete", 60))

    def test_complete_with_open_task_and_red_pr(self):
        self._verification_stack(gate="Approval Required")
        self.seed_task(60, 603, "TASK-003", "OPEN", "WORK-60-TASK-003 [CORE] Follow-up")
        self._prs([_pr(40, state="MERGED"), _pr(41, checks="FAILURE")])
        self.assertGolden("complete-blocked", self.invoke("inspect_complete", 60))

    # --- inspect capability ---

    def test_capability_all_unset(self):
        self.assertGolden("capability-all-unset", self.invoke("inspect_capability"))

    def test_capability_configured_slot(self):
        self._capabilities(**{"test-authoring": "acme-test-writer"})
        self.assertGolden("capability-configured-slot", self.invoke("inspect_capability", "test-authoring"))

    def test_capability_unset_slot(self):
        self.assertGolden("capability-unset-slot", self.invoke("inspect_capability", "test-authoring"))


# The Feature workflow's stages, in order. Listed rather than read off the
# pipeline so a golden's name never moves when the workflow definition does.
STAGES = ("Product", "UI", "Tasks", "Technical Plan", "Implementation", "Testing", "Verification")

# Every inspector whose output turns on Status and Gate State, rendered for
# each cell in this order under its own `## $ pdlc ...` heading.
MATRIX_COMMANDS = (
    ("inspect", "--full"), ("inspect_implement",), ("inspect_review",),
    ("inspect_test",), ("inspect_verify",), ("inspect_complete",),
)


class InspectMatrixGoldenTest(InspectHarness):
    """One golden per (stage, gate) cell of the Feature workflow, holding every
    stage-sensitive inspector's output for that cell, so a routing or readiness
    change shows up as a diff of exactly the cells it moves.

    Each cell seeds the record shape its stage normally has — tasks and PRs
    from Implementation on — plus the evidence its gate implies: a review for
    Changes Required, an invalidation for Stale, a decision for Decision
    Required. Cells the workflow rejects outright are kept: their refusal is
    pinned too. Test methods are generated per cell below.

    Implementation cells seed one task done and one open; the gates in
    `ALL_TASKS_DONE_GATES` also get an `--all-tasks-done` cell, where every
    task is implemented and closed."""

    def _seed_stage(self, stage: str, gate: str, all_tasks_done: bool = False) -> None:
        if stage == "Tasks":
            self.seed_record(60, stage, gate, slug="record-60")
            self.seed_task(60, 601, "TASK-001", "OPEN", "WORK-60-TASK-001 [CORE] Core work")
        elif stage == "Technical Plan":
            self._plan_stage(gate)
        elif stage == "Implementation" and all_tasks_done:
            self._implemented_stack(gate)
            self._prs([_pr(40), _pr(41)])
        elif stage == "Implementation":
            self._second_task_eligible()
            self._set_state(stage, gate)
            self._prs([_pr(40)])
        elif stage == "Testing":
            self._testing_stack(gate)
        elif stage == "Verification":
            self._verification_stack(gate)
        else:
            self.seed_record(60, stage, gate, slug="record-60")
        if gate == Gate.CI_PENDING and stage not in ("Implementation", "Testing", "Verification"):
            self._prs([_pr(90)])

    def _set_state(self, stage: str, gate: str) -> None:
        path = self.records_dir() / "60" / "meta.json"
        meta = json.loads(path.read_text())
        meta["fields"].update({"Status": stage, "Gate State": gate})
        path.write_text(json.dumps(meta, indent=2) + "\n")

    def _seed_gate_evidence(self, stage: str, gate: str) -> None:
        if gate == Gate.CHANGES_REQUIRED:
            body = compose_review(stage, ReviewVerdict.CHANGES_REQUIRED, "## Findings\n\n- Tighten section 2.")
            self._user_comment(60, "PDLC-REVIEW\n\n" + body)
        elif gate == Gate.STALE:
            self.add_invalidation(60, stage=stage)
        elif gate == Gate.DECISION_REQUIRED:
            self._user_comment(60, "PDLC-DECISION\n\n## Decision Required\n\nOn-device vs server-side snapping?")

    def check_cell(self, stage: str, gate: str, all_tasks_done: bool = False) -> None:
        self._seed_stage(stage, gate, all_tasks_done)
        self._seed_gate_evidence(stage, gate)
        blocks = []
        for command, *args in MATRIX_COMMANDS:
            result = self.invoke(command, 60, *args)
            shown = " ".join(["pdlc", *command.split("_"), "60", *args])
            # A cell the workflow rejects is pinned by its refusal: the exit
            # code and stderr are as much the contract as a ready render.
            output = result.stdout if result.code == 0 else f"exit {result.code}\n\n{result.stdout}{result.stderr}"
            blocks.append(f"## $ {shown}\n\n{output.rstrip()}\n")
        name = f"{stage}--{gate}".lower().replace(" ", "-") + ("--all-tasks-done" if all_tasks_done else "")
        self.assertGolden(f"matrix/{name}", "\n".join(blocks))


# Implementation gates where "every task done" routes differently from "a task
# still open", so each gets a second cell with all tasks implemented.
ALL_TASKS_DONE_GATES = (Gate.PENDING, Gate.CHANGES_REQUIRED)


def _cell_test(stage: str, gate: str, all_tasks_done: bool = False):
    def test(self: InspectMatrixGoldenTest) -> None:
        self.check_cell(stage, gate, all_tasks_done)
    return test


for _stage in STAGES:
    for _gate in Gate:
        _name = f"test_{_stage}_{_gate.value}".lower().replace(" ", "_")
        setattr(InspectMatrixGoldenTest, _name, _cell_test(_stage, _gate.value))

for _gate in ALL_TASKS_DONE_GATES:
    _name = f"test_implementation_{_gate.value}_all_tasks_done".lower().replace(" ", "_")
    setattr(InspectMatrixGoldenTest, _name, _cell_test("Implementation", _gate.value, all_tasks_done=True))

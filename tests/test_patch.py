"""Upstream patch mode: the `patched` transition and its policy, `--patch` on
`pdlc post write` / `pdlc post tasks`, the patches `pdlc inspect` surfaces at
Approval Required, and the internal `pdlc prompt patch-reviewer` brief."""

from __future__ import annotations

import json
import unittest

from _support import BODY_DEFAULT, FileBackendTest

from pdlc import cli
from pdlc.commands import prompt
from pdlc.commands.inspect import _due_next_section
from pdlc.domain.completion import SETTLEMENT_MARKERS
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.patch import impact_verdict, patches_since_approval, plan_patch, require_no_impact
from pdlc.domain.workflow import Event, Gate, InvalidationPolicy, State
from pdlc.domain.workflows.workflow_feature import FEATURE_PIPELINE

NO_IMPACT = "Earliest affected stage: none\n\n## UI\nUnaffected.\n## Tasks\nUnaffected.\n"
PRODUCT_PATCH = BODY_DEFAULT.split("## UI")[0].replace("The record lands.", "The record lands atomically.") + (
    "## Decisions\n- none\n"
)


class PatchPolicyTests(unittest.TestCase):
    pipeline = FEATURE_PIPELINE

    def test_patch_matrix_allows_only_upstream_planning_artifacts_from_planning_stages(self):
        allowed = {
            ("UI", "Product"),
            ("Tasks", "Product"), ("Tasks", "UI"),
            ("Technical Plan", "Product"), ("Technical Plan", "UI"), ("Technical Plan", "Tasks"),
        }
        stages = self.pipeline.active_stage_names
        for active in stages:
            for target in stages:
                with self.subTest(active=active, target=target):
                    self.assertEqual(self.pipeline.can_patch(active, target), (active, target) in allowed)

    def test_patched_keeps_work_gates_and_resets_published_gates_to_stale(self):
        for gate in (Gate.PENDING, Gate.CHANGES_REQUIRED, Gate.STALE):
            with self.subTest(gate=gate):
                state = State("Technical Plan", gate)
                self.assertEqual(self.pipeline.next_state(state, Event.PATCHED, requested_target="Product"), state)
        for gate in (Gate.REVIEW_REQUIRED, Gate.APPROVAL_REQUIRED):
            with self.subTest(gate=gate):
                target = self.pipeline.next_state(State("Technical Plan", gate), Event.PATCHED, requested_target="UI")
                self.assertEqual(target, State("Technical Plan", Gate.STALE))

    def test_patched_refuses_decision_required_and_unauthorised_targets(self):
        with self.assertRaisesRegex(ValueError, "pdlc guide decisions"):
            self.pipeline.next_state(State("Tasks", Gate.DECISION_REQUIRED), Event.PATCHED, requested_target="Product")
        with self.assertRaisesRegex(ValueError, "cannot patch"):
            self.pipeline.next_state(State("Implementation", Gate.PENDING), Event.PATCHED, requested_target="Product")
        with self.assertRaisesRegex(ValueError, "cannot patch"):
            self.pipeline.next_state(State("Tasks", Gate.PENDING), Event.PATCHED)

    def test_intermediate_stages_skip_declared_skips(self):
        self.assertEqual(self.pipeline.intermediate_stages("Product", "Technical Plan", set()), ("UI", "Tasks"))
        self.assertEqual(self.pipeline.intermediate_stages("Product", "Technical Plan", {"UI"}), ("Tasks",))
        self.assertEqual(self.pipeline.intermediate_stages("Tasks", "Technical Plan", set()), ())

    def test_patch_targets_must_be_upstream_reentry_targets(self):
        with self.assertRaisesRegex(ValueError, "upstream re-entry targets"):
            InvalidationPolicy({}, {"UI": ("Product", "UI")}, patch_targets={"UI": ("UI",)})
        with self.assertRaisesRegex(ValueError, "upstream re-entry targets"):
            InvalidationPolicy({}, {"UI": ("Product", "UI")}, patch_targets={"UI": ("Tasks",)})

    def test_impact_verdict_and_its_requirement(self):
        self.assertEqual(impact_verdict("Earliest affected stage: Tasks\nTASK-003"), "Tasks")
        with self.assertRaisesRegex(PdlcError, "no verdict"):
            impact_verdict("looks fine")
        plan = plan_patch(self.pipeline, State("Technical Plan", Gate.PENDING), "Product", set())
        self.assertTrue(plan.impact_required)
        with self.assertRaisesRegex(PdlcError, "--impact is required: UI, Tasks"):
            require_no_impact(plan, None)
        with self.assertRaisesRegex(PdlcError, "names Tasks as affected"):
            require_no_impact(plan, "Earliest affected stage: Tasks\n")
        require_no_impact(plan, NO_IMPACT)
        adjacent = plan_patch(self.pipeline, State("UI", Gate.PENDING), "Product", set())
        require_no_impact(adjacent, None)

    def test_patch_is_not_a_settlement(self):
        self.assertNotIn("PATCHED", SETTLEMENT_MARKERS)

    def test_patches_since_approval_ignores_patches_already_approved_past(self):
        comments = [
            {"body": "PDLC-PATCHED\n\nPatched stage: Product\nActive stage: UI / Pending\n", "createdAt": "2026-01-01T00:00:00Z"},
            {"body": "PDLC-APPROVED\n\nok", "createdAt": "2026-01-02T00:00:00Z"},
            {"body": "PDLC-PATCHED\n\nPatched stage: UI\nActive stage: Tasks / Pending\n", "createdAt": "2026-01-03T00:00:00Z"},
        ]
        self.assertEqual([patch["patchedStage"] for patch in patches_since_approval(comments)], ["UI"])


class PostWritePatchTests(FileBackendTest):
    def patch(self, number: int, *extra: object):
        body = self.write_file("product.md", PRODUCT_PATCH)
        return self.invoke("post_write", "--work-item", number, "--body", body, "--patch", *extra)

    def test_lands_product_without_moving_the_pointer(self):
        self.seed_record(70, "Technical Plan", "Pending")
        impact = self.write_file("impact.md", NO_IMPACT)
        result = self.patch(70, "--evidence", self.evidence_file(), "--impact", impact)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(self.state(70), ("Technical Plan", "Pending"))
        self.assertIn("The record lands atomically.", self.body(70))
        self.assertIn("## UI\n\nUJ-1 covers the first run.", self.body(70))
        comments = [json.loads(line)["body"] for line in self.comments_text(70).splitlines()]
        self.assertTrue(comments[0].startswith("PDLC-PRODUCT\n\nevidence body"))
        self.assertEqual(
            comments[1],
            "PDLC-PATCHED\n\nPatched stage: Product\nActive stage: Technical Plan / Pending\n\n" + NO_IMPACT.strip() + "\n",
        )
        self.assertEqual(result.json["gateState"], "Pending")

    def test_resets_a_published_active_stage_to_stale_and_needs_no_impact_next_door(self):
        self.seed_record(71, "UI", "Approval Required")
        result = self.patch(71, "--evidence", self.evidence_file())
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(self.state(71), ("UI", "Stale"))
        self.assertIn("No intermediate stages.", self.comments_text(71))

    def test_refusals_write_nothing(self):
        self.seed_record(72, "Technical Plan", "Pending")
        before = (self.body(72), self.comments_text(72))
        cases = {
            "--impact is required": (),
            "names Tasks as affected": ("--impact", self.write_file("bad.md", "Earliest affected stage: Tasks\n")),
        }
        for message, extra in cases.items():
            with self.subTest(message=message):
                result = self.patch(72, "--evidence", self.evidence_file(), *extra)
                self.assertEqual(result.code, 1)
                self.assertIn(message, result.stderr)
                self.assertEqual((self.body(72), self.comments_text(72)), before)
                self.assertEqual(self.state(72), ("Technical Plan", "Pending"))

    def test_refuses_changed_requirement_ids_when_intermediate_stages_exist(self):
        self.seed_record(73, "Technical Plan", "Pending")
        body = self.write_file("product.md", PRODUCT_PATCH.replace("- FR-2: The record publishes.\n", ""))
        impact = self.write_file("impact.md", NO_IMPACT)
        result = self.invoke(
            "post_write", "--work-item", 73, "--body", body, "--evidence", self.evidence_file(), "--patch", "--impact", impact,
        )
        self.assertEqual(result.code, 1)
        self.assertIn("removes FR-2", result.stderr)
        self.assertEqual(self.comments_text(73), "")

    def test_refuses_own_stage_delivery_stages_and_decisions(self):
        for number, (stage, gate, message) in enumerate((
            ("Product", "Pending", "land it normally"),
            ("Implementation", "Pending", "cannot patch Product"),
            ("Tasks", "Decision Required", "pdlc guide decisions"),
        ), start=74):
            with self.subTest(stage=stage, gate=gate):
                self.seed_record(number, stage, gate)
                result = self.patch(number, "--evidence", self.evidence_file())
                self.assertEqual(result.code, 1)
                self.assertIn(message, result.stderr)
                self.assertEqual(self.comments_text(number), "")

    def test_dry_run_reports_impact_and_requires_patch(self):
        self.seed_record(78, "Technical Plan", "Approval Required")
        result = self.patch(78, "--dry-run")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["impactRequired"], True)
        self.assertEqual(result.json["intermediateStages"], ["UI", "Tasks"])
        self.assertEqual(self.state(78), ("Technical Plan", "Approval Required"))
        self.assertEqual(self.comments_text(78), "")

        body = self.write_file("product.md", PRODUCT_PATCH)
        refused = self.invoke("post_write", "--work-item", 78, "--body", body, "--dry-run")
        self.assertEqual(refused.code, 1)
        self.assertIn("only valid with --patch", refused.stderr)


class PostTasksPatchTests(FileBackendTest):
    def seed_breakdown(self, number: int, status: str, gate: str) -> None:
        self.seed_record(number, status, gate)
        self.seed_task(number, 1, "TASK-001", "OPEN", f"WORK-{number}-TASK-001 [CORE] Land the record")
        self.seed_task(number, 2, "TASK-002", "OPEN", f"WORK-{number}-TASK-002 [UI] First run")

    def manifest(self, **overrides: object) -> str:
        entries = [
            {"id": "TASK-001", "title": "Land the record atomically", "body": self.write_file("t1.md", "## Scope\nnew\n"),
             "ui": False, "covers": ["FR-1", "FR-2", "C-1"], "depends": []},
            {"id": "TASK-002", "unchanged": True, "ui": True, "covers": ["UJ-1", "FR-1"], "depends": ["TASK-001"]},
        ]
        for key, value in overrides.items():
            entries[0][key] = value
        return self.write_file(f"manifest-{len(list(self.work.glob('manifest-*')))}.json", json.dumps(entries))

    def land(self, number: int, manifest: str, *extra: object):
        return self.invoke(
            "post_tasks", "--work-item", number, "--stage", "Tasks", "--manifest", manifest,
            "--evidence", self.evidence_file(), "--patch", *extra,
        )

    def test_tasks_patch_resets_a_published_plan_to_stale(self):
        self.seed_breakdown(80, "Technical Plan", "Review Required")
        result = self.land(80, self.manifest())
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(self.state(80), ("Technical Plan", "Stale"))
        self.assertEqual(self.task_meta(80, 1)["title"], "WORK-80-TASK-001 [CORE] Land the record atomically")
        self.assertIn("PDLC-TASKS", self.comments_text(80))
        self.assertIn("Patched stage: Tasks\\nActive stage: Technical Plan / Review Required", self.comments_text(80))
        self.assertEqual(result.json["patched"], "Tasks")

    def test_tasks_patch_refuses_shape_changes(self):
        cases = {
            "adds TASK-003": self.manifest(id="TASK-003"),
            "has none": self.manifest(id=None),
            "changes it": self.manifest(ui=True),
        }
        for number, (message, manifest) in enumerate(cases.items(), start=81):
            with self.subTest(message=message):
                self.seed_breakdown(number, "Technical Plan", "Pending")
                result = self.land(number, manifest)
                self.assertEqual(result.code, 1)
                self.assertIn(message, result.stderr)
                self.assertEqual(self.comments_text(number), "")
                self.assertEqual(self.task_meta(number, 1)["title"], f"WORK-{number}-TASK-001 [CORE] Land the record")

    def test_ui_patch_lands_and_keeps_applicability(self):
        self.seed_record(85, "Tasks", "Pending")
        body = self.write_file("ui.md", "UJ-1 covers the first run, offline too.\n")
        result = self.invoke(
            "post_tasks", "--work-item", 85, "--stage", "UI", "--body", body, "--evidence", self.evidence_file(), "--patch",
        )
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(self.state(85), ("Tasks", "Pending"))
        self.assertIn("offline too", self.body(85))

        no_ui = self.write_file("no-ui.md", "No user-facing surface.\n")
        refused = self.invoke(
            "post_tasks", "--work-item", 85, "--stage", "UI", "--body", no_ui, "--no-ui",
            "--evidence", self.evidence_file(), "--patch",
        )
        self.assertEqual(refused.code, 1)
        self.assertIn("UI applicability", refused.stderr)

    def test_ui_patch_refuses_changed_journeys_when_intermediate_stages_exist(self):
        self.seed_breakdown(86, "Technical Plan", "Pending")
        body = self.write_file("ui.md", "UJ-1 and UJ-2 cover the first run.\n")
        impact = self.write_file("impact.md", "Earliest affected stage: none\n")
        result = self.invoke(
            "post_tasks", "--work-item", 86, "--stage", "UI", "--body", body, "--evidence", self.evidence_file(),
            "--patch", "--impact", impact,
        )
        self.assertEqual(result.code, 1)
        self.assertIn("adds UJ-2", result.stderr)

    def test_dry_run_reports_the_patch(self):
        self.seed_breakdown(87, "Technical Plan", "Pending")
        result = self.invoke(
            "post_tasks", "--work-item", 87, "--stage", "Tasks", "--manifest", self.manifest(), "--dry-run", "--patch",
        )
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["impactRequired"], False)
        self.assertEqual(result.json["activeStage"], "Technical Plan")


class PatchVisibilityTests(FileBackendTest):
    def test_approval_required_lists_patches_since_last_approval(self):
        item = {"Status": "Technical Plan", "Gate State": "Approval Required", "Skipped States": "", "content": {"number": 90}}
        comments = [
            {"body": "PDLC-APPROVED\n\nok", "createdAt": "2026-01-02T00:00:00Z", "url": "u1"},
            {"body": "PDLC-PATCHED\n\nPatched stage: Product\nActive stage: Technical Plan / Pending\n",
             "createdAt": "2026-01-03T00:00:00Z", "url": "u2"},
        ]
        section = _due_next_section(item, comments, [])
        self.assertIn("### Patches Since Last Approval", section)
        self.assertIn("- Product — ", section)
        self.assertNotIn("### Patches", _due_next_section(item, comments[:1], []))

    def test_patch_reviewer_brief_names_the_stages_to_judge(self):
        self.seed_record(91, "Technical Plan", "Pending")
        body = self.write_file("product.md", PRODUCT_PATCH)
        result = self.invoke("prompt_patch_reviewer", 91, "--stage", "Product", "--body", body)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Artifacts to judge, in order: UI, Tasks", result.stdout)
        self.assertIn("The record lands atomically.", result.stdout)
        self.assertIn("Earliest affected stage:", result.stdout)

    def test_patch_reviewer_brief_is_refused_with_nothing_in_between(self):
        self.seed_record(92, "UI", "Pending")
        body = self.write_file("product.md", PRODUCT_PATCH)
        result = self.invoke("prompt_patch_reviewer", 92, "--stage", "Product", "--body", body)
        self.assertEqual(result.code, 1)
        self.assertIn("needs no impact report", result.stderr)

    def test_patch_reviewer_is_hidden_and_unroutable(self):
        self.assertEqual(cli._resolve(["prompt", "patch-reviewer"])[0], "pdlc.commands.prompt_patch_reviewer")
        self.assertNotIn("patch-reviewer", cli._usage())
        self.assertNotIn("patch-reviewer", prompt.__doc__ or "")
        self.assertNotIn("patch-reviewer", prompt.BRIEF_COMMANDS)
        from pdlc.config import get_capabilities

        self.assertNotIn("patch-reviewer", json.dumps(get_capabilities(), default=str))


if __name__ == "__main__":
    unittest.main()

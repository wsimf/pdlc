"""`Pipeline.heal()` never crosses a guard its equivalent `pdlc post` command enforces.

A heal corrects a state no command writes. The rule it must keep: the healed
state is exactly the one the equivalent command's transition produces from
the same starting point, so healing is never a shortcut past a check that
command would run. The domain half proves that for every pipeline, stage,
gate, and lifecycle; the CLI half runs `pdlc continue` beside the equivalent
command on a twin record and compares where they land, including when the
stage evidence `pdlc post approve` reads is missing, which only a record's
comments can show.
"""

from __future__ import annotations

import unittest

from _support import FileBackendTest
from pdlc.domain.workflow import Event, Gate, Lifecycle, Outcome, Pipeline, State, WorkType
from pdlc.domain.workflows.pipeline import PIPELINE_REGISTRY


def _pipelines() -> list[Pipeline]:
    """Every available pipeline; an unavailable work type has no stages to heal."""
    pipelines = []
    for work_type in WorkType:
        try:
            pipelines.append(PIPELINE_REGISTRY.for_work_type(work_type))
        except ValueError:
            continue
    return pipelines


def _equivalent(pipeline: Pipeline, state: State) -> State:
    """What the command a heal stands in for lands from the same stage."""
    stage = pipeline.stage(state.stage)
    if state.gate == Gate.APPROVED:
        # `pdlc post approve` from the stage's Approval Required; at the
        # completion boundary only `pdlc post complete` may go further.
        source = State(state.stage, Gate.APPROVAL_REQUIRED, state.lifecycle)
        if pipeline.completion_policy is not None and pipeline.completion_policy.is_boundary(source):
            return source
        return pipeline.next_state(source, Event.APPROVED)
    if state.gate == Gate.CI_PENDING:
        # The stage's own publishing command, which never waits on CI.
        return pipeline.next_state(State(state.stage, Gate.PENDING, state.lifecycle), Event.PUBLISHED)
    if state.gate == Gate.REVIEW_REQUIRED and stage.accepts_verification:
        # A clean `pdlc post verify` run.
        return pipeline.next_state(State(state.stage, Gate.PENDING, state.lifecycle), Event.VERIFIED, Outcome.CLEAN)
    if state.gate == Gate.REVIEW_REQUIRED:
        return pipeline.next_state(State(state.stage, Gate.PENDING, state.lifecycle), Event.PUBLISHED)
    raise AssertionError(f"heal() corrected {state.notation}, which has no equivalent command in this test")


class HealRuleTests(unittest.TestCase):
    def _heals(self):
        for pipeline in _pipelines():
            for stage in pipeline.stages:
                for gate in Gate:
                    for lifecycle in Lifecycle:
                        state = State(stage.name, gate, lifecycle)
                        healed = pipeline.heal(state)
                        if healed is not None:
                            yield pipeline, state, healed

    def test_the_rules_cover_every_documented_heal(self):
        notations = {state.notation for _, state, _ in self._heals()}
        self.assertIn("Tasks.Approved", notations)
        self.assertIn("Product.CIPending", notations)
        self.assertIn("Verification.ReviewRequired", notations)
        self.assertIn("Verification.Approved", notations)

    def test_every_heal_lands_a_valid_non_terminal_state(self):
        for pipeline, state, healed in self._heals():
            with self.subTest(pipeline=str(pipeline.work_type), state=state.notation, lifecycle=state.lifecycle.value):
                self.assertFalse(pipeline.validate_state(healed).terminal)
                self.assertIsNone(pipeline.heal(healed))

    def test_every_heal_equals_the_equivalent_commands_transition(self):
        for pipeline, state, healed in self._heals():
            with self.subTest(pipeline=str(pipeline.work_type), state=state.notation, lifecycle=state.lifecycle.value):
                self.assertEqual(healed, _equivalent(pipeline, state))

    def test_a_ci_gated_stage_never_heals_past_ci_pending(self):
        for pipeline, state, healed in self._heals():
            if pipeline.stage(state.stage).ci_gated and state.gate != Gate.APPROVED:
                with self.subTest(state=state.notation):
                    self.assertEqual(healed.gate, Gate.CI_PENDING)

    def test_an_active_stage_with_a_completed_lifecycle_is_never_healed(self):
        for pipeline in _pipelines():
            for stage in pipeline.stages:
                if stage.terminal:
                    continue
                for gate in Gate:
                    with self.subTest(stage=stage.name, gate=gate.value):
                        self.assertIsNone(pipeline.heal(State(stage.name, gate, Lifecycle.COMPLETED)))


class HealCommandTwinTests(FileBackendTest):
    def test_a_stray_approved_lands_where_post_approve_does(self):
        self.seed_record(81, "Tasks", "Approved")
        self.seed_record(82, "Tasks", "Approval Required")
        self.seed_publication(81, "Tasks")
        self.seed_publication(82, "Tasks")
        healed = self.invoke("continue_", 81)
        self.assertEqual(healed.code, 0, healed.stderr)
        approved = self.invoke("post_approve", 82, self.evidence_file())
        self.assertEqual(approved.code, 0, approved.stderr)
        self.assertEqual(self.state(81), self.state(82))
        self.assertIn("PDLC-APPROVED", self.comments_text(81))

    def test_a_stray_approved_without_evidence_stops_where_post_approve_refuses(self):
        # No publication on record: `pdlc post approve` refuses, so the heal
        # must not replay the approval either.
        self.seed_record(89, "Tasks", "Approved")
        self.seed_record(90, "Tasks", "Approval Required")
        healed = self.invoke("continue_", 89)
        self.assertEqual(healed.code, 0, healed.stderr)
        self.assertEqual(healed.json["to"], "Tasks.ApprovalRequired")
        refused = self.invoke("post_approve", 90, self.evidence_file())
        self.assertEqual(refused.code, 1)
        self.assertEqual(self.state(89), self.state(90))
        text = self.comments_text(89)
        self.assertNotIn("PDLC-APPROVED", text)
        self.assertIn("Tasks cannot be approved yet: no PDLC-TASKS publication of Tasks is on record.", text)

    def test_a_stray_approved_with_an_unreviewed_publication_stops_for_approval(self):
        self.seed_record(91, "Implementation", "Approved")
        self.seed_record(92, "Implementation", "Approval Required")
        self.seed_publication(91, "Implementation", passed_review=False)
        self.seed_publication(92, "Implementation", passed_review=False)
        routed = self.next("--work-item", 91)
        self.assertEqual(routed.code, 0, routed.stderr)
        self.assertEqual(routed.front_matter("action"), "human-approval")
        self.assertEqual(self.invoke("post_approve", 92, self.evidence_file()).code, 1)
        self.assertEqual(self.state(91), ("Implementation", "Approval Required"))
        self.assertEqual(self.state(91), self.state(92))

    def test_a_stray_ci_pending_lands_where_the_stages_land_does(self):
        self.seed_record(83, "UI", "CI Pending")
        self.seed_record(84, "UI", "Pending")
        self.assertEqual(self.invoke("continue_", 83).code, 0)
        ui = self.write_file("ui.md", "## UI\n\nUJ-1 covers the first run.\n")
        self.mark_ui_reviewed(84, ui)
        landed = self.invoke("post_tasks", "--work-item", 84, "--stage", "UI", "--body", ui, "--evidence", self.evidence_file())
        self.assertEqual(landed.code, 0, landed.stderr)
        self.assertEqual(self.state(83), self.state(84))

    def test_verification_review_required_still_meets_the_ci_gate_a_clean_run_meets(self):
        # Red CI: a clean `pdlc post verify` lands Changes Required, so the
        # heal must not reach Approval Required around it.
        self.seed_record(85, "Verification", "Review Required")
        self.seed_record(86, "Verification", "Pending")
        self.green_pr(85, number=185, checks="FAILURE")
        self.green_pr(86, number=186, checks="FAILURE")
        self.assertEqual(self.invoke("continue_", 85).code, 0)
        self.assertEqual(self.state(85), ("Verification", "CI Pending"))
        self.assertEqual(self.invoke("post_ci", 85).code, 0)
        verified = self.invoke("post_verify", 86, self.verify_report(86))
        self.assertEqual(verified.code, 0, verified.stderr)
        self.assertEqual(self.state(85), ("Verification", "Changes Required"))
        self.assertEqual(self.state(85), self.state(86))

    def test_next_applies_the_same_heal_as_continue(self):
        self.seed_record(87, "Verification", "Review Required")
        self.seed_record(88, "Verification", "Review Required")
        self.green_pr(87, number=187)
        self.green_pr(88, number=188)
        self.assertEqual(self.invoke("continue_", 87).code, 0)
        routed = self.next("--work-item", 88)
        self.assertEqual(routed.code, 0, routed.stderr)
        self.assertEqual(self.state(87), self.state(88))
        self.assertEqual(routed.front_matter("action"), "pdlc-post-ci")
        self.assertEqual(routed.front_matter("current_status"), "Verification.CIPending")


if __name__ == "__main__":
    unittest.main()

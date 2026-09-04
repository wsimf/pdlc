import unittest
from dataclasses import replace

from pdlc.domain.lifecycle import wants_help
from pdlc.domain.workflow import (
    FEATURE_PIPELINE,
    PIPELINE_REGISTRY,
    Action,
    Event,
    Gate,
    Lifecycle,
    Outcome,
    REQUESTED_TARGET,
    State,
    TransitionOverride,
    WorkType,
)


class LifecycleTests(unittest.TestCase):
    def test_forward_stage_order(self):
        self.assertEqual(FEATURE_PIPELINE.next_stage("Product"), "UI")
        self.assertEqual(FEATURE_PIPELINE.next_stage("Verification"), "Complete")

    def test_feature_pipeline_encodes_custom_transitions(self):
        self.assertEqual(
            FEATURE_PIPELINE.transition(State("Product", Gate.PENDING), Event.PUBLISHED).gate,
            Gate.APPROVAL_REQUIRED,
        )
        self.assertEqual(
            FEATURE_PIPELINE.transition(
                State("Implementation", Gate.REVIEW_REQUIRED),
                Event.REVIEWED,
                Outcome.CLEAN,
            ).gate,
            Gate.CI_PENDING,
        )
        self.assertEqual(
            FEATURE_PIPELINE.transition(
                State("Verification", Gate.APPROVAL_REQUIRED),
                Event.BOUNCED,
                requested_target="Implementation",
            ).stage,
            "Implementation",
        )
        self.assertEqual(
            FEATURE_PIPELINE.transition(
                State("Verification", Gate.APPROVAL_REQUIRED),
                Event.COMPLETED,
            ).stage,
            "Complete",
        )

    def test_feature_pipeline_preserves_skip_boundary(self):
        technical_plan = FEATURE_PIPELINE.next_state(State("Technical Plan", Gate.PENDING), Event.SKIPPED)
        verification = FEATURE_PIPELINE.next_state(State("Verification", Gate.PENDING), Event.SKIPPED)
        self.assertEqual((technical_plan.stage, technical_plan.gate.value), ("Implementation", "Pending"))
        self.assertEqual((verification.stage, verification.gate.value), ("Verification", "Approval Required"))

    def test_feature_pipeline_rejects_unallowed_dynamic_targets(self):
        with self.assertRaises(ValueError):
            FEATURE_PIPELINE.transition(
                State("Verification", Gate.APPROVAL_REQUIRED),
                Event.BOUNCED,
                requested_target="Complete",
            )

    def test_approval_stops_for_human(self):
        route = FEATURE_PIPELINE.route(State("Verification", Gate.APPROVAL_REQUIRED))
        self.assertEqual(route.action, Action.HUMAN_APPROVAL)
        self.assertFalse(route.autonomous)

    def test_help_flag_is_recognized_in_any_argument_position(self):
        self.assertTrue(wants_help(["236", "--help"]))
        self.assertTrue(wants_help(["--work-item", "236", "-h"]))


class FeaturePipelineMatrixTests(unittest.TestCase):
    """Characterization matrix for the current Feature policy."""

    pipeline = FEATURE_PIPELINE

    def state(self, stage: str, gate: Gate) -> State:
        return State(stage, gate, Lifecycle.PLANNING)

    def test_events_describe_completed_facts(self):
        self.assertEqual(
            {event.value for event in Event},
            {
                "published", "reviewed", "ci-reconciled", "approved", "skipped",
                "reauthored", "decision-resolved", "invalidated", "verified", "bounced",
                "completed", "autoapproved",
            },
        )
        with self.assertRaises(ValueError):
            Event("advance")

        self.assertEqual(
            {outcome.value for outcome in Outcome},
            {"clean", "findings", "decision", "checks-passed", "checks-failed", "checks-pending"},
        )
        with self.assertRaises(ValueError):
            Outcome("approved")

    def test_feature_spine_and_stage_policy(self):
        self.assertEqual(
            self.pipeline.active_stage_names,
            ("Product", "UI", "Tasks", "Technical Plan", "Implementation", "Testing", "Verification"),
        )
        self.assertEqual(self.pipeline.terminal_stage, "Complete")
        self.assertEqual(self.pipeline.skippable_stage_names, ("UI", "Tasks", "Technical Plan", "Implementation", "Testing", "Verification"))
        self.assertEqual(self.pipeline.stage("Product").action, Action.WRITE)
        self.assertFalse(self.pipeline.stage("Product").autonomous)
        self.assertTrue(self.pipeline.stage("Implementation").ci_gated)
        self.assertTrue(self.pipeline.stage("Technical Plan").reauthor_in_place)
        self.assertTrue(self.pipeline.stage("Verification").accepts_verification)
        self.assertEqual(self.pipeline.rework_policy.autoapprove_stages, ("Implementation", "Testing"))
        self.assertEqual(self.pipeline.rework_policy.max_iterations, 3)
        self.assertEqual(self.pipeline.stage("UI").review.target.agent, "pdlc-tasks-reviewer")
        self.assertEqual(self.pipeline.stage("Tasks").review.target.artifact, "The delivery tasks")
        self.assertEqual(self.pipeline.stage("Technical Plan").review.target.agent, "pdlc-plan-reviewer")
        self.assertEqual(self.pipeline.stage("Implementation").review.target.agent, "pdlc-implementation-reviewer")
        self.assertEqual(self.pipeline.stage("Testing").review.target.agent, "pdlc-testing-reviewer")
        self.assertEqual(self.pipeline.route(self.state("UI", Gate.PENDING)).action, Action.TASKS)
        self.assertEqual(self.pipeline.route(self.state("Product", Gate.PENDING)).action, Action.WRITE)

    def test_every_work_stage_publishes_to_its_declared_result_gate(self):
        expected = {
            "Product": Gate.APPROVAL_REQUIRED,
            "UI": Gate.APPROVAL_REQUIRED,
            "Tasks": Gate.APPROVAL_REQUIRED,
            "Technical Plan": Gate.APPROVAL_REQUIRED,
            "Implementation": Gate.REVIEW_REQUIRED,
            "Testing": Gate.REVIEW_REQUIRED,
        }
        for stage, result_gate in expected.items():
            for source_gate in (Gate.PENDING, Gate.CHANGES_REQUIRED, Gate.STALE):
                with self.subTest(stage=stage, source_gate=source_gate):
                    result = self.pipeline.next_state(self.state(stage, source_gate), Event.PUBLISHED)
                    self.assertEqual((result.stage, result.gate), (stage, result_gate))
                    route = self.pipeline.route(self.state(stage, source_gate))
                    self.assertEqual(route.action, self.pipeline.stage(stage).action)
        with self.assertRaises(ValueError):
            self.pipeline.next_state(self.state("Verification", Gate.PENDING), Event.PUBLISHED)

    def test_review_outcome_matrix(self):
        expected_clean = {"Implementation": Gate.CI_PENDING, "Testing": Gate.APPROVAL_REQUIRED}
        for stage, clean_gate in expected_clean.items():
            source = self.state(stage, Gate.REVIEW_REQUIRED)
            self.assertEqual(self.pipeline.next_state(source, Event.REVIEWED, Outcome.CLEAN).gate, clean_gate)
            self.assertEqual(self.pipeline.next_state(source, Event.REVIEWED, Outcome.FINDINGS).gate, Gate.CHANGES_REQUIRED)
            self.assertEqual(self.pipeline.next_state(source, Event.REVIEWED, Outcome.DECISION).gate, Gate.DECISION_REQUIRED)
        with self.assertRaises(ValueError):
            self.pipeline.next_state(self.state("UI", Gate.REVIEW_REQUIRED), Event.REVIEWED, Outcome.CLEAN)
        self.assertEqual(self.pipeline.route(self.state("UI", Gate.REVIEW_REQUIRED)).action, Action.BLOCKED)

    def test_ci_outcome_matrix(self):
        source = self.state("Implementation", Gate.CI_PENDING)
        self.assertEqual(self.pipeline.next_state(source, Event.CI_RECONCILED, Outcome.CHECKS_PASSED).gate, Gate.APPROVAL_REQUIRED)
        self.assertEqual(self.pipeline.next_state(source, Event.CI_RECONCILED, Outcome.CHECKS_FAILED).gate, Gate.CHANGES_REQUIRED)
        self.assertEqual(self.pipeline.next_state(source, Event.CI_RECONCILED, Outcome.CHECKS_PENDING), source)
        with self.assertRaises(ValueError):
            self.pipeline.next_state(self.state("Testing", Gate.CI_PENDING), Event.CI_RECONCILED, Outcome.CHECKS_PASSED)
        self.assertEqual(self.pipeline.route(self.state("Testing", Gate.CI_PENDING)).action, Action.BLOCKED)
        self.assertEqual(self.pipeline.route(self.state("Testing", Gate.CI_PENDING)).action, Action.BLOCKED)

    def test_approval_skip_decision_and_autoapproval_matrix(self):
        approvals = {
            "Product": "UI",
            "UI": "Tasks",
            "Tasks": "Technical Plan",
            "Technical Plan": "Implementation",
            "Implementation": "Testing",
            "Testing": "Verification",
        }
        for source, target in approvals.items():
            result = self.pipeline.next_state(self.state(source, Gate.APPROVAL_REQUIRED), Event.APPROVED)
            self.assertEqual((result.stage, result.gate), (target, Gate.PENDING))
        with self.assertRaises(ValueError):
            self.pipeline.next_state(self.state("Verification", Gate.APPROVAL_REQUIRED), Event.APPROVED)
        for source, target in (("UI", "Tasks"), ("Tasks", "Technical Plan"), ("Technical Plan", "Implementation"), ("Implementation", "Testing"), ("Testing", "Verification")):
            result = self.pipeline.next_state(self.state(source, Gate.PENDING), Event.SKIPPED)
            self.assertEqual((result.stage, result.gate), (target, Gate.PENDING))
        self.assertEqual(self.pipeline.next_state(self.state("Verification", Gate.PENDING), Event.SKIPPED).gate, Gate.APPROVAL_REQUIRED)
        with self.assertRaises(ValueError):
            self.pipeline.next_state(self.state("Product", Gate.PENDING), Event.SKIPPED)
        for stage in ("Implementation", "Testing"):
            self.assertEqual(self.pipeline.next_state(self.state(stage, Gate.APPROVAL_REQUIRED), Event.AUTOAPPROVED).gate, Gate.PENDING)
            self.assertFalse(self.pipeline.can_autoapprove(stage, 0))
            self.assertTrue(self.pipeline.can_autoapprove(stage, 1))
            self.assertTrue(self.pipeline.can_autoapprove(stage, 3))
            self.assertFalse(self.pipeline.can_autoapprove(stage, 4))
        with self.assertRaises(ValueError):
            self.pipeline.next_state(self.state("Verification", Gate.APPROVAL_REQUIRED), Event.AUTOAPPROVED)
        self.assertFalse(self.pipeline.can_autoapprove("Verification", 1))
        for stage in ("Implementation", "Testing", "Verification"):
            self.assertEqual(self.pipeline.next_state(self.state(stage, Gate.DECISION_REQUIRED), Event.DECISION_RESOLVED).gate, Gate.CHANGES_REQUIRED)
        self.assertEqual(self.pipeline.route(self.state("Product", Gate.DECISION_REQUIRED)).action, Action.BLOCKED)

    def test_verification_outcomes_bounces_and_completion(self):
        source = self.state("Verification", Gate.PENDING)
        self.assertEqual(self.pipeline.next_state(source, Event.VERIFIED, Outcome.CLEAN).gate, Gate.APPROVAL_REQUIRED)
        self.assertEqual(self.pipeline.next_state(source, Event.VERIFIED, Outcome.FINDINGS).gate, Gate.CHANGES_REQUIRED)
        self.assertEqual(self.pipeline.next_state(source, Event.VERIFIED, Outcome.DECISION).gate, Gate.DECISION_REQUIRED)
        bounce = self.pipeline.next_state(self.state("Verification", Gate.APPROVAL_REQUIRED), Event.BOUNCED, requested_target="Implementation")
        self.assertEqual((bounce.stage, bounce.gate), ("Implementation", Gate.STALE))
        for target in ("Product", "UI", "Tasks", "Technical Plan", "Verification", "Complete"):
            with self.assertRaises(ValueError):
                self.pipeline.next_state(self.state("Verification", Gate.APPROVAL_REQUIRED), Event.BOUNCED, requested_target=target)
        complete = self.pipeline.next_state(self.state("Verification", Gate.APPROVAL_REQUIRED), Event.COMPLETED)
        self.assertEqual((complete.stage, complete.gate, complete.lifecycle), ("Complete", Gate.APPROVED, Lifecycle.COMPLETED))

    def test_invalidation_uses_pipeline_reachability(self):
        target = self.pipeline.next_state(
            self.state("Testing", Gate.APPROVAL_REQUIRED),
            Event.INVALIDATED,
            requested_target="Technical Plan",
        )
        self.assertEqual(target, State("Technical Plan", Gate.STALE, Lifecycle.PLANNING))
        with self.assertRaises(ValueError):
            self.pipeline.next_state(
                self.state("Testing", Gate.APPROVAL_REQUIRED),
                Event.INVALIDATED,
                requested_target="Verification",
            )

    def test_source_gate_and_malformed_transition_validation(self):
        with self.assertRaises(ValueError):
            self.pipeline.next_state(self.state("Implementation", Gate.PENDING), Event.REVIEWED, Outcome.CLEAN)
        with self.assertRaises(ValueError):
            self.pipeline.next_state(self.state("Implementation", Gate.REVIEW_REQUIRED), Event.CI_RECONCILED, Outcome.CHECKS_PASSED)
        with self.assertRaises(ValueError):
            self.pipeline.next_state(self.state("Complete", Gate.APPROVED), Event.COMPLETED)
        with self.assertRaises(TypeError):
            self.pipeline.next_state(self.state("Verification", Gate.PENDING), "advance")
        with self.assertRaises(TypeError):
            self.pipeline.next_state(self.state("Implementation", Gate.REVIEW_REQUIRED), Event.REVIEWED, "unknown")
        with self.assertRaises(ValueError):
            self.pipeline.next_state(self.state("Verification", Gate.PENDING), Event.SKIPPED, Outcome.CLEAN)
        with self.assertRaises(ValueError):
            self.pipeline.next_state(self.state("Verification", Gate.APPROVAL_REQUIRED), Event.BOUNCED, Outcome.CLEAN, "Implementation")
        self.assertEqual(self.pipeline.route(State("Bogus", Gate.PENDING)).action, Action.BLOCKED)
        self.assertEqual(
            self.pipeline.transition(self.state("Testing", Gate.REVIEW_REQUIRED), Event.REVIEWED, Outcome.CLEAN).gate,
            Gate.APPROVAL_REQUIRED,
        )

    def test_malformed_persisted_states_are_blocked(self):
        self.assertEqual(
            self.pipeline.route(State("Complete", Gate.PENDING, Lifecycle.PLANNING)).action,
            Action.BLOCKED,
        )
        self.assertEqual(
            self.pipeline.route(State("Implementation", Gate.PENDING, Lifecycle.COMPLETED)).action,
            Action.BLOCKED,
        )
        self.assertEqual(
            self.pipeline.route(State("Complete", Gate.APPROVED, Lifecycle.COMPLETED)).action,
            Action.NONE,
        )
        with self.assertRaises(ValueError):
            self.pipeline.next_state(
                State("Implementation", Gate.PENDING, Lifecycle.COMPLETED),
                Event.PUBLISHED,
            )
        with self.assertRaises(TypeError):
            self.pipeline.next_state(State("Product", "Pending"), Event.PUBLISHED)
        self.assertEqual(State.parse("Product", "Pending"), State("Product", Gate.PENDING))

    def test_override_definitions_require_coherent_dynamic_targets(self):
        dynamic_without_targets = TransitionOverride(
            "Verification",
            Gate.APPROVAL_REQUIRED,
            Event.BOUNCED,
            REQUESTED_TARGET,
            Gate.STALE,
        )
        invalidation = replace(
            self.pipeline.invalidation_policy,
            reentry_targets={**self.pipeline.invalidation_policy.reentry_targets, "Verification": ()},
        )
        with self.assertRaises(ValueError):
            replace(self.pipeline, overrides=(dynamic_without_targets,), invalidation_policy=invalidation)

        fixed_target = replace(
            dynamic_without_targets,
            target_stage="Implementation",
        )
        fixed_pipeline = replace(self.pipeline, overrides=(fixed_target,))
        with self.assertRaises(ValueError):
            fixed_pipeline.next_state(
                self.state("Verification", Gate.APPROVAL_REQUIRED),
                Event.BOUNCED,
                requested_target="Implementation",
            )

        invalid_terminal_target = replace(
            dynamic_without_targets,
            target_stage="Complete",
        )
        with self.assertRaises(ValueError):
            replace(self.pipeline, overrides=(invalid_terminal_target,))

    def test_pipeline_rejects_incoherent_stage_policy(self):
        implementation = self.pipeline.stage("Implementation")
        invalid_implementation = replace(implementation, review=None)
        invalid_stages = tuple(
            invalid_implementation if stage.name == "Implementation" else stage
            for stage in self.pipeline.stages
        )
        with self.assertRaises(ValueError):
            replace(self.pipeline, stages=invalid_stages)

        terminal = self.pipeline.stage("Complete")
        invalid_terminal = replace(terminal, action=Action.TEST)
        invalid_stages = (*self.pipeline.stages[:-1], invalid_terminal)
        with self.assertRaises(ValueError):
            replace(self.pipeline, stages=invalid_stages)

    def test_work_type_registry_defaults_legacy_records_and_rejects_unknown_types(self):
        self.assertIs(PIPELINE_REGISTRY.for_work_type(WorkType.FEATURE), FEATURE_PIPELINE)
        self.assertIs(PIPELINE_REGISTRY.for_record({}), FEATURE_PIPELINE)
        self.assertIs(PIPELINE_REGISTRY.for_record({"workType": "feature"}), FEATURE_PIPELINE)
        with self.assertRaises(ValueError):
            PIPELINE_REGISTRY.for_work_type("unknown")
        with self.assertRaises(ValueError):
            PIPELINE_REGISTRY.for_record({"workType": "bug"})

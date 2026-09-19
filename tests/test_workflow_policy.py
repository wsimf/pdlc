import unittest

from pdlc.domain.stages import Gate
from pdlc.domain.workflow import Event, InvalidationPolicy, Lifecycle, State, WorkType
from pdlc.domain.workflows.pipeline import PIPELINE_REGISTRY
from pdlc.domain.workflows.workflow_bug import BUG_PIPELINE
from pdlc.domain.workflows.workflow_feature import FEATURE_PIPELINE


class WorkflowPolicyTests(unittest.TestCase):
    def test_feature_completion_policy_declares_current_boundary_and_requirements(self):
        policy = FEATURE_PIPELINE.completion_policy

        self.assertIsNotNone(policy)
        assert policy is not None
        self.assertEqual(policy.boundary_stage, "Verification")
        self.assertEqual(policy.boundary_gate, Gate.APPROVAL_REQUIRED)
        self.assertTrue(policy.is_boundary(State("Verification", Gate.APPROVAL_REQUIRED)))
        self.assertEqual(
            policy.required_stage_evidence,
            ("Product", "UI", "Tasks", "Technical Plan", "Implementation", "Testing"),
        )
        self.assertTrue(policy.require_stage_settlement)
        self.assertTrue(policy.require_tasks_closed)
        self.assertTrue(policy.require_task_implementation)
        self.assertTrue(policy.require_prs_merged)
        self.assertTrue(policy.require_checks_green)
        self.assertEqual(policy.verification_parser, "pdlc.verify/1")

    def test_feature_invalidation_policy_separates_dependencies_and_reentry(self):
        policy = FEATURE_PIPELINE.invalidation_policy

        self.assertIsNotNone(policy)
        assert policy is not None
        self.assertEqual(policy.dependencies_for("Implementation"), ("Testing", "Verification"))
        self.assertTrue(policy.can_reenter("Verification", "Implementation"))
        self.assertTrue(policy.can_reenter("Verification", "Testing"))
        self.assertFalse(policy.can_reenter("Verification", "Product"))
        self.assertTrue(FEATURE_PIPELINE.can_reenter("Testing", "Implementation"))
        self.assertTrue(FEATURE_PIPELINE.can_invalidate("Verification", "Product"))

    def test_unavailable_bug_pipeline_is_registered_without_guessing_its_stages(self):
        self.assertFalse(BUG_PIPELINE.available)
        with self.assertRaisesRegex(ValueError, "workflow unavailable for work type: bug"):
            PIPELINE_REGISTRY.for_work_type(WorkType.BUG)

    def test_invalidation_policy_normalizes_mappings(self):
        policy = InvalidationPolicy({"A": ["B"]}, {"A": ["A"]})

        self.assertEqual(policy.dependencies_for("A"), ("B",))
        with self.assertRaises(TypeError):
            policy.evidence_dependencies["A"] = ("C",)  # type: ignore[index]


    def test_escalation_parks_a_work_gate_at_decision_required_and_nothing_else(self):
        for gate in (Gate.PENDING, Gate.CHANGES_REQUIRED, Gate.STALE):
            with self.subTest(gate=gate):
                target = FEATURE_PIPELINE.next_state(State("Implementation", gate, Lifecycle.DELIVERY), Event.ESCALATED)
                self.assertEqual((target.stage, target.gate, target.lifecycle), ("Implementation", Gate.DECISION_REQUIRED, Lifecycle.DELIVERY))
        for gate in (Gate.REVIEW_REQUIRED, Gate.APPROVAL_REQUIRED, Gate.CI_PENDING, Gate.DECISION_REQUIRED):
            with self.subTest(gate=gate):
                with self.assertRaises(ValueError):
                    FEATURE_PIPELINE.next_state(State("Implementation", gate, Lifecycle.DELIVERY), Event.ESCALATED)

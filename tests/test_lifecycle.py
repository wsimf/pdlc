import unittest

from pdlc.domain.lifecycle import action_for, next_stage


class LifecycleTests(unittest.TestCase):
    def test_forward_stage_order(self):
        self.assertEqual(next_stage("Product"), "UI")

    def test_approval_stops_for_human(self):
        action, autonomous, _ = action_for("Verification", "Approval Required")
        self.assertEqual(action, "human-approval")
        self.assertFalse(autonomous)

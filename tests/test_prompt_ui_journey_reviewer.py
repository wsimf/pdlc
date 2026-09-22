"""`pdlc prompt ui-journey-reviewer` reads the same carried-forward journey/UX
resolution `pdlc inspect verify` renders as its `## Journeys to review` section."""

from __future__ import annotations

from unittest.mock import patch

from tests._prompts import PromptHarness

BODY = """## Product

### 4. Functional requirements
- FR-1: The record lands.

## UI

### UJ-1: Retry sync
**Moment:** offline, tapping retry.
**Entry:** route screen visible.

## Decisions

None.
"""


class PromptUiJourneyReviewerTest(PromptHarness):
    def setUp(self):
        super().setUp()
        patcher = patch("pdlc.commands.prompt.head_commit", return_value="abc1234")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _seeded(self, status: str = "Verification", gate: str = "Pending", *, ui: bool = True):
        self.seed_record(60, status, gate, slug="record-60", body=BODY)
        title = "WORK-60-TASK-001 [UI] Retry screen" if ui else "WORK-60-TASK-001 [CORE] Core work"
        self.seed_task(60, 601, "TASK-001", "OPEN", title)

    def test_a_first_pass_carries_the_due_journey_and_ux(self):
        self._seeded()
        result = self.invoke("prompt_ui_journey_reviewer", 60, "--description", "text:offline retry")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("verifying acceptance for a feature: offline retry.", result.stdout)
        self.assertIn("### UJ-1: Retry sync", result.stdout)
        self.assertIn("Independently review rendered UX", result.stdout)
        self.assertNotIn("{{", result.stdout)

    def test_the_brief_names_no_pdlc_command_or_stage(self):
        self._seeded()
        result = self.invoke("prompt_ui_journey_reviewer", 60, "--description", "text:offline retry")
        for leak in ("pdlc inspect", "pdlc post", "Gate State"):
            self.assertNotIn(leak, result.stdout)

    def test_refuses_when_verification_is_not_due(self):
        self._seeded(status="Testing")
        result = self.invoke("prompt_ui_journey_reviewer", 60, "--description", "text:offline retry")
        self.assertNotEqual(result.code, 0)

    def test_refuses_when_the_record_has_no_ui_task(self):
        self._seeded(ui=False)
        result = self.invoke("prompt_ui_journey_reviewer", 60, "--description", "text:offline retry")
        self.assertNotEqual(result.code, 0)
        self.assertIn("no UI tasks", result.stderr)

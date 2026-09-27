"""`pdlc prompt cumulative-reviewer` renders the brief for the cumulative-review sub-agent, with no work item."""

from __future__ import annotations

from tests._support import FileBackendTest


class PromptCumulativeReviewerTest(FileBackendTest):
    def _invoke(self, *extra: str):
        return self.invoke(
            "prompt_cumulative_reviewer", "--inline",
            "--shipped", "text:routes retry with backoff",
            "--unchanged", "text:existing sync behaviour",
            "--constraints", "text:no more than 3 retries",
            *extra,
        )

    def test_the_intent_packet_is_carried_verbatim(self):
        result = self._invoke()
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("routes retry with backoff", result.stdout)
        self.assertIn("existing sync behaviour", result.stdout)
        self.assertIn("no more than 3 retries", result.stdout)
        self.assertNotIn("{{", result.stdout)

    def test_scope_defaults_to_the_branch_diff(self):
        result = self._invoke()
        self.assertIn("The current branch's diff against its base branch", result.stdout)

    def test_an_explicit_scope_overrides_the_default(self):
        result = self._invoke("--scope", "text:The commit range abc123..def456")
        self.assertIn("The commit range abc123..def456", result.stdout)
        self.assertNotIn("The current branch's diff", result.stdout)

    def test_the_brief_names_no_pdlc_command_or_work_item(self):
        result = self._invoke()
        for leak in ("pdlc inspect", "pdlc post", "Gate State", "work item"):
            self.assertNotIn(leak, result.stdout)

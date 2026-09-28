"""`pdlc prompt product-reviewer` renders the brief for a Product draft, not a record unit."""

from __future__ import annotations

from tests._support import FileBackendTest


class PromptProductReviewerTest(FileBackendTest):
    def test_a_fresh_draft_carries_no_record(self):
        result = self.invoke("prompt_product_reviewer", "--inline", "/tmp/draft.md")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Review the supplied Product draft", result.stdout)
        self.assertIn("`/tmp/draft.md` — read the whole file", result.stdout)
        self.assertNotIn("## Current record", result.stdout)
        self.assertNotIn("## Prior findings", result.stdout)
        self.assertNotIn("{{", result.stdout)

    def test_reconciling_carries_the_current_record_body(self):
        self.seed_record(60, "Product", "Changes Required", slug="record-60")
        result = self.invoke("prompt_product_reviewer", "--inline", "/tmp/draft.md", "--work-item", 60)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("--- BEGIN CURRENT RECORD ---\n\n## Product", result.stdout)
        self.assertIn("FR-1: The record lands.", result.stdout)
        self.assertIn("--- END CURRENT RECORD ---", result.stdout)

    def test_findings_render_for_a_re_review(self):
        result = self.invoke("prompt_product_reviewer", "--inline", "/tmp/draft.md", "--findings", "text:tighten FR-2")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("--- BEGIN PRIOR FINDINGS ---\n\ntighten FR-2\n\n--- END PRIOR FINDINGS ---", result.stdout)

    def test_the_brief_names_no_pdlc_command_or_stage(self):
        result = self.invoke("prompt_product_reviewer", "--inline", "/tmp/draft.md")
        for leak in ("pdlc inspect", "pdlc post", "Gate State"):
            self.assertNotIn(leak, result.stdout)

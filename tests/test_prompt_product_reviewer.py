"""`pdlc prompt product-reviewer` renders the brief for one of a Product draft's two reviews."""

from __future__ import annotations

from tests._support import FileBackendTest, APPROACH_DEFAULT

from pdlc.internal import product_draft

DRAFT = "## Product\n\n### Functional requirements\n- FR-1: The record lands.\n\n## Decisions\n- d\n"


class PromptProductReviewerTest(FileBackendTest):
    def draft(self, text: str = DRAFT, slug: str = "fresh") -> str:
        self.assertEqual(self.invoke("prompt_product_writer", "--inline", "--slug", slug).code, 0)
        path = product_draft.draft_path(f"new-{slug}")
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_a_fresh_draft_carries_no_record(self):
        draft = self.draft()
        result = self.invoke("prompt_product_reviewer", "--inline", draft, "--pass", "product")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Review the supplied Product draft before", result.stdout)
        self.assertIn(f"`{draft}` — read the whole file; review all of it except any `### Technical approach`", result.stdout)
        self.assertIn(str(product_draft.product_findings_path("new-fresh")), result.stdout)
        self.assertNotIn("## Current record", result.stdout)
        self.assertNotIn("## Prior findings", result.stdout)
        self.assertNotIn("{{", result.stdout)

    def test_reconciling_carries_the_current_record_body(self):
        self.seed_record(60, "Product", "Changes Required", slug="record-60")
        self.assertEqual(self.invoke("prompt_product_writer", "--inline", "--work-item", 60).code, 0)
        draft = product_draft.draft_path("60")
        result = self.invoke("prompt_product_reviewer", "--inline", draft, "--pass", "product")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("--- BEGIN CURRENT RECORD ---\n\n## Product", result.stdout)
        self.assertIn("FR-1: The record lands.", result.stdout)

    def test_a_re_review_needs_an_author_response_to_every_finding(self):
        draft = self.draft()
        findings = "- F1 [P1] FR-1 — \"lands\"\n  Evidence: e\n  Recommendation: r\n- F2 [P2] FR-1 — \"x\"\n  Author response: Fixed — tightened\n"
        refused = self.invoke("prompt_product_reviewer", "--inline", draft, "--pass", "product", "--findings", f"text:{findings}")
        self.assertEqual(refused.code, 1)
        self.assertIn("under F1 in", refused.stderr)
        self.assertNotIn("F2", refused.stderr)

        answered = findings.replace("Recommendation: r\n", "Recommendation: r\n  Author response: Rejected — FR-1 already says it\n")
        result = self.invoke("prompt_product_reviewer", "--inline", draft, "--pass", "product", "--findings", f"text:{answered}")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Author response: Rejected — FR-1 already says it", result.stdout)
        self.assertIn("weigh the author's reason", result.stdout)

    def test_the_technical_pass_waits_for_a_spike_on_the_reviewed_product(self):
        draft = self.draft()
        refused = self.invoke("prompt_product_reviewer", "--inline", draft, "--pass", "technical")
        self.assertEqual(refused.code, 1)
        self.assertIn("the technical review is not due", refused.stderr)

    def test_the_technical_pass_reviews_the_approach(self):
        draft = self.draft(DRAFT.replace("## Decisions", APPROACH_DEFAULT + "\n## Decisions"))
        self.invoke("prompt_product_reviewer", "--inline", draft, "--pass", "product")
        product_draft.product_findings_path("new-fresh").write_text("Verdict: Ready to Land\n")
        self.assertEqual(self.invoke("prompt_tech_feasibility", "--inline", draft).code, 0)
        result = self.invoke("prompt_product_reviewer", "--inline", draft, "--pass", "technical")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("including its technical approach", result.stdout)
        self.assertIn("The approach covers every `FR-*` and `C-*`", result.stdout)
        self.assertIn(str(product_draft.technical_findings_path("new-fresh")), result.stdout)

    def test_refuses_a_file_product_writer_did_not_create(self):
        result = self.invoke("prompt_product_reviewer", "--inline", self.write_file("draft.md", DRAFT), "--pass", "product")
        self.assertEqual(result.code, 1)
        self.assertIn("is not a Product draft created by `pdlc prompt product-writer`", result.stderr)

    def test_the_brief_names_no_pdlc_command_or_stage(self):
        result = self.invoke("prompt_product_reviewer", "--inline", self.draft(), "--pass", "product")
        for leak in ("pdlc inspect", "pdlc post", "Gate State"):
            self.assertNotIn(leak, result.stdout)

"""The Product draft's way to landing: `pdlc prompt product-writer` keeps the
draft and names the next step, the two reviews and the feasibility spike
stamp what they saw, and `pdlc post write` lands only a draft both reviews
passed as it stands."""

from __future__ import annotations

import unittest

from tests._support import APPROACH_DEFAULT, FileBackendTest

from pdlc.domain.product_draft import (
    Phase,
    Stamp,
    fingerprint,
    land_problems,
    missing_author_responses,
    phase,
    product_content,
    subsection,
)
from pdlc.internal import product_draft

PRODUCT = "## Product\n\n### Functional requirements\n- FR-1: The record lands.\n\n### Constraints\n- C-1: x.\n"
DRAFT = PRODUCT + "\n## Decisions\n- d\n"
WITH_APPROACH = PRODUCT + "\n" + APPROACH_DEFAULT + "\n## Decisions\n- d\n"


class ProductDraftPolicyTest(unittest.TestCase):
    def test_product_content_leaves_out_only_the_technical_approach(self):
        self.assertEqual(product_content(WITH_APPROACH).strip(), DRAFT.strip())
        self.assertIn("Verdict: Feasible", subsection(WITH_APPROACH, "Technical approach") or "")
        self.assertIsNone(subsection(DRAFT, "Technical approach"))
        self.assertEqual(fingerprint("a  \nb\n\n"), fingerprint("a\nb"))

    def test_an_approach_outside_product_is_not_the_approach(self):
        self.assertIsNone(subsection(DRAFT + "\n### Technical approach\nx\n", "Technical approach"))

    def test_every_finding_needs_an_author_response(self):
        findings = (
            "- F1 [P0–P3] <requirement> — \"<claim>\"\n"
            "### Factually wrong\n"
            "- F1 [P1] FR-1 — \"a\"\n  Evidence: e\n  Author response: Fixed — done\n"
            "- F2 [P2] FR-1 — \"b\"\n  Evidence: e\n"
            "### Inconsistent\n- F3 [P1] C-1 — \"c\"\n  Author response: Rejected — C-1 binds it\n"
            "- F4 [P3] C-1 — \"d\"\n  Author response: maybe\n"
        )
        self.assertEqual(missing_author_responses(findings), ["F2", "F4"])

    def test_land_problems(self):
        self.assertEqual(land_problems(WITH_APPROACH), [])
        self.assertIn("missing subsection: ### Technical approach", land_problems(DRAFT)[0])
        not_feasible = WITH_APPROACH.replace("Verdict: Feasible", "Verdict: Not feasible")
        self.assertIn("Not feasible", land_problems(not_feasible)[0])
        assumed = WITH_APPROACH.replace("### Constraints", "### Assumptions\n- a\n\n### Constraints")
        self.assertIn("### Assumptions must be resolved", land_problems(assumed)[0])

    def test_phase_follows_what_each_step_saw(self):
        product = fingerprint(product_content(WITH_APPROACH))
        whole = fingerprint(WITH_APPROACH)
        cases = [
            (DRAFT, Stamp(), None, None, Phase.DRAFT),
            (DRAFT, Stamp(product="old"), "Ready to Land", None, Phase.PRODUCT_REVIEW),
            (DRAFT, Stamp(product=fingerprint(DRAFT)), None, None, Phase.PRODUCT_REVIEW),
            (DRAFT, Stamp(product=fingerprint(DRAFT)), "Needs Revision", None, Phase.PRODUCT_FINDINGS),
            (DRAFT, Stamp(product=fingerprint(DRAFT)), "Ready to Land", None, Phase.SPIKE),
            (WITH_APPROACH, Stamp(product=product, spiked="old"), "Ready to Land", None, Phase.SPIKE),
            (
                WITH_APPROACH.replace("Verdict: Feasible", "Verdict: Not feasible"),
                Stamp(product=product, spiked=product), "Ready to Land", None, Phase.NOT_FEASIBLE,
            ),
            (WITH_APPROACH, Stamp(product=product, spiked=product), "Ready to Land", None, Phase.TECHNICAL_REVIEW),
            (WITH_APPROACH, Stamp(product, product, "old"), "Ready to Land", "Ready to Land", Phase.TECHNICAL_REVIEW),
            (WITH_APPROACH, Stamp(product, product, whole), "Ready to Land", "Needs Revision", Phase.TECHNICAL_FINDINGS),
            (WITH_APPROACH, Stamp(product, product, whole), "Ready to Land", "Ready to Land", Phase.READY),
        ]
        for draft, stamp, product_verdict, technical_verdict, expected in cases:
            with self.subTest(expected=expected, stamp=stamp):
                self.assertEqual(phase(draft, stamp, product_verdict, technical_verdict), expected)


class ProductWriterTest(FileBackendTest):
    def writer(self, *args: object):
        return self.invoke("prompt_product_writer", "--inline", *args)

    def test_a_new_work_item_starts_from_the_headings(self):
        result = self.writer("--slug", "route-shape")
        self.assertEqual(result.code, 0, result.stderr)
        draft = product_draft.draft_path("new-route-shape")
        self.assertEqual(draft.read_text(), "## Product\n\n## Decisions\n\n## Open Questions\n")
        self.assertIn(f"`{draft}` is the only copy of the draft", result.stdout)
        self.assertIn("This is a new work item, `route-shape`", result.stdout)
        self.assertIn(f"pdlc prompt product-reviewer {draft} --pass product", result.stdout)
        self.assertIn("Run `pdlc prompt product-writer --slug route-shape` again after each step", result.stdout)
        self.assertNotIn("{{", result.stdout)

    def test_a_re_run_keeps_the_draft_and_restart_discards_it(self):
        self.writer("--slug", "kept")
        draft = product_draft.draft_path("new-kept")
        draft.write_text(DRAFT)
        self.assertEqual(self.writer("--slug", "kept").code, 0)
        self.assertEqual(draft.read_text(), DRAFT)
        self.assertEqual(self.writer("--slug", "kept", "--restart").code, 0)
        self.assertEqual(draft.read_text(), "## Product\n\n## Decisions\n\n## Open Questions\n")

    def test_refuses_a_bad_or_used_slug(self):
        self.seed_record(60, "Product", "Approval Required", slug="taken")
        for slug, message in (("Bad Slug", "kebab-case"), ("taken", "already names work item 60")):
            with self.subTest(slug=slug):
                result = self.writer("--slug", slug)
                self.assertEqual(result.code, 1)
                self.assertIn(message, result.stderr)

    def test_the_record_state_picks_the_seed_and_the_mode(self):
        self.seed_record(61, "", "", body="Ship offline routes.\n")
        uninitialized = self.writer("--work-item", 61)
        self.assertEqual(uninitialized.code, 0, uninitialized.stderr)
        self.assertIn("--- BEGIN REQUIREMENTS ---\n\nShip offline routes.", uninitialized.stdout)
        self.assertEqual(product_draft.draft_path("61").read_text(), "## Product\n\n## Decisions\n\n## Open Questions\n")

        self.seed_record(62, "Product", "Stale")
        stale = self.writer("--work-item", 62)
        self.assertEqual(stale.code, 0, stale.stderr)
        self.assertIn("is at Product / Stale", stale.stdout)
        seeded = product_draft.draft_path("62").read_text()
        self.assertIn("- FR-1: The record lands.", seeded)
        self.assertNotIn("## UI", seeded)

        self.seed_record(63, "Product", "Review Required")
        self.assertIn("published without its local review", self.writer("--work-item", 63).stdout)

        self.seed_record(64, "Product", "Approval Required")
        refused = self.writer("--work-item", 64)
        self.assertEqual(refused.code, 1)
        self.assertIn("pass --reauthor only when the driver asked", refused.stderr)
        self.assertFalse(product_draft.draft_path("64").exists())
        reauthor = self.writer("--work-item", 64, "--reauthor")
        self.assertEqual(reauthor.code, 0, reauthor.stderr)
        self.assertIn("--work-item 64 --reauthor", reauthor.stdout)

        self.seed_record(65, "Product", "Decision Required")
        self.assertIn("pdlc guide decisions", self.writer("--work-item", 65).stderr)

        self.seed_record(66, "Technical Plan", "Pending")
        later = self.writer("--work-item", 66)
        self.assertEqual(later.code, 1)
        self.assertIn("pass --patch", later.stderr)
        patch = self.writer("--work-item", 66, "--patch")
        self.assertEqual(patch.code, 0, patch.stderr)
        self.assertIn("is past Product, at Technical Plan / Pending", patch.stdout)


class ProductDraftLoopTest(FileBackendTest):
    """Drive one new work item from first draft to landing, the way the skill does."""

    def run_ok(self, command: str, *args: object) -> str:
        result = self.invoke(command, "--inline", *args)
        self.assertEqual(result.code, 0, result.stderr)
        return result.stdout

    def next_steps(self) -> str:
        return self.run_ok("prompt_product_writer", "--slug", "loop").split("## Next steps", 1)[1]

    def test_the_draft_lands_only_after_both_reviews_and_a_spike(self):
        key = "new-loop"
        self.next_steps()
        draft = product_draft.draft_path(key)
        product_findings = product_draft.product_findings_path(key)
        technical_findings = product_draft.technical_findings_path(key)
        draft.write_text(DRAFT)
        land = ["post_write", "--title", "Loop", "--slug", "loop", "--body", draft, "--evidence", self.evidence_file()]

        self.run_ok("prompt_product_reviewer", draft, "--pass", "product")
        self.assertIn("run `pdlc prompt product-writer --slug loop` again", self.next_steps())
        product_findings.write_text("- F1 [P1] FR-1 — \"x\"\n  Evidence: e\nVerdict: Needs Revision\n")
        self.assertIn(f"Read the product review's findings in `{product_findings}`", self.next_steps())
        self.assertIn(f"--pass product --findings {product_findings}", self.next_steps())

        # A rejected finding with no edit goes back to the reviewer, not on to the spike.
        product_findings.write_text(product_findings.read_text().replace("Evidence: e\n", "Evidence: e\n  Author response: Rejected — fine\n"))
        self.run_ok("prompt_product_reviewer", draft, "--pass", "product", "--findings", product_findings)
        self.assertIn("Prior findings", product_findings.read_text())
        refused_spike = self.invoke("prompt_tech_feasibility", "--inline", draft)
        self.assertEqual(refused_spike.code, 1)
        self.assertIn("the product review must pass", refused_spike.stderr)
        product_findings.write_text("Verdict: Ready to Land\n")
        self.assertIn("pdlc prompt tech-feasibility", self.next_steps())

        refused = self.invoke(*land)
        self.assertEqual(refused.code, 1)
        self.assertIn("missing subsection: ### Technical approach", refused.stderr)

        spike = self.run_ok("prompt_tech_feasibility", draft)
        self.assertIn("#### Feasibility", spike.replace("### Feasibility", "#### Feasibility"))
        self.assertIn("Verdict: <Feasible | Feasible with caveats | Not feasible>", spike)
        draft.write_text(WITH_APPROACH.replace("Verdict: Feasible", "Verdict: Not feasible"))
        self.assertIn("not feasible", self.next_steps())
        self.assertIn("Not feasible", self.invoke(*land).stderr)

        draft.write_text(WITH_APPROACH)
        self.assertIn("First settle what the spike reported", self.next_steps())
        self.run_ok("prompt_product_reviewer", draft, "--pass", "technical")
        technical_findings.write_text("Verdict: Ready to Land\n")
        ready = self.next_steps()
        self.assertIn(f'pdlc post write --title "<TITLE>" --slug loop --body {draft}', ready)

        # A product edit after the technical pass sends the draft back to the product review.
        draft.write_text(WITH_APPROACH.replace("The record lands.", "The record lands atomically."))
        refused = self.invoke(*land)
        self.assertEqual(refused.code, 1)
        self.assertIn("the Product draft is at product review", refused.stderr)
        self.assertEqual(list(self.records_dir().iterdir()), [])
        draft.write_text(WITH_APPROACH)

        landed = self.invoke(*land)
        self.assertEqual(landed.code, 0, landed.stderr)
        self.assertEqual(landed.json["gateState"], "Approval Required")
        self.assertIn("### Technical approach", self.body(landed.json["work_item_number"]))
        for path in (draft, product_findings, technical_findings):
            self.assertFalse(path.exists(), path)

    def test_post_write_refuses_a_draft_for_another_record(self):
        self.seed_record(70, "Product", "Stale")
        self.seed_record(71, "Product", "Stale")
        other = self.product_draft(DRAFT, 71)
        refused = self.invoke("post_write", "--work-item", 70, "--body", other, "--evidence", self.evidence_file())
        self.assertEqual(refused.code, 1)
        self.assertIn("is the Product draft for work item 71, not 70", refused.stderr)
        assumed = self.product_draft(DRAFT.replace("### Constraints", "### Assumptions\n- a\n\n### Constraints"), 70)
        refused = self.invoke("post_write", "--work-item", 70, "--body", assumed, "--evidence", self.evidence_file())
        self.assertEqual(refused.code, 1)
        self.assertIn("### Assumptions must be resolved", refused.stderr)
        self.assertEqual(self.comments_text(70), "")


if __name__ == "__main__":
    unittest.main()

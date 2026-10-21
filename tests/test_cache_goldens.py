"""Whole-file goldens for the files a `pdlc prompt` command writes into the
work-item cache for an agent to read or edit. The brief points the agent at
these files, so their seeded content is as much a contract as the brief
itself. Internal bookkeeping (review stamps, the recorded attachments list)
is left to the behavioural tests.

Regenerate after an intended edit with:

    PDLC_UPDATE_GOLDENS=1 uv run python -m unittest tests.test_cache_goldens

then read the resulting diff before committing it.
"""

from __future__ import annotations

from pathlib import Path

from pdlc.internal import product_draft
from tests._goldens import GoldenMixin
from tests._prompts import PromptHarness
from tests._support import APPROACH_DEFAULT, BODY_DEFAULT

DRAFT = "## Product\n\n### Functional requirements\n- FR-1: The route sheet opens.\n\n## Decisions\n- d\n"
# A landed record carrying every section, so the seed shows what it keeps and what it drops.
LANDED = BODY_DEFAULT.replace("## UI", APPROACH_DEFAULT + "\n## UI")


class CacheGoldenTest(GoldenMixin, PromptHarness):
    GOLDENS = Path(__file__).parent / "fixtures" / "cache"

    def _file(self, path: Path) -> str:
        self.assertTrue(path.is_file(), path)
        return path.read_text(encoding="utf-8")

    def _writer(self, *args: object) -> None:
        result = self.invoke("prompt_product_writer", "--inline", *args)
        self.assertEqual(result.code, 0, result.stderr)

    # --- product draft ---

    def test_product_draft_for_a_new_work_item(self):
        self._writer("--slug", "route-sheet")
        self.assertGolden("product-draft-new", self._file(product_draft.draft_path("new-route-sheet")))

    def test_product_draft_seeded_from_a_landed_record(self):
        self.seed_record(60, "Product", "Changes Required", slug="record-60", body=LANDED)
        self._writer("--work-item", 60)
        self.assertGolden("product-draft-from-record", self._file(product_draft.draft_path("60")))

    def test_product_draft_seeded_from_a_record_without_open_questions(self):
        body = LANDED.split("## Open Questions", 1)[0]
        self.seed_record(60, "Product", "Changes Required", slug="record-60", body=body)
        self._writer("--work-item", 60)
        self.assertGolden("product-draft-from-record-no-open-questions", self._file(product_draft.draft_path("60")))

    # --- review findings outlines ---

    def test_product_review_findings_outline(self):
        self._writer("--slug", "route-sheet")
        draft = product_draft.draft_path("new-route-sheet")
        draft.write_text(DRAFT, encoding="utf-8")
        result = self.invoke("prompt_product_reviewer", "--inline", draft, "--pass", "product")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertGolden("product-findings-outline", self._file(product_draft.product_findings_path("new-route-sheet")))

    def test_technical_review_findings_outline(self):
        draft = self.product_draft(DRAFT, slug="route-sheet")
        result = self.invoke("prompt_product_reviewer", "--inline", draft, "--pass", "technical")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertGolden(
            "technical-findings-outline", self._file(product_draft.technical_findings_path("new-route-sheet")),
        )

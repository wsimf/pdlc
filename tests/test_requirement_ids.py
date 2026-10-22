"""Requirement and constraint ids, including letter (`FR-1a`) and dotted (`FR-1.1`) sub-items."""

from __future__ import annotations

import unittest

from pdlc.domain.patch import requirement_changes, requirement_statements
from pdlc.domain.task_artifact import declared_links
from pdlc.domain.task_plan import REQUIREMENT_ID_PATTERN, declared_identifiers
from pdlc.prompts.context import FR_C_PATTERN, covered_text


class RequirementIdTests(unittest.TestCase):
    def test_pattern_reads_plain_letter_and_dotted_ids_and_nothing_looser(self):
        text = "FR-1, FR-1a, FR-12a, C-4a, FR-1.1, FR-1.1.2, FR-2.3b. FR-3ab FR-4A FR-5-1 ends at FR-6."
        self.assertEqual(
            REQUIREMENT_ID_PATTERN.findall(text),
            ["FR-1", "FR-1a", "FR-12a", "C-4a", "FR-1.1", "FR-1.1.2", "FR-2.3b", "FR-5", "FR-6"],
        )

    def test_task_covers_keep_sub_item_ids(self):
        body = "**Requirements Covered:** FR-1a, FR-1.1, C-4a\n**UI Journeys:** UJ-2\n"
        self.assertEqual(declared_links(body)["covers"], ["C-4a", "FR-1.1", "FR-1a", "UJ-2"])

    def test_parent_declares_sub_item_ids(self):
        product = "- FR-1: Base.\n- FR-1a: Inserted.\n- FR-1.1: Dotted.\n- C-4a: Constraint.\n"
        self.assertEqual(declared_identifiers(product, REQUIREMENT_ID_PATTERN), ["C-4a", "FR-1", "FR-1.1", "FR-1a"])

    def test_brief_resolves_a_sub_item_without_pulling_in_its_parent_or_siblings(self):
        parent = "## Product\n- FR-1: Base.\n- FR-1a: Inserted.\n- FR-10: Tenth.\n\n### FR-2.1: Dotted heading\nBody.\n"
        self.assertEqual(covered_text(parent, "Product", "Covers FR-1a", FR_C_PATTERN), "- FR-1a: Inserted.")
        self.assertEqual(covered_text(parent, "Product", "Covers FR-1", FR_C_PATTERN), "- FR-1: Base.")
        self.assertEqual(covered_text(parent, "Product", "Covers FR-2.1", FR_C_PATTERN), "### FR-2.1: Dotted heading\nBody.")

    def test_patch_tracks_sub_item_statements_in_id_order(self):
        landed = "- FR-1: Base.\n- FR-10: Tenth.\n"
        draft = landed + "- FR-1.1: Dotted.\n- FR-1a: Inserted.\n- FR-2: Second.\n"
        self.assertEqual(requirement_statements(draft)["FR-1a"], "Inserted.")
        self.assertEqual([change["id"] for change in requirement_changes(landed, draft)], ["FR-1a", "FR-1.1", "FR-2"])


if __name__ == "__main__":
    unittest.main()

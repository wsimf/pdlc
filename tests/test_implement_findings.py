"""The task reviewer's findings file splits into one section per fixing agent."""

from __future__ import annotations

import unittest

from pdlc.domain.implement_findings import parse
from pdlc.domain.lifecycle import PdlcError


def _file(implementation: str = "None", test: str = "None", verdict: str = "Changes Required") -> str:
    return (
        "Task review complete: T\n\nLayout:\n\n- F1 [P0–P3] [blocking|non-blocking] <where> — <what>\n\n"
        f"### Implementation findings\n\n{implementation}\n\n"
        f"### Test findings\n\n{test}\n\n"
        f"### Verdict\n\n{verdict}\n"
    )


class ImplementFindingsTest(unittest.TestCase):
    def test_sections_split_by_owner(self):
        findings = parse(_file("- F1 [P1] [blocking] a.py — x", "- F2 [P2] [blocking] t.py — y"), "f")
        self.assertEqual(findings.implementation, "- F1 [P1] [blocking] a.py — x")
        self.assertEqual(findings.test, "- F2 [P2] [blocking] t.py — y")
        self.assertEqual(findings.verdict, "Changes Required")
        self.assertTrue(findings.implementation_blocking)

    def test_none_and_non_blocking_hand_the_implementer_nothing(self):
        self.assertEqual(parse(_file(), "f").implementation, "")
        self.assertFalse(parse(_file("- F1 [P3] [non-blocking] a.py — nit"), "f").implementation_blocking)

    def test_a_fenced_heading_is_content(self):
        body = "- F1 [P1] [blocking] a.py — x\n```\n### Test findings\n```"
        findings = parse(_file(body, "- F2 [P2] [blocking] t.py — y"), "f")
        self.assertIn("```\n### Test findings\n```", findings.implementation)
        self.assertEqual(findings.test, "- F2 [P2] [blocking] t.py — y")

    def test_missing_section_or_unfilled_verdict_is_refused(self):
        with self.assertRaisesRegex(PdlcError, "missing `### Test findings`"):
            parse("### Implementation findings\n\nNone\n\n### Verdict\n\nChanges Required\n", "f")
        with self.assertRaisesRegex(PdlcError, "has no verdict"):
            parse(_file(verdict="<Changes Required|Approval Required>"), "f")


if __name__ == "__main__":
    unittest.main()

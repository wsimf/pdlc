import unittest

from pdlc.domain.completion_evidence import parse_completion_report


class CompletionTests(unittest.TestCase):
    def test_completion_report_parses_required_sections(self):
        body = """## Shipped
- Feature shipped.
## Verification
- clean @ abc123
## Decisions
- None.
## Open Questions
- Is the migration complete? — Resolved: yes.
## Limitations
- None.
## Skipped Stages
- None.
"""
        report = parse_completion_report(body)
        self.assertEqual(report.verified_commit, "abc123")

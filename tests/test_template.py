import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from pdlc.cli import main
from pdlc.domain.lifecycle import PdlcError
from pdlc.templates.template import Section, load_template, require_template, template_names, template_problems, template_sections

VALID = "### What\n\nIt works.\n\n### Why\n\nBecause.\n\n### How\n\nBy design.\n\n### Testing\n\nTests pass.\n"


class TemplateValidationTests(unittest.TestCase):
    def test_sections_come_from_the_template_headings(self):
        sections = template_sections(load_template("implementation-summary"))
        self.assertEqual(sections, [
            Section("What", False), Section("Why", False), Section("How", False),
            Section("Testing", False), Section("Screenshots", True), Section("Anything else", True),
        ])

    def test_a_conforming_body_has_no_problems(self):
        template = load_template("implementation-summary")
        self.assertEqual(template_problems(template, VALID), [])
        with_extras = "## Implementation\n\n" + VALID + "\n### Notes\n\n- extra\n\n---\nStacked on #12; this task's work starts at abc.\n"
        self.assertEqual(template_problems(template, with_extras), [])

    def test_headings_match_at_any_level_and_case(self):
        template = "### Why\n"
        self.assertEqual(template_problems(template, "## why\n\nBecause.\n"), [])

    def test_a_footer_below_a_break_is_not_section_content(self):
        template = "### Verified\n"
        body = "### Verified\n\n---\nStacked on #12.\n"
        self.assertEqual(template_problems(template, body), ["no content under: ### Verified"])

    def test_every_problem_is_reported_in_template_order(self):
        template = load_template("implementation-summary")
        body = "### Testing\n\n- <what was run>\n\n### Anything else\n\n### Why\n\nBecause.\n"
        self.assertEqual(template_problems(template, body), [
            "missing section: ### What",
            "missing section: ### How",
            "no content under: ### Testing",
            "no content under: ### Anything else (fill it in or drop the heading)",
        ])

    def test_a_placeholder_beside_real_content_is_flagged(self):
        self.assertEqual(template_problems("### Why\n", "### Why\n\n- Real.\n- <more>\n"), ["unfilled placeholder under: ### Why"])

    def test_require_template_raises_with_problems_and_template(self):
        with self.assertRaises(PdlcError) as caught:
            require_template("implementation-summary", "Shipped it.", "implementation summary")
        message = str(caught.exception)
        self.assertIn("the implementation summary does not follow the implementation-summary template:", message)
        self.assertIn("- missing section: ### What", message)
        self.assertIn(load_template("implementation-summary").rstrip(), message)
        require_template("implementation-summary", VALID, "implementation summary")

    def test_unknown_or_traversing_names_are_refused(self):
        for name in ("nope", "../guides/guide", ""):
            with self.subTest(name=name), self.assertRaises(PdlcError):
                load_template(name)


class TemplateCommandTests(unittest.TestCase):
    def test_prints_template_without_configuration(self):
        output = io.StringIO()
        with patch("pdlc.cli.load_config", side_effect=AssertionError("template loaded config")), redirect_stdout(output):
            self.assertEqual(main(["template", "implementation-summary"]), 0)
        self.assertEqual(output.getvalue(), load_template("implementation-summary"))

    def test_help_lists_templates(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["template", "--help"]), 0)
        self.assertIn("NAME\n    pdlc template - ", output.getvalue())
        self.assertIn("AVAILABLE TEMPLATES", output.getvalue())
        for name in template_names():
            self.assertIn(f"  {name}", output.getvalue())

    def test_unknown_template_and_bad_arity_fail(self):
        for argv in (["template", "nope"], ["template"], ["template", "a", "b"]):
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()) as error:
                self.assertEqual(main(argv), 1)
            self.assertTrue(error.getvalue())


if __name__ == "__main__":
    unittest.main()

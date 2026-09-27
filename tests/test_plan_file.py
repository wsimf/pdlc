"""The combined task and tech plan file the Technical Plan stage edits in place."""

import unittest

from pdlc.domain.plan_file import (
    EMPTY_PLAN,
    manifest_errors,
    parse,
    plan_baseline,
    plan_errors,
    render,
    same_task,
    stored_plan,
)

BODY = "**Scope:**\nBuild it.\n\n**Acceptance Criteria:**\n- [ ] It works.\n"


class PlanFileTests(unittest.TestCase):
    def test_render_and_parse_round_trip(self):
        planned, errors = parse(render(BODY, "1. `src/a.py` — add it."))
        self.assertEqual(errors, [])
        assert planned is not None
        self.assertTrue(same_task(planned.task, BODY))
        self.assertEqual(planned.plan, "1. `src/a.py` — add it.")

    def test_an_unplanned_task_renders_the_placeholder_which_parses_as_empty(self):
        text = render(BODY, "")
        self.assertIn(EMPTY_PLAN, text)
        planned, _ = parse(text)
        assert planned is not None
        self.assertEqual(planned.plan, "")
        self.assertIn("the tech plan is empty", plan_errors(planned.plan)[0])

    def test_a_placeholder_left_beside_a_plan_is_stripped(self):
        planned, _ = parse(render(BODY, "").replace(EMPTY_PLAN, f"{EMPTY_PLAN}\nThe plan."))
        assert planned is not None
        self.assertEqual(planned.plan, "The plan.")

    def test_a_missing_or_repeated_marker_is_malformed(self):
        text = render(BODY, "Plan.")
        self.assertIsNone(parse(text.replace("--- END TECH PLAN ---\n", ""))[0])
        planned, errors = parse(text + "--- BEGIN TASK ---\n")
        self.assertIsNone(planned)
        self.assertIn("`--- BEGIN TASK ---` must appear exactly once on its own line, found 2", errors)

    def test_markers_out_of_order_are_malformed(self):
        text = "--- BEGIN TECH PLAN ---\nPlan.\n--- END TECH PLAN ---\n--- BEGIN TASK ---\nBody.\n--- END TASK ---\n"
        planned, errors = parse(text)
        self.assertIsNone(planned)
        self.assertIn("must appear in the order", errors[0])

    def test_a_marker_inside_a_code_fence_is_content(self):
        planned, errors = parse(render(BODY, "```\n--- END TECH PLAN ---\n```"))
        self.assertEqual(errors, [])
        assert planned is not None
        self.assertIn("--- END TECH PLAN ---", planned.plan)

    def test_text_outside_the_blocks_is_rejected(self):
        planned, errors = parse("Note.\n" + render(BODY, "Plan."))
        self.assertIsNone(planned)
        self.assertIn("text outside the task and tech plan blocks", errors[0])

    def test_headings_are_rejected_outside_code_fences_only(self):
        self.assertIn("heading", plan_errors("# Plan\n1. Step.")[0])
        self.assertIn("heading", plan_errors("1. Step.\n## Steps")[0])
        self.assertEqual(plan_errors("### Detail\n1. Step."), [])
        self.assertEqual(plan_errors("```bash\n# run the tests\n```"), [])

    def test_stored_plan_drops_its_heading(self):
        self.assertEqual(stored_plan("## Technical Plan\n\nTouch one module.\n"), "Touch one module.")
        self.assertEqual(stored_plan(None), "")

    def test_the_baseline_ignores_line_endings_and_trailing_space(self):
        self.assertEqual(plan_baseline(BODY, "Plan."), plan_baseline(BODY.replace("\n", "\r\n") + "  \n", "Plan.\n"))
        self.assertNotEqual(plan_baseline(BODY, "Plan."), plan_baseline(BODY, "Other plan."))

    def test_manifest_errors_name_each_missing_or_extra_field(self):
        errors = manifest_errors([{"id": "TASK-001", "plan": "/tmp/p.md"}])
        self.assertIn("TASK-001 needs its generated 'number'", errors)
        self.assertIn("TASK-001 carries fields the manifest does not take: plan", errors)
        self.assertEqual(manifest_errors([{"id": "TASK-001", "number": 1, "title": "t", "file": "f", "baseline": "b"}]), [])


if __name__ == "__main__":
    unittest.main()

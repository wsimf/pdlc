"""Tests for the prompt assembly engine and the bundled fragments it renders."""

from __future__ import annotations

from importlib.resources import files
import unittest

from pdlc.prompts.assemble import (
    PromptError,
    check_syntax,
    package_loader,
    render,
    render_text,
)


def _loader(fragments: dict[str, str]):
    def load(path: str) -> str:
        if path not in fragments:
            raise PromptError(f"no such fragment: {path}")
        return fragments[path]

    return load


class RenderTextTests(unittest.TestCase):
    def test_substitutes_placeholder_inline(self) -> None:
        self.assertEqual(
            render_text("task `{{TAG}}` here\n", {"TAG": "WORK-1-TASK-2"}, loader=_loader({})),
            "task `WORK-1-TASK-2` here\n",
        )

    def test_missing_name_is_an_error(self) -> None:
        with self.assertRaises(PromptError) as caught:
            render_text("{{TAG}}\n", {}, loader=_loader({}))
        self.assertIn("TAG", str(caught.exception))

    def test_non_string_value_is_an_error(self) -> None:
        with self.assertRaises(PromptError):
            render_text("{{COUNT}}\n", {"COUNT": 3}, loader=_loader({}))

    def test_include_keeps_the_including_lines_newline(self) -> None:
        rendered = render_text(
            "{{INCLUDE:shared/rules.md}}\ntail line\n",
            {},
            loader=_loader({"shared/rules.md": "first\nsecond\n"}),
        )
        self.assertEqual(rendered, "first\nsecond\ntail line\n")

    def test_include_is_rendered_against_the_same_context(self) -> None:
        rendered = render_text(
            "{{INCLUDE:shared/scope.md}}\n",
            {"SCOPE": "this one task"},
            loader=_loader({"shared/scope.md": "leaf worker for {{SCOPE}}.\n"}),
        )
        self.assertEqual(rendered, "leaf worker for this one task.\n")

    def test_include_cycle_is_an_error(self) -> None:
        with self.assertRaises(PromptError) as caught:
            render_text(
                "{{INCLUDE:a.md}}\n",
                {},
                loader=_loader({"a.md": "{{INCLUDE:b.md}}\n", "b.md": "{{INCLUDE:a.md}}\n"}),
            )
        self.assertIn("cycle", str(caught.exception))

    def test_unknown_fragment_is_an_error(self) -> None:
        with self.assertRaises(PromptError):
            render_text("{{INCLUDE:missing.md}}\n", {}, loader=_loader({}))


class ConditionalBlockTests(unittest.TestCase):
    TEMPLATE = "before\n{{#IF FINDINGS}}\n## Findings\n\n{{FINDINGS_TEXT}}\n\n{{/IF}}\nafter\n"

    def test_truthy_condition_keeps_the_body_and_drops_the_directives(self) -> None:
        rendered = render_text(
            self.TEMPLATE,
            {"FINDINGS": True, "FINDINGS_TEXT": "a red check"},
            loader=_loader({}),
        )
        self.assertEqual(rendered, "before\n## Findings\n\na red check\n\nafter\n")

    def test_falsey_condition_drops_the_whole_section(self) -> None:
        rendered = render_text(
            self.TEMPLATE,
            {"FINDINGS": "", "FINDINGS_TEXT": "unused"},
            loader=_loader({}),
        )
        self.assertEqual(rendered, "before\nafter\n")

    def test_else_body_renders_for_falsey_value(self) -> None:
        rendered = render_text(
            "{{#IF VALUE}}\ntruthy\n{{#ELSE}}\nfalsy\n{{/IF}}\n",
            {"VALUE": 0},
            loader=_loader({}),
        )
        self.assertEqual(rendered, "falsy\n")

    def test_else_body_keeps_lines_up_to_the_closing_if(self) -> None:
        # Regression: the old {{#IF}}...{{#ELSE}}...{{/ELSE}}...{{/IF}} syntax silently
        # dropped any line between {{/ELSE}} and {{/IF}}.
        rendered = render_text(
            "{{#IF X}}\nyes\n{{#ELSE}}\nno\nLOST\n{{/IF}}\n",
            {"X": False},
            loader=_loader({}),
        )
        self.assertEqual(rendered, "no\nLOST\n")

    def test_empty_collection_is_falsy(self) -> None:
        for value in ([], {}):
            rendered = render_text(
                "{{#IF VALUE}}\ntruthy\n{{#ELSE}}\nfalsy\n{{/IF}}\n",
                {"VALUE": value},
                loader=_loader({}),
            )
            self.assertEqual(rendered, "falsy\n")

    def test_nested_else_bodies_render_for_each_selected_branch(self) -> None:
        template = (
            "{{#IF OUTER}}\n"
            "outer true\n"
            "{{#IF INNER}}\ninner true\n{{#ELSE}}\ninner false\n{{/IF}}\n"
            "{{#ELSE}}\nouter false\n"
            "{{/IF}}\n"
        )
        self.assertEqual(
            render_text(template, {"OUTER": True, "INNER": ""}, loader=_loader({})),
            "outer true\ninner false\n",
        )
        self.assertEqual(
            render_text(template, {"OUTER": False, "INNER": True}, loader=_loader({})),
            "outer false\n",
        )

    def test_unclosed_block_is_an_error(self) -> None:
        with self.assertRaises(PromptError):
            render_text("{{#IF X}}\nbody\n", {"X": True}, loader=_loader({}))

    def test_mismatched_close_is_an_error(self) -> None:
        with self.assertRaises(PromptError):
            render_text("{{#IF X}}\nbody\n{{/EACH}}\n", {"X": True}, loader=_loader({}))

    def test_stray_close_is_an_error(self) -> None:
        with self.assertRaises(PromptError):
            render_text("body\n{{/IF}}\n", {}, loader=_loader({}))

    def test_stray_slash_else_is_an_error(self) -> None:
        with self.assertRaises(PromptError):
            render_text("body\n{{/ELSE}}\n", {}, loader=_loader({}))

    def test_two_else_branches_in_one_if_is_an_error(self) -> None:
        with self.assertRaises(PromptError):
            render_text(
                "{{#IF X}}\na\n{{#ELSE}}\nb\n{{#ELSE}}\nc\n{{/IF}}\n",
                {"X": True},
                loader=_loader({}),
            )

    def test_else_inside_each_is_an_error(self) -> None:
        with self.assertRaises(PromptError):
            render_text(
                "{{#EACH STACK}}\na\n{{#ELSE}}\nb\n{{/EACH}}\n",
                {"STACK": []},
                loader=_loader({}),
            )


class EachBlockTests(unittest.TestCase):
    def test_renders_the_body_once_per_item(self) -> None:
        rendered = render_text(
            "{{#EACH STACK}}\n- {{BRANCH}}\n{{/EACH}}\n",
            {"STACK": [{"BRANCH": "one"}, {"BRANCH": "two"}]},
            loader=_loader({}),
        )
        self.assertEqual(rendered, "- one\n- two\n")

    def test_item_scope_falls_back_to_the_surrounding_context(self) -> None:
        rendered = render_text(
            "{{#EACH STACK}}\n{{WORK}} {{BRANCH}}\n{{/EACH}}\n",
            {"WORK": "WORK-7", "STACK": [{"BRANCH": "one"}]},
            loader=_loader({}),
        )
        self.assertEqual(rendered, "WORK-7 one\n")

    def test_item_shadows_the_surrounding_context(self) -> None:
        rendered = render_text(
            "{{#EACH STACK}}\n{{NAME}}\n{{/EACH}}\n",
            {"NAME": "outer", "STACK": [{"NAME": "inner"}]},
            loader=_loader({}),
        )
        self.assertEqual(rendered, "inner\n")

    def test_body_may_include_a_fragment_per_item(self) -> None:
        rendered = render_text(
            "{{#EACH STACK}}\n{{INCLUDE:entry.md}}\n{{/EACH}}\n",
            {"STACK": [{"BRANCH": "one"}, {"BRANCH": "two"}]},
            loader=_loader({"entry.md": "### {{BRANCH}}\n"}),
        )
        self.assertEqual(rendered, "### one\n### two\n")

    def test_empty_sequence_renders_nothing(self) -> None:
        rendered = render_text(
            "a\n{{#EACH STACK}}\n- {{BRANCH}}\n{{/EACH}}\nb\n",
            {"STACK": []},
            loader=_loader({}),
        )
        self.assertEqual(rendered, "a\nb\n")

    def test_non_sequence_value_is_an_error(self) -> None:
        with self.assertRaises(PromptError):
            render_text("{{#EACH STACK}}\nx\n{{/EACH}}\n", {"STACK": "nope"}, loader=_loader({}))

    def test_non_mapping_item_is_an_error(self) -> None:
        with self.assertRaises(PromptError):
            render_text("{{#EACH STACK}}\nx\n{{/EACH}}\n", {"STACK": ["nope"]}, loader=_loader({}))

    def test_nested_condition_inside_each(self) -> None:
        rendered = render_text(
            "{{#EACH STACK}}\n{{BRANCH}}\n{{#IF PLAN}}\nplan: {{PLAN}}\n{{/IF}}\n{{/EACH}}\n",
            {"STACK": [{"BRANCH": "one", "PLAN": "p"}, {"BRANCH": "two", "PLAN": ""}]},
            loader=_loader({}),
        )
        self.assertEqual(rendered, "one\nplan: p\ntwo\n")


class SyntaxCheckTests(unittest.TestCase):
    """`check_syntax` validates template structure without needing a render context."""

    def test_valid_template_passes(self) -> None:
        check_syntax("{{#IF X}}\na\n{{#ELSE}}\nb\n{{/IF}}\n")

    def test_unclosed_block_is_invalid(self) -> None:
        with self.assertRaises(PromptError):
            check_syntax("{{#IF X}}\nbody\n")

    def test_stray_close_is_invalid(self) -> None:
        with self.assertRaises(PromptError):
            check_syntax("body\n{{/IF}}\n")

    def test_slash_else_is_invalid(self) -> None:
        with self.assertRaises(PromptError):
            check_syntax("{{#IF X}}\na\n{{#ELSE}}\nb\n{{/ELSE}}\n{{/IF}}\n")

    def test_two_else_branches_is_invalid(self) -> None:
        with self.assertRaises(PromptError):
            check_syntax("{{#IF X}}\na\n{{#ELSE}}\nb\n{{#ELSE}}\nc\n{{/IF}}\n")

    def test_else_inside_each_is_invalid(self) -> None:
        with self.assertRaises(PromptError):
            check_syntax("{{#EACH X}}\na\n{{#ELSE}}\nb\n{{/EACH}}\n")

    def test_else_outside_any_block_is_invalid(self) -> None:
        with self.assertRaises(PromptError):
            check_syntax("{{#ELSE}}\n")

    def test_block_directive_not_alone_on_line_is_invalid(self) -> None:
        with self.assertRaises(PromptError):
            check_syntax("prefix {{#IF X}} suffix\nbody\n{{/IF}}\n")

    def test_unknown_directive_is_invalid(self) -> None:
        with self.assertRaises(PromptError):
            check_syntax("{{#WEIRD X}}\n")

    def test_unsafe_include_path_is_invalid(self) -> None:
        with self.assertRaises(PromptError):
            check_syntax("{{INCLUDE:../../etc/passwd.md}}\n")

    def test_missing_include_target_is_invalid_when_checked(self) -> None:
        with self.assertRaises(PromptError):
            check_syntax("{{INCLUDE:missing.md}}\n", path_exists=lambda path: False)

    def test_include_target_present_is_valid(self) -> None:
        check_syntax("{{INCLUDE:present.md}}\n", path_exists=lambda path: True)

    def test_missing_include_target_not_checked_without_path_exists(self) -> None:
        check_syntax("{{INCLUDE:missing.md}}\n")


def _bundled_markdown_paths(root: object, base: str = "") -> list[str]:
    """Docs-relative paths of every ``.md`` fragment under ``root``, recursing into ``shared/``."""
    paths: list[str] = []
    for entry in sorted(root.iterdir(), key=lambda item: item.name):  # type: ignore[attr-defined]
        rel = f"{base}/{entry.name}" if base else entry.name
        if entry.is_dir():
            paths.extend(_bundled_markdown_paths(entry, rel))
        elif entry.name.endswith(".md"):
            paths.append(rel)
    return paths


class BundledPromptSyntaxTests(unittest.TestCase):
    """Every bundled prompt fragment must have valid template syntax."""

    def test_every_bundled_fragment_has_valid_syntax(self) -> None:
        docs_root = files("pdlc.prompts").joinpath("docs")
        paths = _bundled_markdown_paths(docs_root)
        self.assertGreater(len(paths), 0)
        for path in paths:
            with self.subTest(path=path):
                text = docs_root.joinpath(*path.split("/")).read_text(encoding="utf-8")
                check_syntax(
                    text,
                    path_exists=lambda p: docs_root.joinpath(*p.split("/")).is_file(),
                )


class PackagedPromptTests(unittest.TestCase):
    """The bundled fragments must render with the context each prompt declares."""

    TASK = {
        "TASK_TAG": "WORK-12-TASK-3",
        "TASK_TITLE": "Add the seam",
        "TASK_BODY": "Scope, non-goals, acceptance criteria.",
        "TECHNICAL_PLAN": "Touch one module.",
    }

    def test_package_loader_reads_a_bundled_fragment(self) -> None:
        self.assertIn("## Execution boundary", package_loader("shared/execution-boundary.md"))

    def test_package_loader_rejects_traversal(self) -> None:
        with self.assertRaises(PromptError):
            package_loader("../../../etc/passwd")

    def test_implement_renders_without_optional_sections(self) -> None:
        rendered = render(
            "implement",
            {
                **self.TASK,
                "EXECUTION_SCOPE": "this one task",
                "PARENT_WORK_ITEM": "12",
                "REQUIREMENTS_TEXT": "FR-1 text",
                "DEPENDENCY_SUMMARIES": "none",
                "JOURNEY_TEXT": "n/a",
                "FINDINGS": "",
                "FINDINGS_TEXT": "",
                "UPSTREAM_CHANGES": "",
                "BUILD_RUN_SKILL": "",
            },
        )
        self.assertIn("## Execution boundary", rendered)
        self.assertIn("leaf worker for this one task.", rendered)
        self.assertIn("WORK-12-TASK-3", rendered)
        self.assertNotIn("## Findings to address", rendered)
        self.assertNotIn("## Changed since last publish", rendered)
        self.assertNotIn("## Verify", rendered)
        self.assertNotIn("{{", rendered)

    def test_implement_renders_optional_sections_when_supplied(self) -> None:
        rendered = render(
            "implement",
            {
                **self.TASK,
                "EXECUTION_SCOPE": "this one task",
                "PARENT_WORK_ITEM": "12",
                "REQUIREMENTS_TEXT": "FR-1 text",
                "DEPENDENCY_SUMMARIES": "none",
                "JOURNEY_TEXT": "n/a",
                "FINDINGS": "yes",
                "FINDINGS_TEXT": "the invalidation text",
                "UPSTREAM_CHANGES": "the upstream patch",
                "BUILD_RUN_SKILL": "build-run-ios",
            },
        )
        self.assertIn("## Findings to address", rendered)
        self.assertIn("the invalidation text", rendered)
        self.assertIn("## Changed since last publish", rendered)
        self.assertIn("--- BEGIN UPSTREAM CHANGES ---\n\nthe upstream patch\n\n--- END UPSTREAM CHANGES ---", rendered)
        self.assertIn("invoke the `build-run-ios` skill", rendered)
        self.assertNotIn("{{", rendered)

    def test_pr_fix_renders(self) -> None:
        rendered = render(
            "pr-fix",
            {
                **self.TASK,
                "EXECUTION_SCOPE": "this one pull request",
                "PR_NUMBER": "42",
                "OWNER": "acme",
                "REPO": "widgets",
                "DECISIONS_TEXT": "No previously recorded decisions.",
                "FAILING_CHECKS": "",
                "FAILING_CHECKS_TEXT": "",
            },
        )
        self.assertIn("pull request `42` in `acme/widgets`", rendered)
        self.assertIn("-F pr=42", rendered)
        self.assertNotIn("## Failing checks", rendered)
        self.assertNotIn("{{", rendered)

    def test_triage_renders_one_entry_per_stack_task(self) -> None:
        rendered = render(
            "triage",
            {
                "EXECUTION_SCOPE": "this one set of requests",
                "OPEN_REQUESTS_TEXT": "Please rename the seam.",
                "STACK": [
                    {
                        "BRANCH": "work-12-task-1",
                        "TASK_TAG": "WORK-12-TASK-1",
                        "TASK_TITLE": "First",
                        "TECHNICAL_PLAN": "Plan one.",
                    },
                    {
                        "BRANCH": "work-12-task-2",
                        "TASK_TAG": "WORK-12-TASK-2",
                        "TASK_TITLE": "Second",
                        "TECHNICAL_PLAN": "Plan two.",
                    },
                ],
            },
        )
        self.assertIn("### work-12-task-1 — `WORK-12-TASK-1` `First`", rendered)
        self.assertIn("### work-12-task-2 — `WORK-12-TASK-2` `Second`", rendered)
        self.assertIn("Plan two.", rendered)
        self.assertNotIn("{{", rendered)


if __name__ == "__main__":
    unittest.main()

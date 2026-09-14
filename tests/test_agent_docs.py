"""The agent-facing Markdown stays consistent with the CLI and the pipeline.

Skills, guides, and design docs describe the CLI as a contract, so a renamed
command, a dropped flag, a moved reference file, or a stage whose CI gating
changed must fail here rather than in an agent's run. The last class is the
deterministic proxy for agent behaviour: whether an LLM actually follows a
`# Due Next` section needs a scripted model run and cannot be unit-tested, but
every section it could be handed can be checked to name at most one skill,
which exists, only commands that resolve, and a target that agrees with the
action `pdlc next` routes.
"""

from __future__ import annotations

import importlib
import re
import unittest
from pathlib import Path

from pdlc import cli
from pdlc.commands.inspect import _due_next_section
from pdlc.domain.evidence import ReviewVerdict, compose_review
from pdlc.domain.model import due_next
from pdlc.domain.workflow import Gate
from pdlc.domain.workflows.pipeline import PIPELINE_REGISTRY
from test_due_next_stages import IMPLEMENTATION_TASKS, TECHNICAL_PLAN_TASKS

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "agent" / "skills"
GUIDES = ROOT / "src" / "pdlc" / "guides"
REFERENCES = SKILLS / "pdlc" / "references"
DOCUMENTS = sorted([*(ROOT / "agent").rglob("*.md"), *GUIDES.glob("*.md"), *(ROOT / "docs").glob("*.md")])

# A family reference ("the `pdlc post *` commands", "`pdlc <command> --help`")
# names no single command, so it has nothing to resolve.
_FAMILY = re.compile(r"^pdlc (--help|<[^>]+>|(inspect|post)\b\s*\*?|inspect\*)(\s+--help)?$")


def _commands(text: str) -> list[str]:
    """Every `pdlc ...` invocation: inline code spans plus shell-block lines."""
    spans = re.findall(r"`(pdlc [^`\n]+)`", text)
    for block in re.findall(r"```(?:bash|sh)?\n(.*?)```", text, re.DOTALL):
        spans += [line.strip() for line in block.splitlines() if line.strip().startswith("pdlc ")]
    return spans


def _feature():
    return PIPELINE_REGISTRY.for_work_type("feature")


class CommandReferenceTests(unittest.TestCase):
    def test_every_documented_command_resolves_and_every_flag_exists(self):
        guides = {path.stem for path in GUIDES.glob("*.md")}
        usage = cli._usage()
        checked = 0
        for path in DOCUMENTS:
            for span in _commands(path.read_text()):
                if _FAMILY.match(span):
                    continue
                with self.subTest(file=str(path.relative_to(ROOT)), command=span):
                    try:
                        module_name, rest = cli._resolve(span.split()[1:])
                    except ValueError:
                        self.fail(f"`{span}` is not a pdlc command")
                    checked += 1
                    if module_name == "pdlc.commands.guide" and rest and not rest[0].startswith(("<", "-")):
                        self.assertIn(rest[0], guides, f"`{span}` names no guide under src/pdlc/guides/")
                    doc = importlib.import_module(module_name).__doc__ or ""
                    for flag in re.findall(r"(?<![\w-])--[a-z][a-z-]*", span):
                        self.assertTrue(flag in doc or flag in usage, f"{flag} is not documented by `{span.split(' --')[0]}`")
        self.assertGreater(checked, 100)

    def test_bare_inspect_is_only_ever_given_a_work_item(self):
        # `pdlc inspect <typo>` would silently resolve to bare `inspect`; its
        # first argument must be a work item or a placeholder for one.
        for path in DOCUMENTS:
            for span in _commands(path.read_text()):
                module_name, rest = cli._resolve(span.split()[1:]) if not _FAMILY.match(span) else ("", [])
                if module_name == "pdlc.commands.inspect" and rest:
                    with self.subTest(file=str(path.relative_to(ROOT)), command=span):
                        self.assertRegex(rest[0], r"^(\d+|<|\{|N\b|WORK_ITEM|ID|#|--|\$)")


class PathReferenceTests(unittest.TestCase):
    def test_relative_links_and_reference_paths_exist(self):
        for path in DOCUMENTS:
            text = path.read_text()
            skill = next((parent for parent in (path.parent, *path.parents) if (parent / "SKILL.md").exists()), path.parent)
            for link in re.findall(r"\]\(([^)\s#]+)(?:#[^)]*)?\)", text):
                if re.match(r"^[a-z]+:", link):
                    continue
                with self.subTest(file=str(path.relative_to(ROOT)), link=link):
                    self.assertTrue((path.parent / link).exists())
            for ref in re.findall(r"`((?:\.\./)*references/[\w./-]+\.md)`", text):
                with self.subTest(file=str(path.relative_to(ROOT)), reference=ref):
                    self.assertTrue((skill / ref).exists() or (path.parent / ref).exists())
            for ref in re.findall(r"`(agent/[\w./-]+)`", text):
                with self.subTest(file=str(path.relative_to(ROOT)), reference=ref):
                    self.assertTrue((ROOT / ref).exists())


class StateDocsMatchPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ci_gated = {stage.name for stage in _feature().stages if stage.ci_gated}
        self.stage_names = {stage.name for stage in _feature().stages}

    def test_stage_ownership_ci_pending_row_names_exactly_the_ci_gated_stages(self):
        text = (REFERENCES / "stage-ownership.md").read_text()
        rows = [line for line in text.splitlines() if line.startswith("|") and "at `CI Pending`" in line.split("|")[1]]
        self.assertEqual(len(rows), 1)
        named = set(re.findall(r"`([^`]+)`", rows[0].split("|")[1])) & self.stage_names
        self.assertEqual(named, self.ci_gated)

    def test_workflow_state_diagram_has_ci_pending_exactly_on_ci_gated_stages(self):
        text = (REFERENCES / "pdlc-workflow.md").read_text()
        blocks = dict(re.findall(r"\n    state (\w+) \{\n(.*?)\n    \}", text, re.DOTALL))
        self.assertEqual(set(blocks), {name.replace(" ", "") for name in self.stage_names if name != "Complete"})
        with_ci = {name for name, body in blocks.items() if "_CIPending" in body}
        self.assertEqual(with_ci, {name.replace(" ", "") for name in self.ci_gated})

    def test_resolve_ci_guide_names_every_ci_gated_stage(self):
        opening = (GUIDES / "resolve-ci.md").read_text().split("\n## ", 1)[0]
        named = set(re.findall(r"`([^`]+)`", opening)) & self.stage_names
        self.assertEqual(named, self.ci_gated)


class DueNextNamesARealTargetTests(unittest.TestCase):
    """Every `# Due Next` section, for every stage and gate, with and without
    the evidence an evidence gate reads."""

    def _sections(self):
        stages = [stage.name for stage in _feature().stages]
        for stage in stages:
            tasks = TECHNICAL_PLAN_TASKS if stage == "Technical Plan" else IMPLEMENTATION_TASKS if stage == "Implementation" else []
            for gate in Gate:
                item = {"Status": stage, "Gate State": gate.value, "Skipped States": "", "content": {"number": 4242}}
                yield stage, gate.value, due_next(item), _due_next_section(item, [], tasks)
                evidence = {
                    Gate.CHANGES_REQUIRED: "PDLC-REVIEW\n\n" + compose_review(stage, ReviewVerdict.CHANGES_REQUIRED, "Tighten section 2."),
                    Gate.STALE: f"PDLC-INVALIDATED\n\nInvalidated stage: {stage}\n\nScope changed.\n",
                    Gate.DECISION_REQUIRED: "PDLC-DECISION\n\n## Decision Required\n\nOn-device or server-side?\n",
                }.get(gate)
                if evidence is not None:
                    comments = [{"body": evidence, "createdAt": "2026-03-01T09:00:00Z", "url": "u", "author": {"login": "reviewer"}}]
                    yield stage, f"{gate.value} (evidence)", due_next(item), _due_next_section(item, comments, tasks)

    def test_every_section_names_at_most_one_existing_skill_and_only_real_commands(self):
        for stage, gate, due, section in self._sections():
            with self.subTest(stage=stage, gate=gate):
                self.assertNotRegex(section, r"\{[A-Za-z_. ]+\}", "an unresolved placeholder reached the agent")
                skills = set(re.findall(r"\b(pdlc-[a-z]+(?:-[a-z]+)*)\b", section)) - {"pdlc-post-ci"}
                self.assertLessEqual(len(skills), 1, f"names several skills: {sorted(skills)}")
                for skill in skills:
                    self.assertTrue((SKILLS / skill / "SKILL.md").exists(), f"{skill} is not a skill under agent/skills/")
                for span in _commands(section):
                    try:
                        cli._resolve(span.split()[1:])
                    except ValueError:
                        self.fail(f"`{span}` is not a pdlc command")

    def test_every_section_hands_over_the_target_its_routed_action_names(self):
        for stage, gate, due, section in self._sections():
            with self.subTest(stage=stage, gate=gate, action=due["action"]):
                action = due["action"]
                if "unable to parse and identify any evidence" in section:
                    # `pdlc next` routes an unevidenced change request to
                    # human-input; the section must stop rather than dispatch.
                    self.assertIn("Stop and request\nthe user's confirmation", section)
                    self.assertNotRegex(section, r"(?i)\binvoke pdlc-")
                elif action == "pdlc-post-ci":
                    self.assertIn("`pdlc post ci 4242`", section)
                elif action == "pdlc-continue":
                    self.assertIn("`pdlc next 4242`", section)
                elif action.startswith("pdlc-"):
                    self.assertRegex(section, rf"(?i)\binvoke {re.escape(action)}\b")
                elif action == "none":
                    self.assertEqual(section, "# Due Next\n\nThis work item has been completed.")
                else:
                    # A human stop may name only the stage's own skill, for the
                    # user to run interactively (Product's pdlc-write).
                    self.assertIn(action, ("human-input", "human-approval", "human-decision", "blocked"))
                    invoked = set(re.findall(r"(?i)\binvoke (pdlc-[a-z-]+)", section))
                    self.assertLessEqual(invoked, {_feature().stage(stage).skill})


if __name__ == "__main__":
    unittest.main()

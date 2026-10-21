"""Run the machine installer in an isolated home with mocked prerequisite CLIs."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "setup.sh"
FAKE_CLI = r'''
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["SETUP_LOG"], "a") as log:
    log.write(json.dumps([name, *args]) + "\n")
if name == "git":
    if args == ["rev-parse", "--show-toplevel"]:
        print(os.environ.get("GIT_ROOT", os.getcwd()))
    elif args == ["config", "--global", "--path", "core.excludesFile"]:
        if not os.environ.get("EXCLUDES_FILE"):
            sys.exit(1)
        print(os.environ["EXCLUDES_FILE"])
    elif os.environ.get("PULL_FAIL"):
        print("pull failed", file=sys.stderr)
        sys.exit(1)
elif name == "uv":
    if args[:2] == ["python", "find"]:
        marker = pathlib.Path(os.environ["HOME"]) / "python-installed"
        if os.environ.get("PYTHON_MISSING") and not marker.exists():
            sys.exit(1)
        print("/compatible/python")
    elif args[:2] == ["python", "install"]:
        (pathlib.Path(os.environ["HOME"]) / "python-installed").touch()
    elif os.environ.get("TOOL_FAIL"):
        print("tool install failed", file=sys.stderr)
        sys.exit(1)
elif name == "gh" and args[:1] == ["stack"]:
    sys.exit(int(os.environ.get("STACK_MISSING", "0")))
elif name == "az":
    if args[:2] == ["extension", "show"]:
        sys.exit(int(os.environ.get("AZ_EXTENSION_MISSING", "0")))
    if os.environ.get("AZ_INSTALL_FAIL"):
        print("Azure install failed", file=sys.stderr)
        sys.exit(1)
'''


class SetupScriptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = self.root / "repo with spaces"
        self.repo.mkdir()
        shutil.copy2(SCRIPT, self.repo / "setup.sh")
        (self.repo / "pyproject.toml").write_text(
            '[project]\nname = "pdlc"\nrequires-python = ">=3.12"\n'
        )
        for name in ("src/pdlc/__init__.py", "src/pdlc/cli.py",
                     "agent/skills/pdlc/SKILL.md",
                     "agent/sub-agents/claude/pdlc-reviewer.md",
                     "agent/sub-agents/codex/pdlc-reviewer.toml",
                     "agent/sub-agents/copilot/pdlc-reviewer.agent.md"):
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture\n")
        self.home = self.root / "home with spaces"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        # A controlled PATH lets missing-tool scenarios ignore the developer's machine.
        for name in ("bash", "dirname", "sed", "cat", "mkdir", "basename", "rm",
                     "ln", "mktemp", "cp", "mv", "grep", "tail"):
            (self.bin / name).symlink_to(shutil.which(name))
        for name in ("git", "uv", "gh", "az"):
            path = self.bin / name
            path.write_text(f"#!{sys.executable}\n" + FAKE_CLI)
            path.chmod(0o755)
        self.log = self.root / "commands.jsonl"
        # Drop XDG_CONFIG_HOME so the global ignore step writes only inside the fake home.
        self.env = {**{k: v for k, v in os.environ.items() if k != "XDG_CONFIG_HOME"},
                    "HOME": str(self.home), "PATH": str(self.bin), "SETUP_LOG": str(self.log)}
        self.ignore_file = self.home / ".config/git/ignore"

    def run_setup(self, *args, answers="", cwd=None, **env):
        return subprocess.run(
            [str(self.bin / "bash"), str(self.repo / "setup.sh"), *args],
            cwd=cwd or self.repo, env={**self.env, **env}, input=answers,
            text=True, capture_output=True, timeout=15,
        )

    def commands(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_all_harnesses_and_repeat_run_replace_only_matching_entries(self):
        for name in (".claude", ".codex", ".copilot"):
            (self.home / name).mkdir()
        copied = self.home / ".codex/agents/pdlc-reviewer.toml"
        copied.parent.mkdir()
        outside = self.root / "outside.toml"
        outside.write_text("preserve")
        copied.symlink_to(outside)
        unrelated = copied.parent / "other.toml"
        unrelated.write_text("preserve")
        for _ in range(2):
            result = self.run_setup("-y")
            self.assertEqual(result.returncode, 0, result.stderr)
            for target, source in (
                (".agents/skills/pdlc", "agent/skills/pdlc"),
                (".claude/skills/pdlc", "agent/skills/pdlc"),
                (".claude/agents/pdlc-reviewer.md", "agent/sub-agents/claude/pdlc-reviewer.md"),
                (".copilot/agents/pdlc-reviewer.agent.md", "agent/sub-agents/copilot/pdlc-reviewer.agent.md"),
            ):
                self.assertTrue((self.home / target).is_symlink())
                self.assertEqual((self.home / target).resolve(), self.repo / source)
            self.assertFalse(copied.is_symlink())
            self.assertEqual(copied.read_text(), "fixture\n")
        self.assertEqual(outside.read_text(), "preserve")
        self.assertEqual(unrelated.read_text(), "preserve")
        calls = self.commands()
        self.assertLess(calls.index(["git", "pull", "--ff-only"]),
                        next(i for i, call in enumerate(calls) if call[0] == "uv"))
        self.assertIn(["uv", "tool", "install", "--force", "--reinstall", "--python",
                       "/compatible/python", "--no-python-downloads", str(self.repo)], calls)

    def test_missing_python_and_stack_are_installed_with_yes(self):
        result = self.run_setup("-y", PYTHON_MISSING="1", STACK_MISSING="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(["uv", "python", "install", "3.12"], self.commands())
        self.assertIn(["gh", "extension", "install", "github/gh-stack"], self.commands())

    def test_required_install_declines_cancel_before_home_changes(self):
        for missing in ("PYTHON_MISSING", "STACK_MISSING"):
            with self.subTest(missing=missing):
                result = self.run_setup(answers="n\n", **{missing: "1"})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Setup cancelled", result.stderr)
                self.assertFalse((self.home / ".agents").exists())

    def test_missing_required_tools_link_to_official_installation(self):
        for name, url in (("uv", "https://docs.astral.sh/uv/"), ("gh", "https://cli.github.com/")):
            with self.subTest(name=name):
                path = self.bin / name
                saved = path.read_text()
                path.unlink()
                result = self.run_setup("-y")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(url, result.stderr)
                self.assertFalse((self.home / ".agents").exists())
                path.write_text(saved)
                path.chmod(0o755)

    def test_optional_azure_decline_and_failure_continue(self):
        for env, answers, args in (
            ({"AZ_EXTENSION_MISSING": "1"}, "n\ny\n", ()),
            ({"AZ_EXTENSION_MISSING": "1", "AZ_INSTALL_FAIL": "1"}, "", ("-y",)),
        ):
            with self.subTest(env=env):
                result = self.run_setup(*args, answers=answers, **env)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("PDLC setup complete", result.stdout)

    def test_missing_azure_does_not_create_absent_harness_directories(self):
        (self.bin / "az").unlink()
        result = self.run_setup("-y")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Azure CLI not found", result.stdout)
        for harness in (".claude", ".codex", ".copilot"):
            self.assertFalse((self.home / harness).exists())

    def test_each_copy_and_link_group_requires_approval(self):
        for name in (".claude", ".codex", ".copilot"):
            (self.home / name).mkdir()
        result = self.run_setup(answers="n\nn\nn\nn\nn\nn\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("[y/N]"), 6)
        self.assertFalse((self.home / ".agents").exists())
        self.assertFalse((self.home / ".config").exists())
        for harness in (".claude", ".codex", ".copilot"):
            self.assertEqual(list((self.home / harness).iterdir()), [])

    def test_global_ignore_is_added_once_after_a_newline(self):
        self.ignore_file.parent.mkdir(parents=True)
        self.ignore_file.write_text("existing")
        for _ in range(2):
            result = self.run_setup("-y")
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.ignore_file.read_text(), "existing\n.pdlc/\n")
        self.assertIn(".pdlc/ is already in", result.stdout)

    def test_global_ignore_uses_configured_excludes_file(self):
        configured = self.home / "custom ignore"
        result = self.run_setup("-y", EXCLUDES_FILE=str(configured))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(configured.read_text(), ".pdlc/\n")
        self.assertFalse(self.ignore_file.exists())

    def test_global_ignore_honors_xdg_config_home(self):
        xdg = self.root / "xdg"
        result = self.run_setup("-y", XDG_CONFIG_HOME=str(xdg))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((xdg / "git/ignore").read_text(), ".pdlc/\n")
        self.assertFalse(self.ignore_file.exists())

    def test_real_skill_directory_is_preserved(self):
        skill = self.home / ".agents/skills/pdlc"
        skill.mkdir(parents=True)
        (skill / "mine").write_text("preserve")
        result = self.run_setup("-y")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((skill / "mine").read_text(), "preserve")

    def test_codex_copy_replaces_directory_symlink_without_writing_through_it(self):
        destination = self.home / ".codex/agents/pdlc-reviewer.toml"
        destination.parent.mkdir(parents=True)
        outside = self.root / "outside directory"
        outside.mkdir()
        destination.symlink_to(outside)
        result = self.run_setup("-y")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(destination.is_symlink())
        self.assertEqual(destination.read_text(), "fixture\n")
        self.assertEqual(list(outside.iterdir()), [])

    def test_invalid_root_or_missing_files_exit_before_pull(self):
        result = self.run_setup("-y", cwd=self.root)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.commands(), [])
        for env in ({"GIT_ROOT": str(self.root)},):
            result = self.run_setup("-y", **env)
            self.assertNotEqual(result.returncode, 0)
        for missing in ("src/pdlc/cli.py", "agent/skills/pdlc/SKILL.md",
                        "agent/sub-agents/codex/pdlc-reviewer.toml"):
            path = self.repo / missing
            saved = path.read_text()
            path.unlink()
            result = self.run_setup("-y")
            self.assertNotEqual(result.returncode, 0, missing)
            path.write_text(saved)
        self.assertNotIn(["git", "pull", "--ff-only"], self.commands())

    def test_pull_or_tool_failure_is_retriable(self):
        for env in ({"PULL_FAIL": "1"}, {"TOOL_FAIL": "1"}):
            result = self.run_setup("-y", **env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("rerun ./setup.sh", result.stderr)
        result = self.run_setup("-y")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_help_and_invalid_arguments_do_not_mutate(self):
        self.assertEqual(self.run_setup("--help").returncode, 0)
        self.assertNotEqual(self.run_setup("--unknown").returncode, 0)
        self.assertEqual(self.commands(), [])

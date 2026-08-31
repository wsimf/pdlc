"""Public PDLC command-line dispatcher."""

from __future__ import annotations

import importlib
import os
import sys

from pdlc.config import ConfigurationError, Config, load_config
from pdlc.domain.lifecycle import wants_help


COMMANDS = {
    ("setup",): "pdlc.commands.setup",
    ("inspect",): "pdlc.commands.inspect",
    ("inspect", "task"): "pdlc.commands.inspect_task",
    ("inspect", "timeline"): "pdlc.commands.inspect_timeline",
    ("inspect", "verify"): "pdlc.commands.inspect_verify",
    ("inspect", "complete"): "pdlc.commands.inspect_complete",
    ("inspect", "test"): "pdlc.commands.inspect_test",
    ("inspect", "implement"): "pdlc.commands.inspect_implement",
    ("inspect", "capability"): "pdlc.commands.inspect_capability",
    ("inspect", "review"): "pdlc.commands.inspect_review",
    ("next",): "pdlc.commands.next",
    ("post", "approve"): "pdlc.commands.post_approve",
    ("post", "attach-pr"): "pdlc.commands.post_attach_pr",
    ("post", "ci"): "pdlc.commands.post_ci",
    ("post", "complete"): "pdlc.commands.post_complete",
    ("post", "decision"): "pdlc.commands.post_decision",
    ("post", "implement-task"): "pdlc.commands.post_implement_task",
    ("post", "implement"): "pdlc.commands.post_implement",
    ("post", "invalidate"): "pdlc.commands.post_invalidate",
    ("post", "plan"): "pdlc.commands.post_plan",
    ("post", "review"): "pdlc.commands.post_review",
    ("post", "skip"): "pdlc.commands.post_skip",
    ("post", "tasks"): "pdlc.commands.post_tasks",
    ("post", "test"): "pdlc.commands.post_test",
    ("post", "verify"): "pdlc.commands.post_verify",
    ("post", "write"): "pdlc.commands.post_write",
}


def _usage() -> str:
    return (
        "usage: pdlc [--repo OWNER/REPO] [--project-number N] [--project-owner OWNER] "
        "[--backend NAME] [--home PATH] [exec] COMMAND ...\n"
        "\nCommands: inspect, next, post\n"
        "\nExamples:\n"
        "  pdlc inspect 236\n"
        "  pdlc post complete 236 completion.md\n"
        "  pdlc exec post complete 236 completion.md"
    )


def _options(argv: list[str]) -> tuple[list[str], list[str]]:
    remaining: list[str] = []
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument in {"--repo", "--project-number", "--project-owner", "--backend", "--home"}:
            if index + 1 >= len(argv):
                raise ValueError(f"{argument} requires a value")
            value = argv[index + 1]
            environment_name = {
                "--repo": "PDLC_REPOSITORY",
                "--project-number": "PDLC_PROJECT_NUMBER",
                "--project-owner": "PDLC_PROJECT_OWNER",
                "--backend": "PDLC_BACKEND",
                "--home": "PDLC_HOME",
            }[argument]
            os.environ[environment_name] = value
            index += 2
            continue
        remaining.append(argument)
        index += 1
    return remaining, []


def _resolve(arguments: list[str]) -> tuple[str, list[str]]:
    if arguments and arguments[0] == "exec":
        arguments = arguments[1:]
    for length in (2, 1):
        key = tuple(arguments[:length])
        module_name = COMMANDS.get(key)
        if module_name:
            return module_name, arguments[length:]
    raise ValueError("unknown command\n\n" + _usage())


def main() -> int:
    raw_arguments = sys.argv[1:]
    if not raw_arguments or raw_arguments in (["--help"], ["-h"]):
        print(_usage())
        return 0
    try:
        load_config()
        arguments, _ = _options(raw_arguments)
        module_name, command_arguments = _resolve(arguments)
        # setup runs the wizard; capability routing is local and needs no backend.
        local_only = {"pdlc.commands.setup", "pdlc.commands.inspect_capability"}
        if module_name not in local_only and not wants_help(command_arguments):
            Config.from_environment().validate_for_backend()
    except ConfigurationError as error:
        print(f"pdlc: {error}")
        return 1
    except ValueError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    module = importlib.import_module(module_name)
    original_argv = sys.argv
    try:
        sys.argv = [f"pdlc {module_name.rsplit('.', 1)[-1]}", *command_arguments]
        return int(module.main())
    finally:
        sys.argv = original_argv

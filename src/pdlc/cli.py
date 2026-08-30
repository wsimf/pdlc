"""Public PDLC command-line dispatcher.

The legacy command modules retain the established validation and transition
behavior while the public command names migrate from script filenames to a
stable CLI surface.
"""

from __future__ import annotations

import importlib
import os
import sys


COMMANDS = {
    ("inspect",): "pdlc.legacy.pdlc_inspect",
    ("inspect", "task"): "pdlc.legacy.pdlc_inspect_task",
    ("inspect", "timeline"): "pdlc.legacy.pdlc_inspect_timeline",
    ("inspect", "verify"): "pdlc.legacy.pdlc_inspect_verify",
    ("inspect", "complete"): "pdlc.legacy.pdlc_inspect_complete",
    ("inspect", "test"): "pdlc.legacy.pdlc_inspect_test",
    ("inspect", "review"): "pdlc.legacy.pdlc_inspect_review",
    ("next",): "pdlc.legacy.pdlc_next_task",
    ("post", "approve"): "pdlc.legacy.pdlc_post_approve",
    ("post", "ci"): "pdlc.legacy.pdlc_post_ci",
    ("post", "complete"): "pdlc.legacy.pdlc_post_complete",
    ("post", "decision"): "pdlc.legacy.pdlc_post_decision",
    ("post", "implement-task"): "pdlc.legacy.pdlc_post_implement_task",
    ("post", "implement"): "pdlc.legacy.pdlc_post_implement",
    ("post", "invalidate"): "pdlc.legacy.pdlc_post_invalidate",
    ("post", "plan"): "pdlc.legacy.pdlc_post_plan",
    ("post", "review"): "pdlc.legacy.pdlc_post_review",
    ("post", "skip"): "pdlc.legacy.pdlc_post_skip",
    ("post", "tasks"): "pdlc.legacy.pdlc_post_tasks",
    ("post", "test"): "pdlc.legacy.pdlc_post_test",
    ("post", "verify"): "pdlc.legacy.pdlc_post_verify",
    ("post", "write"): "pdlc.legacy.pdlc_post_write",
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
    if not sys.argv[1:] or sys.argv[1:] in (["--help"], ["-h"]):
        print(_usage())
        return 0
    try:
        arguments, _ = _options(sys.argv[1:])
        module_name, command_arguments = _resolve(arguments)
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

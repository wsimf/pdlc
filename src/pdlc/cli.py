"""Public PDLC command-line dispatcher."""

from __future__ import annotations

import importlib
import os
import sys

from pdlc.config import ConfigurationError, Config, load_config
from pdlc.internal.inputs import wants_help


COMMANDS = {
    ("setup",): "pdlc.commands.setup",
    # Human-only worktree scaffolding / teardown; deliberately omitted from
    # `_usage()` and the agent workflow. `prepare` is local Git only; `cleanup`
    # additionally resolves the work item to confirm it is Complete.
    ("prepare",): "pdlc.commands.prepare",
    ("cleanup",): "pdlc.commands.cleanup",
    ("inspect",): "pdlc.commands.inspect",
    ("inspect", "task"): "pdlc.commands.inspect_task",
    ("inspect", "comments"): "pdlc.commands.inspect_comments",
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
        "\nGlobal options set PDLC_* environment variables; `exec` is an accepted no-op prefix.\n"
        "\nsetup\n"
        "  setup                       interactive config wizard; writes .pdlc/config.toml\n"
        "\ninspect (read-only)\n"
        "  inspect ISSUE               work-item overview: metadata, task tree, PRs, routing decision\n"
        "  inspect task WI [TASK...]   full text and flags for specific delivery tasks\n"
        "  inspect comments WI --page N  read one page of comments (100 per page)\n"
        "  inspect timeline WI         all evidence comments as a stage-by-stage timeline\n"
        "  inspect implement WI        whether Implementation is due and the next task to implement\n"
        "  inspect review WI           whether review is due; which artifact and reviewer agent\n"
        "  inspect test WI             whether testing is due; testable scope and files the PRs touched\n"
        "  inspect verify WI           verification readiness and what is stale/fixed/deferred\n"
        "  inspect complete WI         completion readiness: open tasks, unmerged/red PRs, open questions\n"
        "  inspect capability [SLOT]  resolve the project's agent/skill routing for a seam\n"
        "\nnext (routing)\n"
        "  next [--work-item N]        route one item (or scan the queue) to the next pdlc-* skill\n"
        "  next loop [--work-item N]   same, retrying with backoff until something is actionable\n"
        "\npost (mutating - only when the transition is authorized)\n"
        "  post write                             publish the Product artifact\n"
        "  post tasks                             land a UI or Tasks stage\n"
        "  post plan                              land the Technical Plan\n"
        "  post implement WI EVIDENCE             register the branch's PR and complete Implementation\n"
        "  post implement-task TASK FILE [--close]  record one task's implementation\n"
        "  post test WI EVIDENCE --traceability FILE  record PR + traceability, set Review Required\n"
        "  post verify WI                         post verification results and move the gate\n"
        "  post review WI VERDICT EVIDENCE        reviewer verdict (changes/approval/decision-required)\n"
        "  post ci WI                             resolve CI Pending against live check state\n"
        "  post decision WI --manifest FILE       close a Decision Required gate\n"
        "  post approve WI EVIDENCE               human approval, advance to next stage (driver-only)\n"
        "  post complete WI EVIDENCE              final lock to Complete (driver-only)\n"
        "  post skip WI STAGE                     mark stages skipped ahead of time (driver-only)\n"
        "  post invalidate WI STAGE EVIDENCE      return a stage to Stale after upstream change\n"
        "  post attach-pr TASK PR#                manually link a PR to a task\n"
        "\nMost post stage/gate commands also take --attachment PATH [--attachment-description TEXT].\n"
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


def _dispatch(raw_arguments: list[str]) -> int:
    if not raw_arguments or raw_arguments in (["--help"], ["-h"]):
        print(_usage())
        return 0
    try:
        load_config()
        arguments, _ = _options(raw_arguments)
        module_name, command_arguments = _resolve(arguments)
        # setup runs the wizard; capability routing is local and needs no backend.
        local_only = {
            "pdlc.commands.setup",
            "pdlc.commands.inspect_capability",
            "pdlc.commands.prepare",
        }
        if module_name not in local_only and not wants_help(command_arguments):
            Config.from_environment().validate_for_backend()
    except ConfigurationError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        print(
            "pdlc: configuration must be fixed before any pdlc command can run. "
            "Stop here, tell the user exactly which values are missing, and ask "
            "them to set the configuration first. Do not continue the task.",
            file=sys.stderr,
        )
        return 1
    except ValueError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    module = importlib.import_module(module_name)
    return int(module.main(argv=command_arguments))


def _reset_runtime() -> None:
    from pdlc.config import reset_config
    from pdlc.hosts.workitem_host import reset_backend
    from pdlc.hosts.code_host import reset_code_host
    from pdlc.hosts.attachment_host import reset_host

    reset_config()
    reset_backend()
    reset_code_host()
    reset_host()
    project = sys.modules.get("pdlc.hosts.lib.github.project")
    if project is not None:
        project.project_fields.cache_clear()
        project._project_id.cache_clear()


def main(argv: list[str] | None = None) -> int:
    """Run one CLI invocation without leaking options or cached hosts to the next."""
    original = {key: value for key, value in os.environ.items() if key.startswith("PDLC_")}
    _reset_runtime()
    try:
        return _dispatch(list(sys.argv[1:] if argv is None else argv))
    finally:
        for key in list(os.environ):
            if key.startswith("PDLC_") and key not in original:
                del os.environ[key]
        os.environ.update(original)
        _reset_runtime()

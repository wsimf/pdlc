"""Public PDLC command-line dispatcher."""

from __future__ import annotations

import importlib
import os
import sys

from pdlc.config import ConfigurationError, load_config
from pdlc.internal.inputs import wants_help


COMMANDS = {
    ("doctor",): "pdlc.commands.doctor",
    ("guide",): "pdlc.commands.guide",
    ("setup",): "pdlc.commands.setup",
    # Human-only worktree scaffolding / teardown; deliberately omitted from
    # `_usage()` and the agent workflow. `prepare` is local Git only; `cleanup`
    # additionally resolves the work item to confirm it is Complete.
    ("prepare",): "pdlc.commands.prepare",
    ("cleanup",): "pdlc.commands.cleanup",
    ("checkout",): "pdlc.commands.checkout",
    ("inspect",): "pdlc.commands.inspect",
    ("inspect", "task"): "pdlc.commands.inspect_task",
    ("inspect", "task", "timeline"): "pdlc.commands.inspect_task_timeline",
    ("inspect", "comments"): "pdlc.commands.inspect_comments",
    ("inspect", "changes"): "pdlc.commands.inspect_changes",
    ("inspect", "timeline"): "pdlc.commands.inspect_timeline",
    ("inspect", "verify"): "pdlc.commands.inspect_verify",
    ("inspect", "complete"): "pdlc.commands.inspect_complete",
    ("inspect", "test"): "pdlc.commands.inspect_test",
    ("inspect", "implement"): "pdlc.commands.inspect_implement",
    ("inspect", "capability"): "pdlc.commands.inspect_capability",
    ("inspect", "review"): "pdlc.commands.inspect_review",
    ("prompt",): "pdlc.commands.prompt",
    ("prompt", "task-implementer"): "pdlc.commands.prompt_task_implementer",
    ("prompt", "task-reviewer"): "pdlc.commands.prompt_task_reviewer",
    ("prompt", "task-test-writer"): "pdlc.commands.prompt_task_test_writer",
    ("prompt", "acceptance-test-writer"): "pdlc.commands.prompt_acceptance_test_writer",
    ("prompt", "task-planner"): "pdlc.commands.prompt_task_planner",
    ("prompt", "tech-planner"): "pdlc.commands.prompt_tech_planner",
    ("next",): "pdlc.commands.next",
    ("continue",): "pdlc.commands.continue_",
    ("post", "approve"): "pdlc.commands.post_approve",
    ("post", "attach-pr"): "pdlc.commands.post_attach_pr",
    ("post", "ci"): "pdlc.commands.post_ci",
    ("post", "complete"): "pdlc.commands.post_complete",
    ("post", "decision"): "pdlc.commands.post_decision",
    ("post", "escalate"): "pdlc.commands.post_escalate",
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
        "USAGE\n"
        "  pdlc [--repo OWNER/REPO] [--project-number N] [--project-owner OWNER] "
        "[--backend NAME] [--home PATH] [exec] COMMAND ...\n"
        "\n"
        "  Global options override .pdlc/config.toml for this run; `exec` is an accepted no-op prefix.\n"
        "  Run `pdlc COMMAND --help` for a command's own usage, flags, and behavioral contract.\n"
        "\nREAD-ONLY COMMANDS\n"
        "  setup                       interactive config wizard; writes .pdlc/config.toml\n"
        "  doctor                      inspect config, derived values, backend CLI access, and all validation results\n"
        "  guide                       print a bundled Markdown guide for PDLC agents\n"
        "  inspect ISSUE               work-item overview: metadata, task tree, PRs, routing decision\n"
        "  inspect task WI [TASK...]   full text and flags for specific delivery tasks\n"
        "  inspect task timeline TASK  one delivery task's plan/implementation/invalidation history\n"
        "  inspect comments WI --page N  read one page of comments (100 per page)\n"
        "  inspect timeline WI         all evidence comments as a stage-by-stage timeline\n"
        "  inspect changes WI [--stage STAGE]  change requests the stage has not addressed since it last published\n"
        "  inspect implement WI        whether Implementation is due, its mode, and the one unit to work next\n"
        "  inspect review WI           whether review is due; which artifact and reviewer agent\n"
        "  inspect test WI             whether testing is due; testable scope and files the PRs touched\n"
        "  inspect verify WI           verification readiness, open findings, and a pre-filled report\n"
        "  inspect complete WI         completion readiness: open tasks, unmerged/red PRs, open questions\n"
        "  inspect capability [SLOT] [--name]  resolve the project's agent/skill routing for a seam\n"
        "  prompt                      index of the sub-agent briefs for the record's next unit\n"
        "  prompt task-implementer WI  the brief for the sub-agent that writes that unit's code\n"
        "  prompt task-reviewer WI --commits REVISIONS  the brief for the reviewer of one dispatch's commits\n"
        "  prompt task-test-writer WI --commits REVISIONS --report FILE --traceability FILE  the test writer's brief\n"
        "  prompt acceptance-test-writer WI --traceability FILE  the brief for the test writer covering the whole implemented scope\n"
        "  prompt task-planner WI      the brief for the sub-agent that decomposes the record into delivery tasks\n"
        "  prompt tech-planner WI      the brief for the sub-agent that spikes the open delivery tasks into plans\n"
        "  next [--work-item N]        route one item (or scan the queue); prints its action and # Due Next\n"
        "  next loop [--work-item N]   same, retrying with backoff until something is actionable\n"
        "\nMUTATING COMMANDS (only when the transition is authorized)\n"
        "  checkout TASK                          put the working tree on one delivery task's branch (local only)\n"
        "  continue WI                            self-heal a stray Approved/CI Pending gate; errors otherwise\n"
        "  post write                             publish the Product artifact\n"
        "  post tasks                             land a UI or Tasks stage\n"
        "  post plan                              land the Technical Plan\n"
        "  post implement WI EVIDENCE             push the task PR stack, ready it for review, complete Implementation\n"
        "  post implement-task TASK FILE          land one task's implementation; closes it when open, re-lands when closed\n"
        "  post test WI EVIDENCE --traceability FILE  push the stack, record PR + traceability, set Review Required\n"
        "  post verify WI REPORT                  post a verification report and move the gate\n"
        "  post review WI VERDICT EVIDENCE        reviewer verdict (changes/approval/decision-required)\n"
        "  post ci WI                             resolve CI Pending against live check state\n"
        "  post escalate WI EVIDENCE              park the current stage on a driver decision (stage owner)\n"
        "  post decision WI --manifest FILE       close a Decision Required gate\n"
        "  post approve WI EVIDENCE [--force]     human approval, advance to next stage (driver-only)\n"
        "  post complete WI EVIDENCE              final lock to Complete (driver-only)\n"
        "  post skip WI STAGE                     mark stages skipped ahead of time (driver-only)\n"
        "  post invalidate WI STAGE EVIDENCE [--task N ...]  return a stage to Stale after upstream change\n"
        "  post attach-pr TASK PR#                manually link a PR to a task\n"
        "\nFLAGS\n"
        "  --repo OWNER/REPO           override [repo] name for this run\n"
        "  --project-number N          override the configured project number\n"
        "  --project-owner OWNER       override the configured project owner\n"
        "  --backend NAME              override [backend] name (github, azure, file)\n"
        "  --home PATH                 override PDLC_HOME for this run\n"
        "\nARGUMENTS\n"
        "  WI, ISSUE, WORK_ITEM        the parent work item number\n"
        "  TASK, DELIVERY_TASK         a delivery task's WORK-N-TASK-NNN name or its own issue number\n"
        "  Most post stage/gate commands also take --attachment PATH [--attachment-description TEXT].\n"
        "\nEXAMPLES\n"
        "  pdlc inspect 236\n"
        "  pdlc post complete 236 completion.md\n"
        "  pdlc exec post complete 236 completion.md\n"
        "\nLEARN MORE\n"
        "  Use `pdlc COMMAND --help` for details about a command."
    )


_FLAG_FIELDS = {
    "--repo": "repository",
    "--project-number": "project_number",
    "--project-owner": "project_owner",
    "--backend": "backend",
    "--home": "home",
}


def _options(argv: list[str]) -> tuple[list[str], dict[str, str]]:
    """Split global config flags off the front-matter and return them as
    ``load_config`` overrides keyed by Config field name."""
    remaining: list[str] = []
    overrides: dict[str, str] = {}
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument in _FLAG_FIELDS:
            if index + 1 >= len(argv):
                raise ValueError(f"{argument} requires a value")
            overrides[_FLAG_FIELDS[argument]] = argv[index + 1]
            index += 2
            continue
        remaining.append(argument)
        index += 1
    return remaining, overrides


def _resolve(arguments: list[str]) -> tuple[str, list[str]]:
    if arguments and arguments[0] == "exec":
        arguments = arguments[1:]
    for length in (3, 2, 1):
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
        arguments, overrides = _options(raw_arguments)
        module_name, command_arguments = _resolve(arguments)
        if module_name == "pdlc.commands.doctor":
            module = importlib.import_module(module_name)
            return int(module.main(argv=command_arguments, overrides=overrides))
        if module_name == "pdlc.commands.guide":
            module = importlib.import_module(module_name)
            return int(module.main(argv=command_arguments))
        config = load_config(overrides=overrides)
        # setup runs the wizard; capability routing is local and needs no backend.
        local_only = {
            "pdlc.commands.setup",
            "pdlc.commands.doctor",
            "pdlc.commands.guide",
            "pdlc.commands.inspect_capability",
            "pdlc.commands.prepare",
        }
        if module_name not in local_only and not wants_help(command_arguments):
            config.validate_for_backend()
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

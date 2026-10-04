"""NAME
    pdlc setup - interactive config wizard; writes .pdlc/config.toml

USAGE
    pdlc setup
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from pdlc.config import config_path, git_remote_repository, load_config
from pdlc.domain.lifecycle import PdlcError
from pdlc.hosts.lib.github.transport import run_gh_json


Input = Callable[[str], str]


def _origin() -> tuple[str | None, str | None]:
    repository = git_remote_repository(Path.cwd())
    if not repository:
        return None, None
    owner, _, name = repository.partition("/")
    return owner, name


def _choose(prompt: str, options: list[str], input_fn: Input) -> int:
    for index, option in enumerate(options, 1):
        print(f"  {index}. {option}")
    while True:
        answer = input_fn(f"{prompt} [1]: ").strip() or "1"
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return int(answer) - 1
        print("Choose one of the listed options.")


def _ask(prompt: str, default: str | None, input_fn: Input) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        answer = input_fn(f"{prompt}{suffix}: ").strip() or (default or "")
        if answer:
            return answer
        print("A value is required.")


def _ask_number(prompt: str, default: str | None, input_fn: Input) -> str:
    while True:
        answer = _ask(prompt, default, input_fn)
        if answer.isdigit():
            return answer
        print("Enter a numeric project number.")


def _projects(owner: str) -> list[dict]:
    result = run_gh_json([
        "project", "list", "--owner", owner, "--format", "json", "--limit", "100"
    ])
    return [project for project in result.get("projects", []) if not project.get("closed")]


def _write_config(
    path: Path,
    *,
    tracker: str,
    code: str,
    tracker_repository: str | None,
    code_repository: str | None,
    project_number: str | None,
    project_owner: str | None,
    azure: dict[str, str] | None = None,
) -> None:
    lines = ["[tracker]", f'provider = "{tracker}"']
    if tracker == "github":
        lines += [
            "",
            "[tracker.github]",
            f'repository = "{tracker_repository}"',
            f"project_number = {project_number}",
            f'project_owner = "{project_owner}"',
        ]
    elif tracker == "azure" and azure:
        lines += [
            "",
            "[tracker.azure]",
            f'organization = "{azure["organization"]}"',
            f'project = "{azure["project"]}"',
        ]
    lines += ["", "[code]", f'provider = "{code}"']
    # The code repository defaults to the checkout's origin, so it is written
    # only when that cannot be detected.
    if code == "github" and code_repository:
        lines += ["", "[code.github]", f'repository = "{code_repository}"']
    lines += ["", "[attachments]", 'provider = "file"']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _code_provider(detected: bool, input_fn: Input) -> str:
    """Ask which provider owns code and pull requests. Independent of the
    tracker: Azure Boards is expected to pair with GitHub repos."""
    options = ["github (detected from remote.origin.url)", "file", "none"] if detected else ["github", "file", "none"]
    return ["github", "file", "none"][_choose("Code provider", options, input_fn)]


def main(input_fn: Input = input, *, argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    # `setup` takes no positional arguments, so only an explicit flag is help;
    # an empty argv means "run the wizard".
    if any(argument in ("-h", "--help") for argument in command_args):
        print(__doc__.strip())
        return 0
    config = load_config()
    current_owner, current_repository = _origin()
    origin = f"{current_owner}/{current_repository}" if current_owner and current_repository else None
    print("pdlc setup")
    print("Configure this repository for the PDLC workflow.\n")

    tracker_options = ["github", "azure", "file"]
    tracker = tracker_options[_choose("Tracker", tracker_options, input_fn)]
    tracker_repository = code_repository = None
    azure: dict[str, str] | None = None
    project_owner = project_number = None

    if tracker == "github":
        if origin:
            print(f"Detected repository: {origin}")
        # Several code repositories may share one tracker, so the tracker can
        # differ from this checkout.
        tracker_repository = _ask(
            "Tracker repository, where work items live (OWNER/REPOSITORY)",
            config.tracker_repository or origin, input_fn,
        )
        code = _code_provider(bool(origin), input_fn)
        tracker_owner = tracker_repository.partition("/")[0]
        owner_options = [tracker_owner] if tracker_owner else []
        owner_options.append("other")
        owner_choice = _choose("Project owner", owner_options, input_fn)
        project_owner = (
            owner_options[owner_choice]
            if owner_options[owner_choice] != "other"
            else _ask("GitHub project owner", config.project_owner, input_fn)
        )
        try:
            projects = _projects(project_owner)
        except PdlcError as error:
            print(f"Could not query GitHub projects: {error}")
            projects = []
        project_options = [
            f"{project.get('number')}: {project.get('title', 'Untitled')}"
            for project in projects
        ] + ["other project number"]
        project_choice = _choose("Project number", project_options, input_fn)
        if project_choice < len(projects):
            project_number = str(projects[project_choice]["number"])
        else:
            project_number = _ask_number("GitHub project number", config.project_number, input_fn)
    elif tracker == "azure":
        azure = {
            # No placeholder default: pressing enter must not write a
            # syntactically valid but nonexistent organization.
            "organization": _ask(
                "Azure DevOps organization URL (https://dev.azure.com/<org>)",
                config.azure_org, input_fn,
            ),
            "project": _ask("Azure DevOps project", config.azure_project, input_fn),
        }
        print(
            "\nThe PDLC custom fields are an organization-admin prerequisite; "
            "see \"Azure Boards fields\" in README.md."
        )
        code = _code_provider(bool(origin), input_fn)
    else:
        code = "file"
        print("Code provider: file")
        print("Attachments provider: file")

    if code == "github" and not origin:
        print("No GitHub repository was detected from remote.origin.url.")
        code_repository = _ask(
            "Code repository, where pull requests live (OWNER/REPOSITORY)",
            config.code_repository or tracker_repository, input_fn,
        )

    path = config_path()
    _write_config(
        path,
        tracker=tracker,
        code=code,
        tracker_repository=tracker_repository,
        code_repository=code_repository,
        project_number=project_number,
        project_owner=project_owner,
        azure=azure,
    )
    print(f"\nWrote {path}")
    return 0

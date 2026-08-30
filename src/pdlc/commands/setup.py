"""Interactive configuration wizard for ``pdlc``."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

from pdlc.config import Config, config_path, load_config
from pdlc.domain.lifecycle import PdlcError
from pdlc.hosts.github_common import run_gh_json


Input = Callable[[str], str]


def _origin() -> tuple[str | None, str | None]:
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None, None
    match = re.search(r"(?:github\.com[:/])([^/ :]+)/([^/]+?)(?:\.git)?$", result.stdout.strip())
    return (match.group(1), match.group(2)) if match else (None, None)


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
    backend: str,
    code_host: str,
    repository: str | None,
    project_number: str | None,
    project_owner: str | None,
) -> None:
    lines = ["[backend]", f'name = "{backend}"', "", "[code_host]", f'name = "{code_host}"', "", "[attachment_host]", 'name = "file"']
    if backend == "github":
        lines += [
            "",
            "[backend.github]",
            f'repository = "{repository}"',
            f"project_number = {project_number}",
            f'project_owner = "{project_owner}"',
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def main(input_fn: Input = input) -> int:
    # `setup` takes no positional arguments, so only an explicit flag is help;
    # an empty argv means "run the wizard".
    if any(argument in ("-h", "--help") for argument in sys.argv[1:]):
        print(__doc__.strip())
        return 0
    config = load_config()
    current_owner, current_repository = _origin()
    print("pdlc setup")
    print("Configure this repository for the PDLC workflow.\n")

    backend_options = ["github", "file"]
    backend = backend_options[_choose("Backend", backend_options, input_fn)]
    if backend == "github" and not current_repository:
        print("No GitHub repository was detected from remote.origin.url.")
        current_repository = _ask("Repository (OWNER/REPOSITORY)", config.repository, input_fn)
    elif backend == "github":
        print(f"Detected repository: {current_owner}/{current_repository}")

    if backend == "github":
        code_options = (
            ["github (detected from remote.origin.url)", "file", "none"]
            if current_repository
            else ["github", "file", "none"]
        )
        code_choice = _choose("Code host", code_options, input_fn)
        code_host = ["github", "file", "none"][code_choice]
        owner_options = [current_owner] if current_owner else []
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
    else:
        code_host = "file"
        project_owner = project_number = None
        print("Code host: file")
        print("Attachment host: file")

    path = config_path()
    _write_config(
        path,
        backend=backend,
        code_host=code_host,
        repository=(
            f"{current_owner}/{current_repository}"
            if backend == "github" and current_owner and current_repository
            else current_repository
        ),
        project_number=project_number,
        project_owner=project_owner,
    )
    print(f"\nWrote {path}")
    return 0

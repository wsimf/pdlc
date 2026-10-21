"""NAME
    pdlc doctor - inspect configuration and report every problem

USAGE
    pdlc doctor

DESCRIPTION
    Print the effective PDLC configuration, its source, derived values, and
    every validation result. Exit 1 when any validation fails; warnings do not
    fail the command.

    A config file that is not valid TOML fails the command and is reported as a
    warning naming the file; its values are ignored, so the remaining
    validations and the tracker access probes are skipped rather than run
    against defaults.

    Home defaults, the matching home repository section, repository settings,
    and CLI overrides merge in ascending priority, above environment values.
    Sources identify the repository section that supplies each effective value.

    In a Git repository, warn when Git does not ignore the .pdlc/ directory
    through the repository's .gitignore, .git/info/exclude, or the global
    ignore file. The command never edits any ignore file.

    When the tracker is github or azure, a "Tracker access" section also shows
    what its CLI reports, using read-only calls only:

    - github: the `gh` version, the active github.com login, its token scopes
      (`project` is required), the repository permission, and whether the
      configured Project can be read.
    - azure: the `az` version, whether the `azure-devops` extension is installed
      and its version, whether AZURE_DEVOPS_EXT_PAT is set, the `az login` user,
      and whether the configured project can be read and its Boards queried.
      Either an `az login` session or a PAT (AZURE_DEVOPS_EXT_PAT or
      `az devops login`) is enough; the project read settles which one works.

    A missing CLI, extension, login, scope, or access fails the command. A CLI
    or extension older than the minimum version pdlc is tested with only warns.
"""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import fields
from pathlib import Path

from pdlc.config import (
    Config,
    ConfigurationError,
    ENVIRONMENT_FIELDS,
    FIELD_LOCATIONS,
    REPOSITORY_FIELDS,
    _BOOL_FIELDS,
    _INT_FIELDS,
    _read_file,
    checkout_identity,
    default_code_provider,
    git_remote_repository,
    home_config_path,
    repository_root,
)
from pdlc.hosts.lib.access import AccessReport
from pdlc.hosts.lib.azure import access as azure_access
from pdlc.hosts.lib.github import access as github_access
from pdlc.hosts.lib.gitignore import pdlc_unignored
from pdlc.internal.inputs import print_help


def _read(
    path: Path, values: dict[str, object], sources: dict[str, str], errors: list[str],
    *, repository: str | None = None, allow_repositories: bool = False,
) -> str:
    """Merges one config layer; returns its status: missing, present, or unparsable."""
    if not path.exists():
        return "missing"
    try:
        tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        errors.append(f"Could not read {path}: {error}")
        return "unparsable"
    parsed, _ = _read_file(
        path, repository=repository, allow_repositories=allow_repositories,
        errors=errors, sources=sources,
    )
    values.update(parsed)
    return "present"


def _typed_values(values: dict[str, object], errors: list[str]) -> dict[str, object]:
    valid = dict(values)
    for name, minimum in _INT_FIELDS.items():
        if name not in valid:
            continue
        raw = valid[name]
        try:
            number = int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            errors.append(f"{FIELD_LOCATIONS[name]} must be an integer >= {minimum}")
            valid.pop(name)
            continue
        if (isinstance(raw, float) and number != raw) or number < minimum:
            errors.append(f"{FIELD_LOCATIONS[name]} must be an integer >= {minimum}")
            valid.pop(name)
            continue
        valid[name] = number
    for name in _BOOL_FIELDS:
        if name not in valid:
            continue
        raw = valid[name]
        if isinstance(raw, bool):
            continue
        text = str(raw).lower()
        if text not in {"true", "false", "1", "0"}:
            errors.append(f"{FIELD_LOCATIONS[name]} must be a boolean")
            valid.pop(name)
        else:
            valid[name] = text in {"true", "1"}
    return valid


def _validate(config: Config, errors: list[str], derived: str | None) -> list[str]:
    warnings: list[str] = []
    tracker = config.tracker_provider or "github"
    if not config.tracker_provider:
        warnings.append("tracker is defaulted to 'github'; set [tracker] provider explicitly")
    if not config.code_provider:
        code = default_code_provider(tracker) if tracker in {"github", "azure", "file"} else "none"
        warnings.append(f"code provider is derived as '{code}' from the tracker; set [code] provider explicitly")
    if derived and config.code_repository and config.code_repository.casefold() != derived.casefold():
        warnings.append(
            f"[code.github] repository is {config.code_repository} but this checkout's origin is {derived}; "
            "branch pushes and stacks follow origin"
        )
    try:
        missing = config.missing_settings()
    except ConfigurationError as error:
        errors.append(str(error))
        return warnings
    errors.extend(f"missing required setting: {name}" for name in missing)
    return warnings


def _tracker_access(config: Config) -> AccessReport | None:
    """Probes the tracker's host CLI; None for trackers that need no CLI."""
    tracker = config.tracker_provider or "github"
    if tracker == "github":
        return github_access.check_access(
            repository=config.tracker_repository,
            project_owner=config.project_owner,
            project_number=config.project_number,
        )
    if tracker == "azure":
        return azure_access.check_access(organization=config.azure_org, project=config.azure_project)
    return None


def _source(field: str, sources: dict[str, str]) -> str:
    return sources.get(field, "default")


def run(*, overrides: dict[str, object] | None = None) -> tuple[str, int]:
    values: dict[str, object] = {}
    home_values: dict[str, object] = {}
    sources: dict[str, str] = {}
    errors: list[str] = []
    warnings: list[str] = []
    home_path = home_config_path()
    home_sources: dict[str, str] = {}
    try:
        root = repository_root()
        repo_path = root / ".pdlc" / "config.toml"
    except ConfigurationError:
        root = None
        repo_path = None
    if root is not None and pdlc_unignored(root):
        warnings.append(
            ".pdlc/ is not ignored by Git; add .pdlc/ to your global Git ignore file (rerun setup) "
            "or to this repository's .gitignore"
        )
    repo_values: dict[str, object] = {}
    repo_sources: dict[str, str] = {}
    repo_status = _read(repo_path, repo_values, repo_sources, errors) if repo_path else "missing"
    derived = git_remote_repository(root) if root is not None else None
    home_status = _read(
        home_path, home_values, home_sources, errors,
        repository=checkout_identity(derived, repo_values), allow_repositories=True,
    )
    for environment_name, field in ENVIRONMENT_FIELDS:
        if os.environ.get(environment_name):
            values[field] = os.environ[environment_name]
            sources[field] = environment_name
    values.update(home_values)
    sources.update(home_sources)
    values.update(repo_values)
    sources.update(repo_sources)
    if overrides:
        for field, value in overrides.items():
            if value is not None:
                values[field] = value
                sources[field] = "CLI override"

    if derived:
        for field in REPOSITORY_FIELDS:
            if not values.get(field):
                values[field] = derived
                sources[field] = "derived from git origin"
    if not values.get("code_repository") and values.get("tracker_repository"):
        values["code_repository"] = values["tracker_repository"]
        sources["code_repository"] = "same as tracker_repository"

    typed = _typed_values(values, errors)
    config = Config.from_values(typed)
    unparsable = [str(path) for path, status in ((home_path, home_status), (repo_path, repo_status)) if status == "unparsable"]
    access = None
    if unparsable:
        # Validating against defaults would report misleading failures for settings the file may hold.
        warnings.extend(
            f"{path} is not valid TOML; its values are ignored and remaining validations are skipped"
            for path in unparsable
        )
    else:
        warnings.extend(_validate(config, errors, derived))
        access = _tracker_access(config)
    if access is not None:
        warnings.extend(access.warnings)
        errors.extend(access.errors)
    lines = ["# PDLC doctor", "", f"Working directory: {Path.cwd()}", f"Repository root: {root or '(not found)' }", "", "## Config files", "", f"- ~/.pdlc/config.toml: {home_status} ({home_path})", f"- repo .pdlc/config.toml: {repo_status} ({repo_path or 'not found'})", "", "## Effective values", ""]
    for field in fields(Config):
        value = getattr(config, field.name)
        shown = "(unset)" if value is None else repr(value)
        lines.append(f"- {field.name} = {shown} [{_source(field.name, sources)}]")
    if access is not None:
        lines += ["", "## Tracker access", ""]
        lines.extend(f"- {fact}" for fact in access.facts)
    lines += ["", "## Warnings", ""]
    lines.extend(f"- WARNING: {warning}" for warning in warnings)
    if not warnings:
        lines.append("- None")
    lines += ["", "## Validations", ""]
    lines.extend(f"- FAIL: {error}" for error in errors)
    if not errors:
        lines.append("- PASS: all validations")
    lines += ["", "Result: " + ("FAIL" if errors else "PASS"), ""]
    return "\n".join(lines), int(bool(errors))


def main(argv: list[str] | None = None, *, overrides: dict[str, object] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if any(argument in ("-h", "--help") for argument in args):
        print_help(__doc__)
        return 0
    if args:
        print("usage: pdlc doctor", file=sys.stderr)
        return 1
    output, code = run(overrides=overrides)
    print(output, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

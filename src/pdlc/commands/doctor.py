"""NAME
    pdlc doctor - inspect configuration and report every problem

USAGE
    pdlc doctor

DESCRIPTION
    Print the effective PDLC configuration, its source, derived values, and
    every validation result. Exit 1 when any validation fails; warnings do not
    fail the command.
"""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import fields
from pathlib import Path

from pdlc.config import (
    CONFIG_FIELDS,
    Config,
    ConfigurationError,
    FIELD_LOCATIONS,
    _BOOL_FIELDS,
    _INT_FIELDS,
    default_code_host,
    git_remote_repository,
    home_config_path,
    repository_root,
)
from pdlc.internal.inputs import print_help


def _read(path: Path, values: dict[str, object], sources: dict[str, str], errors: list[str]) -> bool:
    if not path.exists():
        return False
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        errors.append(f"{path}: could not read config: {error}")
        return True

    def visit(section: tuple[str, ...], section_values: object) -> None:
        if not isinstance(section_values, dict):
            errors.append(f"{path}: [{'.'.join(section)}] must be a TOML table")
            return
        for name, value in section_values.items():
            if isinstance(value, dict):
                visit((*section, name), value)
                continue
            location = (".".join(section), name)
            field = CONFIG_FIELDS.get(location)
            label = f"[{location[0]}] {name}"
            if field is None:
                errors.append(f"{path}: unknown setting {label}")
                continue
            if not isinstance(value, (str, int, float, bool)):
                errors.append(f"{path}: setting {label} must be a TOML scalar")
                continue
            values[field] = value
            sources[field] = str(path)

    if not isinstance(document, dict):
        errors.append(f"{path}: document must be a TOML table")
    else:
        for section, section_values in document.items():
            if section in ("agents", "skills"):
                continue
            visit((section,), section_values)
    return True


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


def _validate(config: Config, errors: list[str]) -> list[str]:
    warnings: list[str] = []
    backend = config.backend or "github"
    if not config.backend:
        warnings.append("backend is defaulted to 'github'; set [backend] name explicitly")
    if backend not in {"github", "azure", "file"}:
        errors.append(f"unknown [backend] name: {backend!r}")
    code_host = config.code_host or default_code_host(backend)
    if not config.code_host:
        warnings.append(f"code_host is derived as '{code_host}' from backend; set [code_host] name explicitly")
    if code_host not in {"github", "file", "none"}:
        errors.append(f"unknown [code_host] name: {code_host!r}")
    if config.attachment_host not in {None, "file", "none"}:
        errors.append(f"unknown [attachment_host] name: {config.attachment_host!r}")

    required: dict[str, object] = {}
    if backend == "github":
        required = {
            "backend.github.repository": config.repository,
            "backend.github.project_number": config.project_number,
            "backend.github.project_owner": config.project_owner,
        }
    elif backend == "azure":
        required = {
            "backend.azure.organization": config.azure_org,
            "backend.azure.project": config.azure_project,
        }
        if code_host == "github":
            required["backend.github.repository"] = config.repository
    elif backend == "file" and code_host == "github":
        required = {"backend.github.repository": config.repository}
    for name, value in required.items():
        if not value:
            errors.append(f"missing required setting: {name}")
    return warnings


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
    home_present = _read(home_path, home_values, home_sources, errors)
    values.update(home_values)
    sources.update(home_sources)
    try:
        root = repository_root()
        repo_path = root / ".pdlc" / "config.toml"
    except ConfigurationError:
        root = None
        repo_path = None
    repo_present = _read(repo_path, values, sources, errors) if repo_path else False

    for environment_name, field in (("PDLC_HOME", "home"), ("PDLC_REPOSITORY", "repository")):
        if os.environ.get(environment_name):
            values[field] = os.environ[environment_name]
            sources[field] = environment_name
    if overrides:
        for field, value in overrides.items():
            if value is not None:
                values[field] = value
                sources[field] = "CLI override"

    if not values.get("repository") and root is not None:
        derived = git_remote_repository(root)
        if derived:
            values["repository"] = derived
            sources["repository"] = "derived from git origin"
            warnings.append("repository is auto-derived from git origin; set backend.github.repository in ~/.pdlc/config.toml or the repo's .pdlc/config.toml")
    if "repository" in home_values:
        warnings.append("repository is set in ~/.pdlc/config.toml; this is likely misconfigured — set repository in the repo's .pdlc/config.toml instead")

    typed = _typed_values(values, errors)
    config = Config.from_values(typed)
    warnings.extend(_validate(config, errors))
    lines = ["# PDLC doctor", "", f"Working directory: {Path.cwd()}", f"Repository root: {root or '(not found)' }", "", "## Config files", "", f"- ~/.pdlc/config.toml: {'present' if home_present else 'missing'} ({home_path})", f"- repo .pdlc/config.toml: {'present' if repo_present else 'missing'} ({repo_path or 'not found'})", "", "## Effective values", ""]
    for field in fields(Config):
        value = getattr(config, field.name)
        shown = "(unset)" if value is None else repr(value)
        lines.append(f"- {field.name} = {shown} [{_source(field.name, sources)}]")
    lines += ["", "## Warnings", ""]
    lines.extend(f"- WARNING: {warning}" for warning in warnings) or lines.append("- None")
    lines += ["", "## Validations", ""]
    lines.extend(f"- FAIL: {error}" for error in errors) or lines.append("- PASS: all validations")
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

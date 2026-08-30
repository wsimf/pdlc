"""Load pdlc configuration from the repository and environment."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from pdlc.domain.lifecycle import PdlcError


ENVIRONMENT_KEYS = (
    "PDLC_REPOSITORY", "PDLC_PROJECT_NUMBER", "PDLC_PROJECT_OWNER",
    "PDLC_BACKEND", "PDLC_CODE_HOST", "PDLC_ATTACHMENT_HOST", "PDLC_HOME",
    "PDLC_ACTOR", "PDLC_REF_LABEL", "PDLC_ITEMS_FILE", "PDLC_SUBISSUES_FILE",
    "PDLC_MAX_ATTEMPTS", "PDLC_INITIAL_DELAY_SECONDS", "PDLC_MAX_DELAY_SECONDS",
    "PDLC_NO_SLEEP", "PDLC_AUTOAPPROVE_CHURN_CAP",
)

TOML_ENVIRONMENT_KEYS = {
    ("backend", "name"): "PDLC_BACKEND",
    ("backend.github", "repository"): "PDLC_REPOSITORY",
    ("backend.github", "project_number"): "PDLC_PROJECT_NUMBER",
    ("backend.github", "project_owner"): "PDLC_PROJECT_OWNER",
    ("backend.github", "items_file"): "PDLC_ITEMS_FILE",
    ("backend.github", "subissues_file"): "PDLC_SUBISSUES_FILE",
    ("code_host", "name"): "PDLC_CODE_HOST",
    ("attachment_host", "name"): "PDLC_ATTACHMENT_HOST",
    ("runtime", "home"): "PDLC_HOME",
    ("runtime", "actor"): "PDLC_ACTOR",
    ("runtime", "ref_label"): "PDLC_REF_LABEL",
    ("workflow", "max_attempts"): "PDLC_MAX_ATTEMPTS",
    ("workflow", "initial_delay_seconds"): "PDLC_INITIAL_DELAY_SECONDS",
    ("workflow", "max_delay_seconds"): "PDLC_MAX_DELAY_SECONDS",
    ("workflow", "no_sleep"): "PDLC_NO_SLEEP",
    ("workflow", "autoapprove_churn_cap"): "PDLC_AUTOAPPROVE_CHURN_CAP",
}

_config_loaded = False


class ConfigurationError(PdlcError):
    """A configuration problem that should be shown directly to the user."""


@dataclass(frozen=True)
class Config:
    repository: str | None = None
    project_number: str | None = None
    project_owner: str | None = None
    backend: str | None = None
    code_host: str | None = None
    attachment_host: str | None = None
    home: str | None = None
    actor: str | None = None
    ref_label: str | None = None
    items_file: str | None = None
    subissues_file: str | None = None
    max_attempts: str | None = None
    initial_delay_seconds: str | None = None
    max_delay_seconds: str | None = None
    no_sleep: str | None = None
    autoapprove_churn_cap: str | None = None

    @classmethod
    def from_environment(cls) -> "Config":
        return cls(**{
            key.removeprefix("PDLC_").lower(): os.environ.get(key)
            for key in ENVIRONMENT_KEYS
        })

    def validate_for_backend(self) -> None:
        """Require GitHub project coordinates when GitHub is in use."""
        if (self.backend or "github") == "file":
            return
        required = {
            "PDLC_REPOSITORY": self.repository,
            "PDLC_PROJECT_NUMBER": self.project_number,
            "PDLC_PROJECT_OWNER": self.project_owner,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ConfigurationError(configuration_guidance(missing))


def repository_root(start: Path | None = None) -> Path:
    """Find the Git repository root containing ``start``."""
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    raise ConfigurationError(configuration_guidance([]))


def config_path(start: Path | None = None) -> Path:
    return repository_root(start) / ".pdlc" / "config.toml"


def _read_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        values = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigurationError(f"Could not read {path}: {error}") from error
    flattened: dict[str, str] = {}

    def visit(section: tuple[str, ...], section_values: dict) -> None:
        for name, value in section_values.items():
            if isinstance(value, dict):
                visit((*section, name), value)
                continue
            section_name = ".".join(section)
            environment_name = TOML_ENVIRONMENT_KEYS.get((section_name, name))
            if environment_name is None:
                raise ConfigurationError(
                    f"Unknown setting in {path}: [{section_name}] {name}"
                )
            if not isinstance(value, (str, int, float, bool)):
                raise ConfigurationError(
                    f"Setting [{section_name}] {name} in {path} must be a TOML scalar"
                )
            flattened[environment_name] = (
                str(value).lower() if isinstance(value, bool) else str(value)
            )

    for section, section_values in values.items():
        if not isinstance(section_values, dict):
            raise ConfigurationError(f"[{section}] in {path} must be a TOML table")
        visit((section,), section_values)
    return flattened


def load_config(start: Path | None = None) -> Config:
    """Apply repository config over the environment and return the result."""
    global _config_loaded
    os.environ.update(_read_file(config_path(start)))
    _config_loaded = True
    return Config.from_environment()


def get_config() -> Config:
    """Return current repository configuration for any pdlc module."""
    if not _config_loaded:
        return load_config()
    return Config.from_environment()


def configuration_guidance(missing: list[str]) -> str:
    required = missing or [
        "PDLC_REPOSITORY", "PDLC_PROJECT_NUMBER", "PDLC_PROJECT_OWNER"
    ]
    details = f"Missing: {', '.join(missing)}\n\n" if missing else ""
    example = "\n".join(f'{name} = "<value>"' for name in required)
    return (
        "pdlc is not configured for this repository.\n\n"
        f"{details}"
        "Create .pdlc/config.toml with the required values, for example:\n\n"
        f"{example}\n\n"
        "You can also set the corresponding PDLC_* environment variables."
    )

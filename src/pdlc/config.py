"""Load pdlc configuration from the repository and environment."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from pdlc.domain.lifecycle import PdlcError


ENVIRONMENT_KEYS = (
    "PDLC_REPOSITORY", "PDLC_PROJECT_NUMBER", "PDLC_PROJECT_OWNER",
    "PDLC_AZURE_ORG", "PDLC_AZURE_PROJECT", "PDLC_AZURE_RECORD_TYPE",
    "PDLC_AZURE_CLOSED_STATE", "PDLC_AZURE_ASSIGNED_TO",
    "PDLC_GITHUB_ASSIGNED_TO",
    "PDLC_BACKEND", "PDLC_CODE_HOST", "PDLC_ATTACHMENT_HOST", "PDLC_PR_ATTACHMENT", "PDLC_HOME",
    "PDLC_ACTOR", "PDLC_REF_LABEL",
    "PDLC_MAX_ATTEMPTS", "PDLC_INITIAL_DELAY_SECONDS", "PDLC_MAX_DELAY_SECONDS",
    "PDLC_NO_SLEEP",
    "PDLC_WORKTREE_ROOT", "PDLC_WORKTREE_INIT_SCRIPT", "PDLC_WORKTREE_BASE_REF",
    "PDLC_DEBUG",
)

TOML_ENVIRONMENT_KEYS = {
    ("backend", "name"): "PDLC_BACKEND",
    ("backend.github", "repository"): "PDLC_REPOSITORY",
    ("backend.github", "project_number"): "PDLC_PROJECT_NUMBER",
    ("backend.github", "project_owner"): "PDLC_PROJECT_OWNER",
    ("backend.github", "assigned_to"): "PDLC_GITHUB_ASSIGNED_TO",
    ("backend.azure", "organization"): "PDLC_AZURE_ORG",
    ("backend.azure", "project"): "PDLC_AZURE_PROJECT",
    ("backend.azure", "record_type"): "PDLC_AZURE_RECORD_TYPE",
    ("backend.azure", "closed_state"): "PDLC_AZURE_CLOSED_STATE",
    ("backend.azure", "assigned_to"): "PDLC_AZURE_ASSIGNED_TO",
    ("code_host", "name"): "PDLC_CODE_HOST",
    ("code_host", "pr_attachment"): "PDLC_PR_ATTACHMENT",
    ("attachment_host", "name"): "PDLC_ATTACHMENT_HOST",
    ("runtime", "home"): "PDLC_HOME",
    ("runtime", "actor"): "PDLC_ACTOR",
    ("runtime", "ref_label"): "PDLC_REF_LABEL",
    ("workflow", "max_attempts"): "PDLC_MAX_ATTEMPTS",
    ("workflow", "initial_delay_seconds"): "PDLC_INITIAL_DELAY_SECONDS",
    ("workflow", "max_delay_seconds"): "PDLC_MAX_DELAY_SECONDS",
    ("workflow", "no_sleep"): "PDLC_NO_SLEEP",
    ("worktree", "root"): "PDLC_WORKTREE_ROOT",
    ("worktree", "init_script"): "PDLC_WORKTREE_INIT_SCRIPT",
    ("worktree", "base_ref"): "PDLC_WORKTREE_BASE_REF",
    ("debug", "enabled"): "PDLC_DEBUG",
}

# Capability slots let a project name the specialist skill or sub-agent PDLC
# should route each seam to. They live in their own `config.toml` tables so a
# project can point the workflow at its own toolchain without the skills
# hardcoding any tool name. `agents` slots fall back to `general-purpose`;
# `skills` slots fall back to the stage doing the work inline (see
# `agent/skills/pdlc/references/capabilities.md` for the per-slot contract).
CAPABILITY_SLOTS: dict[str, tuple[str, ...]] = {
    "agents": ("core-implementer", "ui-implementer"),
    "skills": (
        "build-run", "ux-design", "cumulative-review",
        "test-authoring", "test-framework",
    ),
}

_config_loaded = False
_capabilities: "Capabilities | None" = None


class ConfigurationError(PdlcError):
    """A configuration problem that should be shown directly to the user."""


def default_code_host(backend: str) -> str:
    """The code host implied by a backend when ``PDLC_CODE_HOST`` is unset.

    Azure Boards owns work items only, so it implies no code host at all; the
    GitHub and file backends each host code themselves. Shared with
    ``pdlc.hosts.code_host`` so validation and selection cannot disagree about
    which host a given backend actually runs with.
    """
    return backend if backend in ("github", "file") else "none"


@dataclass(frozen=True)
class Config:
    repository: str | None = None
    project_number: str | None = None
    project_owner: str | None = None
    github_assigned_to: str | None = None
    backend: str | None = None
    code_host: str | None = None
    attachment_host: str | None = None
    # Optional line appended to each task PR body at `pdlc post implement-task`;
    # `{work.number}` resolves to the parent work item's bare number.
    pr_attachment: str | None = None
    home: str | None = None
    actor: str | None = None
    ref_label: str | None = None
    azure_org: str | None = None
    azure_project: str | None = None
    azure_record_type: str | None = None
    azure_closed_state: str | None = None
    azure_assigned_to: str | None = None
    max_attempts: int = 5
    initial_delay_seconds: int = 60
    max_delay_seconds: int = 900
    no_sleep: bool = False
    # When true, every external CLI call (az, gh, git, …) is appended to
    # ~/.pdlc/debug.log by pdlc.internal.trace.
    debug: bool = False
    # `pdlc prepare` / `pdlc cleanup` (human-only) worktree scaffolding.
    # `worktree_root` is the parent directory for every prepared tree, which the
    # commands nest `<root>/<repo-name>/<workitem>` under; unset falls back to
    # `~/.pdlc/worktrees`. `worktree_init_script` is an optional shell snippet
    # run in the new tree, `worktree_base_ref` the ref new branches start from
    # (default: the repo's detected default branch).
    worktree_root: str | None = None
    worktree_init_script: str | None = None
    worktree_base_ref: str | None = None

    @classmethod
    def from_environment(cls) -> "Config":
        values = {
            key.removeprefix("PDLC_").lower(): os.environ.get(key)
            for key in ENVIRONMENT_KEYS
        }
        for name, default, minimum in (
            ("max_attempts", 5, 1), ("initial_delay_seconds", 60, 0),
            ("max_delay_seconds", 900, 0),
        ):
            raw = values[name]
            try:
                value = int(raw) if raw is not None else default
            except (TypeError, ValueError):
                raise ConfigurationError(f"PDLC_{name.upper()} must be an integer >= {minimum}") from None
            if value < minimum:
                raise ConfigurationError(f"PDLC_{name.upper()} must be >= {minimum}")
            values[name] = value
        for name in ("no_sleep", "debug"):
            raw = (values[name] or "false").lower()
            if raw not in {"true", "false", "1", "0"}:
                raise ConfigurationError(f"PDLC_{name.upper()} must be true, false, 1, or 0")
            values[name] = raw in {"true", "1"}
        return cls(**values)

    def validate_for_backend(self) -> None:
        """Require each selected host's own coordinates.

        The work-item backend and the code host are independent: Azure Boards
        is expected to pair with GitHub repos, so an azure backend still needs
        `PDLC_REPOSITORY` whenever the code host is GitHub.
        """
        backend = self.backend or "github"
        if backend not in {"github", "azure", "file"}:
            raise ConfigurationError(f"unknown PDLC_BACKEND: {backend!r}")
        code_host = self.code_host or default_code_host(backend)
        if code_host not in {"github", "file", "none"}:
            raise ConfigurationError(f"unknown PDLC_CODE_HOST: {code_host!r}")
        if self.attachment_host not in {None, "file", "none"}:
            raise ConfigurationError(f"unknown PDLC_ATTACHMENT_HOST: {self.attachment_host!r}")
        if backend == "file":
            if code_host == "github" and not self.repository:
                raise ConfigurationError(configuration_guidance(["PDLC_REPOSITORY"]))
            return
        required: dict[str, str | None] = {}
        if backend == "azure":
            required |= {
                "PDLC_AZURE_ORG": self.azure_org,
                "PDLC_AZURE_PROJECT": self.azure_project,
            }
            if code_host == "github":
                required["PDLC_REPOSITORY"] = self.repository
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise ConfigurationError(configuration_guidance(missing))
            return
        required = {
            "PDLC_REPOSITORY": self.repository,
            "PDLC_PROJECT_NUMBER": self.project_number,
            "PDLC_PROJECT_OWNER": self.project_owner,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ConfigurationError(configuration_guidance(missing))


@dataclass(frozen=True)
class Capabilities:
    """Project-declared routing for PDLC seams, read from the ``[agents]`` and
    ``[skills]`` tables of ``.pdlc/config.toml`` layered over ``~/.pdlc/config.toml``.
    Missing slots resolve to a fallback rather than an error so the workflow
    runs on an unconfigured repo."""

    agents: dict[str, str]
    skills: dict[str, str]

    @classmethod
    def empty(cls) -> "Capabilities":
        return cls(agents={}, skills={})

    def agent(self, slot: str) -> str:
        """The sub-agent to dispatch this slot to; ``general-purpose`` if unset."""
        return self.agents.get(slot) or "general-purpose"

    def skill(self, slot: str) -> str | None:
        """The skill configured for this slot, or ``None`` to run the seam inline."""
        return self.skills.get(slot)


def _read_capabilities(section: str, table: dict, path: Path) -> dict[str, str]:
    known = CAPABILITY_SLOTS[section]
    resolved: dict[str, str] = {}
    for slot, value in table.items():
        if slot not in known:
            raise ConfigurationError(
                f"Unknown capability slot in {path}: [{section}] {slot}. "
                f"Known slots: {', '.join(known)}"
            )
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(
                f"Capability [{section}] {slot} in {path} must be a non-empty string"
            )
        resolved[slot] = value.strip()
    return resolved


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


def home_config_path() -> Path:
    """Machine-wide config, layered under the repository file (see ``load_config``)."""
    return Path.home() / ".pdlc" / "config.toml"


def _read_file(path: Path) -> tuple[dict[str, str], Capabilities]:
    if not path.exists():
        return {}, Capabilities.empty()
    try:
        values = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise ConfigurationError(f"Could not read {path}: {error}") from error
    flattened: dict[str, str] = {}
    capabilities: dict[str, dict[str, str]] = {"agents": {}, "skills": {}}

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
        if section in CAPABILITY_SLOTS:
            capabilities[section] = _read_capabilities(section, section_values, path)
            continue
        visit((section,), section_values)
    return flattened, Capabilities(
        agents=capabilities["agents"], skills=capabilities["skills"]
    )


def load_config(start: Path | None = None) -> Config:
    """Merge config and return the result, in ascending priority:
    process environment, then ``~/.pdlc/config.toml``, then the repository's
    ``.pdlc/config.toml``. Capability slots merge the same way, per slot.

    The repository file is optional when a home file exists, so ``pdlc`` runs
    outside a Git repository on machine-wide config alone.
    """
    global _config_loaded, _capabilities
    home_path = home_config_path()
    home_flat, home_caps = _read_file(home_path)
    try:
        repo_path: Path | None = config_path(start)
    except ConfigurationError:
        if not home_path.exists():
            raise
        repo_path = None
    repo_flat, repo_caps = (
        _read_file(repo_path) if repo_path is not None else ({}, Capabilities.empty())
    )
    os.environ.update({**home_flat, **repo_flat})
    _capabilities = Capabilities(
        agents={**home_caps.agents, **repo_caps.agents},
        skills={**home_caps.skills, **repo_caps.skills},
    )
    _config_loaded = True
    return Config.from_environment()


def get_capabilities() -> Capabilities:
    """Return the project's capability routing, loading config if needed."""
    if _capabilities is None:
        load_config()
    assert _capabilities is not None
    return _capabilities


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
    sections: dict[str, list[str]] = {}
    for (section, key), environment_name in TOML_ENVIRONMENT_KEYS.items():
        if environment_name in required:
            sections.setdefault(section, []).append(f'{key} = "<value>"')
    example = "\n\n".join(
        f"[{section}]\n" + "\n".join(lines) for section, lines in sections.items()
    )
    return (
        "pdlc is not configured for this repository.\n\n"
        f"{details}"
        "Create .pdlc/config.toml with the required values, for example:\n\n"
        f"{example}\n\n"
        "You can also put the same values in ~/.pdlc/config.toml for machine-wide "
        "defaults, or set the corresponding PDLC_* environment variables."
    )


def reset_config() -> None:
    """Forget cached repository configuration at the command boundary."""
    global _config_loaded, _capabilities
    _config_loaded = False
    _capabilities = None

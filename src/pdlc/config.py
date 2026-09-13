"""Load pdlc configuration from ``.pdlc/config.toml`` files.

Configuration is file-first: ``~/.pdlc/config.toml`` for machine-wide defaults,
layered under the repository's ``.pdlc/config.toml``, with CLI flags on top. Only
two settings are still read from the process environment — ``PDLC_HOME`` and
``PDLC_REPOSITORY`` — because they identify *where* the store and the checkout
live before any file has been located.
"""

from __future__ import annotations

import os
import re
import subprocess
import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import Path

from pdlc.domain.lifecycle import PdlcError


# ``(table, key) -> Config field``. The single source of truth for which TOML
# settings exist and where each one lands on the dataclass.
CONFIG_FIELDS = {
    ("backend", "name"): "backend",
    ("backend.github", "repository"): "repository",
    ("backend.github", "project_number"): "project_number",
    ("backend.github", "project_owner"): "project_owner",
    ("backend.github", "assigned_to"): "github_assigned_to",
    ("backend.azure", "organization"): "azure_org",
    ("backend.azure", "project"): "azure_project",
    ("backend.azure", "record_type"): "azure_record_type",
    ("backend.azure", "closed_state"): "azure_closed_state",
    ("backend.azure", "open_state"): "azure_open_state",
    ("backend.azure", "task_closed_state"): "azure_task_closed_state",
    ("backend.azure", "task_open_state"): "azure_task_open_state",
    ("backend.azure", "task_in_progress_state"): "azure_task_in_progress_state",
    ("backend.azure", "assigned_to"): "azure_assigned_to",
    ("code_host", "name"): "code_host",
    ("code_host", "pr_attachment"): "pr_attachment",
    ("code_host", "pr_title_format"): "pr_title_format",
    ("attachment_host", "name"): "attachment_host",
    ("runtime", "home"): "home",
    ("runtime", "actor"): "actor",
    ("runtime", "ref_label"): "ref_label",
    ("workflow", "max_attempts"): "max_attempts",
    ("workflow", "initial_delay_seconds"): "initial_delay_seconds",
    ("workflow", "max_delay_seconds"): "max_delay_seconds",
    ("workflow", "no_sleep"): "no_sleep",
    ("worktree", "root"): "worktree_root",
    ("worktree", "init_script"): "worktree_init_script",
    ("worktree", "base_ref"): "worktree_base_ref",
    ("debug", "enabled"): "debug",
}

# ``field -> "table.key"``, for pointing a user at the setting they are missing.
FIELD_LOCATIONS = {
    field: f"{table}.{key}" for (table, key), field in CONFIG_FIELDS.items()
}

_INT_FIELDS = {
    "max_attempts": 1,
    "initial_delay_seconds": 0,
    "max_delay_seconds": 0,
}
_BOOL_FIELDS = ("no_sleep", "debug")

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

_config: "Config | None" = None
_capabilities: "Capabilities | None" = None


class ConfigurationError(PdlcError):
    """A configuration problem that should be shown directly to the user."""


def default_code_host(backend: str) -> str:
    """The code host implied by a backend when ``[code_host] name`` is unset.

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
    # Optional format string for each task PR title at `pdlc post implement-task`.
    # Placeholders: `{task.title}` (the delivery task's title, with its
    # `WORK-N-TASK-N` id prefix and `[CORE]`/`[UI]` tag stripped), `{task.id}`
    # (e.g. `TASK-001`), `{work.number}` (the parent's bare number), and
    # `{work.type}` (`feature`/`bug`). Unset uses the bare stripped task title.
    pr_title_format: str | None = None
    home: str | None = None
    actor: str | None = None
    ref_label: str | None = None
    azure_org: str | None = None
    azure_project: str | None = None
    azure_record_type: str | None = None
    azure_closed_state: str | None = None
    azure_open_state: str | None = None
    # Delivery tasks (`Task`) commonly use a different state vocabulary than
    # the record's own work-item type; unset falls back to `azure_closed_state`
    # / `azure_open_state`. `azure_task_in_progress_state` has no work-item
    # equivalent to fall back to, so it stays `None` unless set.
    azure_task_closed_state: str | None = None
    azure_task_open_state: str | None = None
    azure_task_in_progress_state: str | None = None
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
    def from_values(cls, values: dict[str, object]) -> "Config":
        """Build a Config from merged ``.pdlc/config.toml`` settings (keyed by
        field name), coercing and range-checking the typed settings."""
        known = {field.name for field in fields(cls)}
        data: dict[str, object] = {
            name: value
            for name, value in values.items()
            if name in known and value is not None
        }
        for name, minimum in _INT_FIELDS.items():
            if name not in data:
                continue
            raw = data[name]
            try:
                number = int(raw)  # type: ignore[call-overload]
            except (TypeError, ValueError):
                raise ConfigurationError(
                    f"[{FIELD_LOCATIONS[name]}] must be an integer >= {minimum}"
                ) from None
            if isinstance(raw, float) and number != raw:
                raise ConfigurationError(
                    f"[{FIELD_LOCATIONS[name]}] must be an integer >= {minimum}"
                )
            if number < minimum:
                raise ConfigurationError(f"[{FIELD_LOCATIONS[name]}] must be >= {minimum}")
            data[name] = number
        for name in _BOOL_FIELDS:
            if name not in data:
                continue
            raw = data[name]
            if isinstance(raw, bool):
                continue
            text = str(raw).lower()
            if text not in {"true", "false", "1", "0"}:
                raise ConfigurationError(
                    f"[{FIELD_LOCATIONS[name]}] must be a boolean"
                )
            data[name] = text in {"true", "1"}
        for name, value in list(data.items()):
            if name not in _INT_FIELDS and name not in _BOOL_FIELDS:
                data[name] = str(value)
        return cls(**data)  # type: ignore[arg-type]

    def validate_for_backend(self) -> None:
        """Require each selected host's own coordinates.

        The work-item backend and the code host are independent: Azure Boards
        is expected to pair with GitHub repos, so an azure backend still needs
        a repository whenever the code host is GitHub.
        """
        backend = self.backend or "github"
        if backend not in {"github", "azure", "file"}:
            raise ConfigurationError(f"unknown [backend] name: {backend!r}")
        code_host = self.code_host or default_code_host(backend)
        if code_host not in {"github", "file", "none"}:
            raise ConfigurationError(f"unknown [code_host] name: {code_host!r}")
        if self.attachment_host not in {None, "file", "none"}:
            raise ConfigurationError(
                f"unknown [attachment_host] name: {self.attachment_host!r}"
            )
        if backend == "file":
            if code_host == "github" and not self.repository:
                raise ConfigurationError(
                    configuration_guidance(["backend.github.repository"])
                )
            return
        required: dict[str, str | None] = {}
        if backend == "azure":
            required |= {
                "backend.azure.organization": self.azure_org,
                "backend.azure.project": self.azure_project,
            }
            if code_host == "github":
                required["backend.github.repository"] = self.repository
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise ConfigurationError(configuration_guidance(missing))
            return
        required = {
            "backend.github.repository": self.repository,
            "backend.github.project_number": self.project_number,
            "backend.github.project_owner": self.project_owner,
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


def git_remote_repository(root: Path) -> str | None:
    """Best-effort ``owner/name`` from the repository's ``origin`` remote.

    This is only the last-resort source for ``PDLC_REPOSITORY``: an environment
    variable or a `config.toml` value always wins and this never overrides one
    (see ``load_config``). Anything unexpected — no git, no ``origin``, a
    non-GitHub URL, or an SSH host alias that hides ``github.com`` — yields
    ``None`` so the normal "not configured" error still stands rather than a
    wrong guess.

    Handles the HTTPS (``https://github.com/owner/repo.git``), SCP-style SSH
    (``git@github.com:owner/repo.git``), and ``ssh://`` URL forms, including an
    explicit port.
    """
    from pdlc.internal.trace import record_external_call

    args = ["git", "-C", str(root), "config", "--get", "remote.origin.url"]
    record_external_call("git", args)
    try:
        result = subprocess.run(args, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    match = re.search(
        r"github\.com(?::\d+)?[:/]([^/ :]+)/([^/]+?)(?:\.git)?$", result.stdout.strip()
    )
    return f"{match.group(1)}/{match.group(2)}" if match else None


def home_config_path() -> Path:
    """Machine-wide config, layered under the repository file (see ``load_config``)."""
    return Path.home() / ".pdlc" / "config.toml"


def _read_file(path: Path) -> tuple[dict[str, object], Capabilities]:
    if not path.exists():
        return {}, Capabilities.empty()
    try:
        values = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise ConfigurationError(f"Could not read {path}: {error}") from error
    flattened: dict[str, object] = {}
    capabilities: dict[str, dict[str, str]] = {"agents": {}, "skills": {}}

    def visit(section: tuple[str, ...], section_values: dict) -> None:
        for name, value in section_values.items():
            if isinstance(value, dict):
                visit((*section, name), value)
                continue
            section_name = ".".join(section)
            field = CONFIG_FIELDS.get((section_name, name))
            if field is None:
                raise ConfigurationError(
                    f"Unknown setting in {path}: [{section_name}] {name}"
                )
            if not isinstance(value, (str, int, float, bool)):
                raise ConfigurationError(
                    f"Setting [{section_name}] {name} in {path} must be a TOML scalar"
                )
            flattened[field] = value

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


def load_config(start: Path | None = None, *, overrides: dict[str, object] | None = None) -> Config:
    """Merge configuration, cache it, and return it. Ascending priority:
    the ``PDLC_HOME`` / ``PDLC_REPOSITORY`` environment variables, then
    ``~/.pdlc/config.toml``, then the repository's ``.pdlc/config.toml``, then
    ``overrides`` (CLI flags). Capability slots merge the same way, per slot.

    The repository file is optional when a home file exists, so ``pdlc`` runs
    outside a Git repository on machine-wide config alone.

    The repository alone has a further fallback: if nothing sets it, it is
    derived from the checkout's ``origin`` remote. An explicit value always
    wins.
    """
    global _config, _capabilities
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
    merged: dict[str, object] = {}
    for environment_name, field in (("PDLC_HOME", "home"), ("PDLC_REPOSITORY", "repository")):
        if os.environ.get(environment_name):
            merged[field] = os.environ[environment_name]
    merged.update(home_flat)
    merged.update(repo_flat)
    if overrides:
        merged.update({k: v for k, v in overrides.items() if v is not None})
    # Last resort only: when nothing names the GitHub repository, derive it from
    # the checkout's `origin` remote so a shared repo works without every
    # developer keeping a local `PDLC_REPOSITORY`.
    if not merged.get("repository") and repo_path is not None:
        derived = git_remote_repository(repo_path.parent.parent)
        if derived:
            merged["repository"] = derived
    _capabilities = Capabilities(
        agents={**home_caps.agents, **repo_caps.agents},
        skills={**home_caps.skills, **repo_caps.skills},
    )
    _config = Config.from_values(merged)
    # The file backend still resolves its store from `PDLC_HOME`; bridge a
    # `[runtime] home` set only in a config file back onto the environment.
    if _config.home:
        os.environ["PDLC_HOME"] = _config.home
    return _config


def install_config(config: Config) -> None:
    """Install a fully-formed Config for the process (tests, embedding)."""
    global _config
    _config = config


def set_config(**overrides: object) -> Config:
    """Replace named fields on the current process config, loading a default
    one first if none is installed. For tests and interactive overrides."""
    global _config
    base = _config if _config is not None else Config()
    _config = replace(base, **overrides)  # type: ignore[arg-type]
    return _config


def get_capabilities() -> Capabilities:
    """Return the project's capability routing, loading config if needed."""
    if _capabilities is None:
        load_config()
    assert _capabilities is not None
    return _capabilities


def get_config() -> Config:
    """Return the process configuration, loading it once if needed."""
    if _config is None:
        return load_config()
    return _config


def configuration_guidance(missing: list[str]) -> str:
    required = missing or [
        "backend.github.repository",
        "backend.github.project_number",
        "backend.github.project_owner",
    ]
    details = f"Missing: {', '.join(missing)}\n\n" if missing else ""
    sections: dict[str, list[str]] = {}
    for (section, key) in CONFIG_FIELDS:
        if f"{section}.{key}" in required:
            sections.setdefault(section, []).append(f'{key} = "<value>"')
    example = "\n\n".join(
        f"[{section}]\n" + "\n".join(lines) for section, lines in sections.items()
    )
    repository_hint = (
        "\n\nThe repository is normally auto-detected from this checkout's "
        "`origin` remote; it must be set explicitly here because that lookup did "
        "not resolve a github.com repository."
        if "backend.github.repository" in missing
        else ""
    )
    return (
        "pdlc is not configured for this repository.\n\n"
        f"{details}"
        "Create .pdlc/config.toml with the required values, for example:\n\n"
        f"{example}\n\n"
        "You can also put the same values in ~/.pdlc/config.toml for machine-wide "
        "defaults. Only PDLC_HOME and PDLC_REPOSITORY are read from the environment."
        f"{repository_hint}"
    )


def reset_config() -> None:
    """Forget cached configuration at the command boundary."""
    global _config, _capabilities
    _config = None
    _capabilities = None

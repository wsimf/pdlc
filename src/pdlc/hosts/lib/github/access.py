"""Read-only `gh` probes for `pdlc doctor`: CLI version, login, token scopes,
and access to the configured repository and Project."""

from __future__ import annotations

from typing import Any

from pdlc.domain.lifecycle import PdlcError
from pdlc.hosts.lib.access import AccessReport, Version, check_version
from pdlc.hosts.lib.process import parse_json, run_process

# The oldest `gh` pdlc is exercised against; older releases only warn.
GH_MIN_VERSION: Version = (2, 100, 0)

_HOST = "github.com"
_TIMEOUT = 30
_WRITE_PERMISSIONS = {"ADMIN", "MAINTAIN", "WRITE"}


def _gh(args: list[str]) -> str:
    return run_process(["gh", *args], timeout=_TIMEOUT, idempotent=True)


def _check_login(report: AccessReport) -> bool:
    """Reports the active github.com account; False stops the remaining probes."""
    status: Any = parse_json(_gh(["auth", "status", "--active", "--hostname", _HOST, "--json", "hosts"]), "gh")
    hosts = status.get("hosts") if isinstance(status, dict) else None
    accounts = (hosts or {}).get(_HOST) or []
    account = next((entry for entry in accounts if entry.get("active")), None)
    if account is None:
        report.facts.append(f"gh login: not logged in to {_HOST}")
        report.errors.append(f"gh is not logged in to {_HOST}; run `gh auth login`")
        return False
    login, state = account.get("login") or "(unknown)", account.get("state") or "(unknown)"
    report.facts.append(f"gh login: {login} via {account.get('tokenSource') or 'unknown source'} ({state})")
    if state != "success":
        detail = account.get("error") or "authentication failed"
        report.errors.append(f"gh auth for {login} on {_HOST} is {state}: {detail}; run `gh auth login`")
        return False
    scopes = [scope.strip() for scope in (account.get("scopes") or "").split(",") if scope.strip()]
    report.facts.append(f"gh token scopes: {', '.join(scopes) if scopes else '(not reported)'}")
    if not scopes:
        report.warnings.append("gh token scopes are not reported (fine-grained token or GH_TOKEN?); Project access is probed directly instead")
    elif "project" not in scopes:
        report.errors.append("gh token lacks the `project` scope pdlc needs to edit the Project; run `gh auth refresh -s project`")
    return True


def _check_repository(report: AccessReport, repository: str) -> None:
    try:
        data: Any = parse_json(_gh(["repo", "view", repository, "--json", "nameWithOwner,viewerPermission"]), "gh")
    except PdlcError as error:
        report.facts.append(f"repository: {repository} (not accessible)")
        report.errors.append(f"gh cannot read repository {repository}: {error}")
        return
    permission = data.get("viewerPermission") or "NONE"
    report.facts.append(f"repository: {data.get('nameWithOwner') or repository} (permission {permission})")
    if permission not in _WRITE_PERMISSIONS:
        report.warnings.append(f"gh has {permission} permission on {repository}; pdlc needs WRITE to push branches and open PRs")


def _check_project(report: AccessReport, owner: str, number: str) -> None:
    try:
        data: Any = parse_json(_gh(["project", "view", number, "--owner", owner, "--format", "json"]), "gh")
    except PdlcError as error:
        report.facts.append(f"project: {owner}/{number} (not accessible)")
        report.errors.append(f"gh cannot read Project {owner}/{number}: {error}")
        return
    report.facts.append(f"project: {owner}/{number} {data.get('title')!r} ({data.get('url') or 'no url'})")


def check_access(*, repository: str | None, project_owner: str | None, project_number: str | None) -> AccessReport:
    """Probes `gh` for the GitHub backend; unset coordinates skip their probe
    because doctor already reports them as missing settings."""
    report = AccessReport()
    try:
        raw = _gh(["--version"])
    except PdlcError as error:
        report.facts.append("gh: not available")
        report.errors.append(f"gh CLI unavailable: {error}; install it from https://cli.github.com")
        return report
    check_version(report, "gh", raw.splitlines()[0] if raw else "", GH_MIN_VERSION)
    try:
        if not _check_login(report):
            return report
    except PdlcError as error:
        report.errors.append(f"gh auth status failed: {error}")
        return report
    if repository:
        _check_repository(report, repository)
    if project_owner and project_number:
        _check_project(report, project_owner, project_number)
    return report

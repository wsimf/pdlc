"""Read-only `az` probes for `pdlc doctor`: CLI and `azure-devops` extension
versions, the credential source, and access to the configured project and its
Boards.

Only Azure DevOps access matters, so either credential works: an `az login`
session or a PAT (`AZURE_DEVOPS_EXT_PAT` or one stored by `az devops login`).
A stored PAT is not observable without using it, so the project probe is the
authority on whether the credentials work, not `az account show`."""

from __future__ import annotations

import os
from typing import Any

from pdlc.domain.lifecycle import PdlcError
from pdlc.hosts.lib.access import AccessReport, Version, check_version
from pdlc.hosts.lib.process import parse_json, run_process

# The oldest `az` and `azure-devops` extension pdlc is exercised against; older
# releases only warn.
AZ_MIN_VERSION: Version = (2, 90, 0)
AZURE_DEVOPS_MIN_VERSION: Version = (1, 0, 8)

_EXTENSION = "azure-devops"
_PAT_VARIABLE = "AZURE_DEVOPS_EXT_PAT"
_TIMEOUT = 30
_LOGIN_HINT = f"run `az login` or `az devops login`, or set {_PAT_VARIABLE}"


def _az(args: list[str]) -> str:
    # An empty stdin keeps an unauthenticated `az devops` from waiting on a prompt.
    return run_process(["az", *args], input="", timeout=_TIMEOUT)


def _report_credentials(report: AccessReport) -> None:
    report.facts.append(f"{_PAT_VARIABLE}: {'set' if os.environ.get(_PAT_VARIABLE) else 'unset'}")
    try:
        user = _az(["account", "show", "--query", "user.name", "-o", "tsv"]).strip()
    except PdlcError:
        user = ""
    report.facts.append(f"az login: {user or 'not logged in (a PAT from `az devops login` may still apply)'}")


def _check_project(report: AccessReport, organization: str, project: str) -> bool:
    try:
        data: Any = parse_json(_az([
            "devops", "project", "show", "--organization", organization, "--project", project, "-o", "json",
        ]), "az")
    except PdlcError as error:
        report.facts.append(f"project: {organization}/{project} (not accessible)")
        report.errors.append(f"az devops cannot read project {project!r} in {organization}: {error}; {_LOGIN_HINT}")
        return False
    report.facts.append(f"project: {organization}/{data.get('name') or project} ({data.get('id') or 'no id'})")
    return True


def _check_boards(report: AccessReport, organization: str, project: str) -> None:
    # Matches nothing, so it proves query access without reading any work item.
    wiql = "SELECT [System.Id] FROM WorkItems WHERE [System.Id] < 0"
    try:
        _az(["boards", "query", "--organization", organization, "--project", project, "--wiql", wiql, "-o", "json"])
    except PdlcError as error:
        report.facts.append("boards: work-item query failed")
        report.errors.append(f"az boards cannot query work items in {project!r}: {error}")
        return
    report.facts.append("boards: work-item query OK")


def check_access(*, organization: str | None, project: str | None) -> AccessReport:
    """Probes `az` for the Azure backend; unset coordinates skip the access
    probes because doctor already reports them as missing settings."""
    report = AccessReport()
    try:
        versions: Any = parse_json(_az(["version", "-o", "json"]), "az")
    except PdlcError as error:
        report.facts.append("az: not available")
        report.errors.append(f"az CLI unavailable: {error}; install it from https://aka.ms/azure-cli")
        return report
    if not isinstance(versions, dict):
        versions = {}
    check_version(report, "az", str(versions.get("azure-cli") or ""), AZ_MIN_VERSION)
    extension = (versions.get("extensions") or {}).get(_EXTENSION)
    if not extension:
        report.facts.append(f"{_EXTENSION} extension: not installed")
        report.errors.append(f"the {_EXTENSION} az extension is not installed; run `az extension add --name {_EXTENSION}`")
        return report
    check_version(report, f"{_EXTENSION} extension", str(extension), AZURE_DEVOPS_MIN_VERSION)
    _report_credentials(report)
    if organization and project:
        organization = organization.rstrip("/")
        if _check_project(report, organization, project):
            _check_boards(report, organization, project)
    return report

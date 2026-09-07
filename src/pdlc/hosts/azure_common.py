"""Shared primitives for the Azure DevOps work-item backend: `az` process
execution and organization/project configuration. No PDLC vocabulary lives
here — see `azure_workitems.py` for the field names and work-item shapes.

Transport is the `az` CLI rather than raw REST on purpose: a bearer token from
`az account get-access-token` is redirected to sign-in on org-scoped endpoints,
so the CLI's own auth path is the only one that works unattended.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from typing import Any, Iterator, Sequence

from pdlc.config import get_config
from pdlc.domain.lifecycle import PdlcError

# `az devops invoke` parses this as a float after stripping `-preview`, so a
# numbered suffix (`7.1-preview.4`) fails outright; the bare form is required.
# The comments resource is preview-only, so plain `7.1` is refused there.
INVOKE_API_VERSION = "7.1-preview"

# The work-item resource, by contrast, rejects the preview suffix.
WIT_API_VERSION = "7.1"

# A JSON Patch document, which is how the work-item REST resource takes writes.
PATCH_MEDIA_TYPE = "application/json-patch+json"


def run_az(args: Sequence[str]) -> str:
    """Runs `az <args>`, raising PdlcError with az's stderr on failure."""
    if shutil.which("az") is None:
        raise PdlcError("required command not found: az")
    result = subprocess.run(["az", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise PdlcError(result.stderr.strip() or f"az {' '.join(args)} failed")
    return result.stdout


def run_az_json(args: Sequence[str]) -> Any:
    """Runs `az <args> -o json` and parses the result.

    An empty WIQL result set prints zero bytes rather than `[]`, so empty
    output is a legitimate "nothing matched" and returns None instead of
    raising a JSON decode error.
    """
    output = run_az([*args, "-o", "json"]).strip()
    return json.loads(output) if output else None


def azure_config() -> tuple[str, str]:
    """The configured organization URL and project name."""
    config = get_config()
    if not config.azure_org or not config.azure_project:
        raise PdlcError(
            "the azure backend needs PDLC_AZURE_ORG and PDLC_AZURE_PROJECT "
            "(or [backend.azure] organization/project in .pdlc/config.toml)"
        )
    return config.azure_org.rstrip("/"), config.azure_project


def org_args() -> list[str]:
    return ["--organization", azure_config()[0]]


def project_args() -> list[str]:
    organization, project = azure_config()
    return ["--organization", organization, "--project", project]


@contextmanager
def _request_file(body: Any) -> Iterator[str]:
    """`az devops invoke` takes a request body only as a file on disk."""
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as handle:
        json.dump(body, handle)
        path = handle.name
    try:
        yield path
    finally:
        os.unlink(path)


def az_invoke(
    area: str,
    resource: str,
    *,
    route_parameters: dict[str, str] | None = None,
    query_parameters: dict[str, str] | None = None,
    api_version: str = INVOKE_API_VERSION,
    http_method: str | None = None,
    media_type: str | None = None,
    body: Any = None,
) -> Any:
    """Reaches a REST resource `az` has no first-class verb for.

    Note the resource-name collision this cannot work around: `wit`/`workItems`
    resolves to the *create* route (`{project}/_apis/wit/workitems/${type}`)
    because both routes share a name and a max version, so an update by id is
    not reachable here — use `az boards work-item update` for that.
    """
    args = ["devops", "invoke", *org_args(), "--area", area, "--resource", resource,
            "--api-version", api_version]
    for flag, values in (("--route-parameters", route_parameters),
                         ("--query-parameters", query_parameters)):
        if values:
            args += [flag, *(f"{key}={value}" for key, value in values.items())]
    if http_method:
        args += ["--http-method", http_method]
    if media_type:
        args += ["--media-type", media_type]
    if body is None:
        return run_az_json(args)
    with _request_file(body) as path:
        return run_az_json([*args, "--in-file", path])

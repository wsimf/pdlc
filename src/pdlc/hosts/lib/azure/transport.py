"""Shared primitives for the Azure DevOps work-item backend: `az` process
execution and organization/project configuration. No PDLC vocabulary lives
here — see `workitems.py` for the field names and work-item shapes.

Transport is the `az` CLI rather than raw REST on purpose: a bearer token from
`az account get-access-token` is redirected to sign-in on org-scoped endpoints,
so the CLI's own auth path is the only one that works unattended.
"""

from __future__ import annotations

import json
import threading
from contextlib import AbstractContextManager, contextmanager
from typing import Any, Iterator, Literal, Sequence

from pdlc.hosts.lib.process import parse_json, run_process
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


# How an `az` call affects the host (see `gh_call_kind`): "read" changes
# nothing, "set" replaces field values outright, "add" is anything a retry could
# duplicate — creation, relation links, comment posts, an unknown call.
_AZ_READS = {("boards", "work-item", "show"), ("boards", "query"), ("account", "show")}
_AZ_SETS = {("boards", "work-item", "update")}


def az_call_kind(args: Sequence[str]) -> Literal["read", "set", "add"]:
    if tuple(args[:2]) == ("devops", "invoke"):
        method = "GET"
        if "--http-method" in args:
            index = list(args).index("--http-method")
            method = args[index + 1].upper() if index + 1 < len(args) else "GET"
        return "read" if method == "GET" else "set" if method in {"PATCH", "PUT"} else "add"
    if tuple(args[:3]) in _AZ_READS or tuple(args[:2]) in _AZ_READS:
        return "read"
    return "set" if tuple(args[:3]) in _AZ_SETS else "add"


# Concurrent `az` processes race on the shared credential/token cache, and a
# loser reports that no login exists. So the first `az` call of this process
# runs alone; once it finishes, pass or fail, the cache is settled and calls run
# concurrently again.
_warm_lock = threading.Lock()
_warmed = threading.Event()


def reset_warm_up() -> None:
    """Make the next `run_az` call run alone again; for tests."""
    _warmed.clear()


def run_az(args: Sequence[str], *, input: str | None = None) -> str:
    if not _warmed.is_set():
        with _warm_lock:
            if not _warmed.is_set():
                try:
                    return _run_az(args, input)
                finally:
                    _warmed.set()
    return _run_az(args, input)


def _run_az(args: Sequence[str], input: str | None) -> str:
    kind = az_call_kind(args)
    return run_process(["az", *args], input=input, idempotent=kind != "add", writes=kind != "read")


def run_az_json(args: Sequence[str]) -> Any:
    """Runs `az <args> -o json` and parses the result.

    An empty WIQL result set prints zero bytes rather than `[]`, so empty
    output is a legitimate "nothing matched" and returns None instead of
    raising a JSON decode error.
    """
    output = run_az([*args, "-o", "json"]).strip()
    return parse_json(output, "az") if output else None


def azure_config() -> tuple[str, str]:
    """The configured organization URL and project name."""
    config = get_config()
    if not config.azure_org or not config.azure_project:
        raise PdlcError(
            "the azure backend needs an organization and project "
            "([backend.azure] organization/project in .pdlc/config.toml)"
        )
    return config.azure_org.rstrip("/"), config.azure_project


def org_args() -> list[str]:
    return ["--organization", azure_config()[0]]


def project_args() -> list[str]:
    organization, project = azure_config()
    return ["--organization", organization, "--project", project]


@contextmanager
def _scratch_file(name: str, text: str, suffix: str) -> Iterator[str]:
    """Write `text` to a scratch file for one `az` call and remove it after."""
    # This transport is also used to create records, before an ID is known.
    from pdlc.internal.scratch import scratch_path, write_scratch

    path = write_scratch(scratch_path("unscoped", name, suffix), text)
    try:
        yield str(path)
    finally:
        path.unlink(missing_ok=True)


def _request_file(body: Any) -> AbstractContextManager[str]:
    """`az devops invoke` takes a request body only as a file on disk."""
    return _scratch_file("azure-request", json.dumps(body), ".json")


def field_file(value: str) -> AbstractContextManager[str]:
    """A file holding one field value, passed to `az` as `name=@<path>`."""
    return _scratch_file("azure-field", value, ".md")


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

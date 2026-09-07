"""Record/replay harness for the Azure DevOps work-item backend.

Every Azure round trip funnels through ``azure_common.run_az`` (``run_az_json``
and ``az_invoke`` both call it), so a single patch point stands in for the live
``az`` CLI. A test registers routes — an argv matcher plus a canned response —
and drives the backend exactly as a command would, without a network or an
``az`` binary.

Responses were shaped from real ``az`` payloads against a live organization;
only the volatile ids and identity blocks are trimmed.
"""

from __future__ import annotations

import json
import os
import threading
import unittest
import unittest.mock
from typing import Any, Callable

import pdlc.hosts.azure_common as azure_common
import pdlc.hosts.workitem_host.azure as workitem_azure

# `workitem_host.azure` bound `run_az` into its own namespace at import time, so
# the patch has to land there as well as on azure_common.
_PATCH_TARGETS = (azure_common, workitem_azure)

Response = Any  # str | dict | list | Exception | Callable[[list[str]], Any]

ORGANIZATION = "https://dev.azure.com/acme"
PROJECT = "delivery"


class _Route:
    def __init__(self, match: Callable[[list[str]], bool], response: Response):
        self.match = match
        self.response = response
        self.calls: list[list[str]] = []


class FakeAz:
    """Routes ``run_az(args)`` calls to registered responses."""

    def __init__(self) -> None:
        self._routes: list[_Route] = []
        self.calls: list[list[str]] = []
        # Request bodies, aligned with `calls`. `az devops invoke` takes a body
        # only as a file on disk, and the caller deletes it once the call
        # returns, so it has to be read here rather than after the fact.
        self.bodies: list[Any] = []
        # The Azure backend reads task comments concurrently, so recording has
        # to be atomic. Call *order* is still nondeterministic under
        # concurrency — assert on call contents, not on `calls[0]`.
        self._lock = threading.Lock()

    # --- registration ---

    def route(self, match: Callable[[list[str]], bool], response: Response) -> "FakeAz":
        self._routes.append(_Route(match, response))
        return self

    def az(self, *prefix: str, response: Response) -> "FakeAz":
        """Match an ``az`` invocation by its leading argv tokens."""
        return self.route(lambda args: args[: len(prefix)] == list(prefix), response)

    def wiql(self, contains: str, response: Response) -> "FakeAz":
        """Match an ``az boards query`` whose WIQL text contains ``contains``."""

        def _match(args: list[str]) -> bool:
            return args[:2] == ["boards", "query"] and any(contains in arg for arg in args)

        return self.route(_match, response)

    def invoke(self, area: str, resource: str, response: Response) -> "FakeAz":
        def _match(args: list[str]) -> bool:
            return args[:2] == ["devops", "invoke"] and area in args and resource in args

        return self.route(_match, response)

    # --- execution ---

    def __call__(self, args) -> str:
        args = list(args)
        with self._lock:
            self.calls.append(args)
            self.bodies.append(self._read_body(args))
            for route in self._routes:
                if route.match(args):
                    route.calls.append(args)
                    response = route.response
                    break
            else:
                raise AssertionError(f"no FakeAz route for: az {' '.join(args)}")
        return self._render(response, args)

    @staticmethod
    def _read_body(args: list[str]) -> Any:
        if "--in-file" not in args:
            return None
        with open(args[args.index("--in-file") + 1]) as handle:
            return json.load(handle)

    @staticmethod
    def _render(response: Response, args: list[str]) -> str:
        if callable(response) and not isinstance(response, type):
            response = response(args)
        if isinstance(response, BaseException):
            raise response
        if isinstance(response, str):
            return response
        return json.dumps(response)

    # --- assertions ---

    def calls_matching(self, *prefix: str) -> list[list[str]]:
        """Every call whose leading argv tokens match, for assertions that must
        not depend on the order concurrent reads happen to complete in."""
        return [args for args in self.calls if args[: len(prefix)] == list(prefix)]

    def body_of(self, *prefix: str) -> Any:
        """The parsed request body of the first call matching ``prefix``."""
        for args, body in zip(self.calls, self.bodies):
            if args[: len(prefix)] == list(prefix) and body is not None:
                return body
        raise AssertionError(f"no az call matched {' '.join(prefix)!r} with a body")

    def fields_written(self, *prefix: str) -> dict[str, str]:
        """The ``-f name=value`` pairs of the first matching call, for asserting
        what an update was asked to write."""
        for args in self.calls:
            if args[: len(prefix)] != list(prefix) or "-f" not in args:
                continue
            pairs = {}
            for value in args[args.index("-f") + 1:]:
                if value.startswith("-"):
                    break
                name, _, text = value.partition("=")
                pairs[name] = text
            return pairs
        raise AssertionError(f"no az call matched {' '.join(prefix)!r} with fields")


def work_item(item_id: int, **fields: Any) -> dict:
    """An ``az boards work-item show`` payload, trimmed to the fields PDLC reads."""
    return {
        "id": item_id,
        "rev": 1,
        "relations": None,
        "fields": {"System.Id": item_id, **fields},
        "url": f"{ORGANIZATION}/_apis/wit/workItems/{item_id}",
    }


class AzureHostTest(unittest.TestCase):
    """Base class: installs a FakeAz and sets Azure backend configuration."""

    def setUp(self) -> None:
        self.az = FakeAz()
        for module in _PATCH_TARGETS:
            patcher = unittest.mock.patch.object(module, "run_az", self.az)
            patcher.start()
            self.addCleanup(patcher.stop)

        self._saved_env: dict[str, str | None] = {}
        for key, value in {
            "PDLC_BACKEND": "azure",
            "PDLC_AZURE_ORG": ORGANIZATION,
            "PDLC_AZURE_PROJECT": PROJECT,
            "PDLC_AZURE_RECORD_TYPE": None,
            "PDLC_AZURE_CLOSED_STATE": None,
        }.items():
            self._saved_env[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.addCleanup(self._restore_env)

    def _restore_env(self) -> None:
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


mock = unittest.mock

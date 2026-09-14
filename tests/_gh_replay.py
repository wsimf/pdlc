"""Record/replay harness for the GitHub work-item and code hosts.

Every GitHub round trip in ``pdlc.hosts`` funnels through
``github_common.run_gh`` (``run_gh_json`` and ``run_graphql`` both call it), so a
single patch point stands in for the live ``gh`` CLI. A test registers routes —
an argv matcher plus a canned response — and drives the host modules exactly as
a command would, without a network or a ``gh`` binary.

Responses were shaped from real ``gh``/GraphQL payloads (see the module
docstrings in ``src/pdlc/hosts``); only the volatile ids and text are trimmed.
"""

from __future__ import annotations

import json
import os
import re
import unittest
import unittest.mock
from typing import Any, Callable

from pdlc.config import Config, install_config, reset_config, set_config
import pdlc.hosts.lib.github.transport as github_common
import pdlc.hosts.lib.github.issues as github_issues
import pdlc.hosts.lib.github.project as github_project
import pdlc.hosts.lib.github.code_host as code_host_github
import pdlc.hosts.lib.github.workitem_backend as workitem_github

# Modules that bound ``run_gh`` into their own namespace at import time and so
# need the patch applied there too, not just on github_common.
_PATCH_TARGETS = (github_common, github_issues, workitem_github, code_host_github)

Response = Any  # str | dict | list | Exception | Callable[[list[str], str | None], Any]


class _Route:
    def __init__(self, match: Callable[[list[str], str | None], bool], response: Response):
        self.match = match
        self.response = response
        self.calls: list[tuple[list[str], str | None]] = []


class FakeGh:
    """Routes ``run_gh(args, input=...)`` calls to registered responses."""

    def __init__(self) -> None:
        self._routes: list[_Route] = []
        self.calls: list[tuple[list[str], str | None]] = []

    # --- registration ---

    def route(self, match: Callable[[list[str], str | None], bool], response: Response) -> "FakeGh":
        self._routes.append(_Route(match, response))
        return self

    def gh(self, *prefix: str, response: Response) -> "FakeGh":
        """Match a plain ``gh`` invocation by the leading argv tokens."""
        return self.route(lambda args, _input: args[: len(prefix)] == list(prefix), response)

    def graphql(self, contains: str, response: Response) -> "FakeGh":
        """Match a ``gh api graphql`` call whose query text contains ``contains``."""

        def _match(args: list[str], _input: str | None) -> bool:
            return args[:2] == ["api", "graphql"] and any(contains in arg for arg in args)

        return self.route(_match, response)

    def api(self, path_fragment: str, response: Response) -> "FakeGh":
        """Match a REST ``gh api`` call (not graphql) by a path fragment."""

        def _match(args: list[str], _input: str | None) -> bool:
            return args[0] == "api" and args[1] != "graphql" and any(path_fragment in arg for arg in args)

        return self.route(_match, response)

    # --- execution ---

    def __call__(self, args, *, input: str | None = None) -> str:
        args = list(args)
        self.calls.append((args, input))
        for route in self._routes:
            if route.match(args, input):
                route.calls.append((args, input))
                return self._render(route.response, args, input)
        raise AssertionError(f"no FakeGh route for: gh {' '.join(args)}")

    @staticmethod
    def _render(response: Response, args: list[str], input: str | None) -> str:
        if callable(response) and not isinstance(response, type):
            response = response(args, input)
        if isinstance(response, BaseException):
            raise response
        if isinstance(response, str):
            return response
        return json.dumps(response)

    # --- assertions ---

    def graphql_variables(self, contains: str) -> dict[str, str]:
        """The ``-f key=value`` / ``-F key=value`` pairs of the first matching
        graphql call, for asserting what a mutation was asked to write."""
        for args, _input in self.calls:
            if args[:2] == ["api", "graphql"] and any(contains in arg for arg in args):
                pairs = {}
                for flag, value in zip(args, args[1:]):
                    if flag in ("-f", "-F") and "=" in value and not value.startswith("query="):
                        key, _, val = value.partition("=")
                        pairs[key] = val
                return pairs
        raise AssertionError(f"no graphql call matched {contains!r}")


def graphql_data(payload: dict) -> dict:
    """Wrap a GraphQL ``data`` body the way ``gh api graphql`` returns it."""
    return {"data": payload}


_PR_ALIAS = re.compile(r"(pr\d+): pullRequest\(number: (\d+)\)")


def pull_request_node(number: int, *, contexts: list[dict] | None = None, has_next_page: bool = False, **fields: Any) -> dict:
    """One aliased ``pullRequest`` node as the batched code-host query returns
    it; ``contexts=None`` is a head commit with no check rollup at all."""
    rollup = None if contexts is None else {"contexts": {"pageInfo": {"hasNextPage": has_next_page}, "nodes": contexts}}
    return {
        "number": number, "title": f"PR {number}", "url": f"u{number}", "state": "OPEN",
        "isDraft": False, "headRefName": f"branch-{number}", "headRefOid": f"sha{number}", "mergedAt": None,
        "commits": {"nodes": [{"commit": {"statusCheckRollup": rollup}}]},
        **fields,
    }


def pull_requests_graphql(node_for: Callable[[int], dict | None]) -> Callable[[list[str], str | None], dict]:
    """A route response for the batched ``pullRequest`` query: each alias in
    the query text is answered by ``node_for(number)`` (None for a miss)."""

    def respond(args: list[str], _input: str | None) -> dict:
        query = next(arg for arg in args if arg.startswith("query="))
        return graphql_data({"repository": {alias: node_for(int(number)) for alias, number in _PR_ALIAS.findall(query)}})

    return respond


class GitHubHostTest(unittest.TestCase):
    """Base class: installs a FakeGh, sets GitHub config, clears host caches."""

    REPOSITORY = "wsimf/pdlc"
    PROJECT_OWNER = "wsimf"
    PROJECT_NUMBER = "7"

    def setUp(self) -> None:
        self.gh = FakeGh()
        for module in _PATCH_TARGETS:
            patcher = unittest.mock.patch.object(module, "run_gh", self.gh)
            patcher.start()
            self.addCleanup(patcher.stop)

        self._saved_repository = os.environ.pop("PDLC_REPOSITORY", None)
        install_config(Config(
            backend="github",
            repository=self.REPOSITORY,
            project_owner=self.PROJECT_OWNER,
            project_number=self.PROJECT_NUMBER,
        ))
        self.addCleanup(self._restore_env)
        self._clear_caches()
        self.addCleanup(self._clear_caches)

    def configure(self, **fields: object) -> None:
        set_config(**fields)

    def _restore_env(self) -> None:
        reset_config()
        if self._saved_repository is not None:
            os.environ["PDLC_REPOSITORY"] = self._saved_repository

    def _clear_caches(self) -> None:
        github_project.project_fields.cache_clear()
        github_project._project_id.cache_clear()

    # --- shared fixtures ---

    def stub_project_metadata(self) -> None:
        """Register the field-list and project-view calls every mutation needs."""
        self.gh.gh("project", "view", response={"id": "PVT_project"})
        self.gh.gh(
            "project", "field-list",
            response={
                "fields": [
                    {"id": "F_status", "name": "Status", "options": [
                        {"id": "opt-product", "name": "Product"},
                        {"id": "opt-impl", "name": "Implementation"},
                        {"id": "opt-testing", "name": "Testing"},
                    ]},
                    {"id": "F_gate", "name": "Gate State", "options": [
                        {"id": "opt-pending", "name": "Pending"},
                        {"id": "opt-review", "name": "Review Required"},
                        {"id": "opt-approval", "name": "Approval Required"},
                    ]},
                    {"id": "F_lifecycle", "name": "Lifecycle", "options": [
                        {"id": "opt-planning", "name": "Planning"},
                        {"id": "opt-delivery", "name": "Delivery"},
                    ]},
                    {"id": "F_slug", "name": "Slug"},
                    {"id": "F_skip", "name": "Skipped States"},
                ]
            },
        )


# Re-export for callers that only import this module.
mock = unittest.mock

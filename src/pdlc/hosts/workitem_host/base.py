"""The work-item host port: everything about a PDLC record's own state — its
body, its Status/Gate State/Lifecycle/Slug/Skipped States, its delivery tasks,
and its evidence comments. Pull requests, CI, and code live behind `code_host`,
not here.

The contract is plain dicts, matching what the `pdlc-*` scripts already read,
so a backend swap does not ripple into call sites. All local-file, stdin, and
`PDLC-<MARKER>` handling happens in the `workitem` facade before a backend is
called — a backend receives and returns plain strings and dicts only.

Dict shapes
-----------
work item:  {id, content: {number, title, url}, issueBody,
             "Status", "Gate State", "Lifecycle", "Skipped States", "Slug",
             comments?}                # comments included only when free to
comment:    {body, createdAt, url, author: {login}}
task:       {number, title, url, state ("OPEN"|"CLOSED"), body, comments: [str],
             taskId}                   # taskId is the WORK-N-TASK-NNN id or None
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class WorkItemBackend(ABC):
    # Capabilities a stage can check instead of assuming. "subissue_graph" —
    # real parent/child task links; "queue_scan" — all_items() is meaningful.
    capabilities: set[str] = set()

    # --- resolution ---

    @abstractmethod
    def resolve(self, ref: str) -> dict:
        """The work item for `ref` (its human-facing number/slug). Raises on an
        unknown or ambiguous ref — never guesses."""

    @abstractmethod
    def all_items(self) -> dict:
        """{"items": [work item, ...]} for the queue scan. May raise
        NotImplementedError on a backend without a queue."""

    # --- state fields ---

    @abstractmethod
    def set_state(self, item_id: str, status: str, gate: str, lifecycle: str) -> None: ...

    @abstractmethod
    def set_gate(self, item_id: str, gate: str) -> None:
        """Move only the Gate State (used to record a review outcome)."""

    @abstractmethod
    def set_slug(self, item_id: str, value: str) -> None: ...

    @abstractmethod
    def set_skipped_states(self, item_id: str, value: str) -> None: ...

    # --- body ---

    @abstractmethod
    def write_body(self, ref: str, body: str) -> None:
        """Replace the whole work-item body. Section splicing is done in the
        facade; the backend only persists the result."""

    # --- comments ---

    @abstractmethod
    def comments(self, ref: str) -> list[dict]:
        """Every evidence/discussion comment, oldest first."""

    @abstractmethod
    def post_comment(self, ref: str, body: str) -> str:
        """Append one comment verbatim — the facade has already composed any
        marker prefix. Returns a reference to the created comment."""

    @abstractmethod
    def post_blocker(self, ref: str, body: str) -> str:
        """Record a blocking review decision the driver must resolve before the
        record can move. The `Decision Required` gate is the machine-readable
        signal; this is the human-readable one. A backend may surface it more
        prominently than an ordinary comment (pinned, labelled, its own column)."""

    # --- delivery tasks ---

    @abstractmethod
    def tasks(self, ref: str) -> list[dict]:
        """The record's delivery tasks (raw; the facade classifies them)."""

    @abstractmethod
    def tasks_by_number(self, numbers: list[str]) -> list[dict]:
        """Specific tasks by their own ref, raw and in the given order."""

    @abstractmethod
    def upsert_tasks(self, parent: str, tasks: list[dict], existing: list[dict]) -> list[dict]:
        """Create or update every task by stable TASK-NNN identity, link new
        ones to the parent, and return one result dict per task:
        {action, taskId, number, title, url}."""

    @abstractmethod
    def close_task(self, task_ref: str) -> None: ...

    @abstractmethod
    def write_task_body(self, task_ref: str, body: str) -> None:
        """Replace a delivery task's whole body — used to persist its
        machine-owned metadata block (the facade composes the block)."""

    # --- creation ---

    @abstractmethod
    def create(self, title: str, body: str, slug: str) -> dict:
        """Create a new work item and register it. Returns {id, number, url}."""

    # --- identity / linking ---

    @abstractmethod
    def current_actor(self) -> str:
        """Who is acting now — for the human-approval audit trail."""

    @abstractmethod
    def ref_label(self) -> str:
        """A short filesystem-safe name for the backing store (repo name, board
        name, …) — used to name inspector scratch files."""

# Stage ownership

| Stage | Owning skill | Required artifact |
|---|---|---|
| Product | `pdlc-write` | Parent Product section: problem, requirements, constraints, decisions, open questions. |
| UI | `pdlc-tasks` | Parent UI section: applicability, accessibility, states, `UJ-*` journeys. |
| Tasks | `pdlc-tasks` | Stable delivery tasks with dependencies, acceptance criteria, risk, HITL/AFK. |
| Technical Plan | `pdlc-plan` | Task-level source ownership, interfaces, sequencing, risks, validation plan. |
| Implementation | `pdlc-implement` | Production/task PRs and per-task implementation notes, one task per dispatch with a `task`-depth review before push, carried through the requested scope. |
| Testing | `pdlc-test` | Requirement-to-source traceability, acceptance coverage, CI evidence. |
| Verification | `pdlc-verify` | Claims, runtime behaviour, UX journeys, review findings, completion recommendation. Sets the gate from its `--recommendation`: `Approval Required` (through `CI Pending` while the registered PR stack's CI settles), `Changes Required`, or `Decision Required` (a finding routed to the driver, cleared by `pdlc post decision`). |
| `Implementation`, `Testing`, or `Verification` at `Decision Required` | `pdlc post decision` (driver) | Land a manifest of per-decision outcomes — answered or deferred to its own work item — and return to `Changes Required`. |
| `Implementation` or `Testing` at `Review Required` | `pdlc-review` | Independent read-only findings; records `Changes Required`, `Decision Required`, or `Approval Required`. A clean review lands `CI Pending`. |
| `Product`, `UI`, `Tasks`, or `Technical Plan` at `Review Required` | the stage's owning skill (`pdlc-write` interactively for Product) | The artifact was published without its local review; the owning skill runs that review and re-lands it to `Approval Required`. |
| `Implementation`, `Testing`, or `Verification` at `CI Pending` | `pdlc post ci` (loop or driver) | Reconcile the registered PR stack's CI: green → `Approval Required`, red → `Changes Required`; with no registered PR on `Implementation` or `Testing` it refuses and the gate holds. Mechanical, no reviewer. |

A stage owner prepares only its own section; the commands re-read the record and update it without overwriting approved upstream work. `UI not required` is still an artifact — it goes through review and human approval like any other.

Every evidence comment opens with a marker identifying its stage, and covers actor, timestamp, scope, work item/PR links, result, and unresolved risk. **The commands stamp the marker** — every evidence file you prepare holds the body only, and one that already carries a marker is refused. The vocabulary lives in `pdlc guide contract`; you never need to type it.

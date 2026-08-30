# Breakdown-reviewer dispatch prompt

`pdlc-tasks` Step 5 fills the placeholders below and spawns `pdlc-tasks-reviewer`
with the result, before the UI fragment or task breakdown is landed. Read-only:
it returns findings and a verdict, and changes nothing.

---

```md
Review the supplied local artifact before it is written to the work item store.

## Parent work item

<complete parent work item body, including every `FR-*` / `C-*` / `UJ-*` identifier>

## Artifact under review

<for a Tasks breakdown: the manifest, then every task body in full>
<for a UI fragment: the fragment file in full>

## Prior findings (re-review only)

`<the previous pass's findings, so each can be confirmed addressed — or "none,
first review">`

## What to check

- Journey and requirement coverage: every task covers at least one FR or C;
  every UI task covers a `UJ-*`; every `UJ-*` has a UI task; no task claims a
  requirement the parent does not declare.
- Dependency validity: dependencies exist, the graph is acyclic, ordering is
  sound.
- Artifact quality: scope, non-goals, acceptance criteria, risk, and HITL/AFK
  classification are concrete and testable; no empty detail block.
- No delivery task carries a `## Technical Plan` or `## Implementation` comment — the
  Tasks stage precedes both.
- Nothing contradicts approved Product or UI intent.

## Report back

Findings with evidence, coverage boundaries, and exactly one of `Clean` or
`Changes`.
```

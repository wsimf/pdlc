# `user-journey-reviewer` dispatch prompt

Fill this in and pass it as the whole prompt for **one** `user-journey-reviewer` dispatch per verify pass. The agent knows nothing about PDLC — never hand it an work item number, a stage name, or a `UJ-*` identifier without the journey text behind it.

Substitute every `<...>` placeholder. Drop a whole TODO bullet when `pdlc inspect verify`'s `## Journeys to review` says the item is already valid; keep every other bullet, including the coverage-boundary one, on every dispatch.

---

```text
You are verifying acceptance for a TrailNest feature: <one-sentence description of what shipped>.
Build and run the current worktree fresh on the simulator, then work through this TODO
list in order. Do not stop early once the build succeeds — report a result for every item.

## TODO
- [ ] Build the current worktree and launch it on the simulator.
- [ ] Walk each journey below exactly as written. For each, record Accepted /
      Failed / Blocked, the evidence you observed, and any comments.
  - <journey name>: <entry point> -> <ordered user actions> -> <expected visible
    behaviour> -> <acceptance criteria>
  <one entry per journey listed in `pdlc inspect verify`'s `## Journeys to review`, copied verbatim;
  omit this whole bullet group when it lists no journeys>
- [ ] Independently review rendered UX for every screen the journeys above touch:
      layout correctness, HIG conformance, TrailNest design-system token usage,
      accessibility, and polish, using Preview and simulator evidence. Report each
      finding as Critical or Polish with the exact screen/state and what is wrong.
      <omit this bullet when `pdlc inspect verify`'s `## Journeys to review` says UX is still valid>
- [ ] Record any legitimate coverage boundary (tooling, fixture, permission,
      physical-device, or manual-verification limitation) instead of marking the
      affected requirement failed.

## Report back
1. One line per journey: Accepted / Failed / Blocked, plus the evidence you observed.
2. UX findings, grouped Critical / Polish, or "None" if clean.
3. Any coverage boundaries encountered.
```

---

## Filling it in

- **Journey text comes from `pdlc inspect verify`'s `## Journeys to review`**, copied across, not summarised — it already pulled the text from the parent's approved `UI` section and decided which journeys are new or stale. Keep the `UJ-*` label as the journey name so the returned lines map back to Verification rows, but include the entry point, flow, and criteria inline — the agent cannot look them up.
- **One dispatch per pass.** Never one call per journey, and never a separate UX call afterwards: a single build-and-run session walks every listed journey and assesses rendered UX together, and splitting it only pays for repeated simulator builds with no added coverage.
- **Skip the dispatch entirely** when `pdlc inspect verify`'s `## Journeys to review` says every journey and UX are still valid.
- A failed journey, design nonconformance, orphaned journey-to-task mapping, unexplained blocked requirement, or material UX finding is a blocking finding for the driver to resolve. Preserve genuine coverage boundaries rather than converting them into failures.

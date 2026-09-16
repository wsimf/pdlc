# `user-journey-reviewer` dispatch prompt

Fill this in and pass it as the whole prompt for **one** `user-journey-reviewer` dispatch per verify pass. The agent knows nothing about PDLC — never hand it an work item number, a stage name, or a `UJ-*` identifier without the journey text behind it.

Substitute every `<...>` placeholder. Drop a whole TODO bullet when `pdlc inspect verify`'s `## Journeys to review` says the item is already valid; keep every other bullet, including the coverage-boundary one, on every dispatch.

---

```text
<the line from `pdlc inspect capability build-run`>

You are verifying acceptance for a feature: <one-sentence description of what shipped>.
Build and run the current worktree fresh, then work through this TODO
list in order. Do not stop early once the build succeeds — report a result for every item.

## Execution boundary

You are being invoked as a leaf worker for this one verification pass.
Do not invoke any `pdlc-*` skill; invoke only the build-run capability named in the line above.
Do not re-run the calling skill or rediscover the lifecycle stage.
Do not spawn, dispatch, or ask another agent to do this work.
Walk the TODO below directly and return one report to the calling `pdlc-verify` skill.

## TODO
- [ ] Build and launch the current worktree.
- [ ] Walk each journey below exactly as written. For each, record Accepted /
      Failed / Blocked, the evidence you observed, and any comments.
  - <journey name>: <entry point> -> <ordered user actions> -> <expected visible
    behaviour> -> <acceptance criteria>
  <one entry per journey listed in `pdlc inspect verify`'s `## Journeys to review`, copied verbatim;
  omit this whole bullet group when it lists no journeys>
- [ ] Independently review rendered UX for every screen the journeys above touch:
      layout correctness, conformance to the platform's interface guidelines,
      the project's design-system token usage, accessibility, and polish, using
      the running app as evidence. Report each finding as Critical or Polish with
      the exact screen/state and what is wrong.
      <omit this bullet when `pdlc inspect verify`'s `## Journeys to review` says UX is carried forward>
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

- **Journey text comes from `pdlc inspect verify`'s `## Journeys to review`**, copied across, not summarised — it already pulled the text from the parent's approved `UI` section and decided which journeys need a fresh review. Keep the `UJ-*` label as the journey name so the returned lines map back to Verification rows, but include the entry point, flow, and criteria inline — the agent cannot look them up.
- **One dispatch per pass.** Never one call per journey, and never a separate UX call afterwards: a single build-and-run session walks every listed journey and assesses rendered UX together, and splitting it only pays for repeated app builds with no added coverage.
- **Skip the dispatch entirely** when `pdlc inspect verify`'s `## Journeys to review` says every journey and UX are carried forward.
- A failed journey, design nonconformance, orphaned journey-to-task mapping, unexplained blocked requirement, or material UX finding is a blocking finding for the driver to resolve. Preserve genuine coverage boundaries rather than converting them into failures.

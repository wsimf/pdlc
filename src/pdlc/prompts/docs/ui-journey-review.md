{{BUILD_RUN_LINE}}

You are verifying acceptance for a feature: {{DESCRIPTION}}.
Build and run the current worktree fresh, then work through this TODO
list in order. Do not stop early once the build succeeds — report a result for every item.

{{INCLUDE:shared/execution-boundary.md}}
Invoke only the build-run capability named in the line above, if any.
Walk the TODO below directly and return one report to the calling skill.

## TODO
- [ ] Build and launch the current worktree.
{{#IF HAS_JOURNEYS}}
- [ ] Walk each journey below exactly as written. For each, record Accepted /
      Failed / Blocked, the evidence you observed, and any comments.

{{#EACH JOURNEYS}}
{{TEXT}}

{{/EACH}}
{{/IF}}
{{#IF UX_STALE}}
- [ ] Independently review rendered UX for every screen the journeys above touch:
      layout correctness, conformance to the platform's interface guidelines,
      the project's design-system token usage, accessibility, and polish, using
      the running app as evidence. Report each finding as Critical or Polish with
      the exact screen/state and what is wrong.
{{/IF}}
- [ ] Record any legitimate coverage boundary (tooling, fixture, permission,
      physical-device, or manual-verification limitation) instead of marking the
      affected requirement failed.

## Report back
1. One line per journey: Accepted / Failed / Blocked, plus the evidence you observed.
2. UX findings, grouped Critical / Polish, or "None" if clean.
3. Any coverage boundaries encountered.

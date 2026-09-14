# UI-planner dispatch prompt

`pdlc-tasks` Author fills the placeholders below and spawns `pdlc-ui-planner`
when `Status = UI`. This is also the dispatch you return to in Review with
reviewer findings — keep it addressable.

---

```md
<the line from `pdlc inspect capability ux-design`>

Author the `UI` section for this PDLC record and return it as one fragment file.

## Execution boundary

You are being invoked as the leaf UI planner.
Do not invoke any `pdlc-*` skill; invoke only the UX-design skill named in the line above, if any.
Do not re-run the calling skill or rediscover the lifecycle stage.
Do not spawn, dispatch, or ask another agent to do this work.
Author the fragment directly and return it to the calling `pdlc-tasks` skill.

## Parent work item

`<number>` — full body:

<complete parent work item body>

## State

- `Status`: UI — `Gate State`: `<Pending | Stale>`.
- Why it is `Stale` (if it is): `<reason, or "n/a — first pass">`.
- Existing task tree, if any: `<...>`.

## Driver follow-up

`<verbatim, or "none">`

## What to return

One fragment file: the `UI` section — information architecture, interaction
states, loading / error / empty states, accessibility, responsive behaviour, and
every named `UJ-*` journey.

UI applicability is always explicit: a feature with no user-facing surface still
says so, in a form that can be reviewed and approved like any other artifact.
```

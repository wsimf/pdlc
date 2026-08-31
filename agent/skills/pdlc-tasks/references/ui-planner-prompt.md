# UI-planner dispatch prompt

`pdlc-tasks` Step 3 fills the placeholders below and spawns `pdlc-ui-planner`
when `Status = UI`. This is also the dispatch you return to in Step 5 with
reviewer findings — keep it addressable.

---

```md
<the line from `pdlc inspect capability ux-design`>

Author the `UI` section for this PDLC record and return it as one fragment file.

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

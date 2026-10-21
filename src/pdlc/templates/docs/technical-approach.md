# Technical approach

Write this as the `### Technical approach` subsection, the last subsection of the Product draft's `## Product` section, for a reader who will break the work into tasks and plan each one. It records whether the product as specified can be built on the current codebase and how, at the level of modules, boundaries, and data flow. Nest its parts one level below the subsection, as `####` headings:

```md
### Feasibility

Verdict: <Feasible | Feasible with caveats | Not feasible>

- <The evidence from current source behind the verdict, and each caveat or blocker with the requirement or constraint it affects.>

### Approach

- <How the feature fits the current codebase: the modules and ownership boundaries it touches, where new behaviour lives, and how data flows between them. Name modules, packages, and types; leave files, signatures, and edits to planning.>

### Risks & unknowns

- <Each risk or unknown, whether the spike settled it, and what changes if it goes wrong. Write `None` only when the spike found none.>

### Verification

- <How the finished feature will be shown to work: the kinds of tests, runtime or visual checks, and any measurement a quality requirement needs.>

### Migration & dependencies <!-- optional -->

- <Data or contract migrations, compatibility concerns, and external libraries, services, or APIs the approach relies on.>

### Slicing <!-- optional -->

- <Natural seams along which the work splits into independently deliverable tasks.>
```

`Feasibility`, `Approach`, `Risks & unknowns`, and `Verification` are required and must have real content. Omit an optional heading entirely when it adds nothing; never leave a placeholder. The verdict is one of the three values exactly; a `Not feasible` draft never lands. Keep the whole subsection to about a screen: deeper spike notes belong in the evidence body.

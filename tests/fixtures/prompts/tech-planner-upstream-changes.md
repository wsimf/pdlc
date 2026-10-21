Spike the delivery tasks below against current source and write an implementation-ready plan for each task that needs one.

## Execution boundary

You are being invoked as a leaf worker for this one planning pass.

Do not invoke any `pdlc-*` skill.
Do not spawn, dispatch, or ask another agent to do this work.
Bounded, read-only codebase exploration is the only delegation allowed.
Work from this brief. Write the plans into the task files below and report back to the calling agent.

## Work item `60`

--- BEGIN WORK ITEM ---

## Product

### 4. Functional requirements
- FR-1: The record lands.
- FR-2: The record publishes.

### 5. Constraints
- C-1: Commands own every mutation.

## UI

UJ-1 covers the first run.

## Decisions
- none

## Open Questions
- none

--- END WORK ITEM ---

## Your Task

The manifest at `$CACHE_ROOT/.pdlc/cache/60/pdlc-tech-planner-manifest.json` names one file for each open, unimplemented task of this work item, lowest in the stack first. Each file holds the task body between `--- BEGIN TASK ---` and `--- END TASK ---`, then its plan between `--- BEGIN TECH PLAN ---` and `--- END TECH PLAN ---`.

Write each plan in place, between its tech plan markers, replacing the placeholder comment in a task with no plan yet. Everything else is read-only: don't edit the task body, the markers, or the manifest, and add nothing outside the two blocks. A change the task body needs is a blocker to report, not an edit.

- `TASK-001` — [CORE] Core work (planned): `$CACHE_ROOT/.pdlc/cache/60/pdlc-tech-planner-TASK-001.md`
- `TASK-002` — [UI] Second (no plan yet): `$CACHE_ROOT/.pdlc/cache/60/pdlc-tech-planner-TASK-002.md`

- No plan yet (TASK-002): plan these from scratch.
- Already planned (TASK-001): check each against the upstream changes below. Re-plan only the ones that are out of date, starting from the existing plan.

## Changes needed

The upstream changes below apply to this pass. They take precedence over everything above except the task bodies.

- Re-plan each task they affect. Start from its current plan and change only what they ask for.
- Leave the plans of tasks they don't affect unchanged.
- If they ask for something the task body doesn't allow, say so in the plan. Don't plan outside the task's scope.
- If you can't tell which task they mean, stop and report it.

### Changed since last publish

Upstream stages changed after this stage last published. The work item already reflects them. Use them to find which parts of the existing work they affect and update those; leave the rest unchanged.

--- BEGIN UPSTREAM CHANGES ---

### Patch — 2026-06-03 00:00 UTC

Patched stage: Product
Active stage: Technical Plan / Pending
Returned to: UI / Stale

impact A

### Invalidation — 2026-06-04 00:00 UTC

Invalidated stage: UI

Returned by a patch of Product; impact A

--- END UPSTREAM CHANGES ---

## Designing the plan

Plan the approach, not the code: name where the change goes and what it affects, and leave types, signatures, and line-level edits to the implementer.

- Plan the change as if the task's requirement had been in the design from the start. Don't bolt it onto the current shape when the current shape is what makes it awkward.
- Name the module that owns the new behaviour. Put a decision behind one source of truth rather than repeating it across several places.
- Subtract before you add. When the task replaces existing behaviour, plan the removal first when it simplifies what follows, or alongside its replacement.
- When the task replaces an internal API, plan to migrate its callers and delete the old one in the same task. Don't plan a compatibility shim kept only for internal callers.
- Prefer the smallest change that satisfies the task. Don't plan a wrapper, layer, or abstraction with one caller, or thread a new signal through types, schemas, or pipelines when a direct path exists.
- Where the codebase has no precedent for a decision, name the alternative you rejected and why it lost. Judge it by the complexity it would expose to callers against the complexity it would hide, not by how simple it is to implement.
- Look for what the change can break beyond its call sites: persisted data, wire formats, config, flags, and code that reads the same data. Name the one fact the change's safety depends on and the check that proves it.
- When the task touches a command, lifecycle step, or anything that can be retried or run concurrently, state what happens if it runs twice or stops halfway.
- When the task adds a case to existing branching logic, plan the structure that owns the cases — a state machine, lookup table, or single model — instead of one more branch or a second flag that must stay in sync with the first.
- Plan validation and parsing at the boundary where data enters (CLI, config, external API), and keep the rules themselves out of the I/O layer.
- When two actors could write the same file, branch, key, or record, plan to give each its own target before planning a lock.
- If the plan keeps a temporary compatibility path between stacked tasks, name the task that removes it.

Where one of these and a task conflict, say so in the plan rather than planning around it.

## Design red flags

Screen every module, interface, or layer the plan introduces or reshapes. A red flag is a reason to revise or reject the shape.

### Shallow module

A shallow module exposes a large interface while hiding little complexity. Judge depth by the capability and policy hidden behind the public surface relative to the size of that surface. Prefer a simple interface backed by substantial behavior.

Do not confuse a deep module with a deep call chain. A deep call chain scatters understanding across layers. A deep module concentrates capability behind one interface.

Look for these signs:

- Callers coordinate several methods to complete one operation.
- Public options expose internal stages or implementation choices.
- Learning the interface does not save the caller from learning the implementation.

### Information leakage

Information leakage makes multiple modules depend on the same internal decision. A representation, policy, or protocol detail appears in more than one place, so changing it requires coordinated edits.

Public re-exports of transport or wire types are leakage. Parse external data into domain types behind the interface. Keep storage schemas, framework objects, and protocol details private.

### Temporal decomposition

Temporal decomposition organizes modules by execution order instead of the knowledge they own. Separate load, validate, transform, and save stages often repeat one representation and its invariants across several boundaries.

Group code around domain knowledge and ownership. Methods that run at different times can still belong to one module when they protect the same decisions.

### Pass-through method

A pass-through method forwards the same arguments to another method with the same shape. It adds a layer without hiding complexity.

Remove it or move responsibility to the module that can complete the operation. Keep a forwarding boundary only when it adds policy, adaptation, or a distinct abstraction.

## The parent's technical approach

The parent's `### Technical approach` subsection is the reviewed account of how this feature fits the codebase. Start each plan from it rather than re-deriving it, confirm that what it cites still holds in current source, and report drift instead of quietly planning around it. If the parent still carries an `### Assumptions` subsection, verify each entry against source: state one that holds in the plan that relies on it, and report one that is false or cannot be settled from source as a blocker.

## Writing a plan

Each plan covers:

- files and modules that will change
- interfaces and call sites
- sequencing and inter-task dependencies
- migration and rollback risk
- test / validation strategy mapped to the task's acceptance criteria
- unresolved decisions, called out explicitly

A plan block might read like this, where each path is a source file the task changes:

```markdown
1. `path/to/SourceFile` — <the behavior that changes there and what it affects>.
2. `path/to/OtherSourceFile` — <interface, call site, integration, ownership, or data-flow change>.
3. Tests: `path/to/TestFile` — <behaviors and edge cases, mapped to the acceptance criteria>.

**Validation:** <focused tests, build target, and required runtime/visual check>
**Migration / rollback:** <data or contract migration and how to back it out, or None>
**Dependencies / risks:** <sequencing against other tasks, concrete blockers, or driver decisions, or None>
**Tradeoffs:** <optional: one "we accept X in exchange for Y" per choice a reader could mistake for an oversight>
```

- Name the exact existing files and modules where the change goes whenever the spike identifies them, and leave types, signatures, and line-level edits to the implementer. If a new file is required, give its proposed package/folder and responsibility. No code snippets or patches.
- Order steps by dependency and keep requirements traceable. Include only changes necessary for that task; do not plan already-completed work.
- Keep the plan scannable: one line per numbered step. When a plan grows long enough that a reviewer loses the thread, the task should have been split — say so rather than writing a longer plan.
- Don't restate scope, non-goals, dependencies, coverage, or acceptance criteria. The task body already carries them.
- Record unanswered questions explicitly. If a task cannot be planned safely without an answer, mark it blocked and report it rather than presenting a speculative plan as ready.
- When you re-plan a task that already carries a plan, rewrite its whole plan block as a first-pass plan, not a diff. Do not write implementation notes or Result prose.

## Report back

A missing prerequisite, or a decision only the driver can make, stops the pass: report it exactly and don't guess. Return:

1. Whether this was a first pass or a reconciliation.
2. Tasks planned, tasks left unchanged, and any open task left unplanned with the reason.
3. Dependency and sequencing order.
4. Concrete blockers or driver decisions surfaced.
5. How each surviving assumption resolved, or `None`.
6. Drift between the record, its technical approach, and current source.
7. Exploration delegated and its results.
8. Validation intentionally not run.

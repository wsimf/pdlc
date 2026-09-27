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
- Already planned (TASK-001): leave their plans unchanged. They are here as context for the tasks you plan.

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

## Writing a plan

Each plan covers:

- files and modules that will change
- interfaces and call sites
- sequencing and inter-task dependencies
- migration and rollback risk
- test / validation strategy mapped to the task's acceptance criteria
- unresolved decisions, called out explicitly

Don't restate scope, non-goals, dependencies, coverage, or acceptance criteria. The task body already carries them.

## Report back

Name the tasks whose plans you wrote or changed, and those you left unchanged. A missing prerequisite, or a decision only the driver can make, stops the pass: report it exactly and don't guess.

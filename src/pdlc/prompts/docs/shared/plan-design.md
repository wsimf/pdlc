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

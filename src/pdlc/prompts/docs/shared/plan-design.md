## Designing the plan

Plan the approach, not the code: name where the change goes and what it affects, and leave types, signatures, and line-level edits to the implementer.

- Plan the change as if the task's requirement had been in the design from the start. Don't bolt it onto the current shape when the current shape is what makes it awkward.
- Name the module that owns the new behaviour. Put a decision behind one source of truth rather than repeating it across several places.
- Subtract before you add. When the task replaces existing behaviour, plan the removal first when it simplifies what follows, or alongside its replacement.
- When the task replaces an internal API, plan to migrate its callers and delete the old one in the same task. Don't plan a compatibility shim kept only for internal callers.
- Prefer the smallest change that satisfies the task. Don't plan a wrapper, layer, or abstraction with one caller, or thread a new signal through types, schemas, or pipelines when a direct path exists.
- Where the codebase has no precedent for a decision, name the alternative you rejected and why.
- Look for what the change can break beyond its call sites: persisted data, wire formats, config, flags, and code that reads the same data. Name the one fact the change's safety depends on and the check that proves it.
- When the task touches a command, lifecycle step, or anything that can be retried or run concurrently, state what happens if it runs twice or stops halfway.

Where one of these and a task conflict, say so in the plan rather than planning around it.

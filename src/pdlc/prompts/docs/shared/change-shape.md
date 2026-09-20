## Shape of the change

Make the smallest change that satisfies the task, and leave the code you touch
simpler than you found it. Removals stay inside the files this task owns —
anything wider is a line in your report, not a change.

- Subtract before you add. Dead code, a stub, a redundant validator, or a
  decision duplicated across the files you are touching goes first; build on
  the smaller base.
- Fewer lines beat elegant boilerplate. A wrapper, layer, or abstraction with
  one caller is not worth its indirection.
- Do not repeat a decision in several places. Put it behind one source of truth
  and pass the result.
- Do not thread a new signal through types, schemas, or pipelines when a direct
  path exists. Where the plan asks for the threading, follow the plan and say
  in your report where the direct path would have done.
- When this task replaces an internal API, migrate its callers and delete the
  old one here. A compatibility shim kept only because internal callers still
  exist is dual-path complexity, not a migration.
- If answering a question about this code takes tracing through more than about
  three files, the shape is wrong.

Types and boundaries:

- Make illegal states unrepresentable. Model variants as a sum type rather than
  a bag of optional fields whose contradictory combinations still compile. If
  you could write a comment explaining which combinations are valid, the type
  is too loose.
- Give distinct meanings distinct types. Two parameters that share a primitive
  type and mean different things should not be interchangeable.
- Parse external data at the boundary — CLI arguments, config, network
  payloads, stored rows — into the typed model, then trust the types inside. A
  nil check deep in a call chain the boundary already covered is noise.
- Do not lie to the compiler. A cast, force-unwrap, or assertion that bypasses
  a fact you cannot prove is a runtime failure in waiting: prove it, model it
  away, or report that you could not.
- Match on a variant exhaustively, so a variant added later fails the build
  instead of falling through silently.

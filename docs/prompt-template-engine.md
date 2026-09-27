# Prompt template engine

Reference for authors of the fragments under `src/pdlc/prompts/docs/`, rendered by `src/pdlc/prompts/assemble.py`.

## Placeholders

`{{NAME}}` is replaced by `context["NAME"]`, which must be a string. It can appear mid-line, e.g. `` task `{{TAG}}` here ``.

## Includes

`{{INCLUDE:path}}` is replaced by the fragment at `path` (relative to `docs/`, e.g. `shared/execution-boundary.md`), rendered against the same context. The included fragment's trailing newlines are dropped and the including line's own newline is kept, so an include alone on its own line contributes exactly its own lines. A cycle of includes is a `PromptError`.

## Conditionals

```
{{#IF NAME}}
kept when NAME is truthy
{{#ELSE}}
kept when NAME is falsy
{{/IF}}
```

`{{#ELSE}}` is optional. When present it sits alone on its line, at the same nesting level as its `{{#IF}}`, and its body is everything from `{{#ELSE}}` down to the matching `{{/IF}}` — there is no separate `{{/ELSE}}` closing tag. At most one `{{#ELSE}}` per `{{#IF}}`; a second one is an error. `{{#ELSE}}` is only valid directly inside an `{{#IF}}` block — using it inside `{{#EACH}}`, or with no enclosing block at all, is an error.

Truthiness is plain Python truthiness: `""`, `None`, `False`, `0`, `[]`, and `{}` are all falsy; anything else is truthy.

## Loops

```
{{#EACH NAME}}
- {{FIELD}}
{{/EACH}}
```

Renders the body once per item in `context["NAME"]`, which must be a sequence of mappings. Inside the body, a name resolves against the current item first and falls back to the surrounding context, so a repeated fragment can still reach values that belong to the whole prompt. An item can shadow an outer name of the same name.

## Every referenced name must exist

There's no "render blank if missing": every `{{NAME}}`, `{{#IF NAME}}`, and `{{#EACH NAME}}` the template references must be present in the context passed to `render`/`render_text`, or rendering raises `PromptError`. A typo fails loudly instead of leaving a silent hole in a prompt.

## Line rules

A block directive — `{{#IF NAME}}`, `{{#ELSE}}`, `{{#EACH NAME}}`, `{{/IF}}`, `{{/EACH}}` — must sit alone on its line (surrounding whitespace is fine). The directive line itself is consumed; it contributes nothing to the output. `{{NAME}}` and `{{INCLUDE:path}}` are the only forms allowed to share a line with other text.

## Nesting

Blocks nest freely: an `{{#IF}}` inside an `{{#EACH}}`, an `{{#IF}}` inside another `{{#IF}}`'s branch (including its `{{#ELSE}}` branch), and so on. Each `{{#ELSE}}` binds to the nearest enclosing `{{#IF}}` at its own nesting level.

## Syntax validation

`check_syntax(text, *, path_exists=None)` validates a template's structure without needing a render context: balanced `{{#IF}}`/`{{#EACH}}` blocks, correct `{{#ELSE}}` placement, that every `{{INCLUDE:path}}` is a safe path (and, when `path_exists` is given, that it exists), that block directives stand alone on their line, and that no other `{{...}}`-looking text is present (e.g. a typo'd directive, or the old `{{/ELSE}}`, which is no longer valid). `tests/test_prompts.py` runs `check_syntax` over every bundled fragment under `src/pdlc/prompts/docs/` (including `shared/`) as a regression gate — a malformed fragment fails the test suite, not just at render time.

## Example

```
{{INCLUDE:shared/execution-boundary.md}}

{{#IF STALE_REASON}}
### Invalidation reason

{{STALE_REASON}}
{{/IF}}

{{#EACH EXISTING_TASKS}}
- `{{TASK_ID}}` — {{TASK_TITLE}}
{{/EACH}}
```

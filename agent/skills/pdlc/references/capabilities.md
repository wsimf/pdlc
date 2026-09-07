# Project capabilities

PDLC skills never name a project-specific skill or sub-agent. Each seam that
could use a specialist reads its routing from `pdlc inspect capability <slot>`
and injects the result into the sub-agent brief it builds.

A project declares its routing in `.pdlc/config.toml`:

```toml
[agents]
core-implementer = "my-core-implementer"
ui-implementer   = "my-ui-implementer"

[skills]
build-run         = "my-build-run"
ux-design         = "my-ux-design"
cumulative-review = "my-cumulative-review"
test-authoring    = "my-test-authoring"
test-framework    = "my-test-framework"
```

Every slot is optional. Both tables may be omitted entirely; the workflow
still runs.

Capability selection does not select workflow policy. The resolved record's `workType` selects its pipeline; `[agents]` and `[skills]` only select who performs an action already returned by that pipeline.

## Slots

| Slot | Kind | Used by | Unset behaviour |
|---|---|---|---|
| `core-implementer` | agent | `pdlc-implement` dispatch for `[CORE]` tasks | dispatch to `general-purpose` |
| `ui-implementer` | agent | `pdlc-implement` dispatch for `[UI]` tasks | dispatch to `general-purpose` |
| `build-run` | skill | `pdlc-tasks` acceptance criteria, `pdlc-verify` UI-journey pass | agent builds and runs the app per `AGENTS.md` |
| `ux-design` | skill | `pdlc-ui-planner` | agent resolves design from `AGENTS.md` references and platform conventions |
| `cumulative-review` | skill | `pdlc-verify` cumulative review, `pdlc-implement` task review | agent performs the review inline over the change scope |
| `test-authoring` | skill | `pdlc-test-writer` | agent follows the existing test suite's conventions |
| `test-framework` | skill | `pdlc-test-writer` (reference only) | omitted |

## Contract

- **agent slots** resolve to exactly one sub-agent name. `pdlc inspect
  capability core-implementer` prints it (or `general-purpose`). The calling
  skill dispatches there. `pdlc inspect task` resolves each task's implementer
  slot from its own `isUI` and prints it under `## Agent`, so `pdlc-implement`
  never asks separately.
- **skill slots**, when set, resolve to an instruction: *"You must invoke the
  `<name>` skill before continuing. If it is not available, say so and exit."*
  The calling skill pastes that line verbatim into the sub-agent brief.
- **skill slots**, when unset, resolve to a fallback sentence that tells the
  agent to handle the seam itself. The seam always runs.

A project supplying its own capability skill owns that skill's own input and
output contract; PDLC only guarantees it is named in the brief and required
before the agent proceeds.

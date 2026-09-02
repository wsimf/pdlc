# PDLC

The PDLC command-line tool and its agent workflow instructions.

## Installation

Install the `pdlc` CLI as a `uv` tool so it lands on `PATH`:

```bash
uv tool install 'git+ssh://git@github.com/wsimf/pdlc.git@master'
```

Pin a branch or tag by changing the `@master` suffix (for example `@my-branch` or `@v0.1.0`).

Verify with:

```bash
pdlc --help
```

### Updating

Re-pull the pinned ref and reinstall:

```bash
uv tool upgrade pdlc --reinstall
```

To switch to a different branch or tag, reinstall with `--force`:

```bash
uv tool install --force 'git+ssh://git@github.com/wsimf/pdlc.git@my-branch'
```

## Development

```bash
uv run pdlc --help
uv build
```

Run from a local checkout without installing with `uv run pdlc ...`.

## Environment variables

Values in `.pdlc/config.toml` override environment variables. CLI options override both.

All variables are optional unless a selected backend or workflow requires them.

| Variable | Default | Purpose |
|---|---|---|
| `PDLC_REPOSITORY` | unset; required for GitHub | GitHub repository in `OWNER/REPOSITORY` form. |
| `PDLC_PROJECT_NUMBER` | unset; required for GitHub | GitHub Projects number. |
| `PDLC_PROJECT_OWNER` | unset; required for GitHub | GitHub Projects owner. |
| `PDLC_BACKEND` | `github` | Work-item backend: `github` or `file`. |
| `PDLC_CODE_HOST` | Follows `PDLC_BACKEND` | Code/PR host: `github`, `file`, or `none`. |
| `PDLC_ATTACHMENT_HOST` | `file` | Attachment host: `file` or `none`. |
| `PDLC_HOME` | `.pdlc` | Local file-backend and attachment storage root. |
| `PDLC_ACTOR` | `local` | Actor name recorded by the file backend. |
| `PDLC_REF_LABEL` | `pdlc` | Label used for local inspector scratch files. |
| `PDLC_ITEMS_FILE` | unset | Fixture file used instead of live GitHub Project items. |
| `PDLC_SUBISSUES_FILE` | unset | Fixture file used instead of live GitHub subissues. |
| `PDLC_MAX_ATTEMPTS` | `5` | Maximum queue-loop polling attempts. |
| `PDLC_INITIAL_DELAY_SECONDS` | `60` | Initial queue-loop retry delay. |
| `PDLC_MAX_DELAY_SECONDS` | `900` | Queue-loop retry delay ceiling. |
| `PDLC_NO_SLEEP` | unset | Any non-empty value skips queue-loop retry sleeps. |
| `PDLC_AUTOAPPROVE_CHURN_CAP` | `3` | Maximum rework count eligible for automatic approval. Set to `0` to disable it. |

For GitHub, create `.pdlc/config.toml` with:

```toml
[backend]
name = "github"

[backend.github]
repository = "OWNER/REPOSITORY"
project_number = 123
project_owner = "OWNER"
```

Run `pdlc setup` to create this file interactively. It detects the GitHub repository from `remote.origin.url`, lists available GitHub Projects with `gh`, and lets you choose the project owner or enter another owner.

### GitHub Project fields

`pdlc setup` does not create Project fields. Add these to the GitHub Project (v2) by hand before running any workflow command; PDLC reads and writes work-item state through them and fails if a field or option name is missing. Names are matched exactly.

| Field | Type | Options / contents |
|---|---|---|
| `Status` | Single select | `Product`, `UI`, `Tasks`, `Technical Plan`, `Implementation`, `Testing`, `Verification`, `Complete` — the fixed lifecycle stages, in order. |
| `Gate State` | Single select | `Pending`, `Review Required`, `Changes Required`, `Decision Required`, `CI Pending`, `Approval Required`, `Approved`, `Stale` — where the current stage sits (pending work, under review, needs a human decision, blocked on CI, awaiting approval, approved, or stale after upstream change). |
| `Lifecycle` | Single select | `Planning`, `Completed` — `Completed` is set only by `pdlc post complete`; everything else stays `Planning`. |
| `Slug` | Text | Short work-item identifier stamped once at creation and never overwritten. |
| `Skipped States` | Text | Comma-separated list of lifecycle stages declared skipped ahead of time via `pdlc post skip`. |

The `file` backend mirrors the same field names under `PDLC_HOME`, so no manual setup is needed there.

## Project capabilities

PDLC skills never name a project-specific skill or sub-agent. Each seam that could use a specialist reads its routing from `pdlc inspect capability <slot>` and injects the result into the sub-agent brief it builds. Declare routing in the `[agents]` and `[skills]` tables of `.pdlc/config.toml`:

```toml
[agents]
core-implementer = "swift-pro"
ui-implementer   = "swiftui-pro"

[skills]
build-run         = "trailnest-build-run"
ux-design         = "trailnest-ux-design"
cumulative-review = "trailnest-cumulative-review"
test-authoring    = "create-swift-tests"
test-framework    = "swift-testing-expert"
```

Every slot is optional; omit both tables and the workflow still runs with the fallback behaviour below.

| Slot | Kind | Plugged into | Unset behaviour |
|---|---|---|---|
| `core-implementer` | agent | `pdlc-implement` dispatch for `[CORE]` tasks | dispatch to `general-purpose` |
| `ui-implementer` | agent | `pdlc-implement` dispatch for `[UI]` tasks | dispatch to `general-purpose` |
| `build-run` | skill | `pdlc-tasks` acceptance criteria, `pdlc-verify` UI-journey pass | agent builds and runs the app per `AGENTS.md` |
| `ux-design` | skill | `pdlc-ui-planner` | agent resolves design from `AGENTS.md` references and platform conventions |
| `cumulative-review` | skill | `pdlc-verify` cumulative review, `pdlc-implement` task review | agent performs the review inline over the change scope |
| `test-authoring` | skill | `pdlc-test-writer` | agent follows the existing test suite's conventions |
| `test-framework` | skill | `pdlc-test-writer` (reference only) | omitted |

Inspect the current wiring with `pdlc inspect capability` (every slot) or `pdlc inspect capability <slot>` (one paste-ready line). Full contract: `agent/skills/pdlc/references/capabilities.md`.

# PDLC

**PDLC runs a feature from idea to shipped code as a governed lifecycle on your existing issue tracker, with coding agents doing the work and the tracker holding the state.**

Point it at a one-line idea or an existing work item. It drives the feature through a fixed sequence of stages — product spec, UI, task breakdown, technical plan, implementation, testing, verification — pausing for human approval at the gates that matter and letting an autonomous loop grind through the rest. Every stage produces a reviewed artifact; every transition is recorded as evidence on the work item itself, not in a side database.

## What it is

- An installable `pdlc` CLI that is the only interface to the workflow state.
- A set of agent **skills** (`agent/skills/`) and specialist **sub-agents** (`agent/sub-agents/`) that drive the lifecycle by calling that CLI — one skill per stage, plus an orchestrator and an autonomous queue loop.
- A backend abstraction: work items live in **GitHub Issues + Projects** or **Azure Boards**; code and pull requests live in **GitHub**; the two are chosen independently, so Azure Boards can pair with GitHub code hosting.

## Core idea

The work-item store is the system of record. Local files are temporary inputs; the CLI is the only way to read or change lifecycle state.

- **Fixed lifecycle.** `Product → UI → Tasks → Technical Plan → Implementation → Testing → Verification → Complete`. A per-work-item `Gate State` (`Pending`, `Review Required`, `Changes Required`, `Decision Required`, `CI Pending`, `Approval Required`, `Approved`, `Stale`) says what the active stage is waiting on.
- **Machine-checked, never inferred.** Stage, gate, task identity, PR linkage, evidence, and completion readiness come from the store — never from branch names, checkboxes, or prose.
- **Evidence, not logs.** Each transition appends an evidence comment explaining why it happened; the work-item body stays a clean current-intent specification.
- **Human gates are explicit.** Approvals, skips, decision resolutions, invalidations, and final completion are always driver actions. Everything else — routing, reviews, CI reconciliation, retries with backoff — can run unattended.
- **Independent review at every stage.** Read-only reviewer sub-agents check each artifact against the requirements and plans before the gate opens; a reviewer can raise a `Decision Required` block when a finding needs a product, architecture, or scope call.
- **Stacked delivery.** Implementation is decomposed into dependency-ordered delivery tasks, each shipped as its own stacked pull request linked back to the parent.

## Capabilities

- **Start** a feature from an idea: `pdlc` with a description hands it to `pdlc-write`, which drafts and reviews the Product artifact.
- **Orient** on any work item: `pdlc inspect <work-item>` returns metadata, the classified task tree, linked-PR check rollup, and the routing decision for what is due next.
- **Drive** the queue: `pdlc next` routes one item (or scans the whole queue) to the next stage skill; `pdlc next loop` retries with backoff until something is actionable.
- **Advance** stages with the `pdlc post *` commands — each one performs a single authorized transition and records its evidence.
- **Inspect** progress read-only with `pdlc inspect timeline`, `pdlc inspect changes`, `pdlc inspect comments --page N`, and per-stage readiness checks (`inspect implement`, `inspect test`, `inspect verify`, `inspect complete`).
- **Route seams to your toolchain.** A consuming repo maps each capability slot (implementer, reviewer, test author, …) to its own skill or sub-agent through `.pdlc/config.toml`; unset slots fall back to a general-purpose agent, so the skills name no project-specific tool.

Run `pdlc --help` for the full command list. Run `pdlc guide guide` for the general guide or `pdlc guide decisions` for the decision-resolution workflow.

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

## Worktrees

`pdlc prepare` and `pdlc cleanup` are human-only helpers — they are not part of the agent workflow and do not appear in `pdlc --help`. They bracket a work item's implementation with an isolated Git worktree so the agent never touches your main checkout.

Run `pdlc prepare` **before starting implementation**, once a record is planned and its tasks are ready:

```bash
cd "$(pdlc prepare 142)"
```

This creates `<worktree.root>/<repo-name>/142` on a `pdlc/record-142` branch (from the repo's default branch), optionally runs your init script, and prints the path so the subshell `cd`s into it. Point the agent at that directory and let it run the `gh stack` implementation loop there. Re-running `pdlc prepare 142` just reprints the existing path.

Run `pdlc cleanup` **after the record is complete**, from your main checkout:

```bash
pdlc cleanup 142
```

It resolves the work item, refuses unless it is locked at `Complete`, then removes the worktree and force-deletes its local branches — `pdlc/record-142` and every `pdlc/<slug>/<task-id>` branch `gh stack` created. Merged pull requests and remote branches are left to GitHub. Add `--yes` to skip the confirmation prompt.

Configure with the optional `[worktree]` table (merged from `~/.pdlc/config.toml` then `.pdlc/config.toml` like every other setting):

```toml
[worktree]
root = "~/.pdlc/worktrees"   # optional; this is also the default
base_ref = "origin/main"      # optional; default: the repo's detected default branch
init_script = "npm ci"        # optional; pdlc prepare offers to run it in the new worktree
```

`init_script` runs as a shell snippet in the new worktree; `pdlc prepare` shows it and prompts before running (`--yes` to skip). Keep it POSIX `sh` — it is passed to the platform shell.

## Development

```bash
uv sync --locked
uv run pdlc --help
uv run ruff check src tests
uv run mypy
uv run python -m unittest discover -s tests -p 'test_*.py'
uv build
```

Run from a local checkout without installing with `uv run pdlc ...`.


Ruff checks all source and tests; the strict mypy baseline covers normalized records, host ports, and shared process/storage boundaries (the files are listed in `pyproject.toml`).
CI runs these checks, the full test suite, and packaging on Python 3.12–3.14.
Provider tests use the replay transports in `tests/_gh_replay.py` and `tests/_az_replay.py`; the old `PDLC_ITEMS_FILE` and `PDLC_SUBISSUES_FILE` fixture switches have been removed from production configuration.

### Provider organization

`src/pdlc/hosts/{azure,github,file,none}_provider.py` exposes each provider's concrete implementations.
Implementation details live together under `hosts/lib/azure/`, `hosts/lib/github/`, `hosts/lib/file/`, and `hosts/lib/none/`.
The `workitem_host/`, `code_host/`, and `attachment_host/` packages retain their neutral ports and configured factories, so Azure Boards can still pair with GitHub code hosting.
`domain/records.py` defines normalized data contracts; task publication passes validated `bodyText`, never a file path, across the work-item port.
`domain/task_plan.py` owns pure task validation and dependency policy, while `internal/inputs.py` owns file/stdin handling.

The CLI accepts explicit argument lists through `main(argv=...)` and resets its host/configuration caches between invocations.
Environment overrides remain available during a command and are restored afterwards; concurrent embedded CLI calls are not supported.

### Local-store writes

File-store inspection does not initialize missing directories.
Writes use UTF-8 atomic file replacement and a fail-fast `$PDLC_HOME/.writer.lock` directory to exclude concurrent writers.
An interrupted writer may leave this lock behind: confirm that no writer is running before removing that directory and retrying.
Atomic replacement protects individual files, not an entire multi-file workflow transaction.
Azure task publication recovers an unlinked task by exact stable identity on retry and rejects ambiguous or foreign-parent matches.
CLI transport failures remain explicit; a timeout after a write requires inspection of remote state before retry.

Inspect comments without loading the full discussion with `pdlc inspect comments ISSUE --page N`. Pages contain 100 comments, are newest first, and report the exact total plus the next command when more remain.

## Configuration

Configuration is file-first. Settings live in `.pdlc/config.toml` at the repository root, layered over `~/.pdlc/config.toml` for machine-wide defaults, with CLI options (`--repo`, `--backend`, `--project-number`, `--project-owner`, `--home`) on top for a single run.

Only two settings are read from the process environment, because they identify *where* things are before any config file is located:

| Variable | Default | Purpose |
|---|---|---|
| `PDLC_REPOSITORY` | unset | GitHub repository in `OWNER/REPOSITORY` form; overrides `[backend.github] repository`. Falls back to the checkout's `origin` remote (HTTPS or SSH) when nothing sets it; an SSH host alias that hides `github.com` is not resolved. |
| `PDLC_HOME` | `.pdlc` | Local file-backend and attachment storage root; overrides `[runtime] home`. |
| `PDLC_DEBUG` | unset | `true` turns on external-call tracing before a config file is read; equivalent to `[debug] enabled = true`. |

Every other setting is a `.pdlc/config.toml` key. All are optional unless a selected backend or workflow requires them:

| Table / key | Default | Purpose |
|---|---|---|
| `[backend] name` | `github` | Work-item backend: `github`, `azure`, or `file`. |
| `[backend.github] repository` | unset; required for GitHub | GitHub repository in `OWNER/REPOSITORY` form. |
| `[backend.github] project_number` | unset; required for GitHub | GitHub Projects number. |
| `[backend.github] project_owner` | unset; required for GitHub | GitHub Projects owner. |
| `[backend.github] assigned_to` | unset | Optional. When set, the GitHub queue scan only returns Issues assigned to this login; `@me` resolves to the authenticated user. |
| `[backend.azure] organization` | unset; required for Azure | Azure DevOps organization URL, e.g. `https://dev.azure.com/OWNER`. |
| `[backend.azure] project` | unset; required for Azure | Azure DevOps project name. |
| `[backend.azure] record_type` | `Product Backlog Item` | Work-item type used for a PDLC record. Set to `User Story` on an Agile process. |
| `[backend.azure] closed_state` | `Done` | Work-item state name. Falls back for `task_closed_state` when that is unset. `Closed` is always recognized as terminal for a delivery task regardless of this setting. |
| `[backend.azure] open_state` | `To Do` | Work-item state name. Falls back for `task_open_state` when that is unset. |
| `[backend.azure] task_closed_state` | Falls back to `closed_state` | Delivery task (`Task`) state closed into. Set this when the record type and `Task` use different state vocabularies. |
| `[backend.azure] task_open_state` | Falls back to `open_state` | Delivery task (`Task`) state a task is reopened into by `pdlc post invalidate` when it targets `Technical Plan` or `Implementation`. |
| `[backend.azure] task_in_progress_state` | unset | Optional. No work-item fallback — set explicitly if your process has an in-progress `Task` state you want recorded. |
| `[backend.azure] assigned_to` | unset | Optional. When set, the Azure queue scan only returns records assigned to this identity (display name or unique name); `@me` maps to Azure's `@Me` WIQL macro. |
| `[code_host] name` | Follows `[backend] name`; `none` for `azure` | Code/PR host: `github`, `file`, or `none`. |
| `[code_host] pr_attachment` | unset | Optional line inserted as the first line of each task PR body when `pdlc post implement-task` submits the stack. Every `{work.number}` is replaced with the parent work item's bare number (no `#`). PR body only — never added to the `## Implementation` comment. |
| `[code_host] pr_title_format` | unset | Optional format string for each task PR title when `pdlc post implement-task` submits the stack. Placeholders: `{task.title}` (the delivery task's title, with its `WORK-N-TASK-N` id prefix and `[CORE]`/`[UI]` tag stripped), `{task.id}` (e.g. `TASK-001`), `{work.number}` (the parent's bare number), `{work.type}` (`feature`/`bug`). Unset uses the bare stripped task title; the `[CORE]`/`[UI]` tag is dropped either way. |
| `[attachment_host] name` | `file` | Attachment host: `file` or `none`. |
| `[runtime] home` | `.pdlc` | Local file-backend and attachment storage root (see also `PDLC_HOME`). |
| `[runtime] actor` | `local` | Actor name recorded by the file backend. |
| `[runtime] ref_label` | `pdlc` | Label used for local inspector scratch files. |
| `[workflow] max_attempts` | `5` | Maximum queue-loop polling attempts. |
| `[workflow] initial_delay_seconds` | `60` | Initial queue-loop retry delay. |
| `[workflow] max_delay_seconds` | `900` | Queue-loop retry delay ceiling. |
| `[workflow] no_sleep` | `false` | `true` skips queue-loop retry sleeps. |
| `[worktree] root` | `~/.pdlc/worktrees` | Parent directory for `pdlc prepare` / `pdlc cleanup` worktrees; each is nested `<root>/<repo-name>/<workitem>`. |
| `[worktree] base_ref` | detected default branch | Ref that new `pdlc prepare` branches start from. |
| `[worktree] init_script` | unset | Shell snippet `pdlc prepare` offers to run in a freshly created worktree. |
| `[debug] enabled` | `false` | `true` appends every external CLI call (`az`, `gh`, `git`, …) to `~/.pdlc/debug.log` as `[<time>] - (<tool>) : <full command>`. |

For GitHub, create `.pdlc/config.toml` with:

```toml
[backend]
name = "github"

[backend.github]
repository = "OWNER/REPOSITORY"
project_number = 123
project_owner = "OWNER"
assigned_to = "@me"          # optional; scope the queue scan to your Issues
```

For Azure Boards, the work-item backend and the code host are separate choices — Azure Boards paired with GitHub repositories is the expected setup, so the GitHub table is still needed for the repository alone:

```toml
[backend]
name = "azure"

[backend.azure]
organization = "https://dev.azure.com/OWNER"
project = "PROJECT"
record_type = "Product Backlog Item"   # optional; defaults to "Product Backlog Item"
closed_state = "Done"        # optional; defaults to "Done"
open_state = "To Do"         # optional; defaults to "To Do"
assigned_to = "@me"          # optional; scope the queue scan to your work items

[code_host]
name = "github"
pr_attachment = "Fixes {work.number}"   # optional; first line of each task PR body
pr_title_format = "[{work.number}] {task.title}"   # optional; each task PR title

[backend.github]
repository = "OWNER/REPOSITORY"
```

`assigned_to` is optional and inactive unless set: with it, `pdlc next` and the queue scan only surface records assigned to that identity (`@me` is Azure's `@Me` macro). The GitHub backend has the same optional `assigned_to` filter under `[backend.github]`.

Only `organization` and `project` are required by the backend itself. `repository` is required by the *code host*, not the backend — the two are validated independently, so `name = "none"` under `[code_host]` needs neither it nor the `[backend.github]` table.

`record_type` is more than a creation default: it is how PDLC recognizes a work item as a record rather than an ordinary board item, and it is the type the queue scan filters on. If you change it, the [custom fields](#azure-boards-fields) have to exist on that type instead.

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

### Azure requirements

The Azure backend shells out to the Azure CLI — there is no Python SDK dependency, and `pdlc` never stores a PAT or any other credential of its own. Everything below is verified against Azure CLI `2.90.0` with the `azure-devops` extension `1.0.8`.

| Requirement | How to satisfy | Why |
|---|---|---|
| Azure CLI (`az`) | `brew install azure-cli` | Every Boards read and write is an `az` subprocess. `pdlc` fails with `required command not found: az` if it is missing. |
| `azure-devops` extension | `az extension add --name azure-devops` | **Not bundled with the Azure CLI.** `az` offers to install it on first use, but that prompt fails in CI or any non-interactive run. For unattended environments set `az config set extension.use_dynamic_install=yes_without_prompt` instead. |
| A signed-in account | `az login` | `az boards` and `az devops` authenticate as the signed-in identity, and `pdlc` reads `az account show` to record the acting user on evidence comments. A PAT supplied through `az devops login` authorizes Boards calls but leaves `az account` empty, so prefer `az login`. |
| Project access | Contributor on the Azure DevOps project | The backend creates work items, edits fields, adds parent links, and posts comments. Read-only access fails on the first `pdlc post` command, not at configuration time. |
| GitHub CLI (`gh`), authenticated | `gh auth login` | Only when the code host is `github`, which is the expected pairing. Pull requests, branches, and CI status come from `gh`; Azure Boards supplies work-item state alone. |

On a fresh machine that is the whole client-side setup:

```bash
az extension add --name azure-devops
az login
```

No `az devops configure --defaults` setup is needed: `pdlc` passes `--organization` and `--project` explicitly on every call, so it is unaffected by, and does not disturb, your local `az` defaults. The same machine can therefore drive several organizations without a global mode switch.

Two things are organization-admin work that `pdlc` deliberately never attempts, because both need permissions a workflow run should not hold:

- **The custom fields**, which require an inherited process. See [Azure Boards fields](#azure-boards-fields) below for the full list and the process for adding them.
- **The project itself**, if it does not exist yet, which must be created against that inherited process. The `az devops project create` command is at the end of the next section.

### Azure Boards fields

Azure Boards has no project-level field layer: fields live on the work-item type and can only be added through a customized (inherited) process, which needs organization-admin rights. There is no `az` command for this and `pdlc` never attempts it — treat the fields below as a prerequisite an admin satisfies once per organization, before anyone runs a workflow command.

In **Organization settings → Process**, create an inherited process from **Scrum** (right-click the process → *Create inherited process*), then add these fields. The reference name is derived from the display name automatically, so enter `PdlcStatus` and Azure stores it as `Custom.PdlcStatus` — do not type the `Custom.` prefix yourself.

Add all six to **`Product Backlog Item`**, the work-item type PDLC uses for a record (use `User Story` instead if you inherit from Agile and set `record_type` accordingly):

| Field | Type | Options / contents |
|---|---|---|
| `PdlcStatus` | Picklist (string) | `Product`, `UI`, `Tasks`, `Technical Plan`, `Implementation`, `Testing`, `Verification`, `Complete` — the fixed lifecycle stages, in order. |
| `PdlcGateState` | Picklist (string) | `Pending`, `Review Required`, `Changes Required`, `Decision Required`, `CI Pending`, `Approval Required`, `Approved`, `Stale` — where the current stage sits. |
| `PdlcLifecycle` | Picklist (string) | `Planning`, `Completed` — `Completed` is set only by `pdlc post complete`; everything else stays `Planning`. |
| `PdlcSkippedStates` | Text (single line) | Comma-separated list of lifecycle stages declared skipped ahead of time via `pdlc post skip`. |
| `PdlcSlug` | Text (single line) | Short work-item identifier stamped once at creation and never overwritten. |
| `PdlcPrs` | Text (single line) | Space-separated pull-request numbers attached to the record. Written by `pdlc post implement` / `post test`. |

Add one field to **`Task`**, the work-item type PDLC uses for a delivery task:

| Field | Type | Options / contents |
|---|---|---|
| `PdlcPrs` | Text (single line) | Space-separated pull-request numbers attached to that task. Written by `pdlc post implement-task` / `post attach-pr`. |

Descriptions and evidence comments are written as Markdown, so they render properly in the Azure UI. PDLC sets that format on the work items it creates; nothing needs configuring.

A delivery task carries no stage state of its own: its identity is the `WORK-<n>-TASK-NNN` prefix on its title, and its parent link is a normal `System.LinkTypes.Hierarchy-Forward` relation.

Option values are matched exactly and validated by Azure, so a typo surfaces on the first write as `The field 'PdlcGateState' contains the value '…' that is not in the list of supported values` rather than corrupting state. Confirm the fields landed on the right types with:

```bash
az devops invoke --organization https://dev.azure.com/<org> \
  --area wit --resource workitemtypes \
  --route-parameters project=<project> --api-version 7.1 -o json
```

Create the project against the inherited process once the fields exist:

```bash
az devops project create --organization https://dev.azure.com/<org> \
  --name <project> --process "<inherited process name>" --source-control git --visibility private
```

## Project capabilities

PDLC skills never name a project-specific skill or sub-agent. Each seam that could use a specialist reads its routing from `pdlc inspect capability <slot>` and injects the result into the sub-agent brief it builds. Declare routing in the `[agents]` and `[skills]` tables of `.pdlc/config.toml`:

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

Inspect the current wiring with `pdlc inspect capability` (every slot) or `pdlc inspect capability <slot>` (one paste-ready line). Full contract: `pdlc guide capabilities`.

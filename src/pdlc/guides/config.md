# PDLC configuration

PDLC reads its settings from TOML files. Run `pdlc doctor` to see the resolved values and any missing or invalid setting.

## Where settings come from

Later sources win, per key:

1. The `PDLC_HOME` and `PDLC_REPOSITORY` environment variables.
2. `~/.pdlc/config.toml` — machine-wide defaults.
3. The repository's `.pdlc/config.toml`.
4. Global CLI flags for one run: `--repo`, `--project-number`, `--project-owner`, `--backend`, `--home`.

The repository file is optional when `~/.pdlc/config.toml` exists. An unknown table or key, or a non-scalar value, is a configuration error. `PDLC_DEBUG` is also read from the environment, as an alternative to `[debug] enabled`; no other environment variable is read.

## Minimal configurations

GitHub (the default backend):

```toml
[backend.github]
project_number = "7"
project_owner  = "my-org"
```

Azure Boards work items with GitHub code:

```toml
[backend]
name = "azure"

[backend.azure]
organization = "https://dev.azure.com/my-org"
project      = "my-project"

[code_host]
name = "github"
```

Local file backend, for scenarios and tests:

```toml
[backend]
name = "file"
```

`[backend.github] repository` is omitted above because it is derived from the checkout's `origin` remote when nothing sets it; set it explicitly when that remote is not a github.com URL.

## `[backend]`

| Key | Required | Default | What it does |
|---|---|---|---|
| `name` | Optional | `github` | Work-item backend: `github`, `azure`, or `file`. Selects which `[backend.*]` table must be filled in. |

## `[backend.github]`

| Key | Required | Default | What it does |
|---|---|---|---|
| `repository` | Required for the `github` backend, and whenever `[code_host] name` is `github` | Derived from `origin` | `owner/name` of the GitHub repository holding Issues and PRs. |
| `project_number` | Required for the `github` backend | — | Number of the GitHub Project that tracks PDLC state. |
| `project_owner` | Required for the `github` backend | — | User or organization that owns that Project. |
| `assigned_to` | Optional | Unset (no filter) | Limits queue scans to Issues assigned to this login; `@me` resolves to the authenticated `gh` user. |

## `[backend.azure]`

| Key | Required | Default | What it does |
|---|---|---|---|
| `organization` | Required for the `azure` backend | — | Azure DevOps organization URL. |
| `project` | Required for the `azure` backend | — | Azure DevOps project; also the reference label on evidence. |
| `record_type` | Optional | `Product Backlog Item` | Work-item type used for PDLC records. |
| `open_state` | Optional | `To Do` | State written when a record opens. |
| `closed_state` | Optional | `Done` | State written when a record closes. |
| `task_open_state` | Optional | `open_state` | Open state for delivery tasks, when their type uses a different vocabulary. |
| `task_closed_state` | Optional | `closed_state` | Closed state for delivery tasks. `Removed` and `Closed` always count as closed. |
| `task_in_progress_state` | Optional | Unset | Accepted but not currently used. |
| `assigned_to` | Optional | Signed-in `az` account | Limits queue scans to this identity and assigns new records and tasks to it; `@me` filters by the signed-in account. |

## `[code_host]`

| Key | Required | Default | What it does |
|---|---|---|---|
| `name` | Optional | `github` for the `github` and `file` backends, `none` for `azure` | Where PRs live: `github`, `file`, or `none`. Set `github` to pair an Azure backend with GitHub PRs. |
| `pr_title_format` | Optional | The task title | Format for task PR titles. Placeholders: `{task.title}` (id prefix and `[CORE]`/`[UI]` tag stripped), `{task.id}`, `{work.number}`, `{work.type}`. |
| `pr_attachment` | Optional | Unset | Line appended to every task PR body; `{work.number}` resolves to the parent work item number. |

## `[attachment_host]`

| Key | Required | Default | What it does |
|---|---|---|---|
| `name` | Optional | `file` | `file` stores `--attachment` files locally (see `pdlc guide attachments`); `none` rejects any `--attachment`. |

## `[runtime]`

| Key | Required | Default | What it does |
|---|---|---|---|
| `home` | Optional | `.pdlc` in the working directory | Store root for the file backend and local attachments. Same as `PDLC_HOME`. |
| `actor` | Optional | `local` | Actor name the file backend records on evidence. |
| `ref_label` | Optional | `pdlc` | Reference label the file backend uses on evidence. |

## `[workflow]`

Retry policy for `pdlc next loop` while no work item is actionable. The delay doubles after each empty attempt, capped at `max_delay_seconds`.

| Key | Required | Default | What it does |
|---|---|---|---|
| `max_attempts` | Optional | `5` | Attempts before giving up; integer `>= 1`. |
| `initial_delay_seconds` | Optional | `60` | First wait between attempts; integer `>= 0`. |
| `max_delay_seconds` | Optional | `900` | Longest wait between attempts; integer `>= 0`. |
| `no_sleep` | Optional | `false` | Skip the waits and retry immediately. |

## `[worktree]`

Used only by the human-run `pdlc prepare` and `pdlc cleanup` commands.

| Key | Required | Default | What it does |
|---|---|---|---|
| `root` | Optional | `~/.pdlc/worktrees` | Parent directory for prepared trees, nested as `<root>/<repo-name>/<work-item>`. |
| `base_ref` | Optional | The repository's default branch | Ref new branches start from. |
| `init_script` | Optional | Unset | Shell snippet run inside each new tree. |

## `[debug]`

| Key | Required | Default | What it does |
|---|---|---|---|
| `enabled` | Optional | `false` | Appends every external `gh`, `az`, and `git` call to `~/.pdlc/debug.log`. |

## `[agents]` and `[skills]`

Optional capability slots that route PDLC seams to a project's own sub-agents and skills. Each slot is set per key and merges per slot across files. See `pdlc guide capabilities` for the slots and their fallbacks.

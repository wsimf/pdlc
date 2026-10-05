# PDLC configuration

PDLC reads its settings from TOML files. Run `pdlc doctor` to see the resolved values and any missing or invalid setting.

## Where settings come from

Later sources win, per key:

1. The `PDLC_HOME` and `PDLC_TRACKER_REPOSITORY` environment variables.
2. `~/.pdlc/config.toml` — machine-wide defaults.
3. The matching `[repository."owner/name"]` section in the home file.
4. The repository's `.pdlc/config.toml`.
5. Global CLI flags for one run: `--tracker-repo`, `--project-number`, `--project-owner`, `--tracker`, `--home`.

The repository file is optional when `~/.pdlc/config.toml` exists. It is the nearest `.pdlc/config.toml` at or above the Git repository root; above that root, only a directory that is not itself a Git repository and whose file sets `[code.github] repositories` counts, so a command run inside one repository of a multi-repository folder reads the folder's shared file while a worktree nested in another checkout does not. An unknown table or key, or a non-scalar value (other than `[code.github] repositories` and `[code.github.checkouts]`), is a configuration error. `PDLC_DEBUG` is also read from the environment, as an alternative to `[debug] enabled`; no other environment variable is read.

## Tracker and code

The tracker holds work items; the code provider holds pull requests. They are configured independently, so one tracker can serve several code repositories — each microservice checkout points `[tracker.github] repository` at the shared tracker while its pull requests stay in its own repository. When unset, both `[tracker.github] repository` and `[code.github] repository` default to the checkout's `origin` remote, and the code repository then to the tracker repository, so a single-repository project sets at most the tracker.

Pull requests are registered on work items as `owner/name#N`, so several code repositories can share one tracker without two PRs of the same number colliding; a PR in the configured code repository still reads as `#N` in output.

## Delivery tasks in several repositories

One work item can deliver into several repositories. `[code.github] repositories` lists every repository its delivery tasks may name; each task names one with a `**Repository:** owner/name` body line, and a task without one belongs to the code repository. One task is always exactly one repository. Unset, the list is just the code repository.

Each repository is worked in one local folder: the code repository in the current checkout, every other one in the clone the home-only `[code.github.checkouts]` table maps it to. `pdlc checkout`, `pdlc post implement-task`, `pdlc post implement`, verification, and the briefs run that task's Git and stack calls in that folder, and name it on `repository:` / `path:` lines; a task whose repository has no mapped folder is refused. Each repository keeps its own task stack, and `pdlc prepare --after` is refused while the list names more than one repository.

```toml
# api/.pdlc/config.toml (shared)
[code.github]
repositories = ["acme/api", "acme/web"]

# ~/.pdlc/config.toml (each developer's own clones)
[code.github.checkouts]
"acme/web" = "~/src/web"
```

## Repository-specific home settings

Home-only repository sections reuse the same tables and keys as ordinary configuration, including `[agents]` and `[skills]`:

```toml
# ~/.pdlc/config.toml
[worktree]
root = "~/worktrees"

[repository."sudara/A".worktree]
init_script = "uv sync"

[repository."sudara/B".worktree]
init_script = "./scripts/bootstrap.sh"

[repository."sudara/A".skills]
build-run = "my-build-skill"
```

Keys must be quoted `owner/name` identities, matched case-insensitively against the checkout's GitHub `origin`; linked worktrees and renamed checkout directories therefore select the same section. Without a recognizable GitHub origin, an explicit `code.github.repository` in the repository file supplies the identity. Global settings, environment values, and `--tracker-repo` do not select a section. Outside a Git repository, or without either identity source, only home defaults apply.

Only the matching section contributes values. All sections are validated, including unmatched ones; duplicate identities differing only in case are rejected. The repository file may also hold `[repository."owner/name"]` sections, but only their `[agents]` and `[skills]` tables: in either file, those tables are that repository's capability layer, applied to the work of a delivery task in that repository (see `pdlc guide capabilities`).

Values override per key; scripts replace rather than concatenate, and capability slots merge per slot. To suppress an inherited init script, set `init_script = ""` in the repository file. `prepare` runs the effective script only after creating a new worktree, subject to its normal confirmation or `--yes`; an existing worktree skips it. `pdlc doctor` reports which home section supplied each effective setting.

## Minimal configurations

GitHub (the default tracker), issues and pull requests in this checkout's repository:

```toml
[tracker.github]
project_number = "7"
project_owner  = "my-org"
```

A shared GitHub tracker, from one of several service repositories:

```toml
[tracker.github]
repository     = "my-org/product"
project_number = "7"
project_owner  = "my-org"
```

Azure Boards work items with GitHub code:

```toml
[tracker]
provider = "azure"

[tracker.azure]
organization = "https://dev.azure.com/my-org"
project      = "my-project"

[code]
provider = "github"
```

Local file tracker, for scenarios and tests:

```toml
[tracker]
provider = "file"
```

The `repository` keys are omitted above where they are derived from the checkout's `origin` remote; set them explicitly when that remote is not a github.com URL, or when pull requests belong to a repository other than `origin` (a fork's upstream).

## `[tracker]`

| Key | Required | Default | What it does |
|---|---|---|---|
| `provider` | Optional | `github` | Where work items live: `github`, `azure`, or `file`. Selects which `[tracker.*]` table must be filled in. |

## `[tracker.github]`

| Key | Required | Default | What it does |
|---|---|---|---|
| `repository` | Required for the `github` tracker | Derived from `origin` | `owner/name` of the GitHub repository holding work-item Issues. |
| `project_number` | Required for the `github` tracker | — | Number of the GitHub Project that tracks PDLC state. |
| `project_owner` | Required for the `github` tracker | — | User or organization that owns that Project. |
| `assigned_to` | Optional | Unset (no filter; new Issues assigned to the authenticated `gh` user) | Limits queue scans to Issues assigned to this login and assigns new records and tasks to it; `@me` resolves to the authenticated `gh` user. |

## `[tracker.azure]`

| Key | Required | Default | What it does |
|---|---|---|---|
| `organization` | Required for the `azure` tracker | — | Azure DevOps organization URL. |
| `project` | Required for the `azure` tracker | — | Azure DevOps project; also the reference label on evidence. |
| `record_type` | Optional | `Product Backlog Item` | Work-item type used for PDLC records. |
| `area_path` | Optional | Project root | Area path new records are created under; delivery tasks inherit their parent record's area path. |
| `open_state` | Optional | `To Do` | State written when a record opens. |
| `closed_state` | Optional | `Done` | State written when `pdlc post complete` closes a record. |
| `task_open_state` | Optional | `open_state` | Open state for delivery tasks, when their type uses a different vocabulary. |
| `task_closed_state` | Optional | `closed_state` | Closed state for delivery tasks. `Removed` and `Closed` always count as closed. |
| `task_removed_state` | Optional | `task_closed_state` | State for a descoped delivery task, e.g. `Removed` on Agile or Scrum; it counts as closed. |
| `task_in_progress_state` | Optional | Unset | Accepted but not currently used. |
| `assigned_to` | Optional | Signed-in `az` account | Limits queue scans to this identity and assigns new records and tasks to it; `@me` filters by the signed-in account. |

## `[code]`

| Key | Required | Default | What it does |
|---|---|---|---|
| `provider` | Optional | `github` for the `github` and `file` trackers, `none` for `azure` | Where PRs live: `github`, `file`, or `none`. Set `github` to pair an Azure tracker with GitHub PRs. |
| `pr_title_format` | Optional | The task title | Format for task PR titles. Placeholders: `{task.title}` (id prefix and `[CORE]`/`[UI]` tag stripped), `{task.id}`, `{work.number}`, `{work.type}`, `{work.ref}`. |
| `pr_attachment` | Optional | Unset | Line appended to every task PR body. `{work.number}` resolves to the parent work item number; `{work.ref}` to a reference that links it from the code repository: `#N` when the tracker is the same GitHub repository, `owner/name#N` for another GitHub repository, `AB#N` for Azure Boards. |

## `[code.github]`

| Key | Required | Default | What it does |
|---|---|---|---|
| `repository` | Required when `[code] provider` is `github` | Derived from `origin`, else `[tracker.github] repository` | `owner/name` of the GitHub repository holding pull requests. Set it only when `origin` is not a github.com URL or pull requests are opened on another repository (a fork's upstream); `pdlc doctor` warns when it differs from `origin`. |
| `repositories` | Optional | The code repository alone | List of `owner/name` every repository a delivery task's `**Repository:**` line may name, in addition to the code repository, which is always allowed; `pdlc post tasks` refuses any other. `pdlc doctor` checks access to each. |

## `[code.github.checkouts]`

Home-only; a table of `"owner/name" = "path"` mapping each repository in `[code.github] repositories`, other than the code repository, to the local clone its delivery tasks are worked in. Each path must be absolute or start with `~`. `pdlc doctor` warns about a listed repository with no mapping or a missing folder.

## `[attachments]`

| Key | Required | Default | What it does |
|---|---|---|---|
| `provider` | Optional | `file` | `file` stores `--attachment` files locally (see `pdlc guide attachments`); `none` rejects any `--attachment`. |

## `[runtime]`

| Key | Required | Default | What it does |
|---|---|---|---|
| `home` | Optional | `.pdlc` in the working directory | Store root for the file tracker and local attachments. Same as `PDLC_HOME`. |
| `actor` | Optional | `local` | Actor name the file tracker records on evidence. |
| `ref_label` | Optional | `pdlc` | Reference label the file tracker uses on evidence. |

## `[cache]`

| Key | Required | Default | What it does |
|---|---|---|---|
| `root` | Optional | `repository_default` | Parent of `.pdlc/cache/<workitem>/` for generated inspector reports and prompt briefs. `repository_default` uses the repository root; `global_default` uses the user's home. A custom absolute path uses that directory; a relative path is resolved from the repository root. Files have random suffixes, so use the path printed by the CLI. Briefs without a work item use `new` or `review` in place of `<workitem>`. Short-lived GitHub/Azure request bodies use `unscoped` and are removed after the request. |

## `[workflow]`

Retry policy for `pdlc next loop` while no work item is actionable. The delay doubles after each empty attempt, capped at `max_delay_seconds`; CI monitoring uses its own fixed one-hour timeout and capped backoff.

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

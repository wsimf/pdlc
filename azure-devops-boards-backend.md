# Research: Azure DevOps Boards as a work-item backend

Goal: add Azure DevOps Boards + Repos as an alternative to the GitHub Issues/Projects backend, selected by `PDLC_BACKEND=azure` (plus `PDLC_CODE_HOST=azure`). GitHub stays the default. This is a feasibility + mapping study, not an implementation.

## Verdict

Feasible. Every port method has an `az` command or a thin `az devops invoke` / `az rest` REST call behind it. Two real friction points:

1. **PDLC's five state fields have no native home.** GitHub Projects gave us arbitrary single-selects (`Status`, `Gate State`, `Lifecycle`, `Skipped States`, `Slug`). Azure Boards has no project-level field layer — fields live on the work item and must be added through a customized (inherited) process. There is no `az` command to create fields; it is a one-time web-UI or Process REST step per org. Everything after that is normal `az boards work-item update -f`.
2. **No stacked-PR mechanism.** There is no `gh stack` equivalent. `submit_task_stack()` raises `PdlcError` on this host, same as the `file`/`none` hosts, and the stacked-implementation flow degrades to one shared PR (the linear path is still supported, through `attach_pr` on the record).

Everything else (hierarchy links, comments, body, queue scan, PR state, CI/policy rollup, actor) maps cleanly.

An earlier draft of this study assumed PDLC would carry its pull-request registry in `System.Description`, inheriting the machine-owned HTML-comment block the GitHub host uses — a real hazard, since Azure's rich-text handling can sanitize or reshape a comment and the failure would be silent. That is no longer how the port works. `WorkItemBackend.attach_pr` / `attached_prs` make PR storage each backend's own choice, so Azure uses native work-item↔PR links and never round-trips machine state through a rich-text field.

## Construct mapping

| PDLC concept | GitHub today | Azure DevOps | `az` surface |
|---|---|---|---|
| PDLC record | Issue | Work item, type **Product Backlog Item** (Scrum) / **User Story** (Agile) / **Issue** (Basic) — configurable via `PDLC_AZURE_RECORD_TYPE` | `az boards work-item create --type` |
| Record body | Issue body (Markdown) | `System.Description` field | `az boards work-item update -f "System.Description=@file"` * |
| Delivery task | Sub-issue | Child work item, type **Task**, linked parent→child | `az boards work-item create` + `az boards work-item relation add --relation-type parent` |
| Task identity | `WORK-<n>-TASK-NNN` title prefix + sub-issue link | Same title prefix + `System.LinkTypes.Hierarchy-Forward` link | title convention only; link via relation add |
| Task `pdlc:meta` block | HTML comment atop task body | Same, in child `System.Description` | field update |
| Evidence comment | Issue comment, `PDLC-<MARKER>` prefix | Work-item discussion comment, same prefix | write: `az boards work-item update --discussion`; read: `az devops invoke --area wit --resource comments` |
| `Status` (lifecycle stage) | Project single-select | Custom field `Custom.PdlcStatus` (picklist) | `az boards work-item update -f` |
| `Gate State` | Project single-select | Custom field `Custom.PdlcGateState` (picklist) | `az boards work-item update -f` |
| `Lifecycle` | Project single-select | Custom field `Custom.PdlcLifecycle` | `az boards work-item update -f` |
| `Skipped States` | Project text | Custom field `Custom.PdlcSkippedStates` (string) | `az boards work-item update -f` |
| `Slug` | Project text | Custom field `Custom.PdlcSlug` (string) | `az boards work-item update -f` |
| Blocker surface (`post_blocker`) | plain comment (no dedicated surface) | comment **+** tag `pdlc-blocked` via `System.Tags`, optionally `Microsoft.VSTS.CMMI.Blocked` | `--discussion` + `-f "System.Tags=pdlc-blocked; ..."` |
| Queue scan (`all_items`) | `gh project item-list` | WIQL flat query filtered to `Custom.PdlcSlug <> ''` | `az boards query --wiql` |
| Record resolution by number | GraphQL issue lookup | `az boards work-item show --id` | direct |
| Record resolution by slug | Project item scan | WIQL `WHERE [Custom.PdlcSlug] = '<slug>'` | `az boards query --wiql` |
| `current_actor` | `gh api user` → login | signed-in account UPN | `az account show --query user.name -o tsv` (or `az devops user show --user <upn>`) |
| `ref_label` | repo name | Azure project name | from config |
| Pull request | `gh pr` | `az repos pr` | see code-host section |
| PR ↔ record link | machine-owned block in the Issue body | native `ArtifactLink` work-item relation | `az repos pr create --work-items <id>`, or `az boards work-item relation add --relation-type "ArtifactLink"` |
| CI / checks rollup | `statusCheckRollup` on head commit | PR **policy evaluations** (build policies included) | `az repos pr policy list --id` |
| Stacked PRs | `gh stack` extension | none — `submit_task_stack` raises | n/a |
| Attachments | file attachment host / issue | no `az` attachment cmd; `az devops invoke --area wit --resource attachments` or keep `PDLC_ATTACHMENT_HOST=file` | REST only |

\* `System.Description` is HTML on legacy orgs and migrated fields; Markdown is supported on work items created after the 2024–25 Markdown rollout and when the field is Markdown-enabled in the process. The comments API returns `text` (Markdown) plus `renderedText` (HTML) — read `text`. If an org is HTML-only, the backend must convert on write/read or document the limitation. **Confirm the target org's field format during `pdlc setup`.**

This is a rendering-fidelity concern, not a correctness one. Bodies crossing the port are human-authored content only, so a lossy HTML round trip degrades how a body reads — it cannot silently destroy machine state. That was not true before `attach_pr` moved PR storage behind the port.

### Work-item-type note

The record type depends on the project's process (Basic / Agile / Scrum / CMMI). Make it configurable (`PDLC_AZURE_RECORD_TYPE`, default resolved from the process) rather than hardcoding "Product Backlog Item". Delivery tasks are always type `Task` with a parent link, matching the "sub-issue" semantics.

## Port-by-port feasibility

### `WorkItemBackend` (`src/pdlc/hosts/workitem_host/base.py`)

| Method | Azure implementation |
|---|---|
| `resolve(ref)` | numeric → `az boards work-item show --id <ref> --expand all`; slug → WIQL then show. Map `System.Description`→`issueBody`, custom fields→`Status`/`Gate State`/`Lifecycle`/`Skipped States`/`Slug`, build `content{number,title,url}`, and read `relations[]` `ArtifactLink` entries into `prs`. |
| `queue_items()` | `az boards query --wiql "SELECT [System.Id] FROM workitems WHERE [Custom.PdlcSlug] <> '' AND [System.TeamProject] = @project"` → then batch `az boards work-item show` (or `az devops invoke --area wit --resource workitemsbatch`). Must return the `QueueItemSummary` shape, not raw work items. |
| `set_state(id, status, gate, lifecycle)` | one `az boards work-item update --id <id> -f "Custom.PdlcStatus=<status>" "Custom.PdlcGateState=<gate>" "Custom.PdlcLifecycle=<lifecycle>"` — atomic in a single PATCH, better than GitHub's 3-mutation dance. |
| `set_gate` / `set_slug` / `set_skipped_states` | single-field `--fields` update. |
| `write_body(ref, body)` | `az boards work-item update --id <id> -f "System.Description=<body>"` (pass via file/`@`), or `az devops invoke ... --http-method PATCH --in-file` with a JSON-Patch doc for large bodies. |
| `comments(ref)` | `az devops invoke --area wit --resource comments --route-parameters project=<p> workItemId=<id> --api-version 7.1-preview.4 --query-parameters '$top=200' order=asc`. Paginate on `continuationToken`. Map `{text→body, createdBy.uniqueName→author.login, createdDate→createdAt, url}`. |
| `post_comment(ref, body)` | `az boards work-item update --id <id> --discussion "<body>"`. Returns the work item; synthesize a comment ref from the response or re-read the latest comment. |
| `post_blocker(ref, body)` | `post_comment` + add `pdlc-blocked` to `System.Tags` (read-modify-write the semicolon list). The `Decision Required` gate remains the machine signal, matching the GitHub host's comment. |
| `tasks(ref)` | children: WIQL `WHERE [System.Parent] = <id>` (or parse `relations[].rel == "System.LinkTypes.Hierarchy-Forward"` from `--expand relations`), then batch-show. Map `state`: Azure `System.State` → `OPEN`/`CLOSED` (Closed/Done/Removed → `CLOSED`). Parse `taskId` from title, and fill `prs` from each child's `ArtifactLink` relations so a queue scan does not need a call per task. |
| `tasks_by_number(numbers)` | batch `az boards work-item show` preserving order. |
| `upsert_tasks(parent, tasks, existing)` | match by `taskId` parsed from existing child titles. Create missing: `az boards work-item create --type Task --title "WORK-<p>-TASK-NNN <title>"` then `az boards work-item relation add --id <child> --relation-type parent --target-id <parent>`. Update changed: `--title` / `-f System.Description`. Return `{action, taskId, number, title, url}` — identical shape. Idempotent by title identity, same as GitHub. |
| `close_task(ref)` | `az boards work-item update --id <ref> --state "Closed"` (or "Done" — process-dependent; resolve the closed-state name from the process, or make it config). |
| `attach_pr(ref, n)` | `az repos pr update` cannot add links, so PATCH an `ArtifactLink` relation: `az devops invoke --area wit --resource workitems --http-method PATCH` with `{"op":"add","path":"/relations/-","value":{"rel":"ArtifactLink","url":"vstfs:///Git/PullRequestId/<project>%2F<repoId>%2F<n>","attributes":{"name":"Pull Request"}}}`. Idempotent: read relations first and skip when present. At creation time `az repos pr create --work-items <id>` does the same thing in one step. |
| `attached_prs(ref)` | `az boards work-item show --id <ref> --expand relations` → parse `PullRequestId/<project>/<repo>/<n>` out of each `ArtifactLink` url. Native, queryable, visible in the work item's Development section, and legible to people who have never heard of PDLC. |
| `create(title, body, slug, work_type)` | `az boards work-item create --type <record type for work_type> --title <title> -f "System.Description=<body>" "Custom.PdlcSlug=<slug>"`. Returns `{id: "AZURE-<id>", number: <id>, url}`. No separate "add to project" step — a work item is already on its board. Unlike GitHub, `WorkType.BUG` maps natively to the process's `Bug` type instead of raising. |
| `current_actor()` | `az account show --query user.name -o tsv`. |
| `ref_label()` | Azure project name from config. |

`capabilities`: `{"subissue_graph", "queue_scan"}` — the same pair GitHub and the file backend declare. Parent/child hierarchy links are real, first-class, and queryable (`System.Parent`), so the graph capability holds exactly as GitHub sub-issues do.

### `CodeHost` (`src/pdlc/hosts/code_host/base.py`)

| Method | Azure implementation |
|---|---|
| `ensure_pull_request_linked(code_ref)` | `az repos pr list --source-branch <current branch> --status active -o json` → first result. If none, the caller already treats that as "no PR". `code_ref` = the Azure repo name (or unused). |
| `pull_requests_by_number(numbers)` | `az repos pr show --id <n>` each. Map `{pullRequestId→number, title, url (build from repo web url + /pullrequest/<n>), status→state (active/completed/abandoned → OPEN/MERGED/CLOSED), isDraft, sourceRefName→branch (strip refs/heads/), closedDate/completionQueueTime→mergedAt, checks←policy rollup}`. |
| `pull_request_files(pr)` | no `az` command. Use `az repos pr show` to get `lastMergeSourceCommit` + `lastMergeTargetCommit`, then local `git diff --name-only <target>...<source>`. Fallback: `az devops invoke --area git --resource pullRequestIterationChanges`. |
| `submit_task_stack()` | `raise PdlcError("Azure DevOps has no stacked-PR mechanism; use the linear implementation flow")`. |

**CI mapping detail:** `az repos pr policy list --id <n> -o json` returns one entry per policy with `status` ∈ `queued|running|approved|rejected|notApplicable` and `configuration.type.displayName` (e.g. "Build"). Roll up to the existing `checks` vocabulary: any `rejected`→`FAILURE`, any `running|queued`→`PENDING`, all `approved`/`notApplicable` with ≥1 build→`SUCCESS`, none→`NONE`. This is a closer fit than GitHub's commit-status rollup and covers required-build gating.

### Attachment host

Keep `PDLC_ATTACHMENT_HOST=file` as the documented default for Azure users. Native work-item attachments need `az devops invoke --area wit --resource attachments` (upload → returns a URL → PATCH `AttachedFiles` relation) — a nice-to-have, not blocking.

## `az` CLI command reference (verified against current docs)

Setup / auth:

```bash
az extension add --name azure-devops
az devops configure --defaults organization=https://dev.azure.com/<org> project=<project>
# auth: az login  OR  az devops login (PAT on stdin)
```

Work items:

```bash
# create record
az boards work-item create --type "Product Backlog Item" --title "<title>" \
  -f "System.Description=<body>" "Custom.PdlcSlug=<slug>" -o json

# show (all fields + relations + links)
az boards work-item show --id <id> --expand all -o json

# update state fields atomically
az boards work-item update --id <id> \
  -f "Custom.PdlcStatus=Implementation" "Custom.PdlcGateState=Review Required" "Custom.PdlcLifecycle=<x>"

# add evidence comment
az boards work-item update --id <id> --discussion "PDLC-IMPLEMENTATION\n\n<body>"

# close a delivery task
az boards work-item update --id <child> --state "Closed"

# parent/child link
az boards work-item relation add --id <child> --relation-type parent --target-id <parent>
az boards work-item relation list-type -o table   # discover exact relation names

# queue scan / slug lookup (flat WIQL only)
az boards query --wiql "SELECT [System.Id] FROM workitems WHERE [Custom.PdlcSlug] <> ''" -o json
az boards query --wiql "SELECT [System.Id] FROM workitems WHERE [System.Parent] = <id>" -o json
```

Comments (read — no native `az boards` verb, issue Azure/azure-devops-cli-extension#1296):

```bash
az devops invoke --area wit --resource comments \
  --route-parameters project=<project> workItemId=<id> \
  --api-version 7.1-preview.4 --query-parameters '$top=200' order=asc -o json
# → { comments: [ { text, createdBy{uniqueName,displayName}, createdDate, url, commentId } ], continuationToken }
```

Pull requests:

```bash
az repos pr list --source-branch <branch> --status active -o json
az repos pr show --id <n> -o json
az repos pr create --repository <repo> --source-branch <b> --target-branch main \
  --title "<t>" --description "<d>" --work-items <recordId>
az repos pr policy list --id <n> -o json       # CI / build / approval policy evaluations
az repos pr set-vote --id <n> --vote approve   # reviewer verdict, if we ever drive it
```

Identity:

```bash
az account show --query user.name -o tsv
```

## Required one-time org customization (no `az` command)

Create an **inherited process** and add these fields to the PDLC record type and the Task type as needed:

| Field | Type | Allowed values |
|---|---|---|
| `Custom.PdlcStatus` | picklist | Product, UI, Tasks, Technical Plan, Implementation, Testing, Verification, Complete |
| `Custom.PdlcGateState` | picklist | Pending, Review Required, Changes Required, Decision Required, CI Pending, Approval Required, Approved, Stale |
| `Custom.PdlcLifecycle` | picklist | (existing Lifecycle vocabulary) |
| `Custom.PdlcSkippedStates` | text (single line) | free |
| `Custom.PdlcSlug` | text (single line) | free |

Done via Organization settings → Process, or the Process REST API (`_apis/work/processes/...`). `pdlc setup` should:
- detect `az` + `azure-devops` extension,
- ask for org URL / project / repo / record work-item type / description format (markdown|html),
- verify the five custom fields exist (`az boards work-item show` a probe, or `az devops invoke --area wit --resource fields`), and print the exact process-customization steps if not,
- write `[backend.azure]` to `.pdlc/config.toml`.

## Config surface

New `.pdlc/config.toml` block, mirroring `[backend.github]`:

```toml
[backend]
name = "azure"

[backend.azure]
organization = "https://dev.azure.com/acme"
project = "Platform"
repository = "platform-api"          # for the code host
record_type = "Product Backlog Item" # optional; resolved from process otherwise
description_format = "markdown"       # markdown | html
closed_state = "Closed"              # optional; process-dependent

[code_host]
name = "azure"

[attachment_host]
name = "file"
```

`config.py` additions: `PDLC_AZURE_ORG`, `PDLC_AZURE_PROJECT`, `PDLC_AZURE_REPOSITORY`, `PDLC_AZURE_RECORD_TYPE`, `PDLC_AZURE_DESCRIPTION_FORMAT`, `PDLC_AZURE_CLOSED_STATE`; extend `TOML_ENVIRONMENT_KEYS`, `validate_for_backend()` (require org+project when `backend == "azure"`), and the `get_backend()` / code-host selector dispatch.

## Implementation shape (when we do it)

New files, no changes to domain or command layers:

- `src/pdlc/hosts/azure_common.py` — `run_az`, `run_az_json`, `az_invoke` (REST), org/project args, JSON-Patch helper.
- `src/pdlc/hosts/azure_workitems.py` — WIQL, batch show, relation upsert (hierarchy and `ArtifactLink`), comment read/write (parallels `github_issues.py` + `github_project.py`).
- `src/pdlc/hosts/workitem_host/azure.py` — `AzureWorkItemBackend(WorkItemBackend)`.
- `src/pdlc/hosts/code_host/azure.py` — `AzureCodeHost(CodeHost)`.
- Wire `azure` into `workitem_host/__init__.py` and `code_host/__init__.py`.
- `tests/` — fixture-driven tests using recorded `az ... -o json` payloads, same pattern as the GitHub fixtures (`PDLC_ITEMS_FILE`-style hooks).

Estimated size: comparable to the existing GitHub host set (~3 host modules + tests). The domain, lifecycle, evidence, and command layers need **zero** changes — the port boundary already isolates all of this. `config.py`, `commands/setup.py`, and the capabilities/parity reference docs do change; count them in the estimate.

## Open questions for the driver

1. Which processes must we support day one — just Agile/Scrum, or Basic too? (Affects record-type and closed-state defaults.)
2. Are custom fields acceptable, or do we want a zero-customization mode that overloads `System.Tags` + `System.State` + `System.Description` front-matter? (Tags-only is uglier and loses single-value guarantees, but needs no org admin.)
3. Do we ever want PDLC to drive Azure PR votes / completion (`az repos pr set-vote`, `--auto-complete`), or stay read-only on the code host as today?
4. Half this surface (comments, attachments, PR file changes) falls through to `az devops invoke` anyway. Go REST-only for one error and JSON shape, or keep the mixed `az boards` / `az repos` / `invoke` transport for readability?

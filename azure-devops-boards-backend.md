# Azure DevOps Boards as a work-item backend

Goal: add Azure DevOps Boards as an alternative to the GitHub Issues/Projects work-item backend, selected by `PDLC_BACKEND=azure`. GitHub stays the default.

Scope decided with the driver: **work-item backend only**. The code host stays GitHub (`PDLC_CODE_HOST=github`) — Azure Boards paired with GitHub repos is the target setup, and `AzureCodeHost` is not being built. The code-host notes at the end are kept for whenever that changes.

**Implemented.** The backend ships as `PDLC_BACKEND=azure`; this document is now the design record behind it rather than a proposal. See `src/pdlc/hosts/lib/azure/transport.py`, `src/pdlc/hosts/lib/azure/workitems.py`, `src/pdlc/hosts/lib/azure/workitem_backend.py`, and `tests/test_azure_hosts.py`.

**Validated against a live org.** Everything below marked ✓ was run against `https://dev.azure.com/madushan92`, project `pdlc-scratch`, on an inherited process named `Kanban` (parent: Agile) with the six PDLC fields installed. Probe work items were created, exercised, and destroyed. Claims not marked ✓ are still inference.

## Verdict

Feasible, and simpler than the first draft assumed. Two friction points remain.

1. **The state fields need a one-time org-admin step.** Azure Boards has no project-level field layer; fields live on the work-item type and are added through a customized (inherited) process. This is out of PDLC's scope by decision — `pdlc setup` does not check, create, or explain the fields, and the backend treats them as a precondition. Admin instructions live in `README.md` under "Azure Boards fields". ✓
2. **No stacked-PR mechanism.** Irrelevant while the code host is GitHub — `gh stack` keeps working exactly as today. It only becomes a problem if an Azure Repos code host is ever built.

Everything else — hierarchy links, comments, bodies, queue scan, actor identity, PR attachment — maps cleanly and was confirmed live.

Two earlier concerns are now closed. An early draft assumed PDLC would carry its pull-request registry in `System.Description`, inheriting the machine-owned HTML-comment block the GitHub host uses; that was a real hazard, and it no longer applies because `WorkItemBackend.attach_pr` / `attached_prs` make PR storage each backend's own choice. The related fear that Azure's rich-text handling would mangle body content also did not reproduce — see "Description format" below.

## Decisions

| Question | Decision |
|---|---|
| State storage | Custom fields on an inherited process. Not tags, not a description block. |
| Who creates the fields | An org admin, once, out of band. PDLC never attempts it and never verifies it. |
| Code host pairing | GitHub repos + Azure Boards. `AzureCodeHost` is out of scope. |
| PR attachment storage | `Custom.PdlcPrs`, a space-separated number list. **Not** `ArtifactLink` — that relation type addresses Azure Repos PRs only and cannot reference a GitHub PR. |
| Transport | `az` CLI shell-out, mirroring the `gh` precedent, with `az devops invoke` for the one gap (reading comments). |
| Record work-item type | `User Story` (Agile-derived process), configurable. Delivery tasks are `Task`. |

## Construct mapping

| PDLC concept | GitHub today | Azure DevOps | `az` surface |
|---|---|---|---|
| PDLC record | Issue | Work item, type `User Story` (Agile) — configurable via `PDLC_AZURE_RECORD_TYPE` | `az boards work-item create --type` ✓ |
| Record body | Issue body (Markdown) | `System.Description`, format `Markdown` set at creation | create: `az devops invoke` + `multilineFieldsFormat` op; update: `az boards work-item update -f` ✓ |
| Delivery task | Sub-issue | Child work item, type `Task`, linked parent→child | `az boards work-item create` + `az boards work-item relation add --relation-type parent` ✓ |
| Task identity | `WORK-<n>-TASK-NNN` title prefix + sub-issue link | Same title prefix + `System.LinkTypes.Hierarchy-Forward` | title convention only; link via relation add ✓ |
| Evidence comment | Issue comment, `PDLC-<MARKER>` prefix | Work-item discussion comment, same prefix, `format=markdown` | read **and** write: `az devops invoke --area wit --resource comments` ✓ |
| `Status` (lifecycle stage) | Project single-select | `Custom.PdlcStatus` (picklist) | `az boards work-item update -f` ✓ |
| `Gate State` | Project single-select | `Custom.PdlcGateState` (picklist) | `az boards work-item update -f` ✓ |
| `Lifecycle` | Project single-select | `Custom.PdlcLifecycle` (picklist) | `az boards work-item update -f` ✓ |
| `Skipped States` | Project text | `Custom.PdlcSkippedStates` (string) | `az boards work-item update -f` ✓ |
| `Slug` | Project text | `Custom.PdlcSlug` (string) | `az boards work-item update -f` ✓ |
| Attached PRs | machine-owned block in the Issue body | `Custom.PdlcPrs` (string), space-separated; on both `User Story` and `Task` | `az boards work-item update -f` ✓ |
| Blocker surface (`post_blocker`) | plain comment (no dedicated surface) | plain comment, same as GitHub | `--discussion` ✓ |
| Queue scan (`queue_items`) | `gh project item-list` | one flat WIQL selecting every needed field | `az boards query --wiql` ✓ |
| Record resolution by number | GraphQL issue lookup | `az boards work-item show --id` ✓ | direct |
| Record resolution by slug | Project item scan | WIQL `WHERE [Custom.PdlcSlug] = '<slug>'` ✓ | `az boards query --wiql` |
| `current_actor` | `gh api user` → login | signed-in account UPN | `az account show --query user.name -o tsv` ✓ |
| `ref_label` | repo name | Azure project name | from config |
| Pull request / CI | `gh pr` | unchanged — GitHub code host | n/a for this backend |

### Description format

Content is stored byte-exact in both directions — no sanitization, no `<div>` wrapping, no newline conversion, in the create response and on an independent re-read: ✓

```
wrote: "## Product\n\nShip **retries**.\n"
read : "## Product\n\nShip **retries**.\n"
```

Rendering is a separate matter. Large text fields written through the API default to **HTML**, so the Azure UI shows `##` and `-` as literal punctuation and collapses blank lines. Markdown for large text fields went GA in July 2025 and is selected per work item, per field, by an extra JSON Patch operation: ✓

```json
{"op": "add", "path": "/multilineFieldsFormat/System.Description", "value": "Markdown"}
```

Two properties make this cheap, both confirmed live: the choice is **sticky** (a later `az boards work-item update -f "System.Description=…"` preserves it) and **per work item**, so it is made once at creation and never thought about again. It is also one-way, which costs nothing here — PDLC only ever reads and writes work items it created itself.

`az boards work-item create` cannot set it: the CLI extension contains no reference to `multilineFieldsFormat` at all, and the feature request is open and unassigned. Creation therefore goes through `az devops invoke`, which reaches the create route natively. Everything else — `write_body`, every field update — stays on `az boards work-item update`, because the format sticks.

Comments carry their own format, per comment, and are **not** sticky. `az boards work-item update --discussion` posts `format=html`; the comments POST with `format=markdown` posts Markdown and returns a populated `renderedText`. So every evidence comment takes the invoke path too. ✓

This replaces what would otherwise have been a Markdown→HTML conversion layer at the port boundary — which would have been lossy on the read side and put `splice_section` at risk of corrupting approved upstream sections.

## Port-by-port

### `WorkItemBackend` (`src/pdlc/hosts/workitem_host/base.py`)

| Method | Azure implementation |
|---|---|
| `resolve(ref)` | numeric → `az boards work-item show --id <ref>`; slug → WIQL then show. Map `System.Description`→`issueBody`, custom fields→`Status`/`Gate State`/`Lifecycle`/`Skipped States`/`Slug`, `Custom.PdlcPrs`→`prs`, build `content{number,title,url}`. ✓ |
| `queue_items()` | **One** WIQL call. `az boards query` returns exactly the fields named in `SELECT`, so no follow-up batch show is needed — the first draft's query-then-batch-show was wrong. ✓ |
| `set_state(id, status, gate, lifecycle)` | one `az boards work-item update -f "Custom.PdlcStatus=…" "Custom.PdlcGateState=…" "Custom.PdlcLifecycle=…"` — atomic in a single PATCH, better than GitHub's 3-mutation dance. ✓ |
| `set_gate` / `set_slug` / `set_skipped_states` | single-field `-f` update. ✓ |
| `write_body(ref, body)` | `az boards work-item update -f "System.Description=<body>"`. No registry to preserve — bodies are human content only. ✓ |
| `comments(ref)` | `az devops invoke --area wit --resource comments --route-parameters project=<p> workItemId=<id> --api-version 7.1-preview`. Map `{text→body, createdBy.uniqueName→author.login, createdDate→createdAt}`. Paginate on `continuationToken`. ✓ |
| `post_comment(ref, body)` | comments POST via `az devops invoke` with `format=markdown` — `--discussion` would post HTML. Returns the created comment, so the reference is a `?discussionId=<id>` deep link. ✓ |
| `post_blocker(ref, body)` | `post_comment`, matching GitHub — the `Decision Required` gate is the machine signal and the `PDLC-DECISION` marker the human one. ✓ |
| `tasks(ref)` | WIQL `WHERE [System.Parent] = <id>`, selecting title/state/description/`Custom.PdlcPrs` in the same call, plus one comment read per task, issued concurrently. Map `System.State` → `OPEN`/`CLOSED` (`Closed`/`Removed` → `CLOSED`). Parse `taskId` from the title. ✓ |
| `tasks_by_number(numbers)` | `az boards work-item show` per id, preserving order. |
| `upsert_tasks(parent, tasks, existing)` | match by `taskId` parsed from existing child titles. Create missing with `az boards work-item create --type Task --title "WORK-<p>-TASK-NNN <title>"`, then `relation add --relation-type parent`. Idempotent by title identity, same as GitHub. ✓ |
| `close_task(ref)` | `az boards work-item update --id <ref> --state "Closed"`. `Task` states on an Agile-derived process are `New`/`Active`/`Closed`/`Removed`. ✓ |
| `attach_pr(ref, n)` | read `Custom.PdlcPrs`, union, sort, write back as a space-joined list. One field update; records and tasks both carry the field, so one implementation serves each. ✓ |
| `attached_prs(ref)` | read and split `Custom.PdlcPrs`. ✓ |
| `create(title, body, slug, work_type)` | `az devops invoke` POST to the create route with a JSON Patch document carrying the title, every field, and the `multilineFieldsFormat` op. All fields settable in the create call. No separate "add to project" step — a work item is already on its board. Unlike GitHub, `WorkType.BUG` could map natively to `Bug` instead of raising, once that pipeline is enabled. ✓ |
| `current_actor()` | `az account show --query user.name -o tsv`. Comments report the same identity as `createdBy.uniqueName`. ✓ |
| `ref_label()` | Azure project name from config. |

`capabilities`: `{"subissue_graph", "queue_scan"}` — the same pair GitHub and the file backend declare. Parent/child hierarchy links are real, first-class, and queryable via `System.Parent`. ✓

### Transport constraints

Four behaviours the implementation has to absorb, all confirmed live: ✓

- **Empty WIQL results return zero bytes, not `[]`.** `az boards query` with no matches exits 0 and prints nothing, so a naive `json.loads` raises. `run_az_json` must treat empty stdout as an empty result. This would otherwise fail on the first empty queue scan.
- **`az devops invoke` rejects numeric preview suffixes.** `--api-version 7.1-preview.4` fails with `could not convert string to float: '7.1.4'`; bare `7.1-preview` works, and plain `7.1` is refused because the resource is preview-only. The first draft prescribed `7.1-preview.4`, which cannot work.
- **Picklist values are validated server-side**, with a clear message: `The field 'PdlcGateState' contains the value 'Bogus Gate' that is not in the list of supported values`. Surface it as a `PdlcError` unchanged — it names the field and the value, matching GitHub's `no option 'X' on Project field 'Y'`.
- **`az devops invoke` cannot update a work item by id.** Two `wit`/`workItems` routes share a resource name at identical `maxVersion 7.2` (`{project}/_apis/wit/workitems/${type}` and `.../{id}`), and the extension picks the highest version with the first entry winning ties — always the create route, failing with `KeyError: 'type'`. Creation is reachable; update by id is not. That shapes where the format op goes, and nothing else — every other write already had a first-class `az boards` verb.
- **`az devops invoke` is slow.** It re-fetches the organization's resource areas and resource locations on every call (`force=True`, and each call is its own process, so nothing caches), costing ~1.3s before the real request — measured 1.78s against 0.48s for an equivalent `az boards` verb. Reads that fan out over tasks are issued concurrently for this reason; single calls just pay it.
- **Raw REST needs a PAT.** A bearer token from `az account get-access-token` gets a 302 redirect to sign-in on org-scoped endpoints, including ones the CLI calls happily. The `az` CLI authenticates by a different path. This is why the transport is CLI shell-out rather than REST.

- **WIQL will select `System.Description`.** It is a long-text field, which WIQL rejects in some filters, but it comes back fine in a `SELECT`. This matters: without it, `tasks()` reports every task body as empty and `upsert_tasks` rewrites every task on every pass instead of reporting `unchanged`. Found by an idempotency check against the live board.

Also: `az devops configure --defaults` is deliberately not used. Every call passes `--organization` and `--project` explicitly so nothing depends on ambient machine state.

## Required one-time org customization

No `az` command exists for this, and `az devops invoke` cannot reach the relevant areas — `processes`, `processAdmin`, and `processDefinitions` all appear in its own resource listing but return `--area is not present in current organization`. ✓ Portal or PAT-authenticated REST only.

By decision, this is entirely an admin's job and PDLC has no part in it. The field list, types, exact option values, and verification commands live in `README.md` under "Azure Boards fields" — that is the single source of truth; do not duplicate it here.

Summary for orientation only: six fields on the record type (`PdlcStatus`, `PdlcGateState`, `PdlcLifecycle`, `PdlcSkippedStates`, `PdlcSlug`, `PdlcPrs`) and one on `Task` (`PdlcPrs`). Azure derives the `Custom.` prefix from the display name automatically. ✓

## `az` command reference (verified live)

```bash
# auth / prerequisites
az extension add --name azure-devops
az login                       # or: az devops login   (PAT on stdin)

# create record — via invoke, so the description renders as Markdown.
# `az boards work-item create` cannot set multilineFieldsFormat, and the
# choice is one-way, so a work item created that way renders literally forever.
az devops invoke --organization <org> --area wit --resource workitems \
  --route-parameters project=<proj> type="User Story" \
  --http-method POST --media-type application/json-patch+json \
  --in-file patch.json --api-version 7.1 -o json
# patch.json:
# [ {"op":"add","path":"/fields/System.Title","value":"<title>"},
#   {"op":"add","path":"/fields/System.Description","value":"<body>"},
#   {"op":"add","path":"/fields/Custom.PdlcSlug","value":"<slug>"},
#   {"op":"add","path":"/multilineFieldsFormat/System.Description","value":"Markdown"} ]

# show (fields + relations)
az boards work-item show --organization <org> --id <id> -o json

# update state fields atomically
az boards work-item update --organization <org> --id <id> \
  -f "Custom.PdlcStatus=Implementation" "Custom.PdlcGateState=Review Required" \
     "Custom.PdlcLifecycle=Planning"

# attach a pull request
az boards work-item update --organization <org> --id <id> -f "Custom.PdlcPrs=148 152"

# evidence comment (write) — format=markdown; --discussion would post HTML
az devops invoke --organization <org> --area wit --resource comments \
  --route-parameters project=<proj> workItemId=<id> \
  --query-parameters format=markdown \
  --http-method POST --in-file comment.json --api-version 7.1-preview -o json
# comment.json: {"text": "PDLC-IMPLEMENTATION\n\n<body>"}

# evidence comments (read) — no native az verb
az devops invoke --organization <org> --area wit --resource comments \
  --route-parameters project=<proj> workItemId=<id> \
  --api-version 7.1-preview -o json
# → { comments: [ { id, text, renderedText, createdBy{uniqueName,displayName}, createdDate } ] }

# close a delivery task
az boards work-item update --organization <org> --id <child> --state "Closed"

# parent/child link
az boards work-item relation add --organization <org> \
  --id <child> --relation-type parent --target-id <parent>

# queue scan — one call, returns exactly the selected fields
az boards query --organization <org> --project <proj> --wiql \
  "SELECT [System.Id],[System.Title],[Custom.PdlcStatus],[Custom.PdlcGateState],\
          [Custom.PdlcLifecycle],[Custom.PdlcSkippedStates],[Custom.PdlcSlug] \
   FROM workitems WHERE [Custom.PdlcSlug] <> '' AND [System.TeamProject] = '<proj>'" -o json

# children of a record
az boards query --organization <org> --project <proj> --wiql \
  "SELECT [System.Id] FROM workitems WHERE [System.Parent] = <id>" -o json

# identity
az account show --query user.name -o tsv

# confirm field bindings per work-item type
az devops invoke --organization <org> --area wit --resource workitemtypes \
  --route-parameters project=<proj> --api-version 7.1 -o json
```

## Config surface

```toml
[backend]
name = "azure"

[backend.azure]
organization = "https://dev.azure.com/madushan92"
project      = "pdlc-scratch"
record_type  = "User Story"   # optional; default for an Agile-derived process
closed_state = "Closed"       # optional; process-dependent
assigned_to  = "@me"          # optional; queue scan returns only your records

[code_host]
name = "github"               # Azure Boards + GitHub repos

[backend.github]
repository = "OWNER/REPOSITORY"   # still required by the GitHub code host

[attachment_host]
name = "file"
```

`assigned_to` (`PDLC_AZURE_ASSIGNED_TO`) is optional and inactive unless set. When set, `records()` appends `AND [System.AssignedTo] = <value>` to the queue-scan WIQL — `@me` becomes the `@Me` macro, any other value is matched literally against the assignee display name or unique name. A single `--work-item` lookup is unaffected.

`config.py` additions: `PDLC_AZURE_ORG`, `PDLC_AZURE_PROJECT`, `PDLC_AZURE_RECORD_TYPE`, `PDLC_AZURE_CLOSED_STATE`, `PDLC_AZURE_ASSIGNED_TO`; extend `TOML_ENVIRONMENT_KEYS`, extend `validate_for_backend()` to require org + project when `backend == "azure"` while still requiring `repository` for the GitHub code host, and extend the `get_backend()` dispatch.

No `description_format` key: the round-trip is faithful either way, so there is nothing to configure.

## Implementation shape

- `src/pdlc/hosts/lib/azure/transport.py` — `run_az`, `run_az_json` (empty-stdout tolerant), `az_invoke`, org/project args.
- `src/pdlc/hosts/lib/azure/workitems.py` — WIQL, work-item show/update, relation add, comment read/write (parallels `github_issues.py` + `github_project.py`).
- `src/pdlc/hosts/lib/azure/workitem_backend.py` — `AzureWorkItemBackend(WorkItemBackend)`.
- Wire `azure` into `workitem_host/__init__.py`.
- `commands/setup.py` — an `azure` branch. The wizard used to assume the backend and code host shared a vendor; the code-host prompt is now its own step (`_code_host`) that every backend runs, and `_write_config` emits a repository-only `[backend.github]` table when an Azure board is paired with GitHub repos.
- `tests/_az_replay.py` + tests — a FakeAz router mirroring `tests/_gh_replay.py`, so the suite stays fully offline. Live-org runs confirm real behaviour; they are not part of CI.

The domain, lifecycle, evidence, and command layers needed **zero** changes — the port boundary already isolated all of this, and it held. `config.py`, `commands/setup.py`, `README.md`, and the capabilities/parity reference docs do change; count them in the estimate.

## Deferred: Azure Repos code host

Not being built. Kept for reference if the pairing ever changes.

| Method | Azure implementation |
|---|---|
| `ensure_pull_request_linked(code_ref)` | `az repos pr list --source-branch <branch> --status active -o json` → first result. |
| `pull_requests_by_number(numbers)` | `az repos pr show --id <n>`. Map `{pullRequestId→number, status→state (active/completed/abandoned → OPEN/MERGED/CLOSED), isDraft, sourceRefName→branch, closedDate→mergedAt, checks←policy rollup}`. |
| `pull_request_files(pr)` | no `az` command. `az devops invoke --area git --resource pullRequestIterationChanges`, or `az repos pr show` for the merge commits then a local `git diff --name-only` (needs both commits fetched). |
| `submit_task_stack()` | raise — no `gh stack` equivalent. |

CI rollup: `az repos pr policy list --id <n>` returns one entry per policy with `status` ∈ `queued|running|approved|rejected|notApplicable`. Map any `rejected`→`FAILURE`, any `running|queued`→`PENDING`, all `approved`/`notApplicable` with ≥1 build→`SUCCESS`, none→`NONE`.

If that host is ever built, `attach_pr` should keep using `Custom.PdlcPrs` rather than switching to `ArtifactLink`, so one backend does not store the same fact two ways depending on the code host.

## Open questions

Settled during implementation:

- **Body rendering.** Descriptions and comments are marked `Markdown` at creation, so the Azure UI renders them properly and no conversion layer is needed. See "Description format".
- **Blocker surface.** `post_blocker` posts a plain comment, exactly as GitHub does. The `Decision Required` gate is the machine signal and the `PDLC-DECISION` marker the human one, so a `pdlc-blocked` tag would be a second place to keep in sync with no reader that needs it. Revisit if someone wants a board filter for parked records.

Still open:

1. Attachments: keep `PDLC_ATTACHMENT_HOST=file`, or implement native work-item attachments (`az devops invoke --area wit --resource attachments`) later?
2. `tasks()` still costs one comment read per delivery task, where GitHub gets them in a single GraphQL query — Azure has no batch comments API. The reads now run concurrently (bounded at 8), so wall time is flat rather than linear up to that width, but a record with many dozens of tasks would start queueing behind the bound.

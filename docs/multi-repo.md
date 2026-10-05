# Multi-repository projects

Status: phases 1 and 2 implemented; phases 3 and 4 planned. The background investigation is in `multi-repo-implement-investigation.md` at the repository root.

## Goal

One PDLC work item can drive changes across several Git repositories — microservices, microfrontends, a shared library and its consumers — while a project that lives in one repository keeps working exactly as it does today. A single repository is the degenerate case of every rule below: wherever a repository is not named, it means the configured code repository.

## Model

- **Tracker**: where work items live (`[tracker] provider`: `github`, `azure`, or `file`). One tracker can serve many code repositories.
- **Code**: where pull requests live (`[code] provider`: `github`, `file`, or `none`). `[code.github] repository` is the repository this checkout's PRs belong to; it defaults to the checkout's `origin`, then to `[tracker.github] repository`.
- **Attachments**: where `--attachment` files live (`[attachments] provider`).
- **Pull-request ref**: a PR is identified by `owner/name#N`, never by its number alone, because two repositories can each have a `#148`.

`pdlc guide config` documents every key.

## Phase 1 — tracker and code are separate (implemented)

The configuration names the tracker and the code host independently, so each service checkout can point at a shared tracker while opening PRs in its own repository.

```toml
# api/.pdlc/config.toml — one of several service checkouts
[tracker.github]
repository     = "acme/product"
project_number = "7"
project_owner  = "acme"
```

- Issue calls (`gh issue …`, project and sub-issue GraphQL) use `[tracker.github] repository`; PR calls (`gh pr …`, review threads, PR GraphQL) use `[code.github] repository`.
- `[backend]`, `[code_host]`, and `[attachment_host]` were renamed to `[tracker]`, `[code]`, and `[attachments]`, each selected by `provider`. There is no backwards compatibility: an old table is an unknown-table error.
- The environment variable is `PDLC_TRACKER_REPOSITORY`; the global flags are `--tracker` and `--tracker-repo`.
- `{work.ref}` in `[code] pr_title_format` and `pr_attachment` renders a reference that links the work item from the PR: `#N` when tracker and code share a repository, `owner/name#N` across GitHub repositories, `AB#N` for Azure Boards.
- `pdlc doctor` warns when `[code.github] repository` differs from `origin`, since branch pushes and `gh stack` follow `origin`.

## Phase 2 — repository-qualified pull requests (implemented)

The PR registry on a work item and its delivery tasks stores `owner/name#N` refs, so a record shared by several repositories never confuses two PRs with the same number.

- `PullRef(number, repository)` in `src/pdlc/domain/records.py` is the one in-memory identity; `repository` is the casefolded `owner/name`, or `""` for code providers without repositories (`file`, `none`).
- Storage: the GitHub tracker's `<!-- pdlc:meta -->` block and Azure's `Custom.PdlcPrs` field hold space-separated `owner/name#N` tokens; the file tracker's `meta.json` `prs` array holds numbers for repository-less PRs and `owner/name#N` strings otherwise.
- Reading is tolerant: a bare `N` written before this phase reads as the configured code repository's PR (`Config.pull_request_repository()`), and the next write rewrites it qualified. Unparseable tokens are dropped, as before.
- The code host resolves each ref in its own repository: `pull_requests` groups refs into one GraphQL query per repository, and `pull_request_files`, `unresolved_review_comments`, `set_pull_request_content`, and `mark_pull_requests_ready` pass the ref's repository as `--repo`.
- `pdlc post attach-pr TASK PR` accepts `N`, `#N`, or `owner/name#N`.
- Output is unchanged for a single repository: JSON and YAML show a code-repository PR as its bare number and text shows it as `#N`; only a PR from another repository appears as `owner/name#N`. `internal.pull_requests` owns that rendering (`pr_label`, `prs_json`, `pr_output`).
- Skills and sub-agents needed no change. The `pr-fix` brief names the PR's own repository in `{{OWNER}}/{{REPO}}`.

Not yet multi-repository: `gh stack` still acts on the current checkout, so stack checkout and submission only make sense for PRs in the configured code repository (phase 3).

## Phase 3 — tasks that name their repository (planned)

- A delivery task body gains a `Repository: owner/name` field; omitted means the configured code repository.
- One `gh stack` per (work item, repository): checkout, submit, and `--after` linking run in that repository's checkout, and `stack.py` picks entry PRs only from refs in the task's repository.
- `pdlc inspect implement` and the briefs route each task to its repository's checkout; verification records a HEAD per repository (`{repository: HEAD}`) and claims use `repository:path`.
- `[code.github] repositories = [...]` lists the repositories a project spans, so planning can validate a task's `Repository:` and `pdlc doctor` can check access to each.

## Phase 4 — multi-repository workspaces (planned)

- A new `--repos` flag on `pdlc prepare` (for example `--repos api,web`) creates `<root>/<WORKITEM>/<repo>/`, one worktree per repository, plus a `.pdlc-workspace.toml` manifest naming each repository and its worktree.
- The home-only `[code.github.checkouts]` table maps `owner/name` to the local clone each worktree is created from.
- `--from` and `--after` are refused when several repositories are given; re-running with more repositories adds worktrees without touching existing ones; `pdlc cleanup` reads the manifest to tear every worktree down.
- Without `--repos`, `prepare` behaves exactly as today.

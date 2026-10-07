# Multi-repository projects

Status: phases 1, 2 and 3 implemented; phases 4 and 5 planned, with phase 4 superseding parts of phase 3. The background investigation is in `multi-repo-implement-investigation.md` at the repository root.

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

## Phase 3 — tasks that name their repository (implemented)

- A delivery task body gains a `Repository: owner/name` field; omitted means the configured code repository. Only the full `owner/name` form is accepted; short aliases may come later.
- One task is strictly one repository. Work that spans repositories is split into one task per repository joined by a dependency edge.
- `[code.github] repositories = [...]` lists the repositories a project spans, so planning can validate a task's `Repository:` and `pdlc doctor` can check access to each. It is optional, and the code repository is always included.
- Folder routing: a code-repository task is worked in the current checkout; any other task in the clone the home-only `[code.github.checkouts]` table maps its repository to (an absolute or `~` path), else it is refused. Git and `gh stack` run with that folder as cwd. Config anchors at the Git root's `.pdlc/config.toml`, or above it at a non-repository folder whose file sets `[code.github] repositories`. Checkout, `pdlc inspect implement`, and the briefs surface `repository:` and `path:` so the agent works in that folder.
- One `gh stack` per (work item, repository): checkout and submit run in that repository's checkout, and `stack.py` picks entry PRs only from refs in the task's repository.
- `pdlc prepare --after` is refused when `[code.github] repositories` lists more than one repository.
- Capability routing gains a per-repository layer: a skill or agent set for the task's repository overrides the global `[skills]` / `[agents]` slot, which still falls back to `general-purpose` or inline.
- Verification records a HEAD per repository (`{repository: HEAD}`) and claims use `repository:path`.
- Known limit: Testing still runs in the code repository only. `pdlc inspect test`, `pdlc post test`, and the test writer read and commit on the current checkout, so acceptance coverage for another repository's tasks is not committed there.

## Phase 4 — multi-repository workspaces (planned)

A work item spanning several repositories is worked in one workspace folder holding a worktree per repository. A single-repository work item keeps working exactly as it does today.

- `pdlc prepare WORKITEM --repos owner/a,owner/b` creates `<worktree.root>/<WORKITEM>/<repo-name>/`, one worktree per repository on a `pdlc/record-<WORKITEM>` branch, plus a `.pdlc-workspace.toml` manifest at the workspace root naming each repository and its worktree. It runs from any folder, since the repositories are passed in. Only the full `owner/name` form is accepted; short aliases may come later.
- Each worktree is created from the clone the home-only `[code.github.checkouts]` table maps its repository to. That table is the one list of repositories a developer can work in; `[code.github] repositories` is removed.
- `pdlc prepare WORKITEM` without `--repos` is unchanged: run from the repository's folder, it creates `<worktree.root>/<repo-name>/<WORKITEM>` from that repository.
- The agent runs from the workspace root. Config follows the existing hierarchy: the current folder's `.pdlc/config.toml` when there is one, else the home config alone, so a workspace root reads `~/.pdlc/config.toml`.
- In a workspace, every delivery task must carry a `**Repository:** owner/name` line naming one of the workspace's repositories; `pdlc post tasks` refuses a missing line or a repository outside the workspace, naming `pdlc prepare --repos` with that repository added as the fix. In a single repository the line stays optional and omitted means that repository.
- Folder routing reads the manifest: a task's Git and `gh stack` calls run in its repository's worktree, never in the developer's own clone, so two work items touching one repository never share a working tree.
- Capabilities stay per repository, set in the repository's config or the home config's `[repository."owner/name"]` section, as today.
- `--from` and `--after` are refused with `--repos`; re-running with more repositories adds worktrees without touching existing ones; `pdlc cleanup` reads the manifest to tear every worktree down.

Phase 3 pieces this supersedes: `[code.github] repositories` (the workspace's repositories replace it for task validation and `pdlc doctor`), config anchoring at a non-repository parent folder (the manifest marks the workspace), and routing tasks into the `[code.github.checkouts]` clone itself.

## Phase 5 — Testing per repository (planned)

Testing still runs in the code repository only (see phase 3's known limit). A workspace has no code repository at its root, so `pdlc inspect test`, `pdlc post test`, and the test writer need to run per repository, each committing coverage in that repository's worktree. Design to follow.

## Future

- A task naming a repository outside its workspace creates a worktree for that repository in the workspace, instead of being refused.
- Short repository aliases for `--repos` and `**Repository:**`.

## Open questions

- Repository-file capability sections: phase 3 lets a repository's own `.pdlc/config.toml` hold `[repository."owner/name".agents]` and `.skills` sections, where before only the home config could. Keep that, or revert to home-only? Undecided.

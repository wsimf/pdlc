# Multi-repo `pdlc implement` — preliminary blast-radius investigation

Status: investigation only. No decision, no design sign-off. Written to scope the
work before any `pdlc post write`.

## Scenario

One PDLC record (work item + delivery tasks) lives in a single "record repo" on
GitHub. Implementation happens in a **mono-repo-like folder layout**: sibling
folders under one working root, each folder its own independent Git repository
that the agent can `cd` into.

- 1 work item.
- Each delivery task lands in **exactly one** repo. Task 1 in repo A, task 2 in
  repo B.
- A task never spans two repos (see "Tasks that cross a repo boundary" below).
- Claude is launched from the working root; the PDLC skills and `.pdlc/config.toml`
  live there.

The single-repo case stays the default and is unchanged: if no task declares a
repo, everything resolves to the one configured repo exactly as today.

## What today's code assumes

`repository` is a single global scalar (`PDLC_REPOSITORY` / `[backend.github]
repository`) that is implicitly **both** the work-item host and the code host.
Pull-request references are **bare integers** everywhere. `gh stack` runs against
the current working directory and its remote. Verification freshness runs local
`git` in `Path.cwd()`.

## The two hard structural blockers

### 1. `gh stack` is single-repo, single-checkout

`submit_task_stack()`, `task_stack_setup()`, `stack_pr_numbers()` in
`src/pdlc/hosts/lib/github/code_host.py` delegate the whole stack — order, bases,
rebases, PR creation — to `gh stack` in the current directory. A stack cannot
span repos.

Multi-repo means **N independent stacks, one per repo**, each with its own entry
PR and its own local checkout. `stack_entry_pr()`
(`src/pdlc/internal/stack.py:23`) currently computes one linear predecessor chain
across *all* tasks; it must chain only within the same repo. Task 2 in repo B has
no stack predecessor even when task 1 in repo A is already implemented.

### 2. PR references are bare, repo-blind integers

- Registry stores `prs: 148 152` as plain ints in an HTML comment
  (`src/pdlc/hosts/lib/github/pr_registry.py`). `#148` in repo A collides with
  `#148` in repo B.
- `registered_pr_numbers()` returns `list[int]`; `record_pull_requests()`,
  `attach_pr`, the `PullRequest` record shape (`domain/records.py`),
  `task_pr_numbers` — none carry a repo dimension.
- `pull_requests_by_number`, `pull_request_files`, `mark_pull_requests_ready`,
  `set_pull_request_content` all pass `*repo_args()` from the single global
  `get_config().repository`.
- CI reconciliation (`pdlc post ci`) and `pdlc inspect verify` iterate that flat
  int list against one repo.

PR identity must become repo-qualified end to end (e.g. `owner/repo#148`). This
changes a **persisted format** (the registry HTML comment), so migration /
back-compat matters. Reading a bare `148` must still work.

## Blast radius by layer

| Layer | Files | Change |
|---|---|---|
| Config | `src/pdlc/config.py` (`repository` scalar, `PDLC_REPOSITORY`, `validate_for_backend`, `repository_root`, `config_path`), `commands/setup.py`, `cli.py` | Repo→path map; per-repo capability layer; config discovery must stop trusting cwd (see below). |
| Code-host port | `hosts/code_host/base.py`, `hosts/code_host/__init__.py` (`get_code_host()` singleton), `hosts/lib/github/code_host.py`, `hosts/lib/none/code_host.py`, `hosts/lib/file/`, `hosts/lib/github/transport.py` (`repo_args`, `owner_repository`) | `get_code_host(repo)`; every method that implies "the repo" takes a repo/cwd; `repo_args()` stops reading the global. |
| PR registry & record shape | `pr_registry.py`, `internal/pull_requests.py`, `domain/records.py`, `hosts/lib/github/workitem_backend.py` (`attach_pr`, `task_pr_numbers`) | PR identity becomes `repo#number`; touches serialization, all readers, the "code host returned fewer PRs than registry" guard. |
| Stack helpers | `internal/stack.py`, `commands/inspect_implement.py` (`_next_task_section` emits one `branch:` + one `stackSetup:`) | Per-repo entry PR; inspector emits `repo:` / `repoPath:` and a repo-scoped `stackSetup:`. |
| implement-task | `commands/post_implement_task.py` (`_submit_task_stack`, `ensure_pull_request_linked`) | Resolve the task's repo, run stack ops with explicit `cwd`, register a qualified PR. |
| Verification freshness | `internal/vcs.py` (all `subprocess` git in cwd), `domain/completion.py`, `domain/evidence.py` (`(Verified @ <sha>)` anchors are repo-blind SHAs), `commands/inspect_verify.py`, `commands/inspect_complete.py` | Each anchor records its repo; staleness check runs `git` in that repo's folder. Correctness-critical: a bare SHA is meaningless across repos. |
| CI gate | `commands/post_ci.py`, domain CI rollup | Reconcile check rollups across multiple repos' PRs. |
| Task schema / planning | `pdlc-task-planner`, `pdlc-tech-planner` sub-agents, `inspect task`, `internal/workitem.py` `task_tree`, task front matter | Tasks gain a `repo` field; planners assign it; `inspect task` surfaces it. |
| Skills & references | `agent/skills/pdlc-implement/SKILL.md` + `references/*`, `pdlc-loop`, `pdlc-test`, `pdlc-review`, `pdlc-verify`, `pdlc/references/{pdlc-contract,parity-contract,capabilities}.md` | All describe one branch / one stack / one `stackSetup:` line / one checkout. Substantial doc work. |
| Tests | `tests/` — code host, registry, stack, vcs, implement, ci, verify | Broad. |

## Config discovery and the cwd tension

`repository_root()` (`config.py:210`) walks up from `Path.cwd()` and stops at the
**first** `.git`. `config_path()` then expects `.pdlc/config.toml` there.

The moment a `pdlc` command runs with cwd inside a sub-repo, it resolves the
sub-repo as the root, fails to find `.pdlc/config.toml`, and either errors or
silently falls back to `~/.pdlc/config.toml`.

Direct conflict: `pdlc post implement-task` shells out to `gh stack`
(`post_implement_task.py:132`), which must run **inside the task's sub-repo**,
while config must come from the **working root**. Today those are the same
directory; here they are not.

Fix direction: PDLC stops inferring root from cwd. Anchor on an explicit marker —
walk up *past* nested `.git` dirs to the directory containing `.pdlc/config.toml`,
or an explicit `PDLC_ROOT`. Then every git / `gh` subprocess takes an explicit
`cwd=<repo path from the repo map>` instead of inheriting the process cwd. `pdlc`
itself stays cwd-independent and is driven entirely by the repo→path table.

## Skills and `AGENTS.md` / `CLAUDE.md` in this layout

The skill files and their discovery do not move — everything anchors at the
working root where Claude launches. What changes:

### Capability routing needs a per-repo layer

`[agents]` / `[skills]` capability slots (`config.py` `CAPABILITY_SLOTS`,
`get_capabilities()`) are currently **global**: one `core-implementer`, one
`build-run`, one `test-framework`. In this layout repo A might be Swift and repo B
a Vite app — one `test-framework` slot cannot serve both.

Sketch:

```toml
[repos.backend]
path = "services/backend"

[repos.backend.skills]
build-run = "swift-build"
test-framework = "swift-testing-expert"

[repos.web]
path = "apps/web"

[repos.web.skills]
build-run = "vite-dev"
test-framework = "vitest-runner"

[repos.web.agents]
ui-implementer = "web-ui-specialist"
```

`pdlc inspect capability` / `get_capabilities()` gain a repo argument; a task's
repo selects the layer, falling back to the global `[skills]` / `[agents]` table,
then to `general-purpose` / inline.

### Per-repo conventions are mostly free

Each sub-repo keeps its own `CLAUDE.md` / `AGENTS.md`. When `pdlc-implement`
dispatches the implementer sub-agent and tells it to `cd services/backend`, the
harness auto-loads that folder's `CLAUDE.md` / `AGENTS.md` as the agent reads
files under it — **provided the dispatch prompt names the folder and tells the
agent to stay in it**.

The one skill change that matters: `references/task-implementation-prompt.md`
gains a "Repository: `<path>` — work only in this folder, use its own build/test
commands" section, populated from the task's `repo` field and its capability
layer. `inspect implement` / `inspect task` must surface `repo:` and `repoPath:`.

The reviewer and verifier need the same repo pointer to run `git show` / diffs in
the right checkout — ties back to the repo-qualified `(Verified @ <sha>)` anchors.

## Tasks that cross a repo boundary

A single delivery task that must change two repos at once **does not work in this
model, and should not be made to**. The PDLC contract rests on *one delivery task
= one branch = one commit = one PR*, and a PR is repo-scoped. `pdlc post
implement-task` submits one stack and registers one task PR; the reviewer,
`pdlc-test-writer`, and the `(Verified @ <sha>)` anchor all assume a single commit
in a single repo.

Cross-repo work is decomposed into **two tasks with a dependency edge** — task 1
in repo A, task 2 in repo B `depends-on` task 1. That is already how PDLC expects
cross-cutting work to be split; the planner just assigns the repo per task. Keep
the "one task, one repo" rule hard and let dependencies handle boundaries.

## Assessment

Medium refactor, not a workflow redesign, concentrated in `hosts/lib/github/`,
`internal/{stack,vcs,pull_requests}.py`, `config.py`, and the implement / verify
skills. The "sibling git folders" framing removes the hardest part — multi-checkout
provisioning — because the folders already exist.

What is left:

1. A working-root config anchor + repo→path map; stop trusting cwd.
2. Thread an explicit `cwd` into every git / `gh` subprocess.
3. Repo-qualified PR identity end to end (persisted-format change → migration).
4. Per-repo stack chaining in `stack_entry_pr` and the inspector.
5. Per-repo capability-routing layer.
6. Repo-qualified verification anchors + checkout-aware staleness.
7. Skill / reference rewrites for the multi-stack, multi-checkout flow.

Recommended next step: decide the task data model (repo as a task attribute is the
assumption here), then a design note via `pdlc post write` before any code.

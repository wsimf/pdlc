# Mutation Recovery Catalog

Status: reference for `docs/transient-errors-plan.md`. Update this catalog with each mutation change.

## Purpose

Every write `pdlc` makes to a work-item host, code host, or local Git, in the order each command makes them, what a failure part-way leaves behind, and how to recover. This is the source for the `Recovery` each command registers with `set_recovery` (`src/pdlc/internal/failure.py`), which `pdlc` prints on exit 76. Update it together with any change to a command's write order.

## How to read this

- **Automatic retries come first.** Per `docs/transient-errors-plan.md`, `pdlc` retries each idempotent call, and any call that failed before its request was sent, at least once. The partial failures below are what is left when a retry is not safe or did not help. They surface as exit 76 with this entry's check and re-run steps, or as exit 75 when nothing had been written yet.
- **Writes** are listed in execution order. A failure at step *n* means steps 1..*n*−1 landed, step *n* may or may not have landed (a timed-out write can still succeed on the server), and nothing after it ran.
- **Check** is the read-only command that shows whether the command landed. `pdlc inspect N` shows the record's stage and gate, `pdlc inspect timeline N` lists `PDLC-*` marker comments newest-last, `pdlc inspect task T` shows a delivery task's state, plan, implementation comment, and PRs.
- **Re-run** says what happens if the exact same command is run again after a partial failure.
- Attachments (`--attachment`) are saved to the local attachment host before any remote write in every command. They are local file copies, so they are not listed per command; a re-run saves them again under new IDs, which is harmless.
- Backend differences are called out only where they change recovery. On GitHub, `set_state` is one GraphQL mutation that updates three Project fields; it already re-reads and retries once to reconcile. On Azure every field write is one `az boards work-item update`.

## Summary

| Command | Writes | Re-run after partial failure | Main risk |
| --- | --- | --- | --- |
| `post write` (new record) | Issue create → project add → state → slug → `PRODUCT` | **Unsafe**: creates a second Issue | Duplicate record |
| `post write --work-item` | slug? → body → `PRODUCT` → state | Safe; may duplicate `PRODUCT` | Duplicate evidence |
| `post write --patch` | body → `PRODUCT` → `PATCHED` → rewind or state | Mostly safe; may duplicate markers | Evidence without state move |
| `post tasks --stage UI` | state? → body → `UI` → state or patch | Safe; may duplicate `UI` | Duplicate evidence |
| `post tasks --stage Tasks` | state? → task upserts → reopen changed → descope comments and close/detach → `TASKS` → state or patch | Check each task after retry | A reopened task may retain stale evidence if failure interrupts its invalidation |
| `post plan` | state? → per-task plan comments → `PLAN` → state | Safe; may duplicate `PLAN` | Duplicate evidence |
| `post implement-task` | stack submit → PR edit → attach PR → implementation comment → close task | Safe by design | Stack conflict |
| `post implement` | stack submit → PRs ready → `IMPLEMENTATION` → state | Safe; may duplicate evidence | Duplicate evidence |
| `post test` | stack submit → attach PR → `TESTING` → state | Safe; may duplicate evidence | Duplicate evidence |
| `post review` | `REVIEW` → `DECISION`? → autoapprove or gate → CI? | Safe; may duplicate `REVIEW` | Duplicate review |
| `post escalate` | `DECISION` → gate | Safe; may duplicate `DECISION` | Duplicate blocker |
| `post decision` | per deferral: child record … → `RESOLUTION` → gate | Mostly safe; child creation is the risk | Duplicate child record |
| `post verify` | `REVIEW` → Open Questions append → `DECISION`? → bounce or gate → CI? | **Duplicates Open Questions lines** | Duplicate deferrals |
| `post ci` | `REVIEW` (red) or autoapprove or gate | Safe; may duplicate CI-failed `REVIEW` | Duplicate CI note |
| `post approve` | `APPROVED` → state | Safe; may duplicate `APPROVED` | Human-only; report instead |
| `post skip` | skipped states → `SKIPPED` | Safe; may duplicate `SKIPPED` | None |
| `post invalidate` | `INVALIDATED` → state → skipped states? → reopen tasks | **Check first**: re-run may refuse | Tasks left closed |
| `post complete` | `COMPLETE` → state → Open Questions → close Issue → prune branches | **Refuses after state lands** | Record Complete but still open |
| `post attach-pr` | attach PR | Safe | None |
| `next`, `continue` (heal) | heal comment → state | Safe; the next poll re-heals | Duplicate heal comment |
| `checkout` | `gh stack checkout`/`add`/`init` | Safe | Dirty tree, stack lock |

"May duplicate" means a re-run after the evidence comment landed but before the state change posts the same marker comment a second time. Readers take the newest marker, so the record reads correctly; the timeline just shows it twice. The comment-hash follow-up in the plan removes this.

## Per-command detail

### `pdlc post write` — new record

`pdlc post write --title T --slug S --body FILE --evidence FILE`

Writes:
1. `gh issue create` (Azure: `az boards work-item create`) with the whole body.
2. GitHub only: `gh project item-add` for the new Issue.
3. `set_state` → Product / Review Required.
4. `set_slug`.
5. `PDLC-PRODUCT` comment.

Partial failure:
- After 1, before 2 finishes (GitHub): an Issue exists but is not on the project, so `pdlc` cannot resolve it by number.
- After 2: the record exists and resolves, with no state, slug, or evidence.
- After 3 or 4: the record is at Product / Review Required with no `PDLC-PRODUCT` evidence.

Check: the error prints the new Issue URL once step 1 returns it; otherwise search for an open Issue with the exact title created in the last few minutes.

Recovery:
- If no Issue was created: re-run the same command.
- If an Issue was created: **do not re-run the create form** — it opens a second Issue. Re-run as `pdlc post write --work-item N --body FILE --evidence FILE`. The existing-record path treats a record with no stage as uninitialized, generates the slug if missing, and lands the evidence and state.
- If `pdlc inspect N` cannot resolve the new Issue (step 2 never ran): stop and ask the driver to add the Issue to the project, then continue as above.
- If step 4 ran after the `--work-item` re-run generated a slug from the title, the slug may differ from `--slug`. Report the difference.

### `pdlc post write --work-item N` — re-author an existing record

Writes:
1. If the gate is Review Required or Approval Required: `set_state` → Product / Stale (silent re-author reset).
2. If the record had no stage and no slug: `set_slug`.
3. `write_body` with the Product, Decisions, and Open Questions sections spliced in (skipped when unchanged).
4. `PDLC-PRODUCT` comment.
5. `set_state` → Product / Review Required.

Check: `pdlc inspect N` — gate is Review Required; `pdlc inspect timeline N` — newest `PDLC-PRODUCT` is this evidence.

Re-run: safe at every step. After 4, a re-run posts a second `PDLC-PRODUCT`.

### `pdlc post write --work-item N --patch`

Writes:
1. `write_body` (Product sections).
2. `PDLC-PRODUCT` comment.
3. `PDLC-PATCHED` comment.
4. Either, when the impact report returns the record to an earlier stage: `PDLC-INVALIDATED` → `set_state` → Stale → `set_skipped_states` if the target was skipped → reopen tasks (per task: `reopen` → `PDLC-INVALIDATED` on the task → delete stale `## Implementation`/`## Technical Plan` comments). Or, otherwise: `set_state` only if the target differs from the current state.

Check: `pdlc inspect timeline N` — `PDLC-PATCHED` is present and newer than this `PDLC-PRODUCT`; `pdlc inspect N` — stage and gate match the dry run's `returnedTo`/`status`.

Re-run: after 1 or 2, safe. After 3, a re-run posts a second `PDLC-PRODUCT` and `PDLC-PATCHED` and, for a rewind, re-plans from the new state; run `--dry-run` first and re-run only if it still reports the same plan. If the record already moved to the returned stage, do not re-run; reopen any task still closed with `pdlc post invalidate N STAGE EVIDENCE --task T`.

### `pdlc post tasks --stage UI`

Writes:
1. If re-authoring from Review/Approval Required: `set_state` → UI / Stale.
2. `write_body` with the `## UI` section spliced in.
3. `PDLC-UI` comment.
4. `--patch`: `land_patch` as in `post write --patch` step 3–4. Otherwise `set_state` → UI / Review Required.

Check: `pdlc inspect N` and `pdlc inspect timeline N`, as for `post write`.

Re-run: safe; may duplicate `PDLC-UI`.

### `pdlc post tasks --stage Tasks`

Writes:
1. If re-authoring: `set_state` → Tasks / Stale.
2. Before any remote write, assign missing `TASK-NNN` identities and save them atomically in the supplied manifest; then, per task, create and link a new task or edit a changed task, leaving unchanged tasks untouched. Tasks created but never linked by an earlier run are found and linked on retry.
3. For each rewritten task that was already closed: `reopen` → `PDLC-INVALIDATED` on the task → delete its `## Implementation` and `## Technical Plan` comments.
4. For each `remove` entry: post a descope comment on the task → close it → detach it from the parent (GitHub sub-issue or Azure parent relation; the file backend retains a removed task record).
5. `PDLC-TASKS` comment (lists open orphans, reopened tasks, and descoped task IDs and reasons).
6. `--patch`: `land_patch`. Otherwise `set_state` → Tasks / Review Required.

Partial failure:
- In 2: some tasks may be created or edited. The manifest keeps generated IDs across retries; a `create` whose task already exists with the requested content and a `retain` whose edit already landed are carried forward.
- Between 2 and 3: a rewritten task may still be closed. A re-run detects that its requested content landed and reopens it.
- During 3: a task may have reopened before its invalidation comment or stale plan and implementation comments were cleared. Inspect it after retry; the current `reopen_tasks` helper skips already-open tasks.
- In 4: a descope comment or close may have landed before detachment, or the task may already be detached. A re-run uses the task number and matching descope comment to recognize a completed detach, then finishes the remaining removals.
- After 5: `PDLC-TASKS` landed, state not moved; a re-run may post a duplicate evidence comment.

Check: `pdlc inspect task T` for each rewritten task — it should be open with no stale `## Technical Plan` or `## Implementation` comment; check each removed task is closed and absent from the parent's active task list; `pdlc inspect N` should show Review Required and the timeline should show this `PDLC-TASKS` evidence.

Recovery:
- Re-run the same command.
- If a rewritten task is still closed or still carries stale plan or implementation evidence after retry, stop and report its inspection output for host repair; `post invalidate` does not repair an already-open task and cannot target Technical Plan while the parent is still at Tasks.
- If a removed task is still linked, inspect its task comment and state, then re-run the same manifest while the parent gate still allows Tasks publication; if the parent already reached Review Required, report the incomplete descope instead of reauthoring blindly.

### `pdlc post plan`

Writes:
1. If re-authoring: `set_state` → Technical Plan / Stale.
2. Per planned task: edit the existing `## Technical Plan` comment on the task, or post one.
3. `PDLC-PLAN` comment on the record.
4. `set_state` → Technical Plan / Review Required.

Check: `pdlc inspect task T` shows the new plan on every task in the manifest; `pdlc inspect N` — gate is Review Required.

Re-run: safe. Step 2 edits in place when a plan comment exists. A failure *during* step 2's post (not edit) can leave two plan comments on one task; the newest wins. After 3, a re-run posts a second `PDLC-PLAN`.

### `pdlc post implement-task`

Writes:
1. Stack: `gh stack sync --prune` if a stack PR merged while its branch is still local, else `gh stack rebase --no-trunk` (aborted on failure); then `gh stack submit --auto`, which pushes every branch and creates or updates one PR per branch. For the first task of a worktree prepared with `--after`: `git branch -m` then `gh stack link` instead.
2. `gh pr edit` — the task PR's title and body.
3. Attach the PR number to the task (registry in the task Issue body; Azure: a field).
4. Keep one `## Implementation` comment: edit the newest, delete older duplicates; post one only if none exists.
5. New implementation: `gh issue close` on the task. Rework: no write, reads back open threads and checks.

Check: `pdlc inspect task T` — the task is closed (or, for rework, stays closed), its PR is registered, and its `## Implementation` comment is this summary.

Re-run: safe at every step; the command is ordered so a failure before step 4 leaves the task offered again by `pdlc inspect implement` and a re-run is clean.

Stack-specific failures are not transient and keep their own handling (`pdlc guide stacks`): a rebase conflict (the rebase is aborted; resolve and re-run), exit 8 "stack file is locked" (wait about 5 seconds and re-run). A transient failure *during* `gh stack submit` may leave some branches pushed and some PRs created; `gh stack view --json` shows the stack, and a re-run submits the rest.

### `pdlc post implement`

Writes:
1. Stack restack and `gh stack submit --auto`, as above.
2. Local `git checkout` of the top task branch.
3. `gh pr ready` on every open registered PR.
4. `PDLC-IMPLEMENTATION` comment.
5. `set_state` → Implementation / Review Required.

Check: `pdlc inspect N` — gate is Review Required; `pdlc inspect timeline N` — newest `PDLC-IMPLEMENTATION` is this evidence.

Re-run: safe through step 3 (all idempotent). After 4, a re-run posts a second `PDLC-IMPLEMENTATION`.

### `pdlc post test`

Writes:
1. Stack restack and submit, as above.
2. Find the current branch's PR (`gh pr view`) and attach it to the record.
3. `PDLC-TESTING` comment (evidence plus `## Traceability`).
4. `set_state` → Testing / Review Required.

Check and re-run: as `post implement`.

### `pdlc post review`

Writes:
1. `PDLC-REVIEW` comment (stage, verdict, findings).
2. `decision-required` only: `PDLC-DECISION` blocker comment.
3. `approval-required` on a stage the rework policy may auto-approve: `PDLC-AUTOAPPROVED` → `set_state` to the next stage. Otherwise `set_gate` to the review outcome (Changes Required, Approval Required, Decision Required, or CI Pending).
4. CI Pending only: resolve CI, as `post ci`.

Check: `pdlc inspect timeline N` — newest `PDLC-REVIEW` is this review; `pdlc inspect N` — gate matches the outcome, or the record auto-approved to the next stage, or CI Pending was resolved.

Re-run: safe; after 1, posts a second `PDLC-REVIEW` (and `PDLC-DECISION` after 2). A second `changes-required` review of Verification counts as an extra rework loop toward the auto-approval cap, so for Verification, prefer checking over re-running when step 1 landed.

Recovery when step 1 landed but the gate did not move: re-run the same command (the gate is still Review Required, so the command accepts it) and note the duplicate in the report.

### `pdlc post escalate`

Writes: `PDLC-DECISION` blocker → `set_gate` → Decision Required.

Check: `pdlc inspect N` — gate is Decision Required.

Re-run: safe while the gate has not moved; may duplicate `PDLC-DECISION`. If the gate is already Decision Required, it landed; do not re-run.

### `pdlc post decision`

Writes:
1. Per deferred entry: if a record with the deferral's slug exists, reuse it and write nothing. Otherwise: create the child record (as `post write` new record, steps 1–2) → `set_state` → first stage / Pending → `set_slug` → a "split out of #N" comment on the child → append a "Deferred — …; tracked as #M" line to the origin's Open Questions.
2. `PDLC-RESOLUTION` comment on the origin.
3. `set_gate` to the stage's post-decision gate.

Partial failure:
- A child record created but its slug not yet set is not found by slug on re-run, so a re-run creates a **second child**.
- A child created with its slug set is reused on re-run, but the Open Questions line is then not appended if the first run failed before it.

Check: `pdlc inspect N` — gate has left Decision Required; `pdlc inspect timeline N` — `PDLC-RESOLUTION` present; for each deferral, look up its slug with `pdlc inspect <slug>`.

Recovery:
- If every deferral's child resolves by slug: re-run.
- If a child Issue was created but does not resolve by slug: do not re-run; report the child's number to the driver to set its slug or close it, then re-run.
- If a reused child's line is missing from the origin's Open Questions, report it; the resolution comment still names the child.

### `pdlc post verify`

Writes:
1. `PDLC-REVIEW` comment for Verification.
2. Append "Deferred — …" lines to Open Questions (read-modify-write of the body).
3. If the report raises decisions: `PDLC-DECISION` blocker.
4. Bounce: `set_state` to the upstream stage and clear it from Skipped States. Otherwise `set_gate` to the verdict's gate.
5. CI Pending only: resolve CI, as `post ci`.

Partial failure: step 2 has no duplicate check, so a re-run after it **appends the deferred lines again**. A re-run after 1 also counts as an extra rework loop when the verdict bounces.

Check: `pdlc inspect timeline N` — newest `PDLC-REVIEW` is this report's head commit; `pdlc inspect N` — gate or stage moved; Open Questions has each deferred line once.

Recovery:
- If step 1 did not land: re-run.
- If step 1 landed and the gate/stage did not move: stop and report to the driver with the check output. Re-running duplicates evidence and deferrals and inflates the loop count. (Once the comment-hash follow-up lands, this becomes a plain re-run.)

### `pdlc post ci`

Writes (only when the gate is CI Pending and CI has settled):
- Red: a CI-failed `PDLC-REVIEW` → `set_gate` → Changes Required.
- Green and the rework policy auto-approves: `PDLC-AUTOAPPROVED` → `set_state` to the next stage.
- Green otherwise: `set_gate` → Approval Required.
- Pending or no PRs: no write.

Check: `pdlc inspect N` — gate left CI Pending.

Re-run: safe; the command is a no-op once the gate has moved. A re-run after the red comment but before the gate moved posts a second CI-failed note. `--wait` polls the same path.

### `pdlc post approve` (human action)

Writes: `PDLC-APPROVED` → `set_state` to the next stage.

Check: `pdlc inspect N` — stage is the next stage.

Recovery: approval is a driver action; an agent does not re-run it. If `PDLC-APPROVED` landed and the state did not move, the next `pdlc next` poll heals a stray approval into the next stage. Otherwise report to the driver.

### `pdlc post skip` (human action)

Writes: `set_skipped_states` (merged with the existing list) → `PDLC-SKIPPED`.

Re-run: safe; the merge is idempotent, the comment may duplicate.

### `pdlc post invalidate`

Writes:
1. `PDLC-INVALIDATED` (stamped with the target stage).
2. `set_state` → target stage / Stale.
3. If the target stage was skipped: `set_skipped_states` without it.
4. Technical Plan or Implementation only: reopen closed tasks (all, or those named by `--task`): per task `reopen` → task `PDLC-INVALIDATED` → delete its stale `## Implementation` (and for Technical Plan, `## Technical Plan`) comments.

Check: `pdlc inspect N` — stage is the target at Stale; `pdlc inspect task T` for each task in scope — open, with no stale implementation/plan comment.

Recovery:
- If the record is not yet at the target / Stale: re-run.
- If it is: do not re-run the whole command. For each task in scope that is still closed or still carries a stale comment, run `pdlc post invalidate N STAGE EVIDENCE --task T`. If that refuses, report to the driver.

### `pdlc post complete` (human action)

Writes:
1. `PDLC-COMPLETE`.
2. `set_state` → Complete (the record is now locked).
3. Replace Open Questions with the settled marker.
4. Close the Issue (Azure: set the closed state).
5. Local: force-delete each merged PR's local branch when its tip still matches the PR head.

Partial failure: after 2 the record is locked, so a re-run refuses. Steps 3–4 then never run, leaving a Complete record that is still open.

Recovery:
- If the state is not Complete: re-run.
- If it is Complete: report to the driver that the record is locked but still open and needs closing on the host. Step 5 is cosmetic; `pdlc cleanup` removes leftover branches.

### `pdlc post attach-pr`

Writes: attach the PR number to the task (read-modify-write of the task body or field). Skipped when already attached.

Re-run: always safe.

### `pdlc next` and `pdlc continue` — self-heal

Writes (only when the record is in a healable state, such as a stray Approved gate): heal comment (with `PDLC-APPROVED` when an approval is replayed into the next stage) → `set_state`.

Re-run: safe. If the comment landed but the state did not, the record is still healable and the next poll heals it again, posting a second heal comment.

### `pdlc checkout`

Writes (local Git plus fetches, no record writes): one of `gh stack checkout <pr>`, `gh stack checkout <branch>`, `gh stack checkout <entry-pr>` + `gh stack add <branch>`, `gh stack top` + `gh stack add <branch>`, or `gh stack init <branch>`.

Re-run: safe. After `add` created the branch, a re-run takes the "existing local branch" path. Exit 8 (stack locked): wait about 5 seconds and re-run.

### Human-only local commands

`pdlc prepare`, `pdlc cleanup`, and `pdlc setup` write only local Git worktrees, branches, and config. They are outside the agent loop and are not covered here; `pdlc cleanup` refuses unless the record is Complete, and removes branches only after checking them.

## Gaps this catalog exposes

These are real recovery hazards independent of transient errors. Each is a candidate follow-up, not part of the transient-error change:

1. **`post write` create is not idempotent.** A failure after `gh issue create` makes the obvious re-run open a duplicate Issue, and a failure before `project item-add` leaves an Issue `pdlc` cannot see.
2. **`post tasks` can leave stale task evidence after reopening.** A failure between reopen and comment cleanup leaves an open task that the current `reopen_tasks` helper skips on retry.
3. **`post verify` appends Open Questions lines without a duplicate check.**
4. **`post decision` child creation is not atomic with its slug**, so a re-run can create a second child.
5. **`post complete` locks before closing.** A failure between them has no command to finish the close.
6. **Evidence comments before state changes duplicate on re-run** in most commands. The comment-hash follow-up in the plan fixes this class in one place.

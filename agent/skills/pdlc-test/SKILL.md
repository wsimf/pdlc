---
name: pdlc-test
description: "Own the Testing stage of a PDLC record: build a requirement-to-source traceability map from the implemented tasks, dispatch pdlc-test-writer for acceptance coverage, and publish at Review Required. Never edits production source or the record's requirements, tasks, or results."
argument-hint: "Parent work item number to test"
---

# Test a PDLC implementation

This skill does not write or run tests itself. It reads one PDLC record's implemented scope, works out from task Results and touched source exactly which requirements and seams need coverage, dispatches `pdlc-test-writer` once with a self-contained brief, and publishes the stage at `Review Required`. The test writer commits its coverage on the current branch.

Read `../pdlc/references/parity-contract.md` before dispatching. This skill never records a review outcome and never sets a gate to `Approved`.

When testing produces local files such as screenshots, pass each one to
`pdlc-post-test.py` as `--attachment PATH [--attachment-description TEXT]`.
Repeat `--attachment PATH` for multiple files; a description applies only to
the immediately preceding file. See [PDLC attachments](../pdlc/references/attachments.md).

## Required input

Require an exact parent work item number. Check the current conversation for an unambiguous one before asking; never infer it from the branch, recent files, open PRs, or history alone.

---

## Step 1: Resolve the record and the testable scope

```bash
python3 .agents/skills/pdlc/scripts/pdlc-inspect-test.py WORK_ITEM
```

`## Readiness` already resolves whether coverage is due. Not ready → stop, report the reason verbatim, name the actual owner. Testing is gated behind implementation, not a substitute for it.

`## Testable Scope` already lists every task that closed with a `## Implementation` comment, its linked PRs, and the files those PRs actually touched — straight from the code host, not from the comment's prose, since implementation routinely touches files the comment never mentions. Read the current source at each seam to confirm the real API — never infer a signature from requirement wording or a task title. If a task's implementation comment names behaviour that doesn't correspond to any real source change, flag it as suspect and report it rather than writing tests against a claim. Nothing implemented → stop and report that.

If the driver explicitly asks for ad hoc coverage on a record not due for `pdlc-test`, you may build and dispatch the map, but say plainly it sits outside the stage contract and will not satisfy the Testing gate — and do not publish.

## Step 2: Handle the gate

`Pending` (first pass), `Changes Required` (a reviewer found missing/failing coverage — read `pdlc-inspect-timeline.py WORK_ITEM`, that's this pass's scope), and `Stale` (implementation changed under existing coverage — reconcile it) are the only gates `## Readiness` lets through.

## Step 3: Build the traceability map

Produce one map, in plain terms, that the test writer can act on without reading the record:

`FR-* / C-* / acceptance criterion → expected behaviour → source file, type, and seam → why it needs coverage`

Include every in-scope `FR-*` and task acceptance criterion. Include a `C-*` constraint only when it creates an observable invariant a test can actually assert. Note coverage boundaries you already know about — anything needing a device, a fixture, a permission, or manual verification.

This map is the deliverable of the stage as much as the tests are: the contract requires requirement-to-source traceability, not just a green suite. `pdlc-post-test.py` persists it verbatim into the `PDLC-TESTING` evidence under a `## Traceability` heading (Step 6), and that persisted copy is the exact artifact `pdlc-testing-reviewer` audits — so write it to a file you can pass through unchanged.

## Step 4: Dispatch `pdlc-test-writer`

Spawn once, building the prompt from [`references/test-writer-prompt.md`](references/test-writer-prompt.md) — the Step 3 traceability map, the complete in-scope source list, the task/parent/PR numbers, and any `Changes Required` findings verbatim.

`pdlc-test-writer` commits its coverage on the current branch **and pushes it**, so the shared implementation PR — which tracks that branch — carries the tests. There is no separate test PR.

Wait for its report. Do not write, edit, or run tests yourself, and do not spawn a second test author for the same scope.

## Step 5: Re-read the evidence before publishing

Do not take the report on trust:

- Re-read the PR carrying the coverage and its checks. Missing coverage, a failing required check, or a PR not linked to the parent work item is `Changes Required` territory — report it and stop rather than publishing a clean claim.
- Confirm every in-scope requirement is either covered or recorded as an explicit coverage boundary.
- A red test left deliberately to expose a real defect is a finding for the driver, not a reason to withhold the work. Report it plainly and let them decide whether implementation must be reopened.

## Step 6: Publish and stop at Review Required

```bash
python3 .agents/skills/pdlc/scripts/pdlc-post-test.py WORK_ITEM /tmp/pdlc-test-evidence.md \
  --traceability /tmp/pdlc-traceability.md
```

The evidence file holds only the compact durable result:

```
Result: acceptance coverage added; PR #153 carries 41 tests.
Coverage changes: all in-scope requirements covered except FR-9.
Exception: FR-9 needs a physical device and remains uncovered.
```

`pdlc-post-test.py` confirms the shared implementation PR still links the parent, appends the `--traceability` map under a `## Traceability` heading, posts the evidence, and sets `Review Required` — one step. Body only — the script stamps the `PDLC-TESTING` marker and refuses one that already carries it, so strip any marker line the sub-agent returned. No linked PR is `Changes Required` territory: the coverage was never pushed.

Do not publish for ad hoc or partial scope (Step 1): report the coverage added and leave the stage exactly as found, since publishing would misrepresent what was verified.

## Step 7: Report

Write a compact durable evidence comment from `pdlc-test-writer`'s report. Include the result, changed coverage or uncovered requirement IDs, the PR/commit, and only defects or limitations that affect the next stage. Keep the *prose* compact — no file inventory, repeated passing-test detail, or historical findings; inspection recovers those from the source and PR. The traceability map is not prose: pass it through `--traceability` so it lands in the evidence intact for the reviewer. Ask for review before verification.

Never claim the record is done from coverage alone, and never set `Approved`.

---

## Boundaries

- Do not edit production source, the parent work item body, or any delivery task — never their requirements, plans, or Results.
- Do not edit fixtures, package manifests, project files, agents, or other skills.
- Do not run or author tests yourself; `pdlc-test-writer` owns both.
- Do not create or switch branches — coverage is committed and pushed on the current branch, onto the shared implementation PR.
- Do not run `pdlc-post-approve.py`, `pdlc-post-skip.py`, `pdlc-post-invalidate.py`, or `pdlc-post-complete.py` — driver-only.
- Do not write lifecycle state into any work item body — those fields are script-owned.
- Preserve unrelated staged, unstaged, and untracked local work.
- Do not claim delegated coverage, traceability, or test-run validation unless `pdlc-test-writer` actually reported it.

## Checklist

- [ ] `## Readiness` from `pdlc-inspect-test.py` reports ready; gate was `Pending`, `Changes Required`, or `Stale`
- [ ] Scope came from `## Testable Scope`, cross-checked against real source at each seam
- [ ] The traceability map covers every in-scope FR, criterion, and observable constraint, and was passed through `--traceability` so it persists in the Testing evidence
- [ ] No coverage was dispatched for unimplemented requirements
- [ ] Coverage was committed and pushed on the current branch; `pdlc-post-test.py` confirmed the shared implementation PR links the parent and its checks were re-read
- [ ] Coverage boundaries are recorded rather than passed off as covered
- [ ] Evidence holds only the durable result, changed coverage, evidence, and exceptions
- [ ] Published exactly once, landing the stage at `Review Required`

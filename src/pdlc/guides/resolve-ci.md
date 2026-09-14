# Resolve a CI-Pending record

Runs when a record sits at `CI Pending` on a CI-gated stage — `Implementation`, `Testing`, or `Verification`: the stage review (or, for Verification, the clean verification run) already passed, and the only thing left is the registered PR stack's CI.
Orientation is read-only — it reports this state and never runs the resolver.

## When this applies

```bash
pdlc inspect <work-item>
```

Proceed only if `Gate State` is `CI Pending` (equivalently `# Due Next` routes to
`pdlc-post-ci`). Any other gate — this workflow does not apply; report the actual
state.

## Step 1: Read the live check state

`pdlc inspect`'s `pullRequests[].checks` carries the rollup for each linked
PR: `SUCCESS`, `FAILURE`, `PENDING`, `ERROR`, or `NONE` (no checks configured).

## Step 2: Act on the driver's "continue"

- **Still running** (`PENDING` / `EXPECTED`) — nothing to do. Tell the driver CI
  has not finished; the autonomous loop re-checks on its own backoff, or they can
  ask again later. Post nothing, change nothing.

- **Green** (`SUCCESS`, or `NONE` — no checks configured; on Verification also no registered PR — nothing to wait on) — run:

  ```bash
  pdlc post ci <work-item>
  ```

  It sets `<Stage> / Approval Required`. Nothing is posted — the stage
  review was already clean. The record now awaits the driver's explicit
  approval: `pdlc post approve` for Implementation and Testing, `pdlc post complete` for Verification.
  On an Implementation or Testing record with 1–3 recorded Verification rework bounces it instead posts `PDLC-AUTOAPPROVED` and lands on the next stage's `Pending` with no human step.

- **Red** (`FAILURE` / `ERROR` / …) — run the same command. It posts a
  `PDLC-REVIEW` note naming the failed checks and sets
  `<Stage> / Changes Required`.
  On the next "continue", invoke the stage's owning skill (`pdlc-implement`, `pdlc-test`, or `pdlc-verify`) — it reads the note, fixes the checks, and re-publishes.

- **No registered PR** on Implementation or Testing — `pdlc post ci` exits non-zero naming the stage and leaves the record at `CI Pending`: those stages publish through their pull requests, so no CI was checked.
  Report it to the driver; once the stage's pull requests are registered (`pdlc post attach-pr <delivery-task> <pr-number>` for a delivery task's PR), run `pdlc post ci` again.

`pdlc post ci` is mechanical: it records the CI outcome and makes no
judgement, so the autonomous loop runs it unattended and a driver may run it
directly. It carries no identity check and refuses any gate other than
`CI Pending`.

## Step 3: Report

The record's resulting state, the CI outcome recorded, and — for a red result —
which owning skill picks it up from `Changes Required`.

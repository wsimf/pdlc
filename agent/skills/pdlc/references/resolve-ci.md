# Resolve a CI-Pending implementation record

Runs when a record sits at `Implementation / CI Pending`: the implementation stage review already passed, and the only thing left is the registered PR stack's CI.
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

- **Green** (`SUCCESS`, or `NONE` — nothing to wait on) — run:

  ```bash
  pdlc post ci <work-item>
  ```

  It sets `Implementation / Approval Required`. Nothing is posted — the stage
  review was already clean. The record now awaits the driver's explicit
  approval (`pdlc post approve`).

- **Red** (`FAILURE` / `ERROR` / …) — run the same command. It posts a
  `PDLC-REVIEW` note naming the failed checks and sets
  `Implementation / Changes Required`.
  On the next "continue", invoke `pdlc-implement` — it reads the note, fixes the checks on the affected task PR, and re-publishes for review.

`pdlc post ci` is mechanical: it records the CI outcome and makes no
judgement, so the autonomous loop runs it unattended and a driver may run it
directly. It carries no identity check and refuses any gate other than
`CI Pending`.

## Step 3: Report

The record's resulting state, the CI outcome recorded, and — for a red result —
that `pdlc-implement` picks it up from `Changes Required`.

# Decision resolver workflow

Runs when a PDLC work item sits at `<stage> / Decision Required` — a
post-publication reviewer (Implementation or Testing), or the Verification audit
itself, raised a finding that only the driver can settle — and the driver has
asked to resolve it.

**Never autonomous.** Every branch below needs a human answer. The PDLC loop
stops on `human-decision` and hands to the driver; this workflow is what the
driver's chosen agent then follows.

## When this applies

```bash
pdlc inspect <work-item>
```

Proceed only if `Gate State` is `Decision Required` (equivalently `# Due Next`
routes to `human-decision`). Any other gate — stop, this workflow does not
apply, report the actual state.

## Step 1: Read every open decision

```bash
pdlc inspect timeline <work-item>
```

Each `## DECISION` entry is a `PDLC-DECISION` comment carrying one
`## Decision Required` block: **Question**, **Options**, **Recommendation**,
**Blocks**, **Why not mechanical**. A later `## RESOLUTION` entry that names a
decision means it is already settled — skip it. Collect every block still open.

Read the parent body and the named task(s) so the question is understood in
context, not just from the reviewer's prose.

## Step 2: Put each open decision to the driver

One question per decision. Use `AskUserQuestion` when available:

- Ask the reviewer's **Question** verbatim.
- First option: the reviewer's **Recommendation**, suffixed `(Recommended)`.
- Then the other realistic **Options** from the block.
- Always a final option: **"Defer — split into its own work item"**.

Never choose for the driver. Carry their exact words forward — a paraphrase
loses intent the reconciling skill depends on.

## Step 3: Write a deferral body for every deferred decision

For each decision the driver chose to defer, write a stub body to
`/tmp/pdlc-deferred-<slug>.md`. It is **not** a finished spec — just the context
a later `pdlc-write` pass needs to pick it up:

```md
## Product

### 1. Problem
<the reviewer's concern, in product terms>

### 2. Context
Split out of #<origin> during <stage> review. The reviewer's block:

> Question: <verbatim>
> Options: <verbatim>
> Recommendation: <verbatim>

### 3. Known bounds
<anything the origin already fixes that constrains this — constraints, non-goals, owned files>

## Decisions
- none yet

## Open Questions
- <the decision, restated as the question to resolve>
```

## Step 4: Land every outcome in one call

Build a manifest — one entry per open decision, each either answered or
deferred:

```json
[
  { "decision": "<reviewer's question 1>",
    "answer": "<driver's choice, verbatim intent>",
    "rationale": "<why>",
    "affects": "<task or section that now carries it>" },

  { "decision": "<reviewer's question 2>",
    "defer": { "title": "<short title>", "slug": "<kebab-slug>",
               "body": "/tmp/pdlc-deferred-<slug>.md" } }
]
```

```bash
pdlc post decision <work-item> --manifest /tmp/pdlc-decisions.json
```

One call does everything: each `defer` becomes its own `Product / Pending` work
item (resolved by slug first, so a re-run after a failure reuses it), linked
back to the origin with an Open Questions pointer; a single `PDLC-RESOLUTION`
comment records every outcome; and the gate moves to `<stage> / Changes
Required`. The loop then routes to the stage's owner (`pdlc-implement`,
`pdlc-test`, or `pdlc-verify`), which reconciles against the recorded
decisions — applying answers, treating a deferred point as out of scope.
Implementation and Testing re-publish for a fresh independent review, where a
deferral is confirmed legitimate or bounced back; Verification re-runs its own
audit against the recorded decisions.

Do not fold the decisions into `Decisions` or task bodies here — the
`PDLC-RESOLUTION` comment is enough to unblock delivery, and `pdlc-complete`
records emergent decisions in the completion evidence at close-out.

## If a decision changes approved upstream intent

Some answers mean an approved constraint, requirement, journey, or task is
wrong — not that the current stage needs a tweak. That is not this workflow:
stop, tell the driver to run `pdlc post invalidate <owning-stage>` so the owning
skill re-authors it. The cascade clears the `Decision Required` gate by moving
`Status` back.

## Step 5: Report

The origin's resulting state, each decision → answered (with the choice) or
deferred (to `#NNN`), and every new work item created.

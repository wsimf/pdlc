---
name: pdlc-write
description: "Use when authoring or reconciling a reviewed PDLC product specification through a source-backed interview, then land it as a PDLC Work Item."
argument-hint: "Fresh feature idea, or work item number to reconcile"
---

# Write product specification

Author product specifications that are clear, actionable, and suitable for implementation. Read `pdlc guide contract`. This skill owns a PDLC Work Item's `Product`, `Decisions`, and `Open Questions` sections and nothing else.

Section format, numbering, and writing rules: [references/product-spec-format.md](references/product-spec-format.md). Read it before Step 1.

When the artifact includes local files such as mockups — including any the
driver supplied in this prompt — pass each one to `pdlc post write` as
`--attachment PATH [--attachment-description TEXT]`.
Repeat `--attachment PATH` for multiple files; a description applies only to
the immediately preceding file. See `pdlc guide attachments`.

## Philosophy: the work item is a spec, not a log

A work item states **current, correct intent** — what to build and why, not a changelog, diary, or audit trail. The record keeps history for free: the body's own revision history holds every revision, and evidence comments hold what was published, reviewed, approved, and invalidated, in order.

- Requirements are edited **in place**. Never strike through superseded text or append "amendment" trails — that duplicates the revision history and makes the body grow forever.
- The product evidence comment is where the *why* of a change lives, not the body.
- Never write lifecycle state into the body. `Status`, `Gate State`, `Lifecycle`, `Slug`, and `Skipped States` are tracked fields, owned by the `pdlc` commands. No frontmatter, no state block, no identity marker.

Keep the whole specification proportional to the feature — a well-scoped record with a dozen tasks should still be readable in one sitting once implemented. If it isn't, the detail belongs in evidence comments, not here.

---

## The Job

1. Receive a feature idea, or an exact work item number, from the driver.
2. Interview the driver until the design is settled, answering from source wherever source can answer.
3. Complete the three Product-owned sections in the scratch file.
4. Have that file independently reviewed **before** anything is published, fixing findings in the file itself.
5. Land the reviewed file: create the work item, or update the existing one, at `Product / Approval Required`.

**Important:** do not design UI, break the work into tasks, technically plan, or implement. Author only the product specification.

### Two inputs

| Input | Meaning |
|---|---|
| A concrete feature idea, no work item yet | New record. Nothing is published until the specification passes review. |
| An exact work item number at `Product / {Pending, Changes Required, Stale}` | Reconcile that work item's sections in place. |
| An exact work item number at `Product / Approval Required`, with a driver request to change the spec | Re-author in place. `pdlc post write` returns Product to Stale itself and re-lands the reviewed spec in one call. |

Never infer either from the branch, recent files, open PRs, or conversation history. A work item at `Product / Approval Required` is a reconcile input **only** when the driver is asking for a change this turn; otherwise it is awaiting the driver's approval — report that and stop. If the named work item is not at a Product stage at all, report the state it is actually at and stop.

When reconciling an existing record, preserve its identity, `Slug`, tasks, plans, results, approved UI section, and approved product intent. Interview only where the current work item and source leave a real decision unresolved. Normalize only the three sections this skill owns.

---

## Step 0: Existing record preflight

Skip this step for a fresh feature idea with no existing work item.

When reconciling an existing record, run `pdlc inspect <WORK_ITEM>` before creating the scratch file or asking questions. Treat its `# Work Item`, work item metadata, and `# Due Next` as the current record snapshot. Continue only when `Due Next` confirms `Product.Pending`, `Product.Changes Required`, or `Product.Stale` — or `Product.Approval Required` when the driver has asked this turn to change the spec (`pdlc post write` returns it to Stale itself on landing). Otherwise report the actual state and stop. Use the snapshot to preserve the record's identity and existing sections during reconciliation.

The snapshot does not include evidence comments; read `pdlc inspect timeline <WORK_ITEM>` when the evidence history is needed.

## Step 1: Clarifying questions

Create one scratch file before the first question, with only `## Product`, `## Decisions`, and `## Open Questions` headings in that order. This is the artifact you complete in Step 2 and land in Step 3.

Interview the driver relentlessly about every aspect of the feature until you reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one by one. Ask one question at a time, with your recommended answer.

**Search the codebase before you ask.** Answer from source or Git history — only bring the driver questions source genuinely cannot. Everything you learn feeds Prior Art & Reuse; write it down as you go.

Use `AskUserQuestion` when available. Otherwise format the one question with lettered options:

```
1. What is the primary goal of this feature?
   A. Improve first-run orientation
   B. Reduce time to plan a multi-day route
   C. Cut support burden for offline downloads
   D. Other: [please specify]
```

Record each settled answer immediately in its scratch-file section — one that binds implementation becomes a **Constraint**; an alternative considered and rejected goes in **Decisions**. Do not leave it in the conversation for a later skill to reconstruct.

Write the sections yourself, from the settled answers. Do not hand drafting to a sub-agent — you hold the interview, the driver's exact words, and the source you explored, none of which survives a handoff intact. The only agent this skill spawns is the Step 2 reviewer, because that review has to be independent of the drafter.

---

## Step 2: Write the draft, then have it reviewed

Complete the scratch file created in Step 1 per [references/product-spec-format.md](references/product-spec-format.md). It contains only `## Product`, `## Decisions`, `## Open Questions`, in that order. The reviewer and `pdlc post write` accept no other level-2 headings. Name it for the slug, e.g. `/tmp/pdlc-route-shape-detection-body.md`.

When reconciling an existing record, read the full work item for context, then write the final form of only those three owned sections. The script preserves every later-stage section unchanged.

Spawn `pdlc-product-reviewer` with the exact scratch file path (and, on a re-review, the prior findings). It reviews the whole supplied draft, reads the file, edits nothing, and returns findings plus a verdict.

- **Findings** — fix them in the same file, going back to Step 1 as the finding demands, then hand the same path and the prior findings back for re-review. After two failed reconciliations, stop and put the decision to a human.
- **Clean** — that same file is what Step 3 lands. Do not rewrite, reformat, or regenerate it; the reviewed bytes ship.

This is why Product has no `Review Required` state — the review happens here, before publication.

---

## Step 3: Land the record

Pass the reviewed file straight through as `--body`, and the evidence body as a file path: your scope, the reviewer's verdict and coverage boundaries, and any unresolved risk. Body only — the script stamps the marker and refuses evidence that already carries one.

**New record** — derive the slug and pass `--title` and `--slug`:

```bash
pdlc post write \
  --title "Route shape detection" \
  --slug route-shape-detection \
  --body /tmp/pdlc-route-shape-detection-body.md \
  --evidence /tmp/pdlc-route-shape-detection-evidence.md
```

`--evidence` takes a file path (a `text:<body>` one-liner is accepted but Product evidence is rarely that short). The body is taken verbatim.

Creates the work item, stamps `Slug`, posts evidence, sets `Product / Approval Required`. Refuses a body that is not exactly the three owned sections.

**Existing record** — pass the same reviewed three-section file with `--work-item`. The script resolves its work item, requires `Product / {Pending, Changes Required, Stale}` — or `Product / Approval Required`, whose gate it resets to Stale itself first (no comment — the re-land's own Product evidence records the change) — reconstructs the full work item body with only those sections replaced, and performs one work-item body edit before it posts Product evidence and sets `Product / Approval Required`.

```bash
pdlc post write \
  --work-item WORK_ITEM \
  --body /tmp/pdlc-route-shape-detection-body.md \
  --evidence /tmp/pdlc-route-shape-detection-evidence.md
```

Never set `Approved` — the driver does that with `pdlc post approve`. On failure, keep the scratch file, report the exact failure, and inspect the work item before retrying. The scratch file is temporary input only — never leave a local product-specification document behind once landed.

---

## Writing style

The reader may be a junior developer or an AI agent:

- Be explicit and unambiguous.
- Avoid jargon, or explain it.
- Give enough detail to understand purpose and core logic.
- Number requirements for easy reference.
- Use concrete examples where they help.

---

## Checklist

- [ ] Interviewed the driver branch by branch, answering from source wherever source could answer
- [ ] Problem statement is a short paragraph stating the problem, not a solution tour
- [ ] Incorporated the driver's answers
- [ ] Prior art & reuse cites real file and type paths found during that exploration
- [ ] Functional requirements are numbered, behavioural, and testable
- [ ] Binding design decisions are Constraints (`C-*`), not smuggled into `FR-*`
- [ ] Assumptions lists only genuinely unverified claims, omitted entirely if none
- [ ] Non-goals define clear boundaries
- [ ] Any diagram is authoritative rather than a restatement, uses a permitted type, labels edges with `FR-*`/`C-*`
- [ ] Decisions are numbered entries of bold decision, rationale, then `Ref:`
- [ ] Open Questions holds only undecided things, not unverified ones
- [ ] Body carries no frontmatter, no lifecycle state, no identity marker
- [ ] The scratch file contains exactly `## Product`, `## Decisions`, `## Open Questions`, in that order
- [ ] `pdlc-product-reviewer` reviewed the scratch body file itself and its verdict is clean
- [ ] The file landed is the reviewed file, not a regenerated copy
- [ ] Evidence holds the comment body only — scope, verdict, coverage boundaries, unresolved risk
- [ ] Landed at `Product / Approval Required` via `pdlc post write`

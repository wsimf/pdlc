---
name: pdlc-write
description: "Use when authoring or reconciling a reviewed PDLC product specification through a source-backed interview, then land it as a PDLC Work Item."
argument-hint: "Fresh feature idea, or work item number to reconcile"
---

# Write product specification

Author a work item's `Product`, `Decisions`, and `Open Questions` sections through a source-backed interview with the driver. You draft the sections, `pdlc-product-reviewer` checks the local draft, and `pdlc post write` lands the reviewed file at `Product / Approval Required`. This skill owns those three sections and nothing else. Review runs on the local file, before anything is landed.

Read `pdlc guide contract` when resolving lifecycle questions. Read [`references/product-spec-format.md`](references/product-spec-format.md) before Interview for section format, numbering, and writing rules. `product-reviewer` builds the reviewer's brief; this skill passes it through untouched and never writes a brief of its own. Run the `pdlc prompt` command afresh for every dispatch, including each follow-up to an agent already dispatched, and never reuse an earlier brief. Keep each dispatch addressable so a follow-up can go back to the same agent, always with its fresh brief.

## Resolve

Take either a concrete feature idea with no work item yet, or an exact work item number, from the conversation. If the input is missing or ambiguous, stop and ask; never infer a work item from a title, branch, recent files, open PRs, or history.

A fresh idea skips straight to Interview; nothing is published until the specification passes review.

For a work item number, run:

```bash
pdlc inspect WORK_ITEM
```

Read the resolved `Status`, `Gate State`, `# Due Next`, and body section. Continue when `Status` is `Product`, or when both state fields are empty and `# Due Next` names `pdlc-write`. In the latter case, treat `# Requirements` as the initial prompt for this existing work item. Otherwise report the actual state and stop. The snapshot does not include evidence comments; read `pdlc inspect timeline WORK_ITEM` when the evidence history is needed. This step is complete when you hold either a fresh idea, Product-stage snapshot, or an uninitialized record's requirements.

## Gate

For an existing record, follow `# Due Next` for what to do, whatever produced that state:

- Names `Uninitialized`: author the three owned sections from `# Requirements`; Land initializes this existing record and assigns its missing slug.
- Names authoring or reauthoring (`Pending`, `Changes Required`, `Stale`): reconcile the three owned sections in place against the recorded evidence.
- Names the review procedure (`Review Required`): the spec was published without its local review. Write the published three sections to the scratch file, then go straight to Review; on a clean verdict, Land it unchanged.
- Names user approval (`Approval Required`): re-author in place only when the driver explicitly requests a spec change in this turn. Without that request, it's a human boundary: report it and stop.
- Names a user decision (`Decision Required`): a human boundary. Report it, point the driver at `pdlc guide decisions`, and stop.

Any other due next result, a malformed record, or a backend error is a blocker: report it and stop.

When reconciling, preserve the record's identity, `Slug`, tasks, plans, results, approved UI section, and approved product intent. Interview only where the current record and source leave a real decision unresolved. This step is complete when the authoring mode and the driver's exact follow-up are settled.

## Interview

Create one scratch file before the first question, named for the slug, e.g. `/tmp/pdlc-route-shape-detection-body.md`, holding only the `## Product`, `## Decisions`, and `## Open Questions` headings in that order. It is the artifact you draft, have reviewed, and land.

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

This step is complete when every branch of the design tree is settled and each answer is recorded in the scratch file.

## Draft

Complete the scratch file per [`references/product-spec-format.md`](references/product-spec-format.md). Write the sections yourself from the settled answers; do not hand drafting to a sub-agent. When reconciling, write the final form of only the three owned sections, using the Resolve snapshot for context.

- Edit requirements in place. Never strike through superseded text or append "amendment" trails.
- The *why* of a change goes in the evidence body, not the spec.
- Write no lifecycle state, frontmatter, or identity marker into the body.
- Keep the whole specification proportional to the feature — a well-scoped record with a dozen tasks should still be readable in one sitting. Detail beyond that belongs in the evidence body.

This step is complete when the file holds exactly the three owned headings, in order, written to the format reference.

## Review

Dispatch `pdlc-product-reviewer` with the brief `product-reviewer DRAFT_FILE [--work-item WORK_ITEM] [--findings FILE]` writes; pass `--work-item` only when reconciling an existing record, and `--findings` only on a re-review. The command prints only the brief's path; hand the agent that path, told plainly that the file holds its instructions and that it is to read the file and carry it out in full. Do not open, edit, summarise, or paste the brief into the dispatch. The reviewer is read-only and must review the actual draft file, not a summary.

On findings, fix them in the same file, going back to Interview when a finding needs the driver, then repeat Review on the same path, re-running `product-reviewer` with `--findings` carrying the prior findings. On a clean verdict, that exact file is what Land ships; do not rewrite, reformat, or regenerate it. After three failed reconciliation passes, stop and put the decision to the driver. This step is complete only when the actual file has a clean reviewer verdict within three reconciliations.

## Land

Write only the evidence body to a local file, e.g. `/tmp/pdlc-route-shape-detection-evidence.md`, covering your scope, the reviewer's verdict and coverage boundaries, and any unresolved risk; do not add a `PDLC-*` marker. Then make exactly one call, passing the reviewed scratch file straight through as `--body`:

- if creating a new record, derive the slug from the title:

  ```bash
  pdlc post write \
    --title "Route shape detection" \
    --slug route-shape-detection \
    --body /tmp/pdlc-route-shape-detection-body.md \
    --evidence /tmp/pdlc-route-shape-detection-evidence.md
  ```

- if updating an existing record:

  ```bash
  pdlc post write \
    --work-item WORK_ITEM \
    --body /tmp/pdlc-route-shape-detection-body.md \
    --evidence /tmp/pdlc-route-shape-detection-evidence.md
  ```

Pass any local files the artifact includes, such as mockups — including any the driver supplied in this prompt — with `--attachment PATH`; see `pdlc guide attachments`. A failed call may already have changed the record, so keep the scratch and evidence files, report the exact error, and inspect the work item before retrying. After a successful landing, delete the scratch and evidence files because the work-item store is now authoritative. This step is complete when the command succeeds and its JSON shows `gateState: Approval Required` and the work item number.

## Report

Relay the command's JSON output, plus:

- the work item number, and whether it was created or reconciled;
- for an existing record, the resolved gate and why it was eligible;
- the review verdict and pass count;
- the Open Questions left on the record and any unresolved risk;
- that Product is now at `Approval Required` and needs driver approval.

The report is complete when it contains the command output, reviewer result, final gate, requested human action, and every unresolved failure or risk.

## Boundaries

- Author only the product specification: do not design UI, break the work into tasks, technically plan, or implement.
- Keep drafting with yourself and review judgement with `pdlc-product-reviewer`; the reviewer is the only agent this skill spawns.
- Use the CLI as the only work-item interface; lifecycle state, evidence markers, and every section other than `Product`, `Decisions`, and `Open Questions` belong to other owners.
- Leave production source and tests untouched.
- Do not run `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, or `pdlc post complete`; those are driver actions.
- Preserve unrelated staged, unstaged, and untracked work.

---
name: pdlc-write
description: "Use when authoring or reconciling a PDLC product specification through a source-backed interview and a technical feasibility spike, then land it as a PDLC Work Item."
argument-hint: "Fresh feature idea, or work item number to reconcile"
---

# Write product specification

Author a work item's `Product`, `Decisions`, and `Open Questions` sections through a source-backed interview with the driver, prove the product feasible with a technical spike, and land the twice-reviewed draft at `Product / Approval Required`. This skill owns those three sections and nothing else.

You drive the loop yourself, inline, so the conversation with the driver stays with you. `pdlc prompt product-writer` is the loop's controller: each run reads the draft and its reviews and prints a brief whose `## Next steps` names the one step due now. Read [`references/product-spec-format.md`](references/product-spec-format.md) before writing any section. Read `pdlc guide contract` when resolving lifecycle questions.

## Resolve

Take either a concrete feature idea with no work item yet, or an exact work item number, from the conversation. If the input is missing or ambiguous, stop and ask; never infer a work item from a title, branch, recent files, open PRs, or history. For a fresh idea, choose the title and a short kebab-case slug derived from it yourself; the driver need not confirm them.

This step is complete when you hold either an exact work item number or a fresh idea with its slug.

## Loop

Run the controller:

- if writing a fresh idea:

  ```bash
  pdlc prompt product-writer --slug SLUG
  ```

- if writing an existing work item:

  ```bash
  pdlc prompt product-writer --work-item WORK_ITEM
  ```

Add `--reauthor` only when the driver asked for a change to a spec awaiting their approval in this turn. Pass each local file the driver supplies, such as a mockup, with `--attachment PATH` on the next run, once; the command keeps it for every later brief and for landing, and `pdlc guide attachments` covers the rest. When the command refuses, report its exact error and stop; a refusal at a human boundary is the driver's to resolve, and `pdlc guide decisions` covers a `Decision Required` record.

The command prints only the brief's path. Read the brief and carry out its `## Next steps`, then run the same command again; repeat until the draft has landed. The brief names the draft file, the only copy of the work; every review, spike, and landing command takes that exact path.

This step is complete when the land command the brief names has succeeded and its JSON shows `gateState: Approval Required` and the work item number.

## Interview

When a step needs an answer source cannot give, interview the driver relentlessly. Walk down each branch of the design tree, resolving dependencies between decisions one by one. Ask one question at a time, with your recommended answer.

**Search the codebase before you ask.** Answer from source or Git history; bring the driver only the questions source genuinely cannot answer. Everything you learn feeds Prior Art & Reuse; write it down as you go.

Use `AskUserQuestion` when available. Otherwise format the one question with lettered options:

```
1. What is the primary goal of this feature?
   A. Improve first-run orientation
   B. Reduce time to plan a multi-day route
   C. Cut support burden for offline downloads
   D. Other: [please specify]
```

Record each settled answer in the draft at once: an answer that binds implementation becomes a **Constraint**; an alternative considered and rejected goes in **Decisions**. A Not feasible spike sends you back here as often as it takes; abandoning the work item is the driver's call alone.

When writing the draft:

- Write the sections yourself from the settled answers; drafting stays with you.
- Edit requirements in place, with no strike-through or "amendment" trail; the *why* of a change goes in the evidence body.
- Write no lifecycle state, frontmatter, or identity marker into the body.
- Keep the whole specification proportional to the feature, readable in one sitting; detail beyond that belongs in the evidence body.

## Dispatch

Each review and the spike run in a sub-agent: `pdlc-product-reviewer` for both reviews, `pdlc-tech-planner` for the spike. Run the `pdlc prompt` command the brief names afresh for every dispatch, including a follow-up to an agent already dispatched, and hand the agent only the path it prints, told plainly that the file holds its instructions and that it is to read the file and carry it out in full. Keep each dispatch addressable so a follow-up can go back to the same agent with its fresh brief.

Run at most three passes of either review before you put the outstanding findings to the driver. A rejected finding the reviewer raises again goes to the driver at once.

## Land

Write the evidence body the brief asks for to a local file, e.g. `/tmp/pdlc-route-shape-detection-evidence.md`, with no `PDLC-*` marker, and run the land command the brief names with it, attachments included.

A failed call may already have changed the record: keep the draft and evidence files, report the exact error, and inspect the work item before retrying. After a successful landing, delete the evidence file; the work-item store is now authoritative.

## Report

Relay the land command's JSON output, plus:

- the work item number, and whether it was created or reconciled;
- both review verdicts and their pass counts, and how many spikes it took to reach feasible;
- every rejected finding with its reason;
- the Open Questions left on the record and any unresolved risk;
- that Product is now at `Approval Required` and needs driver approval.

The report is complete when it contains the command output, both review results, the feasibility outcome, the final gate, the requested human action, and every unresolved failure or risk.

## Boundaries

- Author only the product specification and its technical approach: leave UI design, task breakdown, implementation plans, and code to later stages.
- `pdlc-product-reviewer` and `pdlc-tech-planner` are the only agents this skill spawns.
- Use the CLI as the only work-item interface; lifecycle state, evidence markers, and every section other than `Product`, `Decisions`, and `Open Questions` belong to other owners.
- Leave production source and tests untouched.
- Do not run `pdlc post approve`, `pdlc post skip`, or `pdlc post complete`; those are driver actions.
- Execute `pdlc post invalidate` when explicitly authorized by the driver; authorization persists across turns within the agreed work-item, stage, and task scope until fulfilled or revoked. Do not initiate invalidation autonomously.
- Preserve unrelated staged, unstaged, and untracked work.

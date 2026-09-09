# Cumulative review dispatch prompt

Fill this in and pass it as the whole prompt for **one** general-purpose sub-agent dispatch per verify pass. The sub-agent runs the project's `cumulative-review` capability over the record's cumulative change scope and returns its prioritised findings. Resolve the first line with `pdlc inspect capability cumulative-review`: a configured project emits "You must invoke the `<skill>` skill before continuing…"; an unconfigured one emits an instruction to perform the review inline.

The review runs in a sub-agent rather than inline because it fans out a batch of parallel reviewers over the whole diff — keeping that traffic out of the verify pass leaves room for the claims audit and finding reconciliation that follow it.

Substitute every `<...>` placeholder. The sub-agent knows nothing about PDLC: give it a scope and an intent packet, never an work item number or a stage name.

---

```text
<the line from `pdlc inspect capability cumulative-review`>

Review the change scope below and report the findings verbatim. Review only —
do not edit, stage, commit, or apply any fix.

## Execution boundary

You are being invoked as a leaf worker for this one review.
Do not invoke any `pdlc-*` skill; invoke only the review capability named in the line above.
Do not re-run the calling skill or rediscover the lifecycle stage.
Return the findings to the calling `pdlc-verify` skill.

## Scope
<one of:
 - "The current branch's diff against its base branch" — the default, when the
   record's work is unmerged and still on this branch.
 - "The commit range <base>..<head>" — when the work landed in pieces and no
   meaningful branch diff remains.
 - "These files: <explicit paths>" — only when neither of the above covers the
   record's actual change scope.>

## Intent packet
- Behaviour intended to change: <the shipped scope, in plain terms>
- Behaviour that must remain unchanged: <adjacent behaviour the change must not disturb>
- Constraints: <the record's binding constraints in plain terms — offline behaviour,
  migration, concurrency isolation, performance budgets, safety, privacy — with no
  C-* identifiers, which mean nothing outside the record>

## Report back
1. Every finding, prioritised (Fix now / Fix soon / Optional follow-up), with
   its file and line or nearest symbol, category, severity, why it matters, and
   confidence.
2. Which review passes ran and which were skipped as inapplicable.
3. Anything the scope could not cover.
4. "No findings" plainly, if that is the outcome — never soften or summarise a finding away.
```

---

## Filling it in

- **Resolve the scope before dispatching.** If every commit since the last `Verified @` touched only work-item paperwork, the prior clean result still holds — carry it forward and do not dispatch at all.
- **If the record's work has already been merged in pieces**, the branch diff no longer covers it. Do not let the sub-agent fall back to an automatic scope that silently reviews nothing: work out the right base ref or commit range first, and ask the driver when you cannot.
- **Translate the constraints.** The sub-agent cannot resolve `FR-*`/`C-*`, so write what each one requires rather than citing it.
- **Relay findings unchanged.** Any finding of any severity stops the verify pass before the report is posted; never write clean verification evidence while one is open, and never re-prioritise or reinterpret the sub-agent's verdict.

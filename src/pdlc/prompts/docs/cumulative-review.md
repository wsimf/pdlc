{{CUMULATIVE_REVIEW_LINE}}

Review the change scope below and report the findings verbatim. Review only —
do not edit, stage, commit, or apply any fix.

{{INCLUDE:shared/execution-boundary.md}}
Invoke only the review capability named in the line above, if any.
Do not re-run the calling skill or rediscover the lifecycle stage.
Return the findings to the calling skill.

## Scope

{{SCOPE}}

## Intent packet
- Behaviour intended to change: {{SHIPPED_BEHAVIOR}}
- Behaviour that must remain unchanged: {{UNCHANGED_BEHAVIOR}}
- Constraints: {{CONSTRAINTS}}

## Report back
1. Every finding, prioritised (Fix now / Fix soon / Optional follow-up), with
   its file and line or nearest symbol, category, severity, why it matters, and
   confidence.
2. Which review passes ran and which were skipped as inapplicable.
3. Anything the scope could not cover.
4. "No findings" plainly, if that is the outcome — never soften or summarise a finding away.

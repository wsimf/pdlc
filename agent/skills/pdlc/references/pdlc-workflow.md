# PDLC workflow

This diagram is the enabled Feature pipeline. The resolved record's `workType` selects a pipeline before routing; a missing type uses Feature compatibility, while unknown types and registered unavailable pipelines block.

This flow describes how the parent work item, its state, delivery tasks,
and pull requests work together. The work item store is the system of record;
the focused `pdlc` commands enforce every work item mutation.

```mermaid
flowchart TD
    Start([Human names a work item<br/>or autonomous loop runs])
    New([Human supplies a fresh idea]) --> Write
    Next["pdlc next<br/>reads Status + Gate State"]

    Start --> Next

    Next -->|Pending / Stale / Changes Required| Owner
    Next -->|"Product, any gate"| HumanInput["human-input<br/>autonomous loop stops,<br/>asks the driver to run pdlc-write"]
    Next -->|Review Required| Review["pdlc-review<br/>independent reviewer"]
    Next -->|Decision Required| Decision["human-decision<br/>decision-resolver-workflow"]
    Next -->|CI Pending| CIWait["autonomous loop backs off<br/>while checks run;<br/>driver may run pdlc post ci"]
    Next -->|Approval Required| Human["Human approval required"]
    Next -->|"Skipped stage (Skipped States)"| SkipCascade["pdlc next auto-advances<br/>Pending / Changes / Stale straight to<br/>the next stage's Pending<br/>PDLC-SKIPPED, no specialist or reviewer"]
    Next -->|Complete| Done([No work])
    Next -->|"Malformed / unknown type / unavailable pipeline"| Blocked([Blocked: report exact state])

    SkipCascade --> Next
    CIWait --> CIGate
    HumanInput --> Write

    Decision --> DecisionLand["pdlc post decision<br/>manifest of per-decision outcomes<br/>(each answered, or deferred to its own<br/>Product / Pending work item)<br/>sets Changes Required"]
    DecisionLand --> Owner
    Decision -->|"resolution changes approved upstream intent"| Invalidate

    Invalidate["pdlc post invalidate — human<br/>returns a settled / Approved stage to Stale<br/>PDLC-INVALIDATED<br/>marks downstream evidence stale"]
    Invalidate --> Next
    Settled([Any Approved stage<br/>upstream intent changed]) --> Invalidate

    Owner{"Active stage"}

    Owner -->|Product| Write["pdlc-write — human only<br/>interview, draft, local review"]
    Owner -->|UI| UI["pdlc-tasks<br/>prepare UI section"]
    Owner -->|Tasks| Tasks["pdlc-tasks<br/>prepare delivery tasks"]
    Owner -->|Technical Plan| Plan["pdlc-plan<br/>prepare task plans"]
    Owner -->|Implementation| Implement["pdlc-implement<br/>select one eligible task"]
    Owner -->|Testing| Test["pdlc-test<br/>trace requirements to coverage"]
    Owner -->|Verification| Verify["pdlc-verify<br/>claims, journeys, UX, evidence"]

    Write --> LandProduct["pdlc post write<br/>lands at Product / Approval Required"]
    LandProduct --> Human
    UI --> DryRun
    Tasks --> DryRun

    DryRun["pdlc post tasks --dry-run<br/>guard stage + gate<br/>validate coverage, dependencies,<br/>UI applicability — writes nothing"]
    DryRun --> LocalReview["pdlc-tasks-reviewer<br/>reads the local files, not the record"]
    LocalReview --> LocalVerdict{Findings?}
    LocalVerdict -->|Changes, max 2 passes| UI
    LocalVerdict -->|Changes, max 2 passes| Tasks
    LocalVerdict -->|Clean| Land

    Land["pdlc post tasks<br/>replace UI section, or create/update<br/>delivery tasks<br/>post evidence<br/>set Approval Required"]
    Land --> Human

    Plan --> PlanDryRun["pdlc post plan --dry-run<br/>guard stage + gate<br/>validate plan fragments<br/>against the task tree — writes nothing"]
    PlanDryRun --> PlanReview["pdlc-plan-reviewer<br/>reads the local task bodies"]
    PlanReview --> PlanVerdict{Findings?}
    PlanVerdict -->|Changes, max 2 passes| Plan
    PlanVerdict -->|Clean| PlanLand

    PlanLand["pdlc post plan<br/>post a ## Technical Plan comment per planned task<br/>post evidence<br/>set Approval Required"]
    PlanLand --> Human
    Test --> Publish

    Verify --> VResult{"pdlc post verify<br/>--recommendation"}
    VResult -->|Approval Required| Human
    VResult -->|Decision Required| Decision
    VResult -->|Changes Required| Verify
    VResult -->|"Changes Required --bounce STAGE"| Bounce["PDLC-REVIEW records Bounce + Loop<br/>STAGE → Stale, no driver step<br/>(advances the rework count)"]
    Bounce --> Next

    Implement --> TaskWork["Implement one task<br/>task-depth review<br/>PR + task evidence"]
    TaskWork --> TasksRemain{Any delivery tasks<br/>still open?}
    TasksRemain -->|Yes| Next
    TasksRemain -->|No| Publish

    Publish["pdlc post implement / pdlc post test<br/>complete transition<br/>post evidence<br/>set Review Required"]
    Publish --> Review

    Review --> ReviewResult{Findings?}
    ReviewResult -->|Changes required| Owner
    ReviewResult -->|Decision required| Decision
    ReviewResult -->|"Clean, Testing"| Churned{"Verification rework loop<br/>entered 1–3×?"}
    ReviewResult -->|"Clean, Implementation"| CIGate["pdlc post ci<br/>reconcile the registered PR stack's CI<br/>green → Approval Required<br/>red → Changes Required"]
    CIGate -->|"green"| Churned
    CIGate -->|red| Owner
    Churned -->|no| Human
    Churned -->|yes| AutoApprove["PDLC-AUTOAPPROVED<br/>the CI gate / pdlc post review<br/>skip the human step,<br/>advance to next stage Pending"]
    AutoApprove --> Next

    Human --> Approve["pdlc post approve<br/>post approval evidence<br/>advance to next stage Pending"]
    Approve --> Next

    Human -->|Verification only| Complete["pdlc post complete<br/>requires clean verification<br/>and all delivery tasks closed"]
    Complete --> Done
```

## Gate states per stage

Every `Status` stage carries the same `Gate State` shape, transitioned by a
fixed script and actor. Most stages depart from it. `Product`, `UI`, `Tasks`,
and `Technical Plan` are reviewed **before** publication, so they land straight
at `Approval Required` and never hold `Review Required` — and because
`pdlc post review` is the only thing that sets `Changes Required`, they never
hold that either. Their gate set is `Pending`, `Stale`, `Approval Required`,
`Approved`, and a landed artifact is reworked by returning it to `Stale`.
When the driver asks for a change while one of these stages is still at
`Approval Required`, its own land script (`pdlc post write` /
`pdlc post tasks` / `pdlc post plan`) resets the gate to `Stale` itself
and re-lands the reviewed artifact in the same call. No `PDLC-INVALIDATED`
comment: the artifact never settled at `Approved`, so there is nothing to
invalidate, and the re-land's own stage evidence records the change. Nothing
about it feeds the rework/churn count.
`Testing` keeps the full post-publication review shape; `Implementation` stays
`Pending` across multiple task loops before its first `Review Required`;
`Verification` skips `Review Required` entirely.

`Implementation` has one extra gate: a clean stage review lands `CI Pending`, not `Approval Required`, because the reviewer judges the code without waiting on the registered PR stack's CI.
`pdlc post ci` then reconciles `CI Pending` against the live check rollup — green (or no checks configured) → `Approval Required`, red → `Changes Required` with a `PDLC-IMPLEMENTATION` note.
It is mechanical, carries no identity check, and the autonomous loop runs it unattended once checks finish; while they run, `pdlc next` reports the record as no work so the loop backs off.
`Testing` still lands `Approval Required` straight from review.

Both `Implementation` and `Testing` approval gates are auto-cleared on a record that has demonstrably iterated the rework loop. The count comes only from Verification `PDLC-REVIEW` comments whose `verdict` is `Changes Required`, whose `bounce` names an upstream stage, and whose `loop` matches the pipeline's named rework policy. Between 1 and the selected pipeline's rework cap (three for Feature), the script that would set the gate advances straight past it instead: the CI gate on green CI and `pdlc post review` on a clean Testing review post a `PDLC-AUTOAPPROVED` comment and `set_state` to the next stage's `Pending`, so no human step and no later routing pass is involved. On the first pass, past the cap, and for `Verification` always, the gate still stops for the driver. `pdlc post verify --bounce STAGE` advances the count and returns the named upstream stage to `Stale` without a driver step or `PDLC-INVALIDATED`; explicit driver invalidation remains separate and does not affect the loop count.

Both post-publication reviews (`Implementation`, `Testing`) can also land at
`Decision Required` instead of `Changes Required` when a finding needs a
product, architecture, UX, safety, or scope call from the driver, and
`Verification` can reach the same gate from its own audit
(`pdlc post verify --recommendation "Decision Required" --decision`). That
gate stops the autonomous loop with no reconciliation attempt;
`pdlc next` routes it to `human-decision`. The driver clears it through
`references/decision-resolver-workflow.md`: `pdlc post decision` lands a
manifest of per-decision outcomes — each answered, or deferred into its own
`Product / Pending` work item — and moves the gate to `Changes Required`,
routing back to the stage owner. A decision that changes approved upstream
intent goes through `pdlc post invalidate` instead.

```mermaid
stateDiagram-v2
    [*] --> Product : pdlc post write — pdlc-write (human), reviewed spec only

    state Product {
        [*] --> P_Approval
        P_Pending --> P_Approval : pdlc post write — pdlc-write (human)
        P_Changes --> P_Approval : pdlc post write — pdlc-write (human)
        P_Stale --> P_Approval : pdlc post write — pdlc-write (human)
        P_Approval --> P_Approval : pdlc post write — driver change request (gate reset to Stale first, no comment)
    }
    note left of Product
        Product has no Review Required state: pdlc-write
        drafts and has the specification reviewed locally
        before anything is written to the work item store.
    end note
    Product --> UI : pdlc post approve — human

    state UI {
        [*] --> U_Pending
        U_Pending --> U_Approval : pdlc post tasks — pdlc-tasks
        U_Stale --> U_Approval : pdlc post tasks — pdlc-tasks
        U_Approval --> U_Approval : pdlc post tasks — driver change request (gate reset to Stale first, no comment)
    }
    note left of UI
        UI and Tasks have no Review Required state: pdlc-tasks
        has pdlc-tasks-reviewer review the manifest and files
        before pdlc post tasks writes anything to the work item store.
    end note
    UI --> Tasks : pdlc post approve — human

    state Tasks {
        [*] --> T_Pending
        T_Pending --> T_Approval : pdlc post tasks — pdlc-tasks
        T_Stale --> T_Approval : pdlc post tasks — pdlc-tasks
        T_Approval --> T_Approval : pdlc post tasks — driver change request (gate reset to Stale first, no comment)
    }
    Tasks --> TechnicalPlan : pdlc post approve — human

    state TechnicalPlan {
        [*] --> TP_Pending
        TP_Pending --> TP_Approval : pdlc post plan — pdlc-plan
        TP_Stale --> TP_Approval : pdlc post plan — pdlc-plan
        TP_Approval --> TP_Approval : pdlc post plan — driver change request (gate reset to Stale first, no comment)
    }
    note left of TechnicalPlan
        Technical Plan has no Review Required state:
        pdlc-plan has pdlc-plan-reviewer review the rebuilt
        task bodies before pdlc post plan writes any of them.
    end note
    TechnicalPlan --> Implementation : pdlc post approve — human

    state Implementation {
        [*] --> I_Pending
        I_Pending --> I_Pending : pdlc-implement — one task + PR per pass, any delivery task still open
        I_Pending --> I_Review : pdlc post implement — pdlc-implement, only once every delivery task is closed
        I_Changes --> I_Review : pdlc post implement — pdlc-implement
        I_Stale --> I_Review : pdlc post implement — pdlc-implement
        I_Review --> I_Changes : pdlc post review — pdlc-review (reviewer)
        I_Review --> I_Decision : pdlc post review — pdlc-review (reviewer), finding needs the driver
        I_Review --> I_CIPending : pdlc post review — pdlc-review (reviewer), clean review does not wait for CI
        I_CIPending --> I_Approval : pdlc post ci — CI green, or no checks configured
        I_CIPending --> I_Changes : pdlc post ci — CI red, PDLC-IMPLEMENTATION note
        I_Decision --> I_Changes : pdlc post decision --manifest — driver (each decision answered or deferred to its own work item)
    }
    Implementation --> Testing : pdlc post approve — human
    Implementation --> Testing : pdlc post ci — CI green + reworked 1–3× (PDLC-AUTOAPPROVED, no human)

    state Testing {
        [*] --> Te_Pending
        Te_Pending --> Te_Review : pdlc post test — pdlc-test
        Te_Changes --> Te_Review : pdlc post test — pdlc-test
        Te_Stale --> Te_Review : pdlc post test — pdlc-test
        Te_Review --> Te_Changes : pdlc post review — pdlc-review (reviewer)
        Te_Review --> Te_Decision : pdlc post review — pdlc-review (reviewer), finding needs the driver
        Te_Review --> Te_Approval : pdlc post review — pdlc-review (reviewer)
        Te_Decision --> Te_Changes : pdlc post decision --manifest — driver (each decision answered or deferred to its own work item)
    }
    Testing --> Verification : pdlc post approve — human
    Testing --> Verification : pdlc post review — clean review + reworked 1–3× (PDLC-AUTOAPPROVED, no human)

    state Verification {
        [*] --> V_Pending
        V_Pending --> V_Changes : pdlc-verify — finding (no Review Required stop)
        V_Pending --> V_Approval : pdlc-verify — clean report
        V_Pending --> V_Decision : pdlc-verify — finding needs the driver
        V_Changes --> V_Changes : pdlc-verify — finding persists
        V_Changes --> V_Approval : pdlc-verify — clean report
        V_Changes --> V_Decision : pdlc-verify — finding needs the driver
        V_Decision --> V_Changes : pdlc post decision --manifest — driver
        V_Stale --> V_Changes : pdlc-verify — finding
        V_Stale --> V_Approval : pdlc-verify — clean report
    }
    Verification --> Implementation : pdlc post verify --bounce STAGE — Changes Required, autonomous (STAGE → Stale, PDLC-REVIEW Bounce + Loop)
    Verification --> Complete : pdlc post complete — explicit human instruction

    Complete --> [*]

    note right of Product
        Any stage's Approved/settled state can return to that
        stage's Stale via pdlc post invalidate (human) when
        upstream intent changes, or — for a Verification
        Changes Required run — via pdlc post verify --bounce
        STAGE with no driver step.
        A stage declared in Skipped States (pdlc post skip, human)
        is auto-advanced Pending/Changes/Stale straight to the
        next stage's Pending by pdlc next, bypassing its
        specialist and reviewer entirely.
        On a record with 1–3 Verification rework bounces, the
        Implementation and Testing Approval Required gates are
        auto-cleared (PDLC-AUTOAPPROVED) by the CI gate / pdlc post review — no human, capped by the selected pipeline's rework policy.
        Product, UI, Tasks, and Technical Plan reach Approval
        Required directly; their review happens on local files
        beforehand and leaves no gate state of its own. A driver
        change request while one of them is still at Approval
        Required is handled by its own land script: it resets
        the gate to Stale itself (no comment, no churn) and
        re-lands in the same call.
    end note
```

A skipped `Verification` stage stops at `Verification / Approval Required` rather than auto-completing because completion always requires an explicit `pdlc post complete` instruction from the driver.

`pdlc post tasks` and `pdlc post plan` land a stage at `Approval Required` without
an intervening reviewer gate, so the review each depends on happens inside its
skill, before the call. They, `pdlc post implement`, `pdlc post test`, and `pdlc post review` are the
only scripts a specialist or reviewer agent runs unattended; `pdlc post approve`, `pdlc post invalidate`,
`pdlc post skip`, `pdlc post complete`, and `pdlc post decision` carry no
identity check — every agent acts under the driver's own store credentials — so only the orchestrator
calls them, and only in direct response to an explicit human instruction in this turn.
`pdlc post write`, `pdlc post tasks`, and `pdlc post plan` additionally
reset their own stage's `Approval Required` gate to `Stale` when re-landing on a
driver change request (a bare gate transition, no comment), so that rework needs
no separate `pdlc post invalidate` step.
`pdlc next`'s skip-cascade and `pdlc post ci`'s CI reconciliation are fully automatic gate transitions with no live actor — both record an external fact rather than a judgement, so the loop runs them unattended and a driver may also run `pdlc post ci` directly when resuming a `CI Pending` record.
The churn gate is the other one: the CI gate (green CI) and `pdlc post review` (clean Testing review) clear the `Implementation` / `Testing` `Approval Required` step with a `PDLC-AUTOAPPROVED` comment on a record within the selected pipeline's rework cap, and `pdlc post verify --bounce STAGE` performs the matching `Verification → upstream` re-entry autonomously. All three still stop the loop the moment a reviewer or the audit returns `Decision Required`, and the churn gate reverts to a human stop past the cap and for `Verification` always.

## Implementation aggregation

The parent work item remains `Implementation / Pending` after each task
completion. It may enter `Implementation / Review Required` only after every
delivery task is closed with settled evidence. This prevents testing or
verification from starting after only the first implementation task.

Author the Product draft below with the driver, then take it through review, a feasibility spike, and a technical review until it is ready to land.

You are the agent already talking with the driver. This brief does not replace that conversation: anything the driver has already settled with you counts as an interview answer, so record it in the draft rather than asking again.

## Draft

`{{DRAFT_PATH}}` is the only copy of the draft. Edit it in place; every command below takes this exact path, and nothing else can land.

{{#IF FRESH}}
This is a new work item, `{{SLUG}}`. The draft holds only its headings. The slug is fixed now; the title is yours to choose and may change until it lands.
{{/IF}}
{{#IF UNINITIALIZED}}
Work item `{{WORK_ITEM}}` exists but has never been authored. The draft holds only its headings; author it from the work item's requirements below.

--- BEGIN REQUIREMENTS ---

{{REQUIREMENTS}}

--- END REQUIREMENTS ---
{{/IF}}
{{#IF RECONCILE}}
Work item `{{WORK_ITEM}}` is at Product / {{GATE_STATE}}. The draft holds its current Product, Decisions, and Open Questions; reconcile them in place against the changes below. Preserve approved product intent, requirement and constraint ids, and everything the driver has not asked to change.
{{/IF}}
{{#IF REVIEW_ONLY}}
Work item `{{WORK_ITEM}}` was published without its local review. The draft holds the published sections exactly; review them as they are, and change them only where a finding needs it.
{{/IF}}
{{#IF REAUTHOR}}
Work item `{{WORK_ITEM}}` is awaiting the driver's approval, and the driver asked for a change. The draft holds the published sections; change only what the driver asked for and what follows from it.
{{/IF}}
{{#IF PATCH}}
Work item `{{WORK_ITEM}}` is past Product, at {{ACTIVE_STAGE}}. The draft holds the landed Product sections. Correct only the defect you are patching, following `pdlc guide patch`; do not interview the driver for a product choice nobody has made.
{{/IF}}
{{#IF STALE_REASON}}

### Why Product is Stale

{{STALE_REASON}}
{{/IF}}
{{#IF UPSTREAM_CHANGES}}

### Changed since last publish

{{UPSTREAM_CHANGES}}
{{/IF}}
{{#IF CHANGE_REQUESTS}}

### Change requests

--- BEGIN CHANGE REQUESTS ---

{{CHANGE_REQUESTS}}

--- END CHANGE REQUESTS ---
{{/IF}}

{{#IF ATTACHMENTS}}
{{INCLUDE:shared/attachments.md}}

{{/IF}}
## Where the draft stands

{{PHASE_SUMMARY}}
{{#IF PROBLEMS}}

The draft cannot land as it stands:

{{#EACH PROBLEMS}}
- {{PROBLEM}}
{{/EACH}}
{{/IF}}

## Next steps

{{#IF PHASE_DRAFT}}
{{#IF REVIEW_ONLY}}
1. Leave the draft as it is; the published sections get their review first.
2. Start the product review: `{{PRODUCT_REVIEW_COMMAND}}`
{{#ELSE}}
{{#IF DRAFT_EMPTY}}
1. Write the `## Product`, `## Decisions`, and `## Open Questions` sections into the draft from the settled answers, interviewing the driver on every branch that source and the conversation leave open.
2. Leave out `### Technical approach`; the feasibility spike writes it after the product review.
{{#ELSE}}
1. Revise the draft in place as `## Draft` above directs.
2. Leave any `### Technical approach` as it is; the feasibility spike rewrites it after the product review.
{{/IF}}
3. Start the product review: `{{PRODUCT_REVIEW_COMMAND}}`
{{/IF}}
{{/IF}}
{{#IF PHASE_PRODUCT_REVIEW}}
1. Run `{{PRODUCT_REVIEW_COMMAND}}` and dispatch the product reviewer with the brief it prints.
2. When it replies, run `{{WRITER_COMMAND}}` again.
{{/IF}}
{{#IF PHASE_PRODUCT_FINDINGS}}
1. Read the product review's findings in `{{PRODUCT_FINDINGS_PATH}}`.
2. Under each finding, add one line: `Author response: Fixed — <what changed>` once you have fixed it in the draft, or `Author response: Rejected — <why the draft is right>`. Take a finding that needs a product choice to the driver first.
3. If the reviewer raises a finding you rejected again, put it to the driver and record their answer.
4. Re-review: `{{PRODUCT_REVIEW_COMMAND}}`
{{/IF}}
{{#IF PHASE_SPIKE}}
1. Run `{{SPIKE_COMMAND}}` and dispatch `pdlc-tech-planner` with the brief it prints. It writes `### Technical approach` into the draft and reports driver decisions, assumptions, and blockers.
2. When it replies, run `{{WRITER_COMMAND}}` again.
{{/IF}}
{{#IF PHASE_NOT_FEASIBLE}}
1. The spike found the product, as specified, not feasible. Take its blockers to the driver and settle how the product changes so that it becomes feasible.
2. Revise the product sections in the draft accordingly; the product review and the spike then run again.
3. Repeat until the spike finds the product feasible. Abandoning the work item is the driver's call alone.
{{/IF}}
{{#IF PHASE_TECHNICAL_REVIEW}}
{{#IF SPIKE_FRESH}}
1. First settle what the spike reported: take each driver decision to the driver, fold confirmed assumptions into the requirement or constraint they support, and settle the rest with the driver. Keep `### Assumptions` out of the draft and `## Open Questions` to implementation details that change no requirement or constraint. If any of this changes the product sections, run `{{WRITER_COMMAND}}` again instead of continuing.
2. Run `{{TECHNICAL_REVIEW_COMMAND}}` and dispatch the product reviewer with the brief it prints.
3. When it replies, run `{{WRITER_COMMAND}}` again.
{{#ELSE}}
1. Run `{{TECHNICAL_REVIEW_COMMAND}}` and dispatch the product reviewer with the brief it prints.
2. When it replies, run `{{WRITER_COMMAND}}` again.
{{/IF}}
{{/IF}}
{{#IF PHASE_TECHNICAL_FINDINGS}}
1. Read the technical review's findings in `{{TECHNICAL_FINDINGS_PATH}}`.
2. Under each finding, add one line: `Author response: Fixed — <what changed>` or `Author response: Rejected — <why the draft is right>`. Fix the approach yourself, or run `{{SPIKE_COMMAND}}` again when the fix needs a deeper spike. A finding that changes the product sections sends the draft back to the product review.
3. If the reviewer raises a finding you rejected again, put it to the driver and record their answer.
4. Re-review: `{{TECHNICAL_REVIEW_COMMAND}}`
{{/IF}}
{{#IF PHASE_READY}}
{{#IF PATCH}}
Both reviews are clean. Copy both findings files somewhere safe for the evidence body, then continue `pdlc guide patch` from its impact step, landing this exact draft with `--patch`:

`{{LAND_COMMAND}}`
{{#ELSE}}
Both reviews are clean. Write the evidence body to a file — the scope, both review verdicts and their pass counts, the feasibility iterations, every rejected finding with its reason, and any unresolved risk — then land this exact draft:

`{{LAND_COMMAND}}`
{{/IF}}
{{/IF}}

Run `{{WRITER_COMMAND}}` again after each step; it reads the draft and the reviews and names the next one.

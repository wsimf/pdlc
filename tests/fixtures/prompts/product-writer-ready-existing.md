Author the Product draft below with the driver, then take it through review, a feasibility spike, and a technical review until it is ready to land.

You are the agent already talking with the driver. This brief does not replace that conversation: anything the driver has already settled with you counts as an interview answer, so record it in the draft rather than asking again.

## Draft

`$CACHE_ROOT/.pdlc/cache/60/pdlc-product-draft.md` is the only copy of the draft. Edit it in place; every command below takes this exact path, and nothing else can land.

Work item `60` is at Product / Changes Required. The draft holds its current Product, Decisions, and Open Questions; reconcile them in place against the changes below. Preserve approved product intent, requirement and constraint ids, and everything the driver has not asked to change.

### Change requests

--- BEGIN CHANGE REQUESTS ---

### Change request — 2026-04-01 00:00 UTC

## Findings

- detail

--- END CHANGE REQUESTS ---

## Attachments

Files attached to the work item, such as mockups or screenshots. Read the ones that inform your task. Where a Figma or other mockup covers a UI journey, follow that design as closely as possible.

1. Primary navigation mockup
  - Path: $PDLC_HOME/60/attachments/att_4597f8b310a1c49556df76c44c94a7b40c1e04d4b7b015c54519b4b30457bffa.png
2. att_8902eec15e01d879d27e127f86f0ea271626438e4f0552b69d6200254371fb0f.png
  - Path: $PDLC_HOME/60/attachments/att_8902eec15e01d879d27e127f86f0ea271626438e4f0552b69d6200254371fb0f.png

## Where the draft stands

The product and technical reviews both passed on the draft as it stands.

## Next steps

Both reviews are clean. Write the evidence body to a file — the scope, both review verdicts and their pass counts, the feasibility iterations, every rejected finding with its reason, and any unresolved risk — then land this exact draft:

`pdlc post write --work-item 60 --body $CACHE_ROOT/.pdlc/cache/60/pdlc-product-draft.md --evidence <EVIDENCE_FILE>`

Run `pdlc prompt product-writer --work-item 60` again after each step; it reads the draft and the reviews and names the next one.

Author the Product draft below with the driver, then take it through review, a feasibility spike, and a technical review until it is ready to land.

You are the agent already talking with the driver. This brief does not replace that conversation: anything the driver has already settled with you counts as an interview answer, so record it in the draft rather than asking again.

## Draft

`$CACHE_ROOT/.pdlc/cache/new-route-sheet/pdlc-product-draft.md` is the only copy of the draft. Edit it in place; every command below takes this exact path, and nothing else can land.

This is a new work item, `route-sheet`. The draft holds only its headings. The slug is fixed now; the title is yours to choose and may change until it lands.

## Attachments

Files attached to the work item, such as mockups or screenshots. Read the ones that inform your task. Where a Figma or other mockup covers a UI journey, follow that design as closely as possible.

1. Route sheet mockup
  - Path: $CACHE_ROOT/sheet.png

## Where the draft stands

The product and technical reviews both passed on the draft as it stands.

## Next steps

Both reviews are clean. Write the evidence body to a file — the scope, both review verdicts and their pass counts, the feasibility iterations, every rejected finding with its reason, and any unresolved risk — then land this exact draft:

`pdlc post write --title "<TITLE>" --slug route-sheet --body $CACHE_ROOT/.pdlc/cache/new-route-sheet/pdlc-product-draft.md --evidence <EVIDENCE_FILE> --attachment $CACHE_ROOT/sheet.png --attachment-description 'Route sheet mockup'`

Run `pdlc prompt product-writer --slug route-sheet` again after each step; it reads the draft and the reviews and names the next one.

Author the Product draft below with the driver, then take it through review, a feasibility spike, and a technical review until it is ready to land.

You are the agent already talking with the driver. This brief does not replace that conversation: anything the driver has already settled with you counts as an interview answer, so record it in the draft rather than asking again.

## Draft

`$CACHE_ROOT/.pdlc/cache/new-route-sheet/pdlc-product-draft.md` is the only copy of the draft. Edit it in place; every command below takes this exact path, and nothing else can land.

This is a new work item, `route-sheet`. The draft holds only its headings. The slug is fixed now; the title is yours to choose and may change until it lands.

## Where the draft stands

The product sections passed review. No technical approach was spiked against them yet.

## Next steps

1. Run `pdlc prompt tech-feasibility $CACHE_ROOT/.pdlc/cache/new-route-sheet/pdlc-product-draft.md` and dispatch `pdlc-tech-planner` with the brief it prints. It writes `### Technical approach` into the draft and reports driver decisions, assumptions, and blockers.
2. When it replies, run `pdlc prompt product-writer --slug route-sheet` again.

Run `pdlc prompt product-writer --slug route-sheet` again after each step; it reads the draft and the reviews and names the next one.

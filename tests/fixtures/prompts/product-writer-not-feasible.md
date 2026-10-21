Author the Product draft below with the driver, then take it through review, a feasibility spike, and a technical review until it is ready to land.

You are the agent already talking with the driver. This brief does not replace that conversation: anything the driver has already settled with you counts as an interview answer, so record it in the draft rather than asking again.

## Draft

`$CACHE_ROOT/.pdlc/cache/new-route-sheet/pdlc-product-draft.md` is the only copy of the draft. Edit it in place; every command below takes this exact path, and nothing else can land.

This is a new work item, `route-sheet`. The draft holds only its headings. The slug is fixed now; the title is yours to choose and may change until it lands.

## Where the draft stands

The feasibility spike found the product, as specified, not feasible.

The draft cannot land as it stands:

- the feasibility verdict is Not feasible; revise the product with the driver until it is feasible

## Next steps

1. The spike found the product, as specified, not feasible. Take its blockers to the driver and settle how the product changes so that it becomes feasible.
2. Revise the product sections in the draft accordingly; the product review and the spike then run again.
3. Repeat until the spike finds the product feasible. Abandoning the work item is the driver's call alone.

Run `pdlc prompt product-writer --slug route-sheet` again after each step; it reads the draft and the reviews and names the next one.

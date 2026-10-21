Author the Product draft below with the driver, then take it through review, a feasibility spike, and a technical review until it is ready to land.

You are the agent already talking with the driver. This brief does not replace that conversation: anything the driver has already settled with you counts as an interview answer, so record it in the draft rather than asking again.

## Draft

`$CACHE_ROOT/.pdlc/cache/60/pdlc-product-draft.md` is the only copy of the draft. Edit it in place; every command below takes this exact path, and nothing else can land.

Work item `60` is at Product / Stale. The draft holds its current Product, Decisions, and Open Questions; reconcile them in place against the changes below. Preserve approved product intent, requirement and constraint ids, and everything the driver has not asked to change.

### Why Product is Stale

detail

## Where the draft stands

The product sections have not been reviewed yet.

## Next steps

1. Revise the draft in place as `## Draft` above directs.
2. Leave any `### Technical approach` as it is; the feasibility spike rewrites it after the product review.
3. Start the product review: `pdlc prompt product-reviewer $CACHE_ROOT/.pdlc/cache/60/pdlc-product-draft.md --pass product`

Run `pdlc prompt product-writer --work-item 60` again after each step; it reads the draft and the reviews and names the next one.

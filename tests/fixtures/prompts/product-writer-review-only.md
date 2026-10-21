Author the Product draft below with the driver, then take it through review, a feasibility spike, and a technical review until it is ready to land.

You are the agent already talking with the driver. This brief does not replace that conversation: anything the driver has already settled with you counts as an interview answer, so record it in the draft rather than asking again.

## Draft

`$CACHE_ROOT/.pdlc/cache/60/pdlc-product-draft.md` is the only copy of the draft. Edit it in place; every command below takes this exact path, and nothing else can land.

Work item `60` was published without its local review. The draft holds the published sections exactly; review them as they are, and change them only where a finding needs it.

## Where the draft stands

The product sections have not been reviewed yet.

## Next steps

1. Leave the draft as it is; the published sections get their review first.
2. Start the product review: `pdlc prompt product-reviewer $CACHE_ROOT/.pdlc/cache/60/pdlc-product-draft.md --pass product`

Run `pdlc prompt product-writer --work-item 60` again after each step; it reads the draft and the reviews and names the next one.

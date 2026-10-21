Author the Product draft below with the driver, then take it through review, a feasibility spike, and a technical review until it is ready to land.

You are the agent already talking with the driver. This brief does not replace that conversation: anything the driver has already settled with you counts as an interview answer, so record it in the draft rather than asking again.

## Draft

`$CACHE_ROOT/.pdlc/cache/new-route-sheet/pdlc-product-draft.md` is the only copy of the draft. Edit it in place; every command below takes this exact path, and nothing else can land.

This is a new work item, `route-sheet`. The draft holds only its headings. The slug is fixed now; the title is yours to choose and may change until it lands.

## Where the draft stands

The product sections have not been reviewed yet.

## Next steps

1. Fill every heading in the draft from the settled answers, interviewing the driver on every branch that source and the conversation leave open. Delete `### Design considerations` and `## Open Questions` when they have nothing to say.
2. Leave `### Technical approach` empty; the feasibility spike writes it after the product review.
3. Start the product review: `pdlc prompt product-reviewer $CACHE_ROOT/.pdlc/cache/new-route-sheet/pdlc-product-draft.md --pass product`

Run `pdlc prompt product-writer --slug route-sheet` again after each step; it reads the draft and the reviews and names the next one.

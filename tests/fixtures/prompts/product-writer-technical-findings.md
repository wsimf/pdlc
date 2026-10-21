Author the Product draft below with the driver, then take it through review, a feasibility spike, and a technical review until it is ready to land.

You are the agent already talking with the driver. This brief does not replace that conversation: anything the driver has already settled with you counts as an interview answer, so record it in the draft rather than asking again.

## Draft

`$CACHE_ROOT/.pdlc/cache/new-route-sheet/pdlc-product-draft.md` is the only copy of the draft. Edit it in place; every command below takes this exact path, and nothing else can land.

This is a new work item, `route-sheet`. The draft holds only its headings. The slug is fixed now; the title is yours to choose and may change until it lands.

## Where the draft stands

The technical review found problems.

## Next steps

1. Read the technical review's findings in `$CACHE_ROOT/.pdlc/cache/new-route-sheet/pdlc-technical-findings.md`.
2. Under each finding, add one line: `Author response: Fixed — <what changed>` or `Author response: Rejected — <why the draft is right>`. Fix the approach yourself, or run `pdlc prompt tech-feasibility $CACHE_ROOT/.pdlc/cache/new-route-sheet/pdlc-product-draft.md --findings $CACHE_ROOT/.pdlc/cache/new-route-sheet/pdlc-technical-findings.md` again when the fix needs a deeper spike. A finding that changes the product sections sends the draft back to the product review.
3. If the reviewer raises a finding you rejected again, put it to the driver and record their answer.
4. Re-review: `pdlc prompt product-reviewer $CACHE_ROOT/.pdlc/cache/new-route-sheet/pdlc-product-draft.md --pass technical --findings $CACHE_ROOT/.pdlc/cache/new-route-sheet/pdlc-technical-findings.md`

Run `pdlc prompt product-writer --slug route-sheet` again after each step; it reads the draft and the reviews and names the next one.

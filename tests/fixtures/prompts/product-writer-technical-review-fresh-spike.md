Author the Product draft below with the driver, then take it through review, a feasibility spike, and a technical review until it is ready to land.

You are the agent already talking with the driver. This brief does not replace that conversation: anything the driver has already settled with you counts as an interview answer, so record it in the draft rather than asking again.

## Draft

`$CACHE_ROOT/.pdlc/cache/new-route-sheet/pdlc-product-draft.md` is the only copy of the draft. Edit it in place; every command below takes this exact path, and nothing else can land.

This is a new work item, `route-sheet`. The draft holds only its headings. The slug is fixed now; the title is yours to choose and may change until it lands.

## Where the draft stands

The technical approach has not been reviewed in its current form.

The draft cannot land as it stands:

- ### Assumptions must be resolved before landing: confirm each one and fold it into a requirement or constraint, or settle it with the driver

## Next steps

1. First settle what the spike reported: take each driver decision to the driver, fold confirmed assumptions into the requirement or constraint they support, and settle the rest with the driver. Keep `### Assumptions` out of the draft and `## Open Questions` to implementation details that change no requirement or constraint. If any of this changes the product sections, run `pdlc prompt product-writer --slug route-sheet` again instead of continuing.
2. Run `pdlc prompt product-reviewer $CACHE_ROOT/.pdlc/cache/new-route-sheet/pdlc-product-draft.md --pass technical` and dispatch the product reviewer with the brief it prints.
3. When it replies, run `pdlc prompt product-writer --slug route-sheet` again.

Run `pdlc prompt product-writer --slug route-sheet` again after each step; it reads the draft and the reviews and names the next one.

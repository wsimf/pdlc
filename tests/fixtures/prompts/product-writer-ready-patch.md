Author the Product draft below with the driver, then take it through review, a feasibility spike, and a technical review until it is ready to land.

You are the agent already talking with the driver. This brief does not replace that conversation: anything the driver has already settled with you counts as an interview answer, so record it in the draft rather than asking again.

## Draft

`$CACHE_ROOT/.pdlc/cache/60/pdlc-product-draft.md` is the only copy of the draft. Edit it in place; every command below takes this exact path, and nothing else can land.

Work item `60` is past Product, at Technical Plan / Pending. The draft holds the landed Product sections. Correct only the defect you are patching, following `pdlc guide patch`; do not interview the driver for a product choice nobody has made.

## Where the draft stands

The product and technical reviews both passed on the draft as it stands.

## Next steps

Both reviews are clean. Copy both findings files somewhere safe for the evidence body, then continue `pdlc guide patch` from its impact step, landing this exact draft with `--patch`:

`pdlc post write --work-item 60 --body $CACHE_ROOT/.pdlc/cache/60/pdlc-product-draft.md --evidence <EVIDENCE_FILE> --patch [--impact <IMPACT_FILE>]`

Run `pdlc prompt product-writer --work-item 60 --patch` again after each step; it reads the draft and the reviews and names the next one.

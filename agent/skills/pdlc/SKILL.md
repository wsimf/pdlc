---
name: pdlc
description: Route and operate the PDLC workflow through the installed pdlc CLI.
---

Use the globally installed `pdlc` executable for all PDLC inspection and
publication operations. The CLI owns lifecycle validation and all mutations.

Examples:

```bash
pdlc inspect 236
pdlc inspect timeline 236
pdlc next 236
pdlc post complete 236 completion.md
```

Use `pdlc exec ...` only when an explicit execution namespace is useful for a
caller; it is an alias for the same allow-listed command set.

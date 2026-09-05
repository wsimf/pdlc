# PDLC loop contract

Queue selection is deterministic and bounded. Retry delay is:

`min(initial_delay * 2^(attempt - 1), maximum_delay)`

The loop may return an autonomous action (a `pdlc-*` skill, or `pdlc-post-ci` — run the script, then re-poll), human input, human approval, human decision, blocked state, or no-work exhaustion. Product routes to `human-input`, which stops the loop and asks the driver to invoke `pdlc-write` interactively. An `Implementation / CI Pending` record whose checks are still running is reported as no-work so the loop backs off. It never fabricates work and never treats a completed item as eligible.

Output is a Markdown document: YAML front matter (`id`, `work_item_number`, `title`, `current_status`, `action`) then a one-line instruction. The dispatched skill inspects the record itself; the routing decision is all the loop hands over. No-work exhaustion carries `action: none` and an `attempts` count.

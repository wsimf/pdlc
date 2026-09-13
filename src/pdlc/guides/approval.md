# Record a PDLC approval

Use this manual when a PDLC work item is at `<stage> / Approval Required` and the driver has explicitly approved that stage in the current turn. This is a human-gated workflow: confirm the gate, record the driver's approval as evidence, and report the resulting state.

## Entry check

Run:

```bash
pdlc inspect <WORK_ITEM>
```

Continue only when `Gate State` is `Approval Required` and the driver's approval names this work item and this stage. Otherwise report the actual state and stop; this manual does not apply.

When `Status` is `Verification`, approval is completion rather than a stage transition: hand the work item to `pdlc-complete` and stop.

If the driver asked for changes instead of approving, this manual does not apply; follow the owning stage skill's re-author procedure.

## Step 1: Record the approval

Write the evidence body: which stage the driver approved and their approval quoted verbatim. Commands stamp the marker, so the body carries none.

Run:

```bash
pdlc post approve <WORK_ITEM> text:<evidence>
```

Pass a file path instead of `text:` for a longer body. Pass `--attachment PATH [--attachment-description TEXT]` for any sign-off artifact the driver supplied; see `pdlc guide attachments`.

On success the command prints JSON with `approved: true`, `from` (the approved stage), `to` (the next stage), and `gateState` (`Pending`). On failure it exits non-zero with `pdlc: <reason>` and leaves the record untouched: the gate is not `Approval Required`, the stage is declared in `Skipped States`, or the stage is `Verification`. Report the reason and stop rather than retrying.

Completion criterion: inspect the work item and confirm a `PDLC-APPROVED` evidence comment and `Status` at the next stage with `Gate State` `Pending`.

## Report

Report the approved stage, the work item's resulting `Status`, `Gate State`, and `Lifecycle`, and any attachment stored. Report a blocker when the command fails or the inspected state does not match the expected result.

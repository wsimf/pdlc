# Patch a landed upstream artifact

Use this manual when you own the active stage of a PDLC work item and find that an artifact an earlier stage already landed is wrong. A patch corrects that artifact in place while the record stays on your stage. When the correction would change anything built on top of it, the stage has to be invalidated instead, which is a driver action.

## Entry check

Run `pdlc inspect <WORK_ITEM>` and confirm the record is still on your stage. Name the upstream artifact and the exact defect, citing its requirement, journey, or task ids.

Patch only when the corrected text follows from source or from decisions already on the record. When the correct text is a product choice nobody has made yet, raise it with `pdlc post escalate` (see `pdlc guide decisions`); when your gate does not allow that, report it to the driver and stop.

The landing command's dry run confirms your stage may patch the artifact at all: `pdlc post write --work-item <WORK_ITEM> --body <FILE> --patch --dry-run` for the Product body, `pdlc post tasks --work-item <WORK_ITEM> --stage <STAGE> ... --patch --dry-run` for a UI fragment or Tasks manifest. A refusal names why; report it and stop. Otherwise its `impactRequired` says whether Step 3 applies.

## Step 1: Draft the correction

Write the corrected artifact yourself, in exactly the input form its landing command takes, starting from the landed artifact in `pdlc inspect <WORK_ITEM> --full` or `pdlc inspect task <DELIVERY_TASK>`. Change only what the defect needs. Do not dispatch another stage's planner. A Tasks manifest names every landed task by `id` and keeps each task's `ui`, `covers`, and `depends`; call the landing command's `--help` for what else a patch may not change.

## Step 2: Review the draft

Dispatch the artifact's own reviewer with its brief, exactly as that artifact's stage does: `pdlc-product-reviewer` with `pdlc prompt product-reviewer <FILE> --work-item <WORK_ITEM> --file` for the Product body, `pdlc-tasks-reviewer` with `pdlc prompt tasks-reviewer <WORK_ITEM> --fragment <FILE> --file` or `--manifest <FILE> --file` for UI or Tasks. Revise the draft on findings and re-review; after two failed passes, stop and put the defect to the driver. The clean review is the `--evidence` body.

## Step 3: Judge the impact

Skip this step when the dry run reported `impactRequired: false`.

Dispatch the built-in `general-purpose` agent with the brief `pdlc prompt patch-reviewer <WORK_ITEM> --stage <STAGE> --body <FILE> --file` (or `--manifest <FILE>` for Tasks) writes, handing it the printed path and telling it plainly that the file holds its instructions and that it is to read the file and carry it out in full. Do not open, edit, or summarise the brief. Save its report unchanged; that file is `--impact`.

The report opens with `Earliest affected stage: <stage|none>`. When it names a stage, do not patch: report the defect, the draft, and the impact report to the driver, recommending `pdlc post invalidate` for that stage with the report as evidence, and stop.

## Step 4: Land the patch

Run the artifact's landing command with the reviewed draft, `--evidence`, `--patch`, and `--impact` when Step 3 ran:

```bash
pdlc post write --work-item <WORK_ITEM> --body <FILE> --evidence <FILE> --patch --impact <FILE>
```

A refusal writes nothing; report it. On success the record stays on your stage, reset to `Stale` if your artifact had already been published. Before landing your own stage's work, rebuild any local draft of it from the landed artifacts, since a work gate is left as is and nothing else signals the change.

## Report

State the patched artifact and the ids it changed, the review verdict, the impact verdict (or that no stage lay in between), and your stage's resulting gate. The driver sees the patch at the next approval.

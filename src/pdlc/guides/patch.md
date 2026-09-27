# Patch a landed upstream artifact

Use this manual when you own the active stage of a PDLC work item and find that an artifact an earlier stage already landed is wrong. A patch corrects that artifact in place. The record stays on your stage when nothing built on top of the artifact is affected, and returns to the earliest affected stage when something is.

## Entry check

Run `pdlc inspect <WORK_ITEM>` and confirm the record is still on your stage. Name the upstream artifact and the exact defect, citing its requirement, journey, or task ids.

Patch only when the corrected text follows from source or from decisions already on the record. When the correct text is a product choice nobody has made yet, raise it with `pdlc post escalate` (see `pdlc guide decisions`); when your gate does not allow that, report it to the driver and stop.

The landing command's dry run confirms your stage may patch the artifact at all: `pdlc post write --work-item <WORK_ITEM> --body <FILE> --patch --dry-run` for the Product body, `pdlc post tasks --work-item <WORK_ITEM> --stage <STAGE> ... --patch --dry-run` for a UI fragment or Tasks manifest. A refusal names why; report it and stop. Otherwise its `impactRequired` says whether Step 3 applies.

## Step 1: Draft the correction

Write the corrected artifact yourself, in exactly the input form its landing command takes, starting from the landed artifact in `pdlc inspect <WORK_ITEM> --full` or `pdlc inspect task <DELIVERY_TASK>`. Change only what the defect needs. Do not dispatch another stage's planner. A Tasks manifest names every landed task by `id` and keeps each task's classification, coverage, and dependencies; call the landing command's `--help` for what else a patch may not change.

## Step 2: Review the draft

Dispatch the artifact's own reviewer with its brief, exactly as that artifact's stage does: `pdlc-product-reviewer` with `pdlc prompt product-reviewer <FILE> --work-item <WORK_ITEM> --file` for the Product body, `pdlc-tasks-reviewer` with `pdlc prompt tasks-reviewer <WORK_ITEM> --fragment <FILE> --file` or `--manifest <FILE> --file` for UI or Tasks. Revise the draft on findings and re-review; after two failed passes, stop and put the defect to the driver. The clean review is the `--evidence` body.

## Step 3: Judge the impact

Skip this step when the dry run reported `impactRequired: false`.

Dispatch the built-in `general-purpose` agent with the brief `pdlc prompt patch-reviewer <WORK_ITEM> --stage <STAGE> --body <FILE> --file` (or `--manifest <FILE>` for Tasks) writes, handing it the printed path and telling it plainly that the file holds its instructions and that it is to read the file and carry it out in full. Do not open, edit, or summarise the brief. Save its report unchanged; that file is `--impact`.

The report opens with `Earliest affected stage: <stage|none>`. Land it in Step 4 whatever it names; the verdict decides where the record goes, and you do not edit or second-guess it.

## Step 4: Land the patch

Run the artifact's landing command with the reviewed draft, `--evidence`, `--patch`, and `--impact` when Step 3 ran:

```bash
pdlc post write --work-item <WORK_ITEM> --body <FILE> --evidence <FILE> --patch --impact <FILE>
```

A refusal writes nothing; report it. The printed `status` is where the record now is.

When it is still your stage, the record is reset to `Stale` if your artifact had already been published. Before landing your own stage's work, rebuild any local draft of it from the landed artifacts, since a work gate is left as is and nothing else signals the change.

When `returnedTo` names a stage, the record went back to it at `Stale` and your stage is no longer due. Discard your local draft and stop.

## Report

State the patched artifact and the ids it changed, the review verdict, the impact verdict (or that no stage lay in between), and where the record now is: your stage's resulting gate, or the stage it returned to. The driver sees the patch, with every changed requirement's before and after text, at the next approval.

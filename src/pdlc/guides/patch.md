# Patch a landed upstream artifact

Use this manual when you own the active stage of a PDLC work item and find that an artifact an earlier stage already landed is wrong. A patch corrects that artifact in place. The record stays on your stage when nothing built on top of the artifact is affected, and returns to the earliest affected stage when something is.

## Entry check

Run `pdlc inspect <WORK_ITEM>` and confirm the record is still on your stage. Name the upstream artifact and the exact defect, citing its requirement, journey, or task ids.

Patch only when the corrected text follows from source or from decisions already on the record. When the correct text is a product choice nobody has made yet, raise it with `pdlc post escalate` (see `pdlc guide decisions`); when your gate does not allow that, report it to the driver and stop.

For the Product body, run `pdlc prompt product-writer --work-item <WORK_ITEM> --patch` first: it refuses when your stage may not patch Product, and otherwise writes the draft holding the landed Product sections and prints its brief. The landing command's dry run then confirms your stage may patch the artifact at all: `pdlc post write --work-item <WORK_ITEM> --body <DRAFT> --patch --dry-run` for that Product draft, `pdlc post tasks --work-item <WORK_ITEM> --stage <STAGE> ... --patch --dry-run` for a UI fragment or Tasks manifest. A refusal names why; report it and stop. Otherwise its `impactRequired` says whether Step 3 applies.

## Step 1: Draft the correction

Write the corrected artifact yourself, in exactly the input form its landing command takes, starting from the landed artifact in `pdlc inspect <WORK_ITEM> --full` or `pdlc inspect task <DELIVERY_TASK>`; for the Product body, edit the draft `pdlc prompt product-writer` wrote, the only file that can land. Change only what the defect needs. Do not dispatch another stage's planner. A Tasks manifest names every landed task by `id` and keeps each task's classification, coverage, and dependencies; call the landing command's `--help` for what else a patch may not change.

## Step 2: Review the draft

For the Product draft, follow the `## Next steps` of the `pdlc prompt product-writer --work-item <WORK_ITEM> --patch` brief, re-running it after each step: a product review, a feasibility spike that writes the draft's technical approach, and a technical review, each with its own reviewer brief and findings file, until it names landing. A patch always lands with a technical approach, even on a record that never carried one.

For UI or Tasks, dispatch `pdlc-tasks-reviewer` with the brief `pdlc prompt tasks-reviewer <WORK_ITEM> --fragment <FILE>` or `--manifest <FILE>` writes, exactly as that artifact's stage does. Run the `pdlc prompt` command afresh for every dispatch and never reuse an earlier brief; a re-review may go back to the same reviewer. Each reviewer writes its findings to a file and replies with its verdict and that file's path.

On `Needs Revision`, revise the draft yourself from the findings and re-review, passing the previous findings with `--findings`; a Product re-review also needs an `Author response:` line under every finding. After three failed passes, stop and put the defect to the driver. On `Ready to Land`, the draft lands exactly as last reviewed, so do not touch it again. The clean review is the `--evidence` body: copy it to its own file before landing, since landing deletes the findings file.

## Step 3: Judge the impact

Skip this step when the dry run reported `impactRequired: false`.

Dispatch the built-in `general-purpose` agent with the brief `pdlc prompt patch-reviewer <WORK_ITEM> --stage <STAGE> --body <FILE>` (or `--manifest <FILE>` for Tasks) writes, handing it the printed path and telling it plainly that the file holds its instructions and that it is to read the file and carry it out in full. Do not open, edit, or summarise the brief. Save its report unchanged; that file is `--impact`.

The report opens with `Earliest affected stage: <stage|none>`. Land it in Step 4 whatever it names; the verdict decides where the record goes, and you do not edit or second-guess it.

## Step 4: Land the patch

Run the artifact's landing command with the reviewed draft, `--evidence`, `--patch`, and `--impact` when Step 3 ran:

```bash
pdlc post write --work-item <WORK_ITEM> --body <DRAFT> --evidence <FILE> --patch --impact <FILE>
```

A refusal writes nothing; report it. The printed `status` is where the record now is.

When it is still your stage, the record is reset to `Stale` if your artifact had already been published. Before landing your own stage's work, rebuild any local draft of it from the landed artifacts, since a work gate is left as is and nothing else signals the change.

When `returnedTo` names a stage, the record went back to it at `Stale` and your stage is no longer due. Discard your local draft and stop.

## Report

State the patched artifact and the ids it changed, the review verdict, the impact verdict (or that no stage lay in between), and where the record now is: your stage's resulting gate, or the stage it returned to. The driver sees the patch, with every changed requirement's before and after text, at the next approval.

#!/usr/bin/env bash
set -euo pipefail

# The whole suite runs against the file work-item backend: the pdlc-* scripts
# only ever call the `workitem` / `code_host` facades, so exercising them on a
# real on-disk store proves the facade contract without a GitHub round-trip.
# Swapping PDLC_BACKEND is the only thing that would point this at GitHub.

root="$(cd "$(dirname "$0")/.." && pwd)"
scripts="$root/scripts"
next="$scripts/pdlc-next-task.py"

export PDLC_BACKEND=file
export PDLC_NO_SLEEP=1
export PDLC_ACTOR=tester
PDLC_HOME="$(mktemp -d)"
export PDLC_HOME
work="$(mktemp -d)"
trap 'rm -rf "$PDLC_HOME" "$work"' EXIT

records="$PDLC_HOME/records"
mkdir -p "$records"
printf '40\n' >"$PDLC_HOME/seq"

evidence="$work/evidence.md"
printf 'evidence body\n' >"$evidence"

body_default='## Product

### 4. Functional requirements
- FR-1: The record lands.
- FR-2: The record publishes.

### 5. Constraints
- C-1: Scripts own every mutation.

## UI

UJ-1 covers the first run.

## Decisions
- none

## Open Questions
- none
'

seed_record() {  # number status gate [slug] [skipped]
  local dir="$records/$1"
  mkdir -p "$dir/tasks"
  : >"$dir/comments.jsonl"
  printf '%s' "$body_default" >"$dir/body.md"
  jq -n --argjson n "$1" --arg s "$2" --arg g "$3" \
        --arg slug "${4:-record-$1}" --arg skip "${5:-}" \
    '{id:("FILE-"+($n|tostring)),number:$n,title:("Record "+($n|tostring)),
      url:("file://x/"+($n|tostring)),
      fields:{Status:$s,"Gate State":$g,Lifecycle:"Planning",
              "Skipped States":$skip,Slug:$slug}}' >"$dir/meta.json"
}

seed_task() {  # record number taskId state title
  local dir="$records/$1/tasks/$2"
  mkdir -p "$dir"
  : >"$dir/comments.jsonl"
  printf '## Scope\nx\n\n## Acceptance criteria\n- ok\n' >"$dir/body.md"
  jq -n --argjson n "$2" --arg id "$3" --arg st "$4" --arg t "$5" \
    '{number:$n,title:$t,url:"file://x",state:$st,taskId:$id}' >"$dir/meta.json"
}

json() { jq -r "$1" <<<"$2"; }

# pdlc-next-task.py renders Markdown: a YAML front-matter key is `name: value`,
# with string values JSON-quoted. `fm key <<<doc` pulls one back out.
fm() { sed -n "s/^$1: //p" | sed 's/^"//; s/"$//'; }

# --- routing view -----------------------------------------------------------

seed_record 14 Product "Changes Required"
seed_record 15 Product "Approval Required"
seed_record 16 Complete Approved
seed_record 17 UI Pending
seed_record 18 Tasks Pending
seed_record 19 "Technical Plan" Pending
seed_record 20 Implementation Pending
seed_record 21 Testing Pending
seed_record 22 Verification Pending

# The queue scan skips the Product items — authoring a specification is never
# autonomous — so the first autonomous action is the UI item.
scan="$(python3 "$next")"
[[ "$(fm action <<<"$scan")" == "pdlc-tasks" ]]
[[ "$(fm work_item_number <<<"$scan")" == "17" ]]

product="$(python3 "$next" --work-item 14)"
[[ "$(fm action <<<"$product")" == "pdlc-write" ]]
[[ "$(fm current_status <<<"$product")" == "Product.ChangesRequired" ]]
[[ "$(fm next_status <<<"$product")" == "Product.ApprovalRequired" ]]

approval="$(python3 "$next" --work-item 15)"
[[ "$(fm action <<<"$approval")" == "human-approval" ]]
[[ "$(fm current_status <<<"$approval")" == "Product.ApprovalRequired" ]]
[[ "$(fm next_status <<<"$approval")" == "Product.Approved" ]]

for pair in 17:pdlc-tasks 18:pdlc-tasks 19:pdlc-plan 20:pdlc-implement 21:pdlc-test 22:pdlc-verify; do
  routed="$(python3 "$next" --work-item "${pair%%:*}")"
  [[ "$(fm action <<<"$routed")" == "${pair##*:}" ]]
done

# A Complete record reports done rather than a retry hint.
done_doc="$(python3 "$next" --work-item 16)"
[[ "$(fm action <<<"$done_doc")" == "none" ]]
grep -q "^# Complete$" <<<"$done_doc"

# loop retries only while nothing is actionable, and reports the attempt count.
only_complete="$(mktemp -d)"
mkdir -p "$only_complete/records"
cp -R "$records/16" "$only_complete/records/16"
printf '40\n' >"$only_complete/seq"
no_work="$(PDLC_HOME="$only_complete" PDLC_MAX_ATTEMPTS=3 PDLC_INITIAL_DELAY_SECONDS=0 \
  PDLC_MAX_DELAY_SECONDS=0 python3 "$next" loop 2>/dev/null)"
[[ "$(fm action <<<"$no_work")" == "none" ]]
[[ "$(fm attempts <<<"$no_work")" == "3" ]]
grep -q "Invoke this script again" <<<"$no_work"
rm -rf "$only_complete"

# --- decision-required review outcome ------------------------------------

seed_record 25 Implementation "Review Required"

# A decision-required review must carry a ## Decision Required section.
printf 'Findings: TASK-001 approach is ambiguous.\n' >"$work/no-heading.md"
python3 "$scripts/pdlc-post-review.py" 25 decision-required "$work/no-heading.md" 2>"$work/err" && exit 1
grep -q "must include a '## Decision Required' section" "$work/err"

printf '## Decision Required\n\nQuestion: snap geometry on-device or server-side?\nOptions: A/B.\nRecommendation: A.\nBlocks: TASK-001.\n' >"$work/decision.md"
decided="$(python3 "$scripts/pdlc-post-review.py" 25 decision-required "$work/decision.md")"
[[ "$(json '.gateState' "$decided")" == "Decision Required" ]]
grep -q '"Gate State": "Decision Required"' "$records/25/meta.json"
grep -q "PDLC-DECISION" "$records/25/comments.jsonl"

# The loop halts on it: routed to human-decision, not a specialist.
routed25="$(python3 "$next" --work-item 25)"
[[ "$(fm action <<<"$routed25")" == "human-decision" ]]
grep -q "PDLC-DECISION comment" <<<"$routed25"

# The timeline surfaces the decision under its own marker.
grep -q "## DECISION" <<<"$(python3 "$scripts/pdlc-inspect-timeline.py" 25)"

# A re-review is not due while the driver still owns it.
grep -q "Decision Required" <<<"$(python3 "$scripts/pdlc-inspect-review.py" 25)"

# One pdlc-post-decision --manifest call lands every outcome: an answered
# decision is recorded, a deferred one spins out its own Product / Pending work
# item, and the origin gate moves to Changes Required so the loop resumes.
printf '## Product\n\n### 1. Problem\nTile quota is unsettled.\n\n## Decisions\n- none yet\n\n## Open Questions\n- What is the tile-pin quota ceiling?\n' >"$work/deferred.md"
jq -n --arg b "$work/deferred.md" '[
  {decision:"On-device vs server-side snapping",answer:"On-device",rationale:"offline-first",affects:"TASK-001"},
  {decision:"Tile-pin quota ceiling",defer:{title:"Tile pin quota",slug:"tile-pin-quota",body:$b}}
]' >"$work/decisions.json"
resolved="$(python3 "$scripts/pdlc-post-decision.py" 25 --manifest "$work/decisions.json")"
child="$(json '.deferred[0].number' "$resolved")"
[[ "$(json '.gateState' "$resolved")" == "Changes Required" ]]
grep -q '"Gate State": "Changes Required"' "$records/25/meta.json"
grep -q '"Status": "Product"' "$records/$child/meta.json"
grep -q '"Gate State": "Pending"' "$records/$child/meta.json"
grep -q "Deferred — Tile pin quota; tracked as #$child" "$records/25/body.md"
grep -q "PDLC-RESOLUTION" "$records/25/comments.jsonl"
[[ "$(python3 "$next" --work-item 25 | fm action)" == "pdlc-implement" ]]
grep -q "## RESOLUTION" <<<"$(python3 "$scripts/pdlc-inspect-timeline.py" 25)"

# pdlc-post-decision refuses a record that is not at Decision Required.
python3 "$scripts/pdlc-post-decision.py" 25 --manifest "$work/decisions.json" 2>"$work/err" && exit 1
grep -q "requires Gate State = Decision Required" "$work/err"

# --- CI Pending gate after a clean implementation review ----------------

seed_record 26 Implementation "Review Required"
# CI still running when the review lands: the record parks at CI Pending.
jq -n '[{number:148,title:"impl",url:"u",state:"OPEN",isDraft:false,branch:"b",mergedAt:null,checks:"PENDING",relation:"closes"}]' >"$records/26/pull_requests.json"
ci_review="$(python3 "$scripts/pdlc-post-review.py" 26 approval-required "$evidence")"
[[ "$(json '.gateState' "$ci_review")" == "CI Pending" ]]
grep -q '"Gate State": "CI Pending"' "$records/26/meta.json"

# The loop treats a still-running record as no work (it backs off), never dispatches.
[[ "$(python3 "$next" --work-item 26 | fm action)" == "none" ]]
grep -q "CI is still running" <<<"$(python3 "$next" --work-item 26)"

# A stage review is not due again while CI runs.
grep -q "CI Pending" <<<"$(python3 "$scripts/pdlc-inspect-review.py" 26)"

# CI goes green -> next-task routes to pdlc-post-ci -> it advances to Approval Required.
jq '.[0].checks="SUCCESS"' "$records/26/pull_requests.json" >"$work/prs.json" && mv "$work/prs.json" "$records/26/pull_requests.json"
[[ "$(python3 "$next" --work-item 26 | fm action)" == "pdlc-post-ci" ]]
green="$(python3 "$scripts/pdlc-post-ci.py" 26)"
[[ "$(json '.gateState' "$green")" == "Approval Required" ]]
[[ "$(json '.state' "$green")" == "green" ]]
[[ "$(python3 "$next" --work-item 26 | fm action)" == "human-approval" ]]

# CI already red when the review lands: post-review parks at CI Pending, then
# reconciles immediately — a PDLC-IMPLEMENTATION note and Changes Required.
seed_record 27 Implementation "Review Required"
jq -n '[{number:149,title:"impl",url:"u",state:"OPEN",isDraft:false,branch:"b",mergedAt:null,checks:"FAILURE",relation:"closes"}]' >"$records/27/pull_requests.json"
red_review="$(python3 "$scripts/pdlc-post-review.py" 27 approval-required "$evidence")"
[[ "$(json '.gateState' "$red_review")" == "Changes Required" ]]
grep -q '"Gate State": "Changes Required"' "$records/27/meta.json"
grep -q "PDLC-IMPLEMENTATION" "$records/27/comments.jsonl"
grep -q "CI checks failed" "$records/27/comments.jsonl"
[[ "$(python3 "$next" --work-item 27 | fm action)" == "pdlc-implement" ]]

# pdlc-post-ci refuses a record that is not at CI Pending.
python3 "$scripts/pdlc-post-ci.py" 27 2>"$work/err" && exit 1
grep -q "requires Gate State = CI Pending" "$work/err"

# No linked PR / no checks tracked: a clean review advances straight through.
seed_record 28 Implementation "Review Required"
untracked="$(python3 "$scripts/pdlc-post-review.py" 28 approval-required "$evidence")"
[[ "$(json '.gateState' "$untracked")" == "Approval Required" ]]

# --- pure logic ------------------------------------------------------------

stage="$(PYTHONPATH="$scripts/lib" python3 -c "from pdlc_common import next_stage; print(next_stage('Product'))")"
[[ "$stage" == "UI" ]]

PYTHONPATH="$scripts/lib" python3 - <<'PY'
from pdlc_model import due_next

due = due_next({"Status": "Verification", "Gate State": "Pending", "Skipped States": "Verification"})
assert due["state"] == "Verification.ApprovalRequired", due
assert due["action"] == "human-approval", due

decision = due_next({"Status": "Implementation", "Gate State": "Decision Required", "Skipped States": ""})
assert decision["action"] == "human-decision", decision
assert decision["autonomous"] is False, decision

ci = due_next({"Status": "Implementation", "Gate State": "CI Pending", "Skipped States": ""})
assert ci["action"] == "pdlc-post-ci", ci
assert ci["autonomous"] is True, ci
assert ci["next_state"] == "Implementation.ApprovalRequired", ci
PY

# --- full lifecycle on the file backend -----------------------------------

draft="$work/product.md"
printf '## Product\nThe shell ships.\n\n### 4. Functional requirements\n- FR-1: lands.\n\n### 5. Constraints\n- C-1: scripts own mutations.\n\n## Decisions\n- Decided to ship.\n\n## Open Questions\n- none\n' >"$draft"
mockup="$work/navigation.png"
printf 'navigation mockup bytes\n' >"$mockup"
unlabelled="$work/empty-state.png"
printf 'empty state mockup bytes\n' >"$unlabelled"

created="$(python3 "$scripts/pdlc-post-write.py" --title "Shell" --slug shell \
  --evidence "$evidence" --body "$draft" \
  --attachment "$mockup" --attachment-description "Primary navigation mockup" \
  --attachment "$unlabelled")"
issue="$(json '.work_item_number' "$created")"
[[ "$(json '.gateState' "$created")" == "Approval Required" ]]
[[ -f "$records/$issue/body.md" ]]
[[ "$(json '.attachments | length' "$created")" == "2" ]]
[[ "$(json '.attachments[0].description' "$created")" == "Primary navigation mockup" ]]
[[ -f "$PDLC_HOME/$issue/attachments/files.json" ]]
grep -q "Primary navigation mockup" "$PDLC_HOME/$issue/attachments/files.json"
! grep -q "Primary navigation mockup" "$records/$issue/body.md"
! grep -q "Primary navigation mockup" "$records/$issue/comments.jsonl"

# Malformed local attachment metadata fails cleanly instead of leaking a
# TypeError or KeyError through an inspector.
malformed_home="$work/malformed-pdlc"
mkdir -p "$malformed_home/1/attachments"
printf '{"version":1,"files":[null]}\n' >"$malformed_home/1/attachments/files.json"
PDLC_HOME="$malformed_home" PYTHONPATH="$scripts/lib" python3 - <<'PY'
from attachment_host.file import FileAttachmentHost
from pdlc_common import PdlcError

try:
    FileAttachmentHost().list_for("1")
except PdlcError as error:
    assert "entry 1 is not an object" in str(error), error
else:
    raise AssertionError("malformed attachment metadata was accepted")
PY

python3 "$scripts/pdlc-post-approve.py" "$issue" "$evidence" >/dev/null

printf '## UI\n\nUJ-1 covers the first run.\n' >"$work/ui.md"
python3 "$scripts/pdlc-post-tasks.py" --work-item "$issue" --stage UI \
  --body "$work/ui.md" --evidence "$evidence" >/dev/null
# Driver asks for a change before approving: re-land re-authors in place, a bare
# gate reset with no PDLC-INVALIDATED comment.
reauth_ui="$(python3 "$scripts/pdlc-post-tasks.py" --work-item "$issue" --stage UI \
  --body "$work/ui.md" --evidence "$evidence")"
[[ "$(json '.gateState' "$reauth_ui")" == "Approval Required" ]]
! grep -q "PDLC-INVALIDATED" "$records/$issue/comments.jsonl"
python3 "$scripts/pdlc-post-approve.py" "$issue" "$evidence" >/dev/null
grep -q "UJ-1 covers the first run" "$records/$issue/body.md"

printf '## Scope\nBuild the core.\n\n## Acceptance criteria\n- FR-1 works\n' >"$work/task.md"
jq -n --arg b "$work/task.md" \
  '[{id:"TASK-001",title:"Build core",body:$b,ui:true,covers:["FR-1","C-1","UJ-1"]}]' \
  >"$work/manifest.json"
tasks_out="$(python3 "$scripts/pdlc-post-tasks.py" --work-item "$issue" --stage Tasks \
  --manifest "$work/manifest.json" --evidence "$evidence")"
task_number="$(json '.tasks[0].number' "$tasks_out")"
# Re-land before approval re-authors the breakdown in place, no invalidation comment.
reauth_tasks="$(python3 "$scripts/pdlc-post-tasks.py" --work-item "$issue" --stage Tasks \
  --manifest "$work/manifest.json" --evidence "$evidence")"
[[ "$(json '.gateState' "$reauth_tasks")" == "Approval Required" ]]
! grep -q "PDLC-INVALIDATED" "$records/$issue/comments.jsonl"
python3 "$scripts/pdlc-post-approve.py" "$issue" "$evidence" >/dev/null

printf 'Touch CoreService.swift.\n' >"$work/plan.md"
jq -n --arg p "$work/plan.md" '[{id:"TASK-001",plan:$p}]' >"$work/plan-manifest.json"
python3 "$scripts/pdlc-post-plan.py" --work-item "$issue" \
  --manifest "$work/plan-manifest.json" --evidence "$evidence" >/dev/null
# Re-land before approval re-authors the plan in place, no invalidation comment.
reauth_plan="$(python3 "$scripts/pdlc-post-plan.py" --work-item "$issue" \
  --manifest "$work/plan-manifest.json" --evidence "$evidence")"
[[ "$(json '.gateState' "$reauth_plan")" == "Approval Required" ]]
! grep -q "PDLC-INVALIDATED" "$records/$issue/comments.jsonl"
python3 "$scripts/pdlc-post-approve.py" "$issue" "$evidence" >/dev/null

# The plan lands as a comment on the task, never in its body.
grep -q "## Scope" "$records/$issue/tasks/$task_number/body.md"
grep -q "Technical Plan" "$records/$issue/tasks/$task_number/comments.jsonl"

printf '## Implementation\n\nShipped. FR-1 covered.\n' >"$work/impl.md"
task_attachment="$work/task-screenshot.png"
printf 'task screenshot bytes\n' >"$task_attachment"
impl="$(python3 "$scripts/pdlc-post-implement-task.py" "$task_number" "$work/impl.md" --close \
  --attachment "$task_attachment" --attachment-description "Task implementation screenshot")"
[[ "$(json '.closed' "$impl")" == "true" ]]
[[ "$(json '.attachments[0].description' "$impl")" == "Task implementation screenshot" ]]
grep -q '"state": "CLOSED"' "$records/$issue/tasks/$task_number/meta.json"

cat >"$records/$issue/pull_requests.json" <<'EOF'
[{"number":148,"title":"Implement record 20","url":"https://github.com/example/148",
  "state":"OPEN","isDraft":false,"branch":"feature/record-20","mergedAt":null,
  "checks":"SUCCESS","relation":"closes"}]
EOF
python3 "$scripts/pdlc-post-implement.py" "$issue" "$evidence" >/dev/null
python3 "$scripts/pdlc-post-review.py" "$issue" approval-required "$evidence" >/dev/null
python3 "$scripts/pdlc-post-approve.py" "$issue" "$evidence" >/dev/null
[[ "$(python3 "$next" --work-item "$issue" | fm action)" == "pdlc-test" ]]

printf 'FR-1 -> record lands -> CoreService.swift lands() -> acceptance path\n' >"$work/trace.md"
python3 "$scripts/pdlc-post-test.py" "$issue" "$evidence" --traceability "$work/trace.md" >/dev/null
grep -q "## Traceability" "$records/$issue/comments.jsonl"
grep -q "CoreService.swift lands" "$records/$issue/comments.jsonl"
python3 "$scripts/pdlc-post-review.py" "$issue" approval-required "$evidence" >/dev/null
python3 "$scripts/pdlc-post-approve.py" "$issue" "$evidence" >/dev/null

head_sha="$(git rev-parse HEAD)"
cat >"$work/report.md" <<EOF
### Claims Audit

- FR-1 confirmed against source (Verified @ $head_sha)

### User Journeys

- UJ-1 confirmed on the simulator (Verified @ $head_sha)

### UX

- Reviewed — no critical findings

### Ultra Review

- Clean — no findings
EOF

# A finding the skill cannot settle routes to the driver as a decision: the
# audit posts a PDLC-DECISION blocker and parks at Verification / Decision
# Required, and the loop stops on it.
printf '## Decision Required\n\nQuestion: keep the 2m elevation drift or fix it?\nOptions: keep / fix.\nRecommendation: keep.\nBlocks: completion.\nWhy not mechanical: tolerance is a product call.\n' >"$work/v-decision.md"
v_decided="$(python3 "$scripts/pdlc-post-verify.py" "$issue" "$work/report.md" \
  --recommendation "Decision Required" --decision "$work/v-decision.md")"
[[ "$(json '.gateState' "$v_decided")" == "Decision Required" ]]
grep -q '"Gate State": "Decision Required"' "$records/$issue/meta.json"
grep -q "PDLC-DECISION" "$records/$issue/comments.jsonl"
[[ "$(python3 "$next" --work-item "$issue" | fm action)" == "human-decision" ]]
grep -q "parked at Decision Required" <<<"$(python3 "$scripts/pdlc-inspect-verify.py" "$issue")"

# The driver settles it: gate returns to Changes Required, routing back to pdlc-verify.
jq -n '[{decision:"2m elevation drift",answer:"keep",rationale:"within tolerance",affects:"Verification"}]' >"$work/v-decisions.json"
python3 "$scripts/pdlc-post-decision.py" "$issue" --manifest "$work/v-decisions.json" >/dev/null
grep -q '"Gate State": "Changes Required"' "$records/$issue/meta.json"
[[ "$(python3 "$next" --work-item "$issue" | fm action)" == "pdlc-verify" ]]

# A clean re-run lands Verification / Approval Required directly — no manual gate move.
verified="$(python3 "$scripts/pdlc-post-verify.py" "$issue" "$work/report.md" \
  --recommendation "Approval Required")"
[[ "$(json '.gateState' "$verified")" == "Approval Required" ]]
grep -q '"Gate State": "Approval Required"' "$records/$issue/meta.json"

# --decision is rejected unless the recommendation calls for it.
python3 "$scripts/pdlc-post-verify.py" "$issue" "$work/report.md" \
  --recommendation "Approval Required" --decision "$work/v-decision.md" 2>"$work/err" && exit 1
grep -q "only valid with --recommendation 'Decision Required'" "$work/err"

# The structured completion evidence body: six sections, each dispositioned.
cat >"$work/completion.md" <<EOF
## Shipped

The record shell shipped across its delivery tasks; linked PR merged.

## Verification

clean @ $head_sha — claims, journeys, UX reviewed, ultra review clean.

## Decisions

- None

## Open Questions

- None

## Limitations

- None

## Skipped Stages

- None
EOF

# Malformed completion evidence is rejected before anything is written.
printf 'just a sentence\n' >"$work/bad-evidence.md"
python3 "$scripts/pdlc-post-complete.py" "$issue" "$work/bad-evidence.md" 2>"$work/err" && exit 1
grep -q "evidence-malformed" "$work/err"

# Completion refuses to lock while the linked closing PR is still open.
python3 "$scripts/pdlc-post-complete.py" "$issue" "$work/completion.md" 2>"$work/err" && exit 1
grep -q "not ready to complete" "$work/err"
grep -q "pull-requests" "$work/err"

# inspect-complete reports the same blocker the mutation would raise.
grep -q "Not ready" <<<"$(python3 "$scripts/pdlc-inspect-complete.py" "$issue")"

jq '.[0].state="MERGED" | .[0].mergedAt="2026-01-01T00:00:00Z"' \
  "$records/$issue/pull_requests.json" >"$work/prs.json" \
  && mv "$work/prs.json" "$records/$issue/pull_requests.json"

grep -q "Ready — Status: Verification" <<<"$(python3 "$scripts/pdlc-inspect-complete.py" "$issue")"

completed="$(python3 "$scripts/pdlc-post-complete.py" "$issue" "$work/completion.md")"
[[ "$(json '.completed' "$completed")" == "true" ]]
grep -q '"Status": "Complete"' "$records/$issue/meta.json"
# The Open Questions section is blanked to a pointer; its disposition lives in the comment.
grep -q "see the completion comment" "$records/$issue/body.md"

# The evidence log is append-only: every stage added a comment, none rewritten.
# The default output is a compact index pointing at a temp file; --full is the
# whole thing on stdout.
timeline="$(python3 "$scripts/pdlc-inspect-timeline.py" "$issue")"
grep -q "## PRODUCT" <<<"$timeline"
grep -q "## VERIFICATION" <<<"$timeline"
grep -q "## APPROVED" <<<"$timeline"
grep -q "Primary navigation mockup" <<<"$timeline"
grep -q "$PDLC_HOME/$issue/attachments/" <<<"$timeline"
grep -qE "Read lines [0-9]+-[0-9]+ in .*-timeline-$issue\.md" <<<"$timeline"
timeline_full="$(python3 "$scripts/pdlc-inspect-timeline.py" "$issue" --full)"
grep -q "^# Timeline$" <<<"$timeline_full"
grep -q "#comment-" <<<"$timeline_full"
grep -q "Task implementation screenshot" <<<"$timeline_full"
grep -q "$PDLC_HOME/$issue/attachments/" <<<"$timeline_full"

# The file backend serves pull requests from the record's own pull_requests.json
# rather than a live GitHub: pdlc-inspect.py renders the linked implementation PR
# it was seeded with, and never reaches for a real code host.
inspected="$(python3 "$scripts/pdlc-inspect.py" "$issue")"
grep -q "# Work Item" <<<"$inspected"
grep -q "## Attachments" <<<"$inspected"
grep -q "Primary navigation mockup" <<<"$inspected"
grep -q "Task implementation screenshot" <<<"$inspected"
grep -q "$PDLC_HOME/$issue/attachments/" <<<"$inspected"
grep -qE "pullRequests:" <<<"$inspected"
grep -qE "number: 148" <<<"$inspected"
grep -qE "Full inspection in .*-${issue}\.md" <<<"$inspected"
! grep -q "The shell ships" <<<"$inspected"
inspected_full="$(python3 "$scripts/pdlc-inspect.py" "$issue" --full)"
grep -q "# Work Item" <<<"$inspected_full"
grep -q "The shell ships" <<<"$inspected_full"
grep -q "att_" <<<"$inspected_full"
grep -q "$PDLC_HOME/$issue/attachments/" <<<"$inspected_full"

task_inspected="$(python3 "$scripts/pdlc-inspect-task.py" "$task_number")"
grep -q "## Attachments" <<<"$task_inspected"
grep -q "Task implementation screenshot" <<<"$task_inspected"
grep -q "$PDLC_HOME/$issue/attachments/" <<<"$task_inspected"
for inspector in pdlc-inspect-review.py pdlc-inspect-test.py pdlc-inspect-verify.py pdlc-inspect-complete.py; do
  specialized="$(python3 "$scripts/$inspector" "$issue")"
  grep -q "## Attachments" <<<"$specialized"
  grep -q "Primary navigation mockup" <<<"$specialized"
  grep -q "$PDLC_HOME/$issue/attachments/" <<<"$specialized"
done

# --- pdlc-post-tasks.py validation (backend-independent) ------------------

seed_record 30 Tasks Pending
seed_task 30 301 TASK-001 OPEN "WORK-30-TASK-001 Old wording"
seed_task 30 309 TASK-009 OPEN "WORK-30-TASK-009 Dropped"

printf 'task body\n' >"$work/body.md"
plan_tasks() {
  printf '%s' "$1" >"$work/m.json"
  python3 "$scripts/pdlc-post-tasks.py" --work-item 30 --stage Tasks --manifest "$work/m.json" --dry-run
}
valid="$(plan_tasks "$(jq -c --arg b "$work/body.md" '[
  {id:"TASK-001",title:"Reworded same task",body:$b,ui:false,covers:["FR-1","C-1"]},
  {title:"Ship the journey",body:$b,ui:true,covers:["FR-2","UJ-1"],depends:["TASK-001"]}
]' -n)")"
[[ "$(json '.tasks[1].id' "$valid")" == "TASK-010" ]]
[[ "$(json '.order | join(",")' "$valid")" == "TASK-001,TASK-010" ]]
[[ "$(json '.orphans | join(",")' "$valid")" == "TASK-009" ]]

assert_rejects() {
  printf '%s' "$2" >"$work/m.json"
  python3 "$scripts/pdlc-post-tasks.py" --work-item 30 --stage Tasks --manifest "$work/m.json" \
    --dry-run 2>"$work/err" && { echo "expected rejection: $1"; exit 1; }
  grep -qF "$1" "$work/err" || { printf 'wanted %s, got:\n' "$1"; cat "$work/err"; exit 1; }
}
assert_rejects "covers FR-99, which the parent does not declare" \
  "$(jq -c --arg b "$work/body.md" '[{id:"TASK-001",title:"Typo",body:$b,covers:["FR-99"]}]' -n)"
assert_rejects "is a UI task but covers no UJ-*" \
  "$(jq -c --arg b "$work/body.md" '[{id:"TASK-001",title:"U",body:$b,ui:true,covers:["FR-1"]}]' -n)"
assert_rejects "dependency cycle" \
  "$(jq -c --arg b "$work/body.md" '[
    {id:"TASK-001",title:"A",body:$b,ui:true,covers:["FR-1","UJ-1"],depends:["TASK-002"]},
    {id:"TASK-002",title:"B",body:$b,covers:["FR-2"],depends:["TASK-001"]}]' -n)"
assert_rejects "duplicate task id: TASK-001" \
  "$(jq -c --arg b "$work/body.md" '[
    {id:"TASK-001",title:"A",body:$b,ui:true,covers:["FR-1","UJ-1"]},
    {id:"TASK-001",title:"B",body:$b,covers:["FR-2"]}]' -n)"

# A record already awaiting approval: a dry run still refuses, but a real land
# re-authors it in place — a bare gate reset to Stale, no PDLC-INVALIDATED comment.
seed_record 31 Tasks "Approval Required"
printf '%s' "$(jq -c --arg b "$work/body.md" '[{id:"TASK-001",title:"A",body:$b,ui:true,covers:["FR-1","UJ-1"]}]' -n)" >"$work/m.json"
python3 "$scripts/pdlc-post-tasks.py" --work-item 31 --stage Tasks --manifest "$work/m.json" \
  --dry-run 2>"$work/err" && exit 1
grep -q "return it to Stale with pdlc-post-invalidate.py" "$work/err"
reauth="$(python3 "$scripts/pdlc-post-tasks.py" --work-item 31 --stage Tasks --manifest "$work/m.json" --evidence "$evidence")"
[[ "$(json '.gateState' "$reauth")" == "Approval Required" ]]
! grep -q "PDLC-INVALIDATED" "$records/31/comments.jsonl"

# UI applicability must be explicit.
seed_record 32 UI Pending
printf '## UI\n\nUJ-1 covers the first run.\n' >"$work/ui-ok.md"
[[ "$(json '.journeys | join(",")' "$(python3 "$scripts/pdlc-post-tasks.py" --work-item 32 \
  --stage UI --body "$work/ui-ok.md" --dry-run --attachment "$mockup")")" == "UJ-1" ]]
[[ ! -d "$PDLC_HOME/32/attachments" ]]
printf 'Some prose that decides nothing.\n' >"$work/vague.md"
python3 "$scripts/pdlc-post-tasks.py" --work-item 32 --stage UI --body "$work/vague.md" \
  --dry-run 2>"$work/err" && exit 1
grep -q "UI applicability must be explicit" "$work/err"

# --- pdlc-post-plan.py validation ---------------------------------------

seed_record 40 "Technical Plan" Pending
seed_task 40 401 TASK-001 OPEN "WORK-40-TASK-001 One"
seed_task 40 402 TASK-002 OPEN "WORK-40-TASK-002 Two"
printf '## Technical Plan\n\nalready planned\n' \
  | jq -R -s '{body:.,createdAt:"2026-01-01T00:00:00Z",url:"u",author:{login:"x"}}' -c \
  >"$records/40/tasks/402/comments.jsonl"

printf 'Files: CoreService.swift\n' >"$work/plan-body.md"
plan_plan() {
  printf '%s' "$1" >"$work/pm.json"
  python3 "$scripts/pdlc-post-plan.py" --work-item 40 --manifest "$work/pm.json" --dry-run
}
# TASK-002 already carries a plan, so re-spiking only TASK-001 is complete.
planned="$(plan_plan "$(jq -c --arg b "$work/plan-body.md" '[{id:"TASK-001",plan:$b}]' -n)")"
[[ "$(json '.targeted | join(",")' "$planned")" == "TASK-001" ]]
[[ "$(json '.alreadyPlanned | join(",")' "$planned")" == "TASK-002" ]]

printf '\n' >"$work/plan-empty.md"
printf '%s' "$(jq -c --arg b "$work/plan-empty.md" '[{id:"TASK-001",plan:$b}]' -n)" >"$work/pm.json"
python3 "$scripts/pdlc-post-plan.py" --work-item 40 --manifest "$work/pm.json" --dry-run 2>"$work/err" && exit 1
grep -q "the plan file for TASK-001 is empty" "$work/err"

printf '%s' "$(jq -c --arg b "$work/plan-body.md" '[{id:"TASK-404",plan:$b}]' -n)" >"$work/pm.json"
python3 "$scripts/pdlc-post-plan.py" --work-item 40 --manifest "$work/pm.json" --dry-run 2>"$work/err" && exit 1
grep -q "no such task on this record: TASK-404" "$work/err"

# --- pdlc-post-write.py section reconstruction --------------------------

seed_record 50 Product Stale
printf '## Product\nold\n\n## UI\nowned later\n\n## Decisions\nold\n\n## Open Questions\nold\n' >"$records/50/body.md"
printf '## Product\nnew product\n\n## Decisions\nnew decision\n\n## Open Questions\nnew question\n' >"$work/rewrite.md"
python3 "$scripts/pdlc-post-write.py" --work-item 50 --evidence "$evidence" --body "$work/rewrite.md" >/dev/null
grep -q "new product" "$records/50/body.md"
grep -q "owned later" "$records/50/body.md"
grep -q '"Gate State": "Approval Required"' "$records/50/meta.json"

# A record already at Product / Approval Required is re-authored in place: the
# script resets the gate to Stale itself and re-lands, no PDLC-INVALIDATED comment.
seed_record 51 Product "Approval Required"
printf '## Product\nrevised\n\n## Decisions\nd\n\n## Open Questions\nq\n' >"$work/reauthor.md"
reauth51="$(python3 "$scripts/pdlc-post-write.py" --work-item 51 --evidence "$evidence" --body "$work/reauthor.md")"
[[ "$(json '.gateState' "$reauth51")" == "Approval Required" ]]
grep -q "revised" "$records/51/body.md"
! grep -q "PDLC-INVALIDATED" "$records/51/comments.jsonl"

# Product authoring supplies exactly its three owned sections, in order.
PYTHONPATH="$scripts/lib" python3 - "$scripts" "$work" <<'PY'
import importlib.util
import sys
from pathlib import Path

from pdlc_common import PdlcError

scripts, work = Path(sys.argv[1]), Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("pdlc_write", scripts / "pdlc-post-write.py")
pdlc_write = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pdlc_write)

draft = work / "owned.md"
draft.write_text("## Product\np\n\n## Decisions\nd\n\n## Open Questions\nq\n")
assert pdlc_write.product_fragments(draft) == {"Product": "p", "Decisions": "d", "Open Questions": "q"}

draft.write_text("Intro\n\n## Product\np\n\n## Decisions\nd\n\n## Open Questions\nq\n")
try:
    pdlc_write.product_fragments(draft)
except PdlcError as error:
    assert "only ## Product" in str(error), error
else:
    raise AssertionError("accepted content before ## Product")
PY

# --- skip / invalidate ------------------------------------------------

seed_record 60 Product "Approval Required"
python3 "$scripts/pdlc-post-skip.py" --work-item 60 --state Testing --justification "service only" >/dev/null
grep -q '"Skipped States": "Testing"' "$records/60/meta.json"
python3 "$scripts/pdlc-post-invalidate.py" 60 Product "$evidence" >/dev/null
grep -q '"Gate State": "Stale"' "$records/60/meta.json"
# The comment records which stage was invalidated, not just the transient state.
python3 "$scripts/pdlc-inspect-timeline.py" 60 --full | grep -q "Invalidated stage: Product"

# A completed record is locked: invalidation is refused outright.
seed_record 61 Complete Approved
python3 "$scripts/pdlc-post-invalidate.py" 61 Verification "$evidence" 2>"$work/err" && exit 1
grep -q "Complete and locked" "$work/err"

# Invalidation cannot target a stage downstream of the active one.
seed_record 62 Tasks Pending
python3 "$scripts/pdlc-post-invalidate.py" 62 Implementation "$evidence" 2>"$work/err" && exit 1
grep -q "downstream of the active stage" "$work/err"

# --- churn-gated autonomous approval --------------------------------
#
# The mechanism lives in the scripts that write each approval gate, not the
# router: ci_gate.py past the Implementation gate on green CI, pdlc-post-review.py
# past the Testing gate on a clean review, pdlc-post-verify.py --bounce for the
# Verification -> Implementation loop-back. On-disk state is always real.

# One `Invalidated stage: <STAGE>` comment = one rework loop, whichever stage.
add_invalidation() {  # record [stage=Implementation]
  jq -nc --arg b "PDLC-INVALIDATED"$'\n\n'"Invalidated stage: ${2:-Implementation}"$'\n'"detail" \
    '{body:$b,createdAt:"2026-04-01T00:00:00Z",url:"",author:{login:"t"}}' \
    >>"$records/$1/comments.jsonl"
}
green_pr() {  # record
  jq -n '[{number:900,title:"impl",url:"u",state:"OPEN",isDraft:false,branch:"b",mergedAt:null,checks:"SUCCESS",relation:"closes"}]' \
    >"$records/$1/pull_requests.json"
}

# First pass (no loop back): green CI parks Implementation at Approval Required.
seed_record 63 Implementation "CI Pending"
green_pr 63
[[ "$(json '.gateState' "$(python3 "$scripts/pdlc-post-ci.py" 63)")" == "Approval Required" ]]

# After one loop back, green CI skips the human step straight to Testing / Pending.
seed_record 64 Implementation "CI Pending"
green_pr 64
add_invalidation 64
ci64="$(python3 "$scripts/pdlc-post-ci.py" 64)"
[[ "$(json '.gateState' "$ci64")" == "Testing / Pending" ]]
[[ "$(json '.autoApproved' "$ci64")" == "true" ]]
grep -q '"Status": "Testing"' "$records/64/meta.json"
grep -q "PDLC-AUTOAPPROVED" "$records/64/comments.jsonl"
[[ "$(python3 "$next" --work-item 64 | fm action)" == "pdlc-test" ]]

# A clean Testing review does the same, landing Verification / Pending. Rework
# loops count across stages — one Implementation bounce plus one Testing bounce.
seed_record 65 Testing "Review Required"
add_invalidation 65
add_invalidation 65 Testing
tr65="$(python3 "$scripts/pdlc-post-review.py" 65 approval-required "$evidence")"
[[ "$(json '.gateState' "$tr65")" == "Verification / Pending" ]]
[[ "$(json '.autoApproved' "$tr65")" == "true" ]]
grep -q '"Status": "Verification"' "$records/65/meta.json"
grep -q "PDLC-AUTOAPPROVED" "$records/65/comments.jsonl"

# Past the cap of 3 loop backs, the gate stops for the driver again.
seed_record 66 Implementation "CI Pending"
green_pr 66
add_invalidation 66; add_invalidation 66; add_invalidation 66; add_invalidation 66
[[ "$(json '.gateState' "$(python3 "$scripts/pdlc-post-ci.py" 66)")" == "Approval Required" ]]

# Verification approval is never auto-advanced, however much it churned.
seed_record 67 Verification Pending
add_invalidation 67
python3 "$scripts/pdlc-post-verify.py" 67 "$work/report.md" --recommendation "Approval Required" >/dev/null
grep -q '"Gate State": "Approval Required"' "$records/67/meta.json"
[[ "$(python3 "$next" --work-item 67 | fm action)" == "human-approval" ]]

# A clean run with a structurally invalid report is refused at publish time.
seed_record 71 Verification Pending
printf 'just some prose\n' | python3 "$scripts/pdlc-post-verify.py" 71 - \
  --recommendation "Approval Required" 2>"$work/err" && exit 1
grep -q "clean verification evidence is not valid" "$work/err"
grep -q '"Gate State": "Pending"' "$records/71/meta.json"

# Testing publication refuses a record whose implementation PR is not linked.
seed_record 72 Testing Pending
printf 'FR-1 -> x -> y\n' >"$work/tr.md"
python3 "$scripts/pdlc-post-test.py" 72 "$evidence" --traceability "$work/tr.md" 2>"$work/err" && exit 1
grep -q "no pull request linked" "$work/err"

# PDLC_AUTOAPPROVE_CHURN_CAP=0 disables it entirely.
seed_record 68 Implementation "CI Pending"
green_pr 68
add_invalidation 68
out68="$(PDLC_AUTOAPPROVE_CHURN_CAP=0 python3 "$scripts/pdlc-post-ci.py" 68)"
[[ "$(json '.gateState' "$out68")" == "Approval Required" ]]

# Verification --bounce returns an upstream stage to Stale with no driver step.
seed_record 69 Verification Pending
printf 'report\n' | python3 "$scripts/pdlc-post-verify.py" 69 - \
  --recommendation "Changes Required" --bounce Implementation >/dev/null
grep -q '"Status": "Implementation"' "$records/69/meta.json"
grep -q '"Gate State": "Stale"' "$records/69/meta.json"
grep -q "Invalidated stage: Implementation" "$records/69/comments.jsonl"
grep -q "PDLC-VERIFICATION" "$records/69/comments.jsonl"
[[ "$(python3 "$next" --work-item 69 | fm action)" == "pdlc-implement" ]]

# --bounce is rejected unless the recommendation is Changes Required.
seed_record 70 Verification Pending
printf 'report\n' | python3 "$scripts/pdlc-post-verify.py" 70 - \
  --recommendation "Approval Required" --bounce Implementation 2>"$work/err" && exit 1
grep -q "bounce is only valid" "$work/err"

# --- CLI guards -------------------------------------------------------

printf 'report\n' | python3 "$scripts/pdlc-post-verify.py" 22 - \
  --recommendation "Approval Required" --fixed - 2>"$work/err" && exit 1
grep -q "stdin can supply only one input" "$work/err"

# --- GitHub body ref neutralization (pure, backend-independent) -------

PYTHONPATH="$scripts/lib" python3 - <<'PY'
from github_common import neutralize_refs

assert neutralize_refs("see #148 now") == r"see \#148 now"
assert neutralize_refs("#1 and #23.") == r"\#1 and \#23."
assert neutralize_refs("## Heading") == "## Heading"          # not a ref
assert neutralize_refs("hex #123abc") == "hex #123abc"        # not a ref
assert neutralize_refs(r"already \#5") == r"already \#5"      # idempotent
assert neutralize_refs("entity &#8212;") == "entity &#8212;"  # HTML entity
assert neutralize_refs("owner/repo#9") == "owner/repo#9"      # qualified, deliberate
assert neutralize_refs("https://github.com/x/y/pull/12") == "https://github.com/x/y/pull/12"
assert neutralize_refs("```\ncode #5\n```\nprose #6\n") == "```\ncode #5\n```\nprose \\#6\n"
PY

# --- evidence parser + completion policy (pure, backend-independent) --

PYTHONPATH="$scripts/lib" python3 - <<'PY'
from pdlc_common import PdlcError
from evidence import parse_verification_report
from completion import completion_blockers
from completion_evidence import parse_completion_report, undispositioned_questions

good = """## Verification Run Results

### Claims Audit

- FR-1 holds (Verified @ abc123)

### User Journeys

- UJ-1 confirmed (Verified @ abc123)

### UX

- Reviewed — clean

### Ultra Review

- Clean

### Findings

None

Recommendation: Approval Required
"""

report = parse_verification_report(good)
assert report.recommendation == "Approval Required"
assert report.verified_commits == ("abc123", "abc123"), report.verified_commits
assert report.findings == ()

def rejects(body, needle):
    try:
        parse_verification_report(body)
    except PdlcError as error:
        assert needle in str(error), (needle, str(error))
    else:
        raise AssertionError(f"expected rejection for: {needle}")

rejects(good.replace("### UX\n\n- Reviewed — clean\n\n", ""), "missing required section")
rejects(good.replace("- FR-1 holds (Verified @ abc123)", "- FR-1 holds"), "Verified @")
rejects(good.replace("Recommendation: Approval Required", "Recommendation: Ship it"), "recommendation must be one of")

closed_task = {"state": "CLOSED", "hasImplementation": True, "number": 1, "title": "t"}
markers = ["PRODUCT", "APPROVED", "UI", "APPROVED", "TASKS", "APPROVED",
          "PLAN", "APPROVED", "IMPLEMENTATION", "APPROVED", "TESTING", "APPROVED"]

clean = completion_blockers(
    status="Verification", gate="Approval Required",
    tasks=[closed_task],
    pull_requests=[{"relation": "closes", "state": "MERGED", "checks": "SUCCESS", "number": 9}],
    timeline_markers=markers, skipped_states="",
    verification_body=good, stale_rows=[], open_questions="- none",
)
assert clean == [], clean

codes = {b.code for b in completion_blockers(
    status="Testing", gate="Pending",
    tasks=[{"state": "OPEN", "hasImplementation": False, "number": 2, "title": "x"}],
    pull_requests=[{"relation": "closes", "state": "OPEN", "checks": "FAILURE", "number": 9}],
    timeline_markers=["PRODUCT"], skipped_states="",
    verification_body=None, stale_rows=None,
    open_questions="- Should we cache tiles?",
)}
assert codes == {"status", "gate", "open-tasks", "pull-requests",
                "stage-evidence", "stage-settlement", "no-verification"}, codes

# --- completion evidence parser -------------------------------------------

good_evidence = """## Shipped

Tile pinning shipped across 7 tasks, PRs #144-#153, all merged.

## Verification

clean @ abc123 — claims, journeys, UX reviewed, ultra review clean.

## Decisions

- Evict pinned tiles LRU once the regional cap is hit — simpler than a manual queue (TASK-004).

## Open Questions

- Should tile eviction be LRU or manual-only? — Resolved: LRU, capped per region.
- Do we cap pinned regions at five? — Deferred: revisit for the paid tier, tracked as #210.

## Limitations

- Profile migration deferred to a follow-up record.

## Skipped Stages

- None
"""

report = parse_completion_report(good_evidence)
assert report.verified_commit == "abc123", report.verified_commit
assert len(report.decisions) == 1
assert len(report.dispositioned_questions) == 2
assert report.skipped_stages == ()

def rejects_completion(body, needle):
    try:
        parse_completion_report(body)
    except PdlcError as error:
        assert needle in str(error), (needle, str(error))
    else:
        raise AssertionError(f"expected rejection for: {needle}")

rejects_completion("just a sentence", "missing required section")
rejects_completion(good_evidence.replace("clean @ abc123 — ", ""), "clean @ <commit>")
rejects_completion(
    good_evidence.replace("- Should tile eviction be LRU or manual-only? — Resolved: LRU, capped per region.",
                          "- Should tile eviction be LRU or manual-only?"),
    "not a disposition",
)

# undispositioned_questions matches live parent entries against the evidence.
live_section = "- Should tile eviction be LRU or manual-only?\n- What is the tile-pin quota ceiling?"
missing = undispositioned_questions(report, live_section)
assert missing == ["What is the tile-pin quota ceiling?"], missing
assert undispositioned_questions(report, "- none") == []

# A '- None' evidence section disposes of nothing: any live entry is unaccounted.
none_report = parse_completion_report(good_evidence.replace(
    "- Should tile eviction be LRU or manual-only? — Resolved: LRU, capped per region.\n"
    "- Do we cap pinned regions at five? — Deferred: revisit for the paid tier, tracked as #210.\n",
    "- None\n",
))
assert undispositioned_questions(none_report, "- a real question") == ["a real question"]

# completion_blockers surfaces a malformed evidence body and undispositioned entries.
ev_codes = {b.code for b in completion_blockers(
    status="Verification", gate="Approval Required", tasks=[closed_task],
    pull_requests=[{"relation": "closes", "state": "MERGED", "checks": "SUCCESS", "number": 9}],
    timeline_markers=markers, skipped_states="",
    verification_body=good, stale_rows=[],
    open_questions="- a lingering question",
    evidence_body=good_evidence,
)}
assert ev_codes == {"open-questions"}, ev_codes
assert any(b.code == "evidence-malformed" for b in completion_blockers(
    status="Verification", gate="Approval Required", tasks=[closed_task],
    pull_requests=[{"relation": "closes", "state": "MERGED", "checks": "SUCCESS", "number": 9}],
    timeline_markers=markers, skipped_states="",
    verification_body=good, stale_rows=[], open_questions="- none",
    evidence_body="not structured",
))

# AUTOAPPROVED / SKIPPED count as valid stage settlement.
churn_markers = ["PRODUCT", "APPROVED", "UI", "APPROVED", "TASKS", "APPROVED",
                "PLAN", "APPROVED", "IMPLEMENTATION", "AUTOAPPROVED", "TESTING", "AUTOAPPROVED"]
assert not any(b.code == "stage-settlement" for b in completion_blockers(
    status="Verification", gate="Approval Required", tasks=[closed_task],
    pull_requests=[{"relation": "closes", "state": "MERGED", "checks": "SUCCESS", "number": 9}],
    timeline_markers=churn_markers, skipped_states="",
    verification_body=good, stale_rows=[], open_questions="- none",
))

# A Complete record short-circuits to a single blocker.
done = completion_blockers(
    status="Complete", gate="Approved", tasks=[], pull_requests=[],
    timeline_markers=[], skipped_states="", verification_body=None,
)
assert [b.code for b in done] == ["already-complete"], done
PY

printf '%s\n' "pdlc tests passed"

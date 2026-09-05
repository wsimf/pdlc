## Recommendation

  Refactor the dirty spike into:

  flowchart LR
      Record["Resolved record + work type"] --> Registry["Pipeline registry"]
      Registry --> Pipeline["Resolved Pipeline"]
      Pipeline --> Route["route(state)"]
      Pipeline --> Transition["next_state(state, event, outcome)"]
      Pipeline --> Invalidation["invalidation policy"]
      Pipeline --> Completion["completion policy"]

      Route --> InspectNext["inspect / next"]
      Transition --> Commands["post commands"]
      Invalidation --> Commands
      Completion --> InspectComplete["inspect/post complete"]
      Commands --> Hosts["work-item/code hosts"]

  One pipeline definition owns policy. Generic domain functions interpret it. Commands perform I/O.

  Do not build a general graph yet. Use an ordered stage spine plus sparse exceptions.

  ## Target domain

  ### Typed vocabulary

  Add string enums:

  class WorkType(StrEnum): ...
  class Gate(StrEnum): ...
  class Lifecycle(StrEnum): ...
  class StageKind(StrEnum): ...
  class Event(StrEnum): ...
  class Outcome(StrEnum): ...
  class Action(StrEnum): ...

  Persisted values remain current GitHub strings. Enums prevent internal spelling drift.

  Add:

  @dataclass(frozen=True)
  class State:
      stage: str
      gate: Gate
      lifecycle: Lifecycle

  Stage names remain strings because pipelines may define different stages. Pipeline construction validates them.

  ### Stage policy

  @dataclass(frozen=True)
  class WorkPolicy:
      action: Action
      autonomous: bool
      result_gate: Gate
      reason: str

  @dataclass(frozen=True)
  class ReviewPolicy:
      target: str
      reviewer: str
      ci_gated: bool = False
      permits_decision: bool = True

  @dataclass(frozen=True)
  class Stage:
      name: str
      kind: StageKind
      marker: str | None
      work: WorkPolicy | None
      review: ReviewPolicy | None = None
      work_queue: str | None = None
      skippable: bool = True
      reauthor_in_place: bool = False
      autoapprove_on_rework: bool = False
      terminal: bool = False

  This replaces:

  - action_for() stage checks.
  - _REVIEW_TARGETS.
  - _OWNER_FOR_ACTION.
  - REAUTHOR_STAGES.
  - AUTOAPPROVE_STAGES.
  - Implementation-specific CI checks.

  kind describes broad semantics but must not become another switch statement. Explicit fields remain authoritative.

  ### Transition policy

  @dataclass(frozen=True)
  class TransitionOverride:
      source_stage: str
      source_gate: Gate
      event: Event
      outcome: Outcome | None
      target_stage: str
      target_gate: Gate
      target_lifecycle: Lifecycle

  @dataclass(frozen=True)
  class Pipeline:
      work_type: WorkType
      stages: tuple[Stage, ...]
      overrides: tuple[TransitionOverride, ...]
      completion_policy: CompletionPolicy
      invalidation_policy: InvalidationPolicy
      rework_policy: ReworkPolicy | None = None
      available: bool = True

      def route(self, state: State) -> Route: ...
      def next_state(self, state: State, event: Event, outcome: Outcome | None = None, requested_target: str | None = None) -> State: ...
      def can_invalidate(self, active: str, target: str) -> bool: ...

  The generic engine derives ordinary behavior:

  - Work completed → stage’s result_gate.
  - Review findings → same stage / Changes Required.
  - Review decision → same stage / Decision Required.
  - Clean review → Approval Required, or CI Pending when ci_gated.
  - CI red → same stage / Changes Required.
  - CI green → same stage / Approval Required.
  - Human approval → next spine stage / Pending.
  - Ordinary skip → next spine stage / Pending.
  - Decision resolved → same stage / Changes Required.

  Overrides encode only exceptions:

  - Skipped Verification → Verification / Approval Required.
  - Verification bounce → requested permitted target / Stale.
  - Verification completion → Complete / Approved / Completed.

  Every transition validates source stage and source gate.

  ## Feature definition

  Rename STANDARD_WORKFLOW to FEATURE_PIPELINE. “Work item” is the wrong type name because bugs are also work items.

  Transcribe today’s behavior exactly:

  Product
  UI
  Tasks
  Technical Plan
  Implementation
  Testing
  Verification
  Complete

  Important declarations:

  - Product not autonomous or skippable.
  - Product/UI/Tasks/Technical Plan reauthor in place.
  - Implementation and Testing reviewed.
  - Implementation CI-gated.
  - Implementation and Testing auto-approved during bounded rework.
  - Verification is completion boundary.
  - Verification bounce targets restricted to Implementation and Testing.
  - Complete terminal and locked.

  Avoid changing behavior during this transcription.

  ## Completion policy

  Completion cannot remain implicitly Feature-specific.

  Represent it as composable requirements:

  @dataclass(frozen=True)
  class CompletionPolicy:
      boundary_stage: str
      boundary_gate: Gate
      required_stage_evidence: tuple[str, ...]
      require_stage_settlement: bool
      require_tasks_closed: bool
      require_task_implementation: bool
      require_prs_merged: bool
      require_checks_green: bool
      verification_parser: str | None

  The current Feature policy enables every existing requirement.

  completion_blockers() accepts the resolved pipeline and evaluates its policy. This preserves one shared inspector/mutator decision while allowing Bug to require different evidence later.

  ## Invalidation policy

  Do not use one concept of “downstream” for everything.

  @dataclass(frozen=True)
  class InvalidationPolicy:
      evidence_dependencies: Mapping[str, tuple[str, ...]]
      reentry_targets: Mapping[str, tuple[str, ...]]

  Separate questions:

  - Can the active stage return to target?
  - Which evidence becomes stale?
  - Which targets may Verification bounce to?
  - May this stage reauthor before approval?

  For the linear Feature pipeline, reachability can use spine order. Evidence dependencies retain the existing explicit table. Verification bounce uses declared reentry targets.

  ## Work-type resolution

  ### Normalized record contract

  Add workType to resolved work-item dictionaries.

  Update:

  - src/pdlc/hosts/workitem_host/base.py:26
  - GitHub backend normalization.
  - File backend persistence.
  - Test fixtures and replay data.

  Resolution rules:

  - Native GitHub Issue Type Feature → WorkType.FEATURE.
  - Native GitHub Issue Type Bug → WorkType.BUG.
  - Legacy record with no type → explicit Feature compatibility.
  - Unknown type → blocked.
  - Known but unavailable pipeline → blocked with reason.

  Resolve once:

  pipeline = PIPELINES.for_record(record)

  Pass that object through the operation. Never repeatedly resolve strings downstream.

  ### Creation

  Eventually extend:

  create_work_item(title, body, slug, work_type)

  GitHub creation supplies the native Issue Type. File backend stores the same normalized value.

  Do this after Feature policy parity, not simultaneously with the first domain refactor.

  ## Migration phases

  ### 1. Characterize current behavior

  Before changing the dirty spike, add a complete Feature transition matrix test covering:

  - Every stage with Pending, Stale, and Changes Required.
  - Review outcomes: clean, findings, decision.
  - CI pending, green, red.
  - Every human approval.
  - Every skip.
  - Decision resolution.
  - Verification outcomes and permitted bounces.
  - Churn auto-approval boundaries: 0, 1–3, over 3.
  - Completion.
  - Malformed states.

  These tests become the anti-regression contract for the refactor.

  ### 2. Reshape the dirty domain spike

  Rework src/pdlc/domain/workflow.py:11:

  - Add typed state/event/outcome vocabulary.
  - Replace the generated explicit graph with spine-derived behavior.
  - Replace stage-name special cases with stage properties.
  - Validate source gates.
  - Restrict dynamic targets.
  - Add Feature policy.
  - Add registry.
  - Keep Bug absent or unavailable.

  Keep src/pdlc/domain/lifecycle.py:55 temporarily as a compatibility façade delegating into FEATURE_PIPELINE.

  ### 3. Move read-only routing first

  Change:

  - domain.model.due_next()
  - commands.next
  - commands.inspect

  They should resolve and use the same pipeline route.

  Delete policy duplication from:

  - action_for()
  - next_status_for()
  - _OWNER_FOR_ACTION

  This is low-risk because inspection and routing can be tested without mutations.

  ### 4. Move normal mutations

  Migrate:

  - post approve
  - post skip
  - common stage publication
  - post review
  - post ci
  - post decision

  Each command should:

  1. Resolve record and pipeline.
  2. Ask pipeline for a transition.
  3. Validate command-specific evidence.
  4. Persist the returned state.
  5. Post evidence.

  Commands should no longer calculate destination gates or next stages.

  Specialized commands may still name their artifact stage. post plan owning Technical Plan is legitimate command ownership, not duplicated routing policy.

  ### 5. Move reauthor, churn, and invalidation

  Replace:

  - REAUTHOR_STAGES
  - AUTOAPPROVE_STAGES
  - STAGES.index()
  - unrestricted Verification bounce targets

  Use the resolved pipeline’s stage and rework policies.

  Keep churn counting as an I/O/data concern. The pipeline decides whether a stage participates and what transition follows.

  ### 6. Move completion

  Pass pipeline.completion_policy into completion_blockers().

  Update both:

  - inspect complete
  - post complete

  Remove global Feature assumptions such as SETTLED_STAGES and _EVIDENCE_MARKER_FOR_STAGE.

  Verify inspector and mutator still produce identical blocker sets.

  ### 7. Remove compatibility globals

  Once every consumer takes a pipeline:

  - Remove global STAGES.
  - Remove global SKIPPABLE_STAGES.
  - Remove global next_stage().
  - Remove action_for() and next_status_for().
  - Reduce lifecycle.py to generic utilities or merge those utilities into more appropriate modules.

  Use rg to confirm hardcoded workflow stage names remain only in:

  - Pipeline definitions.
  - Stage-specific artifact commands.
  - Evidence parsers.
  - Tests and documentation.

  ### 8. Register Bug safely

  Add BUG_PIPELINE, initially available=False.

  This proves:

  - Registry selection.
  - Different stage names.
  - Different transition choices.
  - Different completion policy.
  - Unknown/unavailable blocking.

  Do not enable it until its exact stages, actions, reviewers, evidence, Status options, and completion contract exist.

  Do not model Bug as Feature plus skips.

  ### 9. GitHub Project setup

  Once multiple pipelines are enabled:

  - Compute required Status options from all enabled pipelines.
  - Compare with live Project options.
  - Report missing options.
  - Modify them only through explicit confirmed pdlc setup.
  - Preserve existing option IDs because GitHub replaces the option collection.

  No implicit Project mutation during work-item creation.

  ### 10. Update agent contracts

  After code behavior settles, update:

  - pdlc-contract.md
  - parity-contract.md
  - capabilities.md
  - controller/loop skills
  - stage skills affected by renamed/generalized actions

  Document pipeline resolution, unavailable types, and ownership. Do not write hypothetical Bug skill behavior yet.

  ## Validation

  Focused:

  XDG_CACHE_HOME=/tmp/pdlc-uv-cache uv run python -m unittest tests.test_lifecycle tests.test_routing tests.test_skip_invalidate tests.test_review_ci tests.test_completion

  Full:

  XDG_CACHE_HOME=/tmp/pdlc-uv-cache uv run python -m unittest discover -s tests -p 'test_*.py'
  XDG_CACHE_HOME=/tmp/pdlc-uv-cache uv build
  PYTHONPYCACHEPREFIX=/tmp/pdlc-pycache python3 -m compileall -q src
  git diff --check

  Also run file-backend end-to-end scenarios for:

  - Complete unchanged Feature lifecycle.
  - Legacy missing-type Feature compatibility.
  - Unknown type blocked.
  - Bug known but unavailable.
  - Skip cascade.
  - Verification bounce and churn cap.

  ## Definition of done

  - Existing Feature behavior unchanged.
  - One Feature pipeline definition owns stage order and policy.
  - inspect and next use the same route().
  - Every mutation obtains its destination from next_state().
  - Impossible source gates are rejected.
  - Invalidation and completion are pipeline-aware.
  - Unknown types never fall back silently.
  - Adding an available pipeline requires a pipeline definition plus genuinely new executors/reviewers—not edits to existing generic routing.
  - Dirty work remains preserved and reviewed before implementation starts.
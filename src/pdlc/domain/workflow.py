"""Pure, typed workflow policy.

The Feature pipeline is deliberately an ordered spine. Ordinary movement is
derived from that spine and stage policy; only exceptional edges (such as a
Verification bounce) are declared explicitly. This module performs no host
I/O and is safe to use from both read-only routing and mutating commands.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

REQUESTED_TARGET = "$requested"


class WorkType(StrEnum):
    FEATURE = "feature"
    BUG = "bug"


class Gate(StrEnum):
    PENDING = "Pending"
    REVIEW_REQUIRED = "Review Required"
    CHANGES_REQUIRED = "Changes Required"
    DECISION_REQUIRED = "Decision Required"
    CI_PENDING = "CI Pending"
    APPROVAL_REQUIRED = "Approval Required"
    APPROVED = "Approved"
    STALE = "Stale"


class Lifecycle(StrEnum):
    PLANNING = "Planning"
    DELIVERY = "Delivery"
    COMPLETED = "Completed"


class Event(StrEnum):
    PUBLISHED = "published"
    REVIEWED = "reviewed"
    CI_RECONCILED = "ci-reconciled"
    APPROVED = "approved"
    SKIPPED = "skipped"
    REAUTHORED = "reauthored"
    DECISION_RESOLVED = "decision-resolved"
    INVALIDATED = "invalidated"
    VERIFIED = "verified"
    BOUNCED = "bounced"
    COMPLETED = "completed"
    AUTOAPPROVED = "autoapproved"


class Outcome(StrEnum):
    CLEAN = "clean"
    FINDINGS = "findings"
    DECISION = "decision"
    CHECKS_PASSED = "checks-passed"
    CHECKS_FAILED = "checks-failed"
    CHECKS_PENDING = "checks-pending"


class Action(StrEnum):
    NONE = "none"
    BLOCKED = "blocked"
    HUMAN_INPUT = "human-input"
    HUMAN_APPROVAL = "human-approval"
    HUMAN_DECISION = "human-decision"
    REVIEW = "pdlc-review"
    CI = "pdlc-post-ci"
    TASKS = "pdlc-tasks"
    PLAN = "pdlc-plan"
    IMPLEMENT = "pdlc-implement"
    TEST = "pdlc-test"
    VERIFY = "pdlc-verify"


@dataclass(frozen=True)
class State:
    """The complete persisted workflow state used as a transition source."""

    stage: str
    gate: Gate
    lifecycle: Lifecycle = Lifecycle.PLANNING

    @classmethod
    def parse(
        cls,
        stage: str,
        gate: Gate | str,
        lifecycle: Lifecycle | str = Lifecycle.PLANNING,
    ) -> State:
        """Parse persisted strings at the domain boundary."""
        try:
            return cls(stage, Gate(gate), Lifecycle(lifecycle))
        except ValueError as error:
            raise ValueError(f"invalid workflow state: {error}") from None

    @property
    def notation(self) -> str:
        return f"{self.stage.replace(' ', '')}.{self.gate.value.replace(' ', '')}"


@dataclass(frozen=True)
class ReviewerTarget:
    """The artifact and specialist that own an independent review."""

    artifact: str
    agent: str

    @property
    def reviewer(self) -> str:
        return self.agent


@dataclass(frozen=True)
class ReviewPolicy:
    """Review behavior for a stage that requires an independent review."""

    target: ReviewerTarget | None = None
    clean_gate: Gate = Gate.APPROVAL_REQUIRED
    permits_decision: bool = True
    independent: bool = True


@dataclass(frozen=True)
class Stage:
    """Policy attached to one stage in a pipeline."""

    name: str
    marker: str | None
    action: Action | None
    autonomous: bool
    result_gate: Gate | None
    reason: str = ""
    review: ReviewPolicy | None = None
    ci_gated: bool = False
    skippable: bool = True
    reauthor_in_place: bool = False
    accepts_verification: bool = False
    terminal: bool = False


@dataclass(frozen=True)
class TransitionOverride:
    """An exceptional edge keyed by exact source state and event."""

    source_stage: str
    source_gate: Gate
    event: Event
    target_stage: str
    target_gate: Gate
    target_lifecycle: Lifecycle = Lifecycle.PLANNING
    outcome: Outcome | None = None
    loop: str | None = None


@dataclass(frozen=True)
class TransitionResult:
    """Compatibility rendering of a resolved transition."""

    event: str
    source_stage: str
    target_stage: str
    gate: str
    lifecycle: str
    loop: str | None = None


@dataclass(frozen=True)
class Route:
    action: Action
    autonomous: bool
    reason: str


@dataclass(frozen=True)
class ReworkPolicy:
    """Bounded Verification-triggered rework and autonomous approval rules."""

    name: str
    max_iterations: int
    autoapprove_stages: tuple[str, ...]
    human_boundary: str

    def __post_init__(self) -> None:
        if self.max_iterations < 0:
            raise ValueError("rework cap cannot be negative")
        object.__setattr__(self, "autoapprove_stages", tuple(self.autoapprove_stages))


@dataclass(frozen=True)
class CompletionPolicy:
    """Evidence and state requirements at a pipeline's completion boundary."""

    boundary_stage: str
    boundary_gate: Gate
    required_stage_evidence: tuple[str, ...]
    require_stage_settlement: bool = True
    require_tasks_closed: bool = True
    require_task_implementation: bool = True
    require_prs_merged: bool = True
    require_checks_green: bool = True
    verification_parser: str | None = "parse_verification_report"

    def __post_init__(self) -> None:
        if not isinstance(self.boundary_gate, Gate):
            raise TypeError("completion boundary gate must be a Gate")
        evidence = tuple(self.required_stage_evidence)
        if len(evidence) != len(set(evidence)):
            raise ValueError("completion policy contains duplicate evidence stages")
        object.__setattr__(self, "required_stage_evidence", evidence)

    def is_boundary(self, state: State) -> bool:
        """Whether a typed state is exactly the state from which completion runs."""
        return state.stage == self.boundary_stage and state.gate == self.boundary_gate

    def settled_stages(self, active_stages: tuple[str, ...], skipped: set[str] | frozenset[str]) -> tuple[str, ...]:
        """Return active stages whose settlement must be represented in evidence."""
        return tuple(stage for stage in self.required_stage_evidence if stage in active_stages and stage not in skipped)

    def requires_evidence_for(self, stage: str) -> bool:
        """Whether completion requires the stage's evidence marker."""
        return stage in self.required_stage_evidence


@dataclass(frozen=True)
class InvalidationPolicy:
    """Downstream evidence dependencies and explicitly permitted re-entry targets.

    ``evidence_dependencies`` maps a stage being changed to downstream stages
    whose existing evidence is no longer trustworthy. ``reentry_targets`` maps
    the active stage to the stages it may re-enter; Verification's entries are
    therefore also the only allowed Verification bounce targets.
    """

    evidence_dependencies: Mapping[str, tuple[str, ...]]
    reentry_targets: Mapping[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        def normalize(values: Mapping[str, tuple[str, ...]]) -> Mapping[str, tuple[str, ...]]:
            result: dict[str, tuple[str, ...]] = {}
            for source, targets in values.items():
                normalized = tuple(targets)
                if len(normalized) != len(set(normalized)):
                    raise ValueError(f"invalidation policy contains duplicate targets for {source}")
                result[source] = normalized
            return MappingProxyType(result)

        object.__setattr__(self, "evidence_dependencies", normalize(self.evidence_dependencies))
        object.__setattr__(self, "reentry_targets", normalize(self.reentry_targets))

    def dependencies_for(self, stage: str) -> tuple[str, ...]:
        """Return stages whose evidence becomes stale when ``stage`` changes."""
        return self.evidence_dependencies.get(stage, ())

    def targets_for(self, active_stage: str) -> tuple[str, ...]:
        """Return the explicit re-entry targets for the active stage."""
        return self.reentry_targets.get(active_stage, ())

    def can_reenter(self, active_stage: str, target_stage: str) -> bool:
        """Whether ``active_stage`` may return to ``target_stage``."""
        return target_stage in self.targets_for(active_stage)


_WORK_GATES = (Gate.PENDING, Gate.CHANGES_REQUIRED, Gate.STALE)


@dataclass(frozen=True)
class Pipeline:
    """A validated ordered workflow spine plus sparse exceptional edges."""

    work_type: WorkType
    stages: tuple[Stage, ...]
    overrides: tuple[TransitionOverride, ...] = ()
    completion_policy: CompletionPolicy | None = None
    invalidation_policy: InvalidationPolicy | None = None
    available: bool = True
    rework_policy: ReworkPolicy | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "stages", tuple(self.stages))
        object.__setattr__(self, "overrides", tuple(self.overrides))
        if not isinstance(self.work_type, WorkType):
            raise TypeError("pipeline work_type must be a WorkType")
        if not self.available:
            if self.stages or self.overrides or self.completion_policy or self.invalidation_policy or self.rework_policy:
                raise ValueError("an unavailable pipeline cannot declare workflow policy")
            return
        if self.completion_policy is None or self.invalidation_policy is None:
            raise ValueError(f"pipeline {self.work_type!s} must declare completion and invalidation policy")
        names = tuple(stage.name for stage in self.stages)
        if len(names) != len(set(names)):
            raise ValueError(f"pipeline {self.work_type!s} contains duplicate stages")
        if not names or sum(stage.terminal for stage in self.stages) != 1 or not self.stages[-1].terminal:
            raise ValueError(f"pipeline {self.work_type!s} must have exactly one terminal stage")
        known = set(names)
        for stage in self.stages:
            if stage.action is not None and not isinstance(stage.action, Action):
                raise TypeError(f"stage action must be an Action: {stage.name}")
            if stage.result_gate is not None and not isinstance(stage.result_gate, Gate):
                raise TypeError(f"stage result gate must be a Gate: {stage.name}")
            if stage.review is not None and not isinstance(stage.review.clean_gate, Gate):
                raise TypeError(f"review clean gate must be a Gate: {stage.name}")
            if stage.terminal and (
                stage.action is not None
                or stage.result_gate is not None
                or stage.review is not None
                or stage.ci_gated
                or stage.skippable
                or stage.reauthor_in_place
                or stage.accepts_verification
            ):
                raise ValueError(f"terminal stage carries active policy: {stage.name}")
            if stage.ci_gated and (stage.review is None or not stage.review.independent):
                raise ValueError(f"CI-gated stage requires independent review: {stage.name}")
        keys: set[tuple[str, Gate, Event, Outcome | None]] = set()
        for override in self.overrides:
            if not isinstance(override.source_gate, Gate) or not isinstance(override.target_gate, Gate):
                raise TypeError("transition gates must be Gate values")
            if not isinstance(override.target_lifecycle, Lifecycle):
                raise TypeError("transition lifecycle must be a Lifecycle value")
            key = (override.source_stage, override.source_gate, override.event, override.outcome)
            if key in keys:
                raise ValueError(f"pipeline {self.work_type!s} contains duplicate transition: {key}")
            keys.add(key)
            if override.source_stage not in known or (override.target_stage not in known and override.target_stage != REQUESTED_TARGET):
                raise ValueError(f"transition references an unknown stage: {key}")
            dynamic = override.target_stage == REQUESTED_TARGET
            allowed_targets = self.invalidation_policy.targets_for(override.source_stage) if dynamic else ()
            if dynamic and not allowed_targets:
                raise ValueError(f"dynamic transition has no declared re-entry targets: {key}")
            self._validate_event_outcome(override.event, override.outcome)
            self.validate_state(State(override.source_stage, override.source_gate))
            targets = allowed_targets if dynamic else (override.target_stage,)
            for target in targets:
                self.validate_state(State(target, override.target_gate, override.target_lifecycle))
        if self.rework_policy is not None:
            references = (*self.rework_policy.autoapprove_stages, self.rework_policy.human_boundary)
            if any(stage not in known for stage in references):
                raise ValueError(f"rework policy references an unknown stage: {references}")
        completion = self.completion_policy
        if completion.boundary_stage not in known or completion.boundary_stage == self.terminal_stage:
            raise ValueError(f"completion policy references an invalid boundary stage: {completion.boundary_stage}")
        if any(stage not in known or stage == self.terminal_stage for stage in completion.required_stage_evidence):
            raise ValueError("completion policy references an unknown evidence stage")
        invalidation = self.invalidation_policy
        for mapping_name, mapping in (
            ("evidence dependencies", invalidation.evidence_dependencies),
            ("re-entry targets", invalidation.reentry_targets),
        ):
            if any(source not in known for source in mapping):
                raise ValueError(f"invalidation policy has an unknown {mapping_name} source")
            if any(target not in known for targets in mapping.values() for target in targets):
                raise ValueError(f"invalidation policy has an unknown {mapping_name} target")
        for override in self.overrides:
            if override.loop is not None and (
                self.rework_policy is None or override.loop != self.rework_policy.name
            ):
                raise ValueError(f"transition references an unknown rework policy: {override.loop}")

    @property
    def all_stage_names(self) -> tuple[str, ...]:
        return tuple(stage.name for stage in self.stages)

    @property
    def active_stage_names(self) -> tuple[str, ...]:
        return tuple(stage.name for stage in self.stages if not stage.terminal)

    @property
    def terminal_stage(self) -> str:
        return next(stage.name for stage in self.stages if stage.terminal)

    @property
    def skippable_stage_names(self) -> tuple[str, ...]:
        return tuple(stage.name for stage in self.stages if stage.skippable and not stage.terminal)

    @property
    def completion_boundary(self) -> tuple[str, Gate]:
        """The stage and gate that completion must validate before locking."""
        if self.completion_policy is None:
            raise ValueError(f"pipeline {self.work_type!s} has no completion policy")
        return self.completion_policy.boundary_stage, self.completion_policy.boundary_gate

    def stage(self, name: str) -> Stage:
        for stage in self.stages:
            if stage.name == name:
                return stage
        raise ValueError(f"unknown workflow stage: {name}")

    # Kept as a readable alias for callers of the initial spike.
    rule_for = stage

    def marker_for_stage(self, stage: str) -> str:
        marker = self.stage(stage).marker
        if marker is None:
            raise ValueError(f"no evidence marker for stage: {stage}")
        return marker

    @staticmethod
    def _validate_event_outcome(event: Event, outcome: Outcome | None) -> None:
        allowed = {
            Event.REVIEWED: {Outcome.CLEAN, Outcome.FINDINGS, Outcome.DECISION},
            Event.CI_RECONCILED: {Outcome.CHECKS_PASSED, Outcome.CHECKS_FAILED, Outcome.CHECKS_PENDING},
            Event.VERIFIED: {Outcome.CLEAN, Outcome.FINDINGS, Outcome.DECISION},
        }
        if not isinstance(event, Event):
            raise TypeError("workflow event must be an Event")
        if outcome is not None and not isinstance(outcome, Outcome):
            raise TypeError("workflow outcome must be an Outcome")
        if event in allowed:
            if outcome is not None and outcome not in allowed[event]:
                raise ValueError(f"invalid outcome for {event.value}: {outcome.value}")
        elif outcome is not None:
            raise ValueError(f"{event.value} does not accept an outcome")

    def validate_state(self, state: State) -> Stage:
        """Validate a persisted stage/gate/lifecycle combination."""
        if not isinstance(state, State):
            raise TypeError("workflow state must be a State")
        if not isinstance(state.gate, Gate) or not isinstance(state.lifecycle, Lifecycle):
            raise TypeError("workflow state must contain typed gate and lifecycle values")

        stage = self.stage(state.stage)
        if stage.terminal:
            if state.gate != Gate.APPROVED or state.lifecycle != Lifecycle.COMPLETED:
                raise ValueError(f"invalid terminal workflow state: {state.stage} / {state.gate.value} / {state.lifecycle.value}")
            return stage
        if state.lifecycle == Lifecycle.COMPLETED:
            raise ValueError(f"active stage cannot have Completed lifecycle: {state.stage}")
        if state.gate in _WORK_GATES and stage.action is None:
            raise ValueError(f"stage has no work action: {state.stage}")
        if state.gate == Gate.REVIEW_REQUIRED and (stage.review is None or not stage.review.independent):
            raise ValueError(f"stage does not support persisted independent review: {state.stage}")
        if state.gate == Gate.CI_PENDING and not stage.ci_gated:
            raise ValueError(f"stage is not CI-gated: {state.stage}")
        if state.gate == Gate.DECISION_REQUIRED and not (
            stage.accepts_verification
            or (stage.review is not None and stage.review.independent and stage.review.permits_decision)
        ):
            raise ValueError(f"stage does not support decisions: {state.stage}")
        if state.gate == Gate.APPROVED:
            raise ValueError(f"active stage cannot remain Approved: {state.stage}")
        return stage

    def route(self, state: State) -> Route:
        """Resolve the next action without predicting its outcome."""
        try:
            stage = self.validate_state(state)
        except (TypeError, ValueError):
            return Route(Action.BLOCKED, False, "missing or unsupported work item state")

        gate = state.gate
        if stage.terminal:
            return Route(Action.NONE, False, "complete")
        if gate == Gate.DECISION_REQUIRED:
            return Route(Action.HUMAN_DECISION, False, "a reviewer raised a blocking decision that only the user can resolve")
        if gate == Gate.CI_PENDING:
            return Route(Action.CI, True, "the implementation review passed; the registered PR stack's CI outcome must be recorded")
        if gate == Gate.APPROVAL_REQUIRED:
            return Route(Action.HUMAN_APPROVAL, False, "explicit human approval is required")
        if gate == Gate.REVIEW_REQUIRED:
            return Route(Action.REVIEW, True, "review is due")
        if gate in _WORK_GATES and stage.action is not None:
            return Route(stage.action, stage.autonomous, stage.reason or f"{stage.name} work is due")
        return Route(Action.BLOCKED, False, "missing or unsupported work item state")

    def _require_source(self, state: State, event: Event) -> Stage:
        stage = self.validate_state(state)
        if stage.terminal:
            raise ValueError(f"no {event.value} transition from terminal stage: {state.stage}")
        return stage

    def _override(self, state: State, event: Event, outcome: Outcome | None, requested_target: str | None) -> State | None:
        for rule in self.overrides:
            if rule.source_stage != state.stage or rule.source_gate != state.gate or rule.event != event:
                continue
            if rule.outcome != outcome:
                continue
            target = rule.target_stage
            if rule.target_stage == REQUESTED_TARGET:
                allowed_targets = self.invalidation_policy.targets_for(state.stage)
                if requested_target is None:
                    raise ValueError(f"transition {event.value} from {state.stage} requires a target")
                if requested_target not in allowed_targets:
                    allowed = ", ".join(allowed_targets)
                    raise ValueError(f"invalid target {requested_target} for {event.value} from {state.stage}; expected one of: {allowed}")
                target = requested_target
            elif requested_target is not None:
                raise ValueError(f"transition {event.value} from {state.stage} does not accept a target")
            return State(target, rule.target_gate, rule.target_lifecycle)
        return None

    def next_state(
        self,
        state: State,
        event: Event,
        outcome: Outcome | None = None,
        requested_target: str | None = None,
    ) -> State:
        """Resolve a transition, requiring the exact source stage and gate."""
        if not isinstance(event, Event):
            raise TypeError("next_state requires an Event")
        if outcome is not None and not isinstance(outcome, Outcome):
            raise TypeError("next_state outcome must be an Outcome")
        stage = self._require_source(state, event)
        self._validate_event_outcome(event, outcome)
        overridden = self._override(state, event, outcome, requested_target)
        if overridden is not None:
            return overridden
        if requested_target is not None and event != Event.INVALIDATED:
            raise ValueError(f"transition {event.value} from {state.stage} does not accept a target")

        if event == Event.PUBLISHED:
            if state.gate not in _WORK_GATES or stage.result_gate is None:
                raise ValueError(f"publish requires a work gate from {state.stage}")
            return State(stage.name, stage.result_gate, state.lifecycle)
        if event == Event.REVIEWED:
            if state.gate != Gate.REVIEW_REQUIRED or stage.review is None or not stage.review.independent:
                raise ValueError(f"review requires Review Required from {state.stage}")
            if outcome == Outcome.CLEAN:
                gate = Gate.CI_PENDING if stage.ci_gated else stage.review.clean_gate
            elif outcome == Outcome.FINDINGS:
                gate = Gate.CHANGES_REQUIRED
            elif outcome == Outcome.DECISION and stage.review.permits_decision:
                gate = Gate.DECISION_REQUIRED
            else:
                raise ValueError(f"invalid review outcome from {state.stage}: {outcome}")
            return State(stage.name, gate, state.lifecycle)
        if event == Event.CI_RECONCILED:
            if state.gate != Gate.CI_PENDING or not stage.ci_gated:
                raise ValueError(f"CI requires CI Pending from {state.stage}")
            if outcome == Outcome.CHECKS_PASSED:
                return State(stage.name, Gate.APPROVAL_REQUIRED, state.lifecycle)
            if outcome == Outcome.CHECKS_FAILED:
                return State(stage.name, Gate.CHANGES_REQUIRED, state.lifecycle)
            if outcome == Outcome.CHECKS_PENDING:
                return state
            raise ValueError(f"invalid CI outcome from {state.stage}: {outcome}")
        if event == Event.VERIFIED:
            if not stage.accepts_verification or state.gate not in _WORK_GATES:
                raise ValueError(f"verification requires a work gate from {state.stage}")
            if outcome == Outcome.CLEAN:
                return State(stage.name, Gate.APPROVAL_REQUIRED, state.lifecycle)
            if outcome == Outcome.FINDINGS:
                return State(stage.name, Gate.CHANGES_REQUIRED, state.lifecycle)
            if outcome == Outcome.DECISION:
                return State(stage.name, Gate.DECISION_REQUIRED, state.lifecycle)
            raise ValueError(f"invalid verification outcome: {outcome}")
        if event == Event.APPROVED:
            if state.gate != Gate.APPROVAL_REQUIRED:
                raise ValueError(f"approval requires Approval Required before the completion boundary: {state.stage}")
            if self.completion_policy is not None and self.completion_policy.is_boundary(state):
                raise ValueError(f"approval cannot cross the completion boundary: {state.stage}")
            target = self._next_name(stage.name)
            if target == self.terminal_stage:
                raise ValueError(f"approval requires Approval Required before the completion boundary: {state.stage}")
            return State(target, Gate.PENDING, self._lifecycle_for(target))
        if event == Event.SKIPPED:
            if state.gate not in _WORK_GATES or not stage.skippable:
                raise ValueError(f"skip is not allowed from {state.stage} / {state.gate.value}")
            target = self._next_name(stage.name)
            return State(target, Gate.PENDING, self._lifecycle_for(target))
        if event == Event.REAUTHORED:
            if state.gate != Gate.APPROVAL_REQUIRED or not stage.reauthor_in_place:
                raise ValueError(f"reauthor is not allowed from {state.stage} / {state.gate.value}")
            return State(stage.name, Gate.STALE, state.lifecycle)
        if event == Event.DECISION_RESOLVED:
            if state.gate != Gate.DECISION_REQUIRED:
                raise ValueError(f"decision resolution requires Decision Required from {state.stage}")
            return State(stage.name, Gate.CHANGES_REQUIRED, state.lifecycle)
        if event == Event.INVALIDATED:
            if requested_target is None:
                raise ValueError(f"invalidation from {state.stage} requires a target")
            if not self.can_invalidate(state.stage, requested_target):
                raise ValueError(f"cannot invalidate {requested_target}: it is downstream of the active stage {state.stage}")
            target = State(requested_target, Gate.STALE, Lifecycle.PLANNING)
            self.validate_state(target)
            return target
        if event == Event.AUTOAPPROVED:
            if (
                state.gate != Gate.APPROVAL_REQUIRED
                or self.rework_policy is None
                or stage.name not in self.rework_policy.autoapprove_stages
            ):
                raise ValueError(f"auto-approval is not allowed from {state.stage} / {state.gate.value}")
            target = self._next_name(stage.name)
            return State(target, Gate.PENDING, self._lifecycle_for(target))
        if event == Event.COMPLETED:
            completion = self.completion_policy
            if completion is None or not completion.is_boundary(state):
                boundary = self.completion_boundary
                raise ValueError(f"completion requires {boundary[0]} at {boundary[1].value}: {state.stage}")
            return State(self.terminal_stage, Gate.APPROVED, Lifecycle.COMPLETED)
        raise ValueError(f"unsupported workflow event: {event.value}")

    def _next_name(self, stage: str) -> str:
        position = self.active_stage_names.index(stage)
        try:
            return self.active_stage_names[position + 1]
        except IndexError:
            return self.terminal_stage

    def _lifecycle_for(self, stage: str) -> Lifecycle:
        # Existing persisted approvals land in Planning; lifecycle ownership is
        # still a separate concern until command consumers migrate to policy.
        return Lifecycle.PLANNING

    def next_stage(self, stage: str) -> str:
        return self._next_name(stage)

    def state_after_skip(self, stage: str) -> tuple[str, str]:
        state = State(stage, Gate.PENDING, self._lifecycle_for(stage))
        result = self.next_state(state, Event.SKIPPED)
        return result.stage, result.gate.value

    def can_autoapprove(self, stage: str, iterations: int) -> bool:
        """Whether bounded Verification rework permits autonomous approval."""
        return (
            iterations >= 1
            and self.rework_policy is not None
            and iterations <= self.rework_policy.max_iterations
            and stage in self.rework_policy.autoapprove_stages
        )

    def can_reenter(self, active_stage: str, target_stage: str) -> bool:
        """Whether a rework or invalidation may return to the requested stage."""
        if self.invalidation_policy is None:
            return False
        return self.invalidation_policy.can_reenter(active_stage, target_stage)

    def can_invalidate(self, active_stage: str, target_stage: str) -> bool:
        """Whether an active stage may be invalidated to an already-reached stage."""
        try:
            active_position = self.active_stage_names.index(active_stage)
            target_position = self.active_stage_names.index(target_stage)
        except ValueError:
            return False
        return target_position <= active_position

    def evidence_dependencies_for(self, stage: str) -> tuple[str, ...]:
        """Return downstream stages whose evidence becomes stale after a change."""
        if self.invalidation_policy is None:
            return ()
        return self.invalidation_policy.dependencies_for(stage)

    def transition(
        self,
        state: State,
        event: Event,
        outcome: Outcome | None = None,
        requested_target: str | None = None,
    ) -> State:
        """Readable alias for the canonical typed transition API."""
        return self.next_state(state, event, outcome, requested_target)


def _feature_stages() -> tuple[Stage, ...]:
    return (
        Stage(
            name="Product",
            marker="PRODUCT",
            action=Action.HUMAN_INPUT,
            autonomous=False,
            result_gate=Gate.APPROVAL_REQUIRED,
            reason="product artifact is due; the driver must invoke pdlc-write interactively",
            skippable=False,
            reauthor_in_place=True,
        ),
        Stage(
            name="UI",
            marker="UI",
            action=Action.TASKS,
            autonomous=True,
            result_gate=Gate.APPROVAL_REQUIRED,
            reason="UI or task artifact is due",
            review=ReviewPolicy(
                ReviewerTarget("The parent's UI section and its UJ-* journeys", "pdlc-tasks-reviewer"),
                independent=False,
            ),
            reauthor_in_place=True,
        ),
        Stage(
            name="Tasks",
            marker="TASKS",
            action=Action.TASKS,
            autonomous=True,
            result_gate=Gate.APPROVAL_REQUIRED,
            reason="UI or task artifact is due",
            review=ReviewPolicy(
                ReviewerTarget("The delivery tasks", "pdlc-tasks-reviewer"),
                independent=False,
            ),
            reauthor_in_place=True,
        ),
        Stage(
            name="Technical Plan",
            marker="PLAN",
            action=Action.PLAN,
            autonomous=True,
            result_gate=Gate.APPROVAL_REQUIRED,
            reason="technical plan is due",
            review=ReviewPolicy(
                ReviewerTarget("The Technical Plan on each incomplete task", "pdlc-plan-reviewer"),
                independent=False,
            ),
            reauthor_in_place=True,
        ),
        Stage(
            name="Implementation",
            marker="IMPLEMENTATION",
            action=Action.IMPLEMENT,
            autonomous=True,
            result_gate=Gate.REVIEW_REQUIRED,
            reason="next eligible delivery task is due",
            review=ReviewPolicy(
                ReviewerTarget("Production PRs and each task's implementation", "pdlc-implementation-reviewer"),
            ),
            ci_gated=True,
        ),
        Stage(
            name="Testing",
            marker="TESTING",
            action=Action.TEST,
            autonomous=True,
            result_gate=Gate.REVIEW_REQUIRED,
            reason="acceptance coverage is due",
            review=ReviewPolicy(
                ReviewerTarget("Test PRs, coverage, and requirement traceability", "pdlc-testing-reviewer"),
            ),
        ),
        Stage(
            name="Verification",
            marker="REVIEW",
            action=Action.VERIFY,
            autonomous=True,
            result_gate=None,
            reason="verification is due",
            accepts_verification=True,
        ),
        Stage(
            name="Complete",
            marker=None,
            action=None,
            autonomous=False,
            result_gate=None,
            skippable=False,
            terminal=True,
        ),
    )


_FEATURE_STAGES = _feature_stages()
_FEATURE_ACTIVE_STAGES = tuple(stage.name for stage in _FEATURE_STAGES if not stage.terminal)

_FEATURE_COMPLETION_POLICY = CompletionPolicy(
    boundary_stage="Verification",
    boundary_gate=Gate.APPROVAL_REQUIRED,
    required_stage_evidence=(
        "Product",
        "UI",
        "Tasks",
        "Technical Plan",
        "Implementation",
        "Testing",
    ),
    require_stage_settlement=True,
    require_tasks_closed=True,
    require_task_implementation=True,
    require_prs_merged=True,
    require_checks_green=True,
    verification_parser="parse_verification_report",
)

_FEATURE_INVALIDATION_POLICY = InvalidationPolicy(
    evidence_dependencies={
        "Product": ("UI", "Tasks", "Technical Plan", "Implementation", "Testing", "Verification"),
        "UI": ("Tasks", "Technical Plan", "Implementation", "Testing", "Verification"),
        "Tasks": ("Technical Plan", "Implementation", "Testing", "Verification"),
        "Technical Plan": ("Implementation", "Testing", "Verification"),
        "Implementation": ("Testing", "Verification"),
        "Testing": ("Verification",),
        "Verification": (),
    },
    reentry_targets={
        "Product": ("Product",),
        "UI": ("Product", "UI"),
        "Tasks": ("Product", "UI", "Tasks"),
        "Technical Plan": ("Product", "UI", "Tasks", "Technical Plan"),
        "Implementation": ("Product", "UI", "Tasks", "Technical Plan", "Implementation"),
        "Testing": ("Product", "UI", "Tasks", "Technical Plan", "Implementation", "Testing"),
        "Verification": ("Implementation", "Testing"),
    },
)

FEATURE_PIPELINE = Pipeline(
    work_type=WorkType.FEATURE,
    stages=_FEATURE_STAGES,
    overrides=(
        TransitionOverride("Verification", Gate.PENDING, Event.SKIPPED, "Verification", Gate.APPROVAL_REQUIRED),
        TransitionOverride("Verification", Gate.CHANGES_REQUIRED, Event.SKIPPED, "Verification", Gate.APPROVAL_REQUIRED),
        TransitionOverride("Verification", Gate.STALE, Event.SKIPPED, "Verification", Gate.APPROVAL_REQUIRED),
        TransitionOverride("Verification", Gate.CHANGES_REQUIRED, Event.BOUNCED, REQUESTED_TARGET, Gate.STALE, Lifecycle.PLANNING, loop="delivery-rework"),
        TransitionOverride("Verification", Gate.APPROVAL_REQUIRED, Event.BOUNCED, REQUESTED_TARGET, Gate.STALE, Lifecycle.PLANNING, loop="delivery-rework"),
    ),
    completion_policy=_FEATURE_COMPLETION_POLICY,
    invalidation_policy=_FEATURE_INVALIDATION_POLICY,
    rework_policy=ReworkPolicy("delivery-rework", 3, ("Implementation", "Testing"), "Verification"),
)

# The Bug vocabulary and evidence contract are intentionally not guessed from
# Feature. Keeping a registered unavailable entry makes resolution explicit
# while the real Bug pipeline is designed.
BUG_PIPELINE = Pipeline(work_type=WorkType.BUG, stages=(), available=False)


class PipelineRegistry:
    """Registry for resolving a policy by work type."""

    def __init__(self, pipelines: Mapping[WorkType, Pipeline]) -> None:
        self._pipelines = dict(pipelines)

    def for_work_type(self, work_type: WorkType | str) -> Pipeline:
        try:
            normalized = WorkType(work_type)
        except ValueError:
            raise ValueError(f"unknown work type: {work_type}") from None
        try:
            pipeline = self._pipelines[normalized]
        except KeyError:
            raise ValueError(f"no workflow configured for work type: {normalized.value}") from None
        if not pipeline.available:
            raise ValueError(f"workflow unavailable for work type: {normalized.value}")
        return pipeline

    def for_record(self, record: Mapping[str, Any]) -> Pipeline:
        raw = record.get("workType") or record.get("Work Type") or record.get("work_type")
        return self.for_work_type(raw or WorkType.FEATURE)


PIPELINE_REGISTRY = PipelineRegistry({WorkType.FEATURE: FEATURE_PIPELINE, WorkType.BUG: BUG_PIPELINE})
PIPELINES = PIPELINE_REGISTRY

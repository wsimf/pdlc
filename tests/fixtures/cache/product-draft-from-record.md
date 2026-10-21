## Product

### 4. Functional requirements
- FR-1: The record lands.
- FR-2: The record publishes.

### 5. Constraints
- C-1: Commands own every mutation.

### Technical approach

#### Feasibility

Verdict: Feasible

- The record store already supports this.

#### Approach

- Commands own every mutation through the work-item facade.

#### Risks & unknowns

- None.

#### Verification

- Command tests over the file backend.

## Decisions

- none

## Open Questions

- none
